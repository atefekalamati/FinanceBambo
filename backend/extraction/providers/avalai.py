# -*- coding: utf-8 -*-
"""AvalAI as a structured-extraction provider: recognised text in, candidate fields out.

WHERE THIS SITS

    image / audio -> PaddleOCR / Whisper -> raw text -> [ this ] -> candidate fields
                                                    \\-> invoice_parser -> candidate fields

It is a SECOND reader of the same text, never a replacement for the first. `invoice_parser`
is deterministic and explains every number it returns; this asks a model. Where they agree
the answer is stronger; where the parser found something, the parser wins, because a rule
that can be read beats a model that cannot. The composition lives in `adapters.py` -- this
module only talks to AvalAI and hands back what it said.

WHAT IT REFUSES TO DO

  * It never invents. The prompt says so, and the response is filtered: a value the model
    returns for a field it also marks absent is dropped rather than shown to a reviewer.
  * It never fabricates confidence. A field returned without one is dropped, because a
    number nobody stated is exactly what confidence exists to prevent.
  * It never repairs the text. Persian digits, spacing and the original spelling travel to
    the model unchanged and come back as the model returned them.

SECRETS

The key comes from `AVALAI_API_KEY` and appears in exactly one place: the Authorization
header. It is never logged, never returned in an error, and never written into a draft.
`describe()` exists so an operator can ask whether the provider is configured without the
answer containing the key.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

LOG = logging.getLogger(__name__)

PROVIDER = "avalai"

#: AvalAI speaks the OpenAI chat-completions dialect. Overridable because a gateway
#: address is deployment configuration, not a fact about the code.
DEFAULT_BASE_URL = "https://api.avalai.ir/v1"
DEFAULT_MODEL = "gpt-4o-mini"

#: One request. Long enough for a page of invoice text, short enough that a hung gateway
#: does not hold an extraction open for minutes -- the caller is a background task and the
#: attachment is sitting in `processing` until this returns.
TIMEOUT_SECONDS = 45

#: Two retries, on transport failures and 5xx only. A 400 is the request being wrong and
#: repeating it changes nothing; a 401 is the key being wrong and repeating it is how an
#: account gets rate-limited.
MAX_ATTEMPTS = 3
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
BACKOFF_SECONDS = (1, 3)

#: Refuse a response larger than this before parsing it. A gateway that answers with a
#: login page instead of JSON should cost one read, not a megabyte of it.
MAX_RESPONSE_BYTES = 512 * 1024

#: The fields the model is asked for, in the vocabulary the rest of the pipeline already
#: uses. Named here rather than in the prompt string so the prompt and the parser cannot
#: drift into two different field lists.
FIELD_DEFINITIONS = (
    ("invoiceNumber", "شماره فاکتور — the invoice's own number, as printed"),
    ("invoiceDate", "تاریخ فاکتور — the invoice date, exactly as printed, digits unchanged"),
    ("supplierName", "فروشنده — who issued the invoice"),
    ("buyerName", "خریدار — who it was issued to"),
    ("currency", "the currency word if one appears: IRR, TOMAN, ریال, تومان"),
    ("totalAmount", "مبلغ کل — the final payable total, digits only, no separators"),
    ("taxAmount", "مالیات — the tax amount if stated separately"),
)

SYSTEM_PROMPT = """You read Iranian invoices. You are given text that was recognised from
an image or transcribed from speech, and you return what that text STATES.

Rules, in order of importance:

1. Never invent. If the text does not state a field, return null for its value. A missing
   field is a useful answer; a guessed one is a wrong invoice.
2. Never compute. Do not derive a total from line items, a unit price from a total, or a
   tax from a percentage. Return only numbers that appear in the text.
3. Never normalise digits. Persian digits stay Persian. Return the characters as printed.
4. Never reformat dates. If the text says ۱۴۰۵/۰۶/۲۲, return ۱۴۰۵/۰۶/۲۲.
5. Strip thousands separators from amounts and nothing else: 1,350,000 becomes 1350000.
6. Confidence is about the TEXT, not about your fluency. If the recognised text is
   garbled where a field should be, say so with a low confidence rather than a clean guess.

Return ONLY a JSON object, no prose and no code fence, shaped exactly:

{"fieldName": {"value": <string or null>, "confidence": <number 0..1>}, ...}

Include every field you were asked about. A field you cannot find gets
{"value": null, "confidence": 0}."""


class ProviderUnavailable(RuntimeError):
    """AvalAI could not be reached or refused the request. Nothing was extracted."""


class ProviderResponseInvalid(RuntimeError):
    """AvalAI answered with something that is not the agreed JSON shape."""


def api_key():
    """The configured key, or None. None means this provider is switched off."""
    value = (os.environ.get("AVALAI_API_KEY") or "").strip()
    return value or None


def describe():
    """Whether the provider is usable, in a form safe to print or return.

    Says that a key is configured and how long it is. Never the key: an operator debugging
    a deployment needs to know the variable reached the process, not what is in it.
    """
    key = api_key()
    return {"provider": PROVIDER,
            "configured": key is not None,
            "keyLength": len(key) if key else 0,
            "baseUrl": os.environ.get("AVALAI_BASE_URL", DEFAULT_BASE_URL),
            "model": os.environ.get("AVALAI_MODEL", DEFAULT_MODEL)}


def _user_prompt(text, transcript=None, metadata=None):
    """Everything the model is allowed to read, laid out so the sources stay separable."""
    parts = []
    if metadata:
        parts.append("INVOICE METADATA (context only, never an answer):\n%s"
                     % json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    if text:
        parts.append("TEXT RECOGNISED FROM THE IMAGE:\n%s" % text)
    if transcript:
        # Kept separate from the OCR text on purpose. Speech and a scan disagree in
        # different ways, and a model told which is which can weigh them; a model handed
        # one concatenated blob cannot.
        parts.append("TEXT TRANSCRIBED FROM SPEECH:\n%s" % transcript)
    parts.append("FIELDS TO RETURN:\n%s"
                 % "\n".join("- %s: %s" % (key, description)
                             for key, description in FIELD_DEFINITIONS))
    return "\n\n".join(parts)


def _post(url, payload, key, timeout):
    """One HTTP call. Returns `(status, body)`; raises only on transport failure."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 # The one place the key appears.
                 "Authorization": "Bearer %s" % key,
                 "Accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        # An HTTP error still has a body, and the body is usually where the gateway says
        # what was wrong. Read it, cap it, and let the caller decide whether to retry.
        return error.code, error.read(MAX_RESPONSE_BYTES + 1)


def _content(body):
    """The assistant's message text out of a chat-completions envelope."""
    try:
        envelope = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ProviderResponseInvalid("AvalAI did not return JSON") from error
    try:
        return envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderResponseInvalid(
            "AvalAI returned no assistant message") from error


def parse_fields(content):
    """The model's text as `{key: (value, confidence)}`, keeping only what it stated.

    Tolerant of a code fence, because models add them, and of extra keys, because a model
    naming a field nobody asked for is not a reason to lose the six that are right. NOT
    tolerant of a missing confidence or a non-numeric one: a field arriving without one
    would otherwise be shown to a reviewer as if somebody had vouched for it.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -3]
    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise ProviderResponseInvalid(
            "AvalAI's answer is not the agreed JSON object") from error
    if not isinstance(parsed, dict):
        raise ProviderResponseInvalid("AvalAI's answer is not a JSON object")

    fields = {}
    for key, entry in parsed.items():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            # The model saying "not in the text" is an answer, and the answer is nothing.
            continue
        confidence = entry.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            LOG.warning("avalai: field %r arrived without a usable confidence; dropped", key)
            continue
        fields[str(key)] = (value if not isinstance(value, str) else value.strip(),
                            max(0.0, min(1.0, float(confidence))))
    return fields


class AvalAIProvider:
    """Structured invoice extraction over AvalAI's chat-completions endpoint."""

    provider = PROVIDER

    def __init__(self, key=None, base_url=None, model=None, timeout=TIMEOUT_SECONDS,
                 post=_post, sleep=time.sleep):
        self._key = key or api_key()
        self._base_url = (base_url or os.environ.get("AVALAI_BASE_URL")
                          or DEFAULT_BASE_URL).rstrip("/")
        self._model = model or os.environ.get("AVALAI_MODEL") or DEFAULT_MODEL
        self._timeout = timeout
        self._post = post
        self._sleep = sleep

    @property
    def configured(self):
        return self._key is not None

    def extract(self, text, transcript=None, metadata=None):
        """`{key: (value, confidence)}` for one invoice's text.

        Raises `ProviderUnavailable` when AvalAI could not be reached or would not answer,
        and `ProviderResponseInvalid` when it answered with something else. Both are
        conditions the caller can report; neither is a reason to lose the OCR text, which
        is why the composition in `adapters.py` catches them and carries on.
        """
        if not self.configured:
            raise ProviderUnavailable(
                "AVALAI_API_KEY is not set; the AvalAI extractor is switched off")
        if not (text or transcript):
            # Nothing to read. Asking anyway would spend a request to be told nothing.
            return {}

        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user",
                          "content": _user_prompt(text, transcript, metadata)}],
            # Deterministic as the gateway allows: the same invoice should not read
            # differently on a retry.
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        url = "%s/chat/completions" % self._base_url

        last = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                status, body = self._post(url, payload, self._key, self._timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last = "transport failure: %s" % type(error).__name__
                status = None
            else:
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ProviderResponseInvalid("AvalAI's answer is implausibly large")
                if status == 200:
                    return parse_fields(_content(body))
                # The body may name the problem; it may also echo the request. Log a short
                # prefix only, and never the payload -- the payload is the invoice.
                last = "HTTP %s" % status
                LOG.warning("avalai: %s on attempt %d", last, attempt + 1)
                if status not in RETRY_STATUS:
                    break
            if attempt < len(BACKOFF_SECONDS):
                self._sleep(BACKOFF_SECONDS[attempt])
        raise ProviderUnavailable("AvalAI did not answer (%s)" % (last or "unknown"))
