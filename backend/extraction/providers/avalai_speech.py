# -*- coding: utf-8 -*-
"""Speech to text over AvalAI, beside the local Whisper rather than instead of it.

WHY A SECOND PROVIDER AND NOT A REPLACEMENT

`whisper_voice.py` loads a model onto this machine. That works offline and costs nothing
per minute, and it is the right answer on a host that has the model. It is the wrong answer
on a host that does not, and it is not the model the benchmark measured: on the two Persian
invoice recordings, `groq.whisper-large-v3-turbo` through AvalAI transcribed 46 seconds of
audio in 4.3 seconds for 0.0011 USD and recovered 10 of 12 critical numbers -- the best
numeric result of the eight candidates tested.

So both exist and configuration chooses. The business layer asks for a transcript and never
learns which one answered.

THE CONTRACT

`transcribe(path)` returns `{"text", "language", "provider", "confidence"}`, exactly as the
local provider does, because `VoiceExtractionAdapter` reads that shape and a second shape
would mean a second adapter.

`confidence` is None here rather than a number. The API returns no per-segment logprobs, and
inventing a figure -- 1.0, or 0.5, or anything -- would put a value in a field a reviewer
reads as measured. A missing confidence is a fact; a fabricated one is a claim.

WHAT IT NEVER DOES

Correct anything. If the speaker said the wrong amount, the wrong amount is what comes
back: this is a transcription layer, and a transcript that silently agreed with an invoice
would destroy the one piece of evidence that the two disagree.
"""

import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

#: The provider name recorded on the transcript, matching the vocabulary the local
#: provider already uses.
PROVIDER = "avalai"

#: The model used when configuration names none. CURRENT TEST DEFAULT, not a decision: it
#: is the best-measured candidate from the 2026-09-23 benchmark and is expected to change
#: when more audio is benchmarked. It lives here, next to the transport, rather than in
#: anything that reasons about invoices.
DEFAULT_MODEL = "groq.whisper-large-v3-turbo"

DEFAULT_BASE_URL = "https://api.avalai.ir/v1"

#: Credentials, in the order the rest of the project already looks for them. AVALAI_API_KEY
#: first because that is the name the AvalAI notes use; the Finance-wide name is accepted
#: so a host configuring every provider through one variable keeps working.
KEY_NAMES = ("AVALAI_API_KEY", "FINANCE_AI_API_KEY")
MODEL_NAMES = ("FINANCE_STT_MODEL", "AVALAI_STT_MODEL")
BASE_URL_NAMES = ("AVALAI_BASE_URL",)


class ProviderUnavailable(RuntimeError):
    """The transcription could not be attempted or the endpoint refused it.

    NOT raised for silence: audio with no speech returns empty text, the same as locally.
    """


def _first_set(names):
    """The first of these environment variables carrying a value, or None.

    Returns the VALUE and never the name, and logs nothing: these are credentials.
    """
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


class AvalAISpeechProvider:
    """`transcribe(path)` against an OpenAI-compatible `/audio/transcriptions`."""

    def __init__(self, api_key=None, model=None, base_url=None, language="fa",
                 timeout=600, transport=None):
        self._key = api_key or _first_set(KEY_NAMES)
        self._model = model or _first_set(MODEL_NAMES) or DEFAULT_MODEL
        self._base_url = (base_url or _first_set(BASE_URL_NAMES)
                          or DEFAULT_BASE_URL).rstrip("/")
        self._language = language
        self._timeout = timeout
        # Injectable so a test exercises the parsing and the error paths without a network
        # call and without a key. Nothing in the test suite may need a credential to run.
        self._transport = transport

    @property
    def configured(self):
        """Whether a key is present. Says nothing about the key's VALUE."""
        return bool(self._key)

    @property
    def model(self):
        return self._model

    def _endpoint(self):
        return self._base_url + "/audio/transcriptions"

    def _multipart(self, audio_path):
        """One multipart body. Built by hand because `urllib` has no multipart writer.

        The file's bytes go in untouched -- no resampling, no re-encoding -- so that what
        the model hears is what the microphone recorded.
        """
        boundary = "----bambo" + uuid.uuid4().hex
        mime = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
        parts = [
            ("--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n%s\r\n"
             % (boundary, self._model)).encode("utf-8"),
        ]
        if self._language:
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n%s\r\n"
                 % (boundary, self._language)).encode("utf-8"))
        parts.append(
            ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
             "Content-Type: %s\r\n\r\n" % (boundary, audio_path.name, mime)).encode("utf-8"))
        parts.append(audio_path.read_bytes())
        parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
        return boundary, b"".join(parts)

    def _post(self, boundary, body):
        request = urllib.request.Request(
            self._endpoint(), data=body,
            headers={"Authorization": "Bearer %s" % self._key,
                     "Content-Type": "multipart/form-data; boundary=" + boundary})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as answer:
                return answer.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            # The status and the server's own words, never the request headers: the
            # Authorization header is in this request and must not reach a log.
            raise ProviderUnavailable(
                "AvalAI refused the transcription: HTTP %s %s" % (error.code, detail)) from error
        except Exception as error:                        # noqa: BLE001
            raise ProviderUnavailable(
                "AvalAI transcription failed: %s" % error) from error

    def transcribe(self, audio_path):
        """`{"text", "language", "provider", "confidence"}` for one audio file.

        Same shape the local provider returns, so the adapter above cannot tell them apart.
        """
        source = Path(audio_path)
        if not source.is_file():
            raise ProviderUnavailable("audio file is missing: %s" % source.name)
        if not self._key:
            raise ProviderUnavailable(
                "AvalAI speech is not configured: set AVALAI_API_KEY or FINANCE_AI_API_KEY")

        started = time.monotonic()
        boundary, body = self._multipart(source)
        raw = self._transport(boundary, body) if self._transport else self._post(boundary, body)

        try:
            parsed = json.loads(raw)
        except ValueError as error:
            raise ProviderUnavailable(
                "AvalAI returned a body that is not JSON: %s" % error) from error

        text = str((parsed or {}).get("text") or "").strip()
        return {
            "text": text,
            "language": (parsed or {}).get("language") or self._language,
            "provider": PROVIDER,
            # None, not a number. The endpoint reports no per-segment probability, and a
            # figure invented here would be read as measured by whoever reviews the draft.
            "confidence": None,
            "model": self._model,
            "duration_seconds": round(time.monotonic() - started, 2),
        }
