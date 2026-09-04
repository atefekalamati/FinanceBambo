# -*- coding: utf-8 -*-
"""What every extraction provider has to satisfy, and what it may return.

The shape below is dictated by `app/finance/schemas/extractions.py`:
`ProviderExtractionResult` accepts a list of fields, each with a key, an extracted value and
a confidence between 0 and 1, and it rejects duplicate keys. `ExtractionResult.as_contract()`
produces exactly that, so a provider that builds one of these cannot produce something the
service will reject at validation time.

CONFIDENCE IS NOT A GATE
Nothing here refuses to report a low-confidence reading. A provider that quietly dropped its
least certain field would leave the reviewer looking at a form with a value missing and no
statement that anything was missing -- worse than a value marked uncertain. The confidence
travels with the field and the reviewer decides.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Protocol, runtime_checkable


class ProviderUnavailable(RuntimeError):
    """The provider could not run at all -- model absent, binary missing, out of memory.

    Distinct from "it ran and read nothing". The service maps this to a 503 and leaves the
    attachment retryable; an empty reading is a completed extraction with nothing in it,
    which is a different thing for the reviewer to look at.
    """


@dataclass(frozen=True)
class ExtractedField:
    """One value a provider believes it read, and how sure it is."""
    key: str
    value: Any
    confidence: Decimal

    def __post_init__(self):
        if not str(self.key).strip():
            raise ValueError("extraction field key must not be blank")
        if not Decimal(0) <= Decimal(self.confidence) <= Decimal(1):
            raise ValueError("confidence must be between 0 and 1: %r" % (self.confidence,))


@dataclass(frozen=True)
class ExtractionResult:
    """Everything one run of a provider produced.

    `raw_text` is kept beside the parsed fields rather than instead of them. A reviewer
    looking at a wrong quantity needs to see the line it came from; a structured result
    alone leaves them guessing whether the model misread the document or the parser misread
    the model.
    """
    raw_text: str
    fields: tuple[ExtractedField, ...] = ()
    confidence: Decimal = Decimal(0)
    provider_name: str = ""
    language: str | None = None
    processing_seconds: Decimal = Decimal(0)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_contract(self) -> dict:
        """The `ProviderExtractionResult` shape the finance service validates against.

        `rawText`, `confidence` and the rest ride as ordinary fields because that contract
        has one list and no envelope. They are prefixed so a parsed invoice field can never
        collide with them -- a document containing the word "confidence" would otherwise
        overwrite the provider's own.
        """
        entries = [{"key": item.key, "extractedValue": item.value,
                    "confidence": float(item.confidence)} for item in self.fields]
        entries.append({"key": "_rawText", "extractedValue": self.raw_text,
                        "confidence": float(self.confidence)})
        entries.append({"key": "_provider", "extractedValue": self.provider_name,
                        "confidence": 1.0})
        entries.append({"key": "_processingSeconds",
                        "extractedValue": format(self.processing_seconds, "f"),
                        "confidence": 1.0})
        if self.language is not None:
            entries.append({"key": "_language", "extractedValue": self.language,
                            "confidence": float(self.confidence)})
        if self.warnings:
            entries.append({"key": "_warnings", "extractedValue": list(self.warnings),
                            "confidence": 1.0})
        return {"fields": entries}


@runtime_checkable
class OCRProvider(Protocol):
    """Reads text out of an image. Satisfies `InvoiceImageExtractor`."""
    adapter_name: str

    async def extract(self, file: object, hints: Mapping[str, Any]) -> dict: ...

    async def extract_text(self, file_path: str) -> ExtractionResult: ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Reads text out of audio. Satisfies `InvoiceVoiceExtractor`."""
    adapter_name: str

    async def extract(self, file: object, hints: Mapping[str, Any]) -> dict: ...

    async def transcribe(self, file_path: str) -> ExtractionResult: ...
