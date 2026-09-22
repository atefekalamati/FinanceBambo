# -*- coding: utf-8 -*-
"""Configurable LLM invoice extraction provider.

This module is deliberately outside the Finance domain service. Finance owns the review
draft and confirmation rules; this provider only reads already-recognised text and returns
candidate fields. A low-confidence or malformed answer never creates financial effect.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

LOG = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

#: The model used when a PAGE is sent rather than a transcription.
#:
#: Separate from DEFAULT_MODEL because the right answer differs by task. Measured
#: on the audited invoices: gpt-4o scored highest overall accuracy, was the only
#: model to read currency correctly every time, and cost 1,512 prompt tokens a page
#: against gpt-4o-mini's 37,045 -- 24x more for the same image, because "mini"
#: describes the text model and not the vision tiling. Overridable for the same
#: reason every other setting is: the benchmark was three pages of one supplier.
DEFAULT_VISION_MODEL = "gpt-4o"
MAX_RESPONSE_BYTES = 512 * 1024
TIMEOUT_SECONDS = 45
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
BACKOFF_SECONDS = (1, 3)

SYSTEM_PROMPT = """You are extracting structured data from a construction invoice.

Rules:
- Never invent values.
- If uncertain return null.
- Preserve Persian numbers.
- Detect construction materials.
- Return JSON only.
- Extract line items if possible.
- If table structure is missing, infer from text cautiously.
- Confidence must be included."""


class ExtractionProviderUnavailable(RuntimeError):
    """The configured provider is unavailable or disabled."""


class ExtractionProviderResponseInvalid(RuntimeError):
    """The provider returned a response that cannot become a safe draft candidate."""


@dataclass(frozen=True)
class InvoiceCandidate:
    invoice: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    provider: str = "llm"


@runtime_checkable
class ExtractionProvider(Protocol):
    provider: str

    def extract_invoice(self, text: str, hints: Mapping[str, Any] | None = None) -> InvoiceCandidate: ...


def _enabled() -> bool:
    value = (os.environ.get("FINANCE_AI_EXTRACTION_ENABLED") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


#: The gateways this provider can speak to, and where each keeps its settings.
#:
#: Both are OpenAI's chat-completions API -- AvalAI is a gateway in front of the same
#: models, which is why one client serves both and why adding it is a table entry rather
#: than a second implementation. What differs is only the base url and which environment
#: variables an operator is expected to have set.
#:
#: `avalai` was previously refused. `build_extraction_provider` accepted the literal
#: string "openai" and nothing else, so an operator following the AvalAI setup notes got
#: `finance AI extraction disabled: unsupported provider 'avalai'` in a log nobody reads
#: and a pipeline that silently did without its second reader.
PROVIDER_SETTINGS = {
    "openai": {"key": ("FINANCE_AI_API_KEY",),
               "model": ("FINANCE_AI_MODEL",),
               "base_url": ("FINANCE_AI_BASE_URL",),
               "default_base_url": None},
    "avalai": {# AVALAI_API_KEY first: it is the name the AvalAI notes use. FINANCE_AI_API_KEY
               # is accepted too so a host that configures every provider through the one
               # Finance variable keeps working.
               "key": ("AVALAI_API_KEY", "FINANCE_AI_API_KEY"),
               "model": ("AVALAI_MODEL", "FINANCE_AI_MODEL"),
               "base_url": ("AVALAI_BASE_URL",),
               "default_base_url": "https://api.avalai.ir/v1"},
}


def _first_set(names):
    """The first of these environment variables that carries a value, or None.

    Returns the VALUE, never the name, and nothing here is logged: these are credentials.
    """
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def _settings():
    """`(provider, settings)` for the configured gateway, or `(provider, None)`."""
    provider = (os.environ.get("FINANCE_AI_PROVIDER") or "").strip().lower()
    return provider, PROVIDER_SETTINGS.get(provider)


def provider_configured() -> bool:
    _provider, settings = _settings()
    if not _enabled() or settings is None:
        return False
    return _first_set(settings["key"]) is not None


def build_extraction_provider() -> ExtractionProvider | None:
    if not _enabled():
        return None
    provider, settings = _settings()
    if settings is None:
        LOG.warning("finance AI extraction disabled: unsupported provider %r (known: %s)",
                    provider, ", ".join(sorted(PROVIDER_SETTINGS)))
        return None
    key = _first_set(settings["key"])
    if not key:
        # The NAMES of the variables, never a value. An operator needs to know which one
        # to set; nothing about the key itself belongs in a log.
        LOG.warning("finance AI extraction disabled: none of %s is set for provider %r",
                    ", ".join(settings["key"]), provider)
        return None
    return LLMInvoiceExtractionProvider(
        key=key,
        model=_first_set(settings["model"]),
        base_url=_first_set(settings["base_url"]) or settings["default_base_url"],
        # The gateway that actually answered, so `extractionSource` on the draft names it.
        # The class default is "openai" because the WIRE FORMAT is OpenAI's, but a format
        # is not a counterparty: a draft saying `openai` when AvalAI read the page
        # misdirects anyone auditing where a number came from.
        provider=provider)


def _post(url: str, payload: dict[str, Any], key: str, timeout: int):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer %s" % key,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        return error.code, error.read(MAX_RESPONSE_BYTES + 1)


def _assistant_content(body: bytes) -> str:
    try:
        envelope = json.loads(body.decode("utf-8"))
        return envelope["choices"][0]["message"]["content"]
    except (UnicodeDecodeError, ValueError, KeyError, IndexError, TypeError) as error:
        raise ExtractionProviderResponseInvalid("AI provider returned no assistant JSON") from error


def _json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise ExtractionProviderResponseInvalid("AI provider response is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise ExtractionProviderResponseInvalid("AI provider response is not a JSON object")
    return parsed


def _clamp_confidence(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def parse_candidate(payload: Mapping[str, Any], provider: str = "llm") -> InvoiceCandidate:
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    clean_items = [item for item in items if isinstance(item, dict)]
    warnings = payload.get("warnings")
    clean_warnings = [str(item) for item in warnings] if isinstance(warnings, list) else []
    return InvoiceCandidate(
        invoice=dict(invoice),
        items=clean_items,
        confidence=_clamp_confidence(payload.get("confidence")),
        warnings=clean_warnings,
        provider=provider,
    )


class LLMInvoiceExtractionProvider:
    """OpenAI-compatible chat-completions provider for invoice structure extraction."""

    #: The default names the WIRE FORMAT, which is OpenAI's chat-completions API. It is
    #: overridden per instance by `build_extraction_provider` with the gateway that was
    #: actually configured, because that is what a draft's `extractionSource` has to say.
    provider = "openai"

    def __init__(
        self,
        key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = TIMEOUT_SECONDS,
        post=_post,
        sleep=time.sleep,
        provider: str | None = None,
        vision_model: str | None = None,
    ):
        if provider:
            self.provider = provider
        self._key = key or (os.environ.get("FINANCE_AI_API_KEY") or "").strip()
        self._model = model or os.environ.get("FINANCE_AI_MODEL") or DEFAULT_MODEL
        self._vision_model = (vision_model
                              or os.environ.get("FINANCE_AI_VISION_MODEL")
                              or DEFAULT_VISION_MODEL)
        self._base_url = (base_url or os.environ.get("FINANCE_AI_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._post = post
        self._sleep = sleep

    def extract_invoice(self, text: str, hints: Mapping[str, Any] | None = None,
                        image: bytes | None = None,
                        media_type: str = "image/jpeg") -> InvoiceCandidate:
        """Candidate fields from the recognised text, and from the PAGE when given one.

        `image` is optional and everything about the text path is unchanged without it:
        same prompt, same model, same schema, same parsing. That matters because the text
        path is the fallback, and a fallback that drifts from the thing it is backing up
        is not one.

        WHY THE IMAGE IS WORTH SENDING

        Reading OCR output is reading a transcription. On the audited invoices PaddleOCR
        scores 0.47 and 0.45 -- `تعداد: ۲۰` arrives as `تعداد١` -- and no reader,
        model or human, reconstructs a price from that. A vision model reads the page.

        It is still not an accounting authority. Measured against ground truth, the best
        model reproduced 3 of 9 prices exactly and the errors were single digits:
        544,322,000 for 544,222,000, which is a hundred million rial and looks right.
        That is what `fusion` and the validation checks exist for, and why nothing here
        writes a number anywhere near money.
        """
        if not self._key:
            raise ExtractionProviderUnavailable("FINANCE_AI_API_KEY is not set")
        if not (text or "").strip() and not image:
            return InvoiceCandidate(provider=self.provider)

        model = self._vision_model if image else self._model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",
                 "content": self._vision_content(text, hints or {}, image, media_type)
                 if image else self._user_prompt(text, hints or {})},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        url = "%s/chat/completions" % self._base_url
        last = None
        for attempt in range(len(BACKOFF_SECONDS) + 1):
            try:
                status, body = self._post(url, payload, self._key, self._timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                status, body = None, b""
                last = "transport failure: %s" % type(error).__name__
            else:
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ExtractionProviderResponseInvalid("AI provider response is too large")
                if status == 200:
                    return parse_candidate(_json_object(_assistant_content(body)), self.provider)
                last = "HTTP %s" % status
                LOG.warning("finance AI extraction provider returned %s on attempt %d", last, attempt + 1)
                if status not in RETRY_STATUS:
                    break
            if attempt < len(BACKOFF_SECONDS):
                self._sleep(BACKOFF_SECONDS[attempt])
        raise ExtractionProviderUnavailable("AI extraction provider did not answer (%s)" % (last or "unknown"))

    @classmethod
    def _vision_content(cls, text, hints, image, media_type):
        """The multimodal message: the instruction, the page, and the OCR beside it.

        The OCR text is included rather than withheld. It is a second witness -- often a
        poor one -- and a model that can see both can say "the page says 544,222,000 and
        the transcription agrees" where otherwise it could only assert. `fusion` compares
        the two answers afterwards regardless; this just means the model is not reading
        blind when the transcription happens to be good.
        """
        parts = [{"type": "text", "text": cls._vision_prompt(text, hints)},
                 {"type": "image_url",
                  "image_url": {"url": "data:%s;base64,%s"
                                       % (media_type, base64.b64encode(image).decode())}}]
        return parts

    @staticmethod
    def _vision_prompt(text: str, hints: Mapping[str, Any]) -> str:
        """What the model is asked of the page. Every rule here was earned by a failure.

        The measured failures, on real BAMBO invoices:

          * every model invented an invoice number on every page, 9 times out of 9, where
            the documents carry only a PROJECT number. Hence the explicit instruction that
            a project number is not an invoice number;
          * every model produced line items for a summary page that has no item table,
            assembling one from a descriptive paragraph and the floor area;
          * two models read the document's own title, «پیش فاکتور», as the supplier;
          * one produced Jalali year 1442, which is 2063.

        And the rule that looks wrong and is not: item names on these invoices really are
        «آیتم ۱» … «آیتم ۱۵». That is printed in the عنوان column. A model told to avoid
        placeholder-looking names would discard the correct answer, so the instruction is
        to copy what is printed and to withhold only what cannot be read.
        """
        language = (hints or {}).get("locale") or "fa-IR"
        # The SAME shape the text path asks for. `parse_candidate` and `_candidate_fields`
        # already know how to read it, so a vision answer lands in the draft through the
        # identical route -- no second mapping, no second set of key names to keep in step.
        # Asking for camelCase here cost an entire run: `quantity` and `unit` happened to
        # match and survived, while `name`, `unitPrice` and `totalPrice` were silently
        # dropped and the draft showed eight items with no names and no money.
        return (
            "Extract the invoice in this image. Language: %s.\n\n"
            "Return ONLY this JSON object, using null for anything missing:\n"
            '{"invoice":{"supplier":null,"customer":null,"invoice_number":null,'
            '"invoice_date":null,"currency":null,"total_amount":null},'
            '"items":[{"description":null,"quantity":null,"unit":null,'
            '"unit_price":null,"total_price":null}],'
            '"confidence":0,"warnings":[]}\n\n'
            "RULES\n"
            "- Read only what is visibly printed. Never guess, infer or calculate.\n"
            "- Anything you cannot read clearly is null. null is a correct answer.\n"
            "- Copy item descriptions EXACTLY as printed. If the document prints 'آیتم ۱' or\n"
            "  'آیتم ۲' as the description, that IS it -- return it unchanged, not as a placeholder.\n"
            "- Only invent nothing: no invoice number, no date, no supplier, no total\n"
            "  that is not on the page.\n"
            "- A project number (شماره پروژه) is NOT an invoice number. If the page shows\n"
            "  only a project number, invoice_number is null.\n"
            "- The document's own title -- 'پیش فاکتور', 'فاکتور' -- is NOT the supplier.\n"
            "- If the page has no item table, items is an empty list. Do not assemble\n"
            "  items from prose, totals, areas or unit counts.\n"
            "- Do not compute total_amount by adding rows. Return it only if it is printed.\n"
            "- Convert Persian and Arabic digits to ASCII. No thousands separators.\n"
            "- currency must be exactly 'IRR', 'TOMAN', or null.\n"
            "- 'warnings' may list anything you found unclear.\n"
            "- confidence is your honest confidence, 0 to 1.\n\n"
            "This feeds financial software and every value is reviewed by a person. A null "
            "costs them a moment; a confident wrong number costs them the audit.\n\n"
            "For reference, an OCR transcription of the same page is below. It is often "
            "unreliable -- trust the image over this text, and ignore it where they "
            "disagree.\n\n--- OCR ---\n%s\n--- end OCR ---"
            % (language, (text or "")[:4000])
        )

    @staticmethod
    def _user_prompt(text: str, hints: Mapping[str, Any]) -> str:
        schema = {
            "invoice": {
                "supplier": None,
                "customer": None,
                "invoice_number": None,
                "invoice_date": None,
                "currency": None,
                "total_amount": None,
            },
            "items": [
                {
                    "description": None,
                    "quantity": None,
                    "unit": None,
                    "unit_price": None,
                    "total_price": None,
                }
            ],
            "confidence": 0,
            "warnings": [],
        }
        parts = [
            "Return this JSON shape exactly, using null for missing values:",
            json.dumps(schema, ensure_ascii=False),
            "OCR_TEXT:",
            text,
        ]
        if hints:
            parts.extend(["HINTS:", json.dumps(dict(hints), ensure_ascii=False, sort_keys=True)])
        return "\n\n".join(parts)
