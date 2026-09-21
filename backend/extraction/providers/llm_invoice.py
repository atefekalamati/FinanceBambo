# -*- coding: utf-8 -*-
"""Configurable LLM invoice extraction provider.

This module is deliberately outside the Finance domain service. Finance owns the review
draft and confirmation rules; this provider only reads already-recognised text and returns
candidate fields. A low-confidence or malformed answer never creates financial effect.
"""

from __future__ import annotations

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


def provider_configured() -> bool:
    return _enabled() and (os.environ.get("FINANCE_AI_PROVIDER") or "").strip().lower() == "openai" and bool(
        (os.environ.get("FINANCE_AI_API_KEY") or "").strip()
    )


def build_extraction_provider() -> ExtractionProvider | None:
    if not _enabled():
        return None
    provider = (os.environ.get("FINANCE_AI_PROVIDER") or "").strip().lower()
    if provider != "openai":
        LOG.warning("finance AI extraction disabled: unsupported provider %r", provider)
        return None
    key = (os.environ.get("FINANCE_AI_API_KEY") or "").strip()
    if not key:
        LOG.warning("finance AI extraction disabled: FINANCE_AI_API_KEY is not set")
        return None
    return LLMInvoiceExtractionProvider(key=key)


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

    provider = "openai"

    def __init__(
        self,
        key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = TIMEOUT_SECONDS,
        post=_post,
        sleep=time.sleep,
    ):
        self._key = key or (os.environ.get("FINANCE_AI_API_KEY") or "").strip()
        self._model = model or os.environ.get("FINANCE_AI_MODEL") or DEFAULT_MODEL
        self._base_url = (base_url or os.environ.get("FINANCE_AI_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._post = post
        self._sleep = sleep

    def extract_invoice(self, text: str, hints: Mapping[str, Any] | None = None) -> InvoiceCandidate:
        if not self._key:
            raise ExtractionProviderUnavailable("FINANCE_AI_API_KEY is not set")
        if not (text or "").strip():
            return InvoiceCandidate(provider=self.provider)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._user_prompt(text, hints or {})},
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
