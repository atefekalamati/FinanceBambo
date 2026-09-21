# -*- coding: utf-8 -*-
"""The seam between the self-hosted models and Finance's extraction ports.

Finance asks for `InvoiceImageExtractor` / `InvoiceVoiceExtractor`:

    adapter_name: str
    async def extract(self, file, hints) -> object

The providers in `extraction.providers` answer a different question -- `read(path)` and
`transcribe(path)`, both synchronous, both returning `{"text", "confidence", ...}`. This
module is the whole of the difference, and it lives HERE rather than in either side: Finance
must not know a model exists, and a provider must not know what an invoice is.

THREE THINGS IT RECONCILES

**Bytes against a path.** `FileStorage.get` returns the file's BYTES (see
`devhost.ports.LocalFileStorage`), while PaddleOCR and Whisper both want something on disk.
The bytes are written to a temporary file with a real extension -- both libraries decide how
to decode from the suffix, and ffmpeg in particular refuses a file it cannot name.

**Sync against async.** The model calls block for seconds to minutes. Called directly from
the event loop they would stall every other request in the process, so they go through
`asyncio.to_thread`.

**Free text against `ProviderExtractionResult`.** See `_as_contract` -- the one place where
"what the model said" becomes "what Finance stores", and the place where it would be easiest
to invent a number.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

#: What a model's whole answer is called when it reaches the draft. ONE field, deliberately.
#:
#: The provider returns free text. Turning that text into `quantity`, `unitPrice` and
#: `totalAmount` means deciding which number is which, and a wrong decision is
#: indistinguishable from a right one once it is a value in a form -- the reviewer sees a
#: filled field either way. So nothing is parsed here: the text is handed over whole, a
#: person reads it, and the invoice is theirs.
#:
#: Structured fields are now parsed beside it -- deterministically, from the recognised
#: text and nothing else, by `invoice_parser`. They are ADDED to the raw text, never
#: instead of it: a reviewer must always be able to see what the recogniser actually read.
#: A field the text does not support is absent rather than blank, and nothing here creates
#: or confirms an invoice.
from .invoice_parser import parse_invoice
from .providers.llm_invoice import (ExtractionProviderResponseInvalid,
                                    ExtractionProviderUnavailable,
                                    build_extraction_provider)

LOG = logging.getLogger("extraction.adapters")

RAW_TEXT_KEY = "rawText"

#: Structured keys, in the order a reviewer reads them. The value of `items` is a list of
#: plain dicts; `ExtractionFieldDto.extracted_value` is `Any`, so no schema change is
#: needed to carry them.
STRUCTURED_KEYS = ("invoiceNumber", "invoiceDate", "supplierName", "buyerName",
                   "items", "totalAmount", "currency", "validationStatus",
                   "parserWarnings")

#: What the parser's certainty is worth as a confidence number. The recogniser's own
#: confidence is about characters; this is about the reading of them, and the two are
#: multiplied so a crisp scan of an ambiguous layout is not reported as certain.
PARSER_CERTAINTY = {"EXACT": 1.0, "AMBIGUOUS": 0.5, "NOT_FOUND": 0.0}

#: Byte signatures -> extension. The suffix is not cosmetic: PaddleOCR and Whisper both
#: choose a decoder from it, and a temporary file called `.tmp` is simply refused.
IMAGE_SIGNATURES = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"))
AUDIO_SIGNATURES = ((b"ID3", ".mp3"), (b"\xff\xfb", ".mp3"), (b"\xff\xf3", ".mp3"),
                    (b"OggS", ".ogg"))


def _suffix(content, kind):
    """The extension these bytes deserve, defaulting to the family's common one.

    `RIFF` heads both WebP and WAV, so the tag at offset 8 settles it. Defaulting rather
    than refusing: the upload endpoint already validated this file by its bytes, and a
    second, stricter opinion here would reject something Finance has already accepted.
    """
    head = bytes(content[:16])
    for signature, suffix in (IMAGE_SIGNATURES if kind == "image" else AUDIO_SIGNATURES):
        if head.startswith(signature):
            return suffix
    if head.startswith(b"RIFF"):
        tag = head[8:12]
        if tag == b"WEBP":
            return ".webp"
        if tag == b"WAVE":
            return ".wav"
    if head[4:8] == b"ftyp":
        return ".m4a"
    return ".jpg" if kind == "image" else ".mp3"


def _as_contract(result):
    """A provider's answer as `ProviderExtractionResult` sees it.

    `{"fields": [{"key", "extractedValue", "confidence", "editedByUser"}]}` and nothing
    else: `ApiModel` forbids extra keys, so `text`, `provider` and `language` cannot simply
    be passed along -- the service would reject the whole payload as off-contract.

    Empty text yields NO fields rather than one empty field. "The model read nothing" and
    "the model read an empty string" are the same fact, and a blank field in a review form
    invites someone to type a number into it that no document ever contained.
    """
    text = "" if result.get("text") is None else str(result["text"])
    confidence = result.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    # The column is 0..1 and the schema enforces it. A provider that reported something
    # outside that range is clamped rather than allowed to fail the whole extraction.
    confidence = min(1.0, max(0.0, confidence))
    fields = [{"key": RAW_TEXT_KEY, "extractedValue": text,
               "confidence": confidence, "editedByUser": False}]
    if not text.strip():
        fields.extend(_warning_fields("ocrWarnings", ["no text recognized"], "ocr-empty"))
        return {"fields": fields}
    structured = _structured_fields(text, confidence)
    fields.extend(structured)
    fields.extend(_ai_fields(text, {field["key"] for field in fields},
                             transcript=result.get("transcript"),
                             metadata=result.get("metadata"),
                             needs_ai=_needs_ai(structured, confidence)))
    return {"fields": fields}


#: How much of the model's stated confidence survives into the draft. A model's own number
#: is about its fluency as much as about the document, and these candidates have had no
#: rule applied to them -- so they arrive visibly less certain than a parser field, which
#: is what puts them below the review UI's 0.8 "look at this" threshold by default.
AI_CONFIDENCE_WEIGHT = 0.9


def _needs_ai(structured_fields, ocr_confidence):
    keys = {field["key"] for field in structured_fields}
    if ocr_confidence < 0.5:
        return True
    if "items" not in keys:
        return True
    warnings = next((field["extractedValue"] for field in structured_fields
                     if field["key"] == "parserWarnings"), [])
    return any(isinstance(item, dict) and item.get("code") == "INVOICE_TABLE_NOT_RECOGNISED"
               for item in warnings)


def _ai_fields(text, already_emitted, transcript=None, metadata=None, needs_ai=True):
    """LLM candidates for fields the deterministic parser could not find.

    THE ORDER IS THE POINT. `_structured_fields` runs first and its keys are passed in
    here as `already_emitted`; anything it produced is never asked of the model and never
    overwritten by it. A rule that can be read beats a model that cannot, so the model
    fills gaps and does not arbitrate.

    Switched off unless `FINANCE_AI_EXTRACTION_ENABLED=true`,
    `FINANCE_AI_PROVIDER=openai`, and `FINANCE_AI_API_KEY` are configured. Every failure
    returns warning fields and lets the extraction continue: OCR text and parser
    candidates are already in `fields`, and losing them because a second opinion was
    unavailable would make the pipeline less reliable.
    """
    if not needs_ai:
        return []
    provider = build_extraction_provider()
    if provider is None:
        legacy = _legacy_avalai_fields(text, already_emitted, transcript, metadata)
        return legacy
    try:
        candidate = provider.extract_invoice(text, {"transcript": transcript,
                                                    "metadata": metadata})
    except (ExtractionProviderUnavailable, ExtractionProviderResponseInvalid) as error:
        LOG.warning("finance AI extraction skipped: %s", error)
        return _warning_fields("aiWarnings", [str(error)], "ai-unavailable")
    except Exception:                                          # noqa: BLE001
        LOG.exception("finance AI extraction failed; the rest of the extraction stands")
        return _warning_fields("aiWarnings", ["AI extraction failed"], "ai-failed")

    emitted = []
    emitted.append({"key": "extractionSource", "extractedValue": candidate.provider,
                    "confidence": 1.0, "editedByUser": False})
    emitted.append({"key": "extractionConfidence", "extractedValue": candidate.confidence,
                    "confidence": 1.0, "editedByUser": False})
    warnings = list(candidate.warnings)
    if candidate.confidence < 0.5:
        warnings.append("AI confidence is below 0.5; structured AI fields were not used.")
        emitted.extend(_warning_fields("aiWarnings", warnings, "ai-low-confidence"))
        return emitted
    if candidate.confidence < 0.85:
        warnings.append("AI confidence is below 0.85; review is required before use.")
    if warnings:
        emitted.extend(_warning_fields("aiWarnings", warnings, "ai-review-required"))

    for key, value in _candidate_fields(candidate):
        if key in already_emitted:
            continue
        confidence = candidate.confidence
        emitted.append({"key": key, "extractedValue": value,
                        "confidence": min(1.0, max(0.0, confidence * AI_CONFIDENCE_WEIGHT)),
                        "editedByUser": False})
    return emitted


def _legacy_avalai_fields(text, already_emitted, transcript=None, metadata=None):
    setting = (os.environ.get("FINANCE_AI_EXTRACTION_ENABLED") or "").strip().lower()
    if setting in {"0", "false", "no", "off"}:
        return []
    try:
        from extraction.providers.avalai import (AvalAIProvider, ProviderResponseInvalid,
                                                 ProviderUnavailable)
    except ImportError:                                        # noqa: BLE001
        return []
    provider = AvalAIProvider()
    if not provider.configured:
        return []
    try:
        candidates = provider.extract(text, transcript=transcript, metadata=metadata)
    except (ProviderUnavailable, ProviderResponseInvalid) as error:
        LOG.warning("legacy avalai extraction skipped: %s", error)
        return _warning_fields("aiWarnings", [str(error)], "ai-unavailable")
    except Exception:                                          # noqa: BLE001
        LOG.exception("legacy avalai extraction failed; the rest of the extraction stands")
        return _warning_fields("aiWarnings", ["AI extraction failed"], "ai-failed")

    emitted = []
    for key, (value, confidence) in sorted(candidates.items()):
        if key in already_emitted:
            continue
        emitted.append({"key": key, "extractedValue": value,
                        "confidence": min(1.0, max(0.0, confidence * AI_CONFIDENCE_WEIGHT)),
                        "editedByUser": False})
    return emitted


def _warning_fields(key, warnings, source):
    return [{"key": key, "extractedValue": [{"source": source, "message": item}
                                            for item in warnings],
             "confidence": 1.0, "editedByUser": False}]


def _candidate_fields(candidate):
    invoice = candidate.invoice or {}
    mapping = (
        ("supplierName", invoice.get("supplier")),
        ("buyerName", invoice.get("customer")),
        ("invoiceNumber", invoice.get("invoice_number")),
        ("invoiceDate", invoice.get("invoice_date")),
        ("currency", invoice.get("currency")),
        ("totalAmount", invoice.get("total_amount")),
    )
    fields = [(key, value) for key, value in mapping if value is not None]
    items = []
    for item in candidate.items:
        items.append({
            "name": item.get("description"),
            "description": item.get("description"),
            "quantity": item.get("quantity"),
            "unit": item.get("unit"),
            "unitPrice": item.get("unit_price"),
            "amount": item.get("total_price"),
            "totalPrice": item.get("total_price"),
            "warnings": [],
        })
    if items:
        fields.append(("items", items))
    return fields


def _decimal_text(value):
    """A parsed number as an exact string. Never a float: these are money."""
    return None if value is None else format(value, "f")


def _structured_fields(text, ocr_confidence):
    """The parser's candidates as contract fields, or nothing when it read nothing.

    A field is emitted only where the parser says EXACT -- an ambiguous reading is carried
    in `parserWarnings` for the reviewer instead of pre-filling a form with a number the
    document did not clearly state. Parsing never raises into the extraction: a text this
    parser cannot handle must still deliver its raw text.
    """
    try:
        parsed = parse_invoice(text)
    except Exception:                                          # noqa: BLE001
        LOG.exception("invoice parsing failed; raw text is still delivered")
        return []
    emitted = []

    def add(key, value, certainty):
        if value is None:
            return
        emitted.append({"key": key, "extractedValue": value,
                        "confidence": min(1.0, max(0.0, ocr_confidence
                                                   * PARSER_CERTAINTY.get(certainty, 0.0))),
                        "editedByUser": False})

    for key, candidate in (("invoiceNumber", parsed.invoice_number),
                           ("invoiceDate", parsed.invoice_date),
                           ("supplierName", parsed.supplier_name),
                           ("buyerName", parsed.buyer_name),
                           ("currency", parsed.currency)):
        if candidate.found:
            add(key, candidate.value, candidate.certainty)
    if parsed.total_amount.found:
        add("totalAmount", _decimal_text(parsed.total_amount.value),
            parsed.total_amount.certainty)
    if parsed.items:
        add("items", [{"name": item.name,
                       "quantity": _decimal_text(item.quantity),
                       "unit": item.unit,
                       "unitPrice": _decimal_text(item.unit_price),
                       "amount": _decimal_text(item.amount),
                       "warnings": [dict(warning) for warning in item.warnings]}
                      for item in parsed.items], "EXACT")
    add("validationStatus", parsed.validation_status, "EXACT")
    if parsed.warnings:
        add("parserWarnings", [dict(warning) for warning in parsed.warnings], "EXACT")
    return emitted


class _TemporaryUpload:
    """The stored bytes as a real file on disk, deleted afterwards whatever happens.

    `file` is whatever `FileStorage.get` returned. `LocalFileStorage` returns bytes; a
    different storage might return a path, so both are accepted rather than assuming the
    one that happens to be wired today.
    """

    def __init__(self, file, kind):
        self._file, self._kind, self._temporary = file, kind, None

    def __enter__(self):
        if isinstance(self._file, (str, os.PathLike)) and Path(self._file).is_file():
            return Path(self._file)
        content = self._file if isinstance(self._file, (bytes, bytearray)) else None
        if content is None:
            raise TypeError("storage returned %s; expected bytes or a path"
                            % type(self._file).__name__)
        handle = tempfile.NamedTemporaryFile(suffix=_suffix(content, self._kind),
                                             delete=False)
        try:
            handle.write(content)
        finally:
            handle.close()
        self._temporary = Path(handle.name)
        return self._temporary

    def __exit__(self, *_exc):
        if self._temporary is not None:
            try:
                self._temporary.unlink()
            except OSError:
                pass
        return False


class ImageExtractionAdapter:
    """`InvoiceImageExtractor` over a local OCR provider."""

    adapter_name = "paddleocr-local"

    def __init__(self, provider=None, adapter_name=None):
        self._provider = provider
        if adapter_name:
            self.adapter_name = adapter_name

    def _load(self):
        if self._provider is None:
            from extraction.providers.paddle_ocr import PaddleOCRProvider
            self._provider = PaddleOCRProvider()
        return self._provider

    def _read(self, path):
        return self._load().read(path)

    async def extract(self, file, hints=None):
        with _TemporaryUpload(file, "image") as path:
            # to_thread, because the OCR call is CPU-bound and blocking. Without it one
            # upload would hold the event loop for the length of a recognition.
            result = await asyncio.to_thread(self._read, path)
        return _as_contract(result)


class VoiceExtractionAdapter:
    """`InvoiceVoiceExtractor` over a local speech provider."""

    adapter_name = "whisper-local"

    def __init__(self, provider=None, adapter_name=None):
        self._provider = provider
        if adapter_name:
            self.adapter_name = adapter_name

    def _load(self):
        if self._provider is None:
            from extraction.providers.whisper_voice import WhisperProvider
            self._provider = WhisperProvider()
        return self._provider

    def _transcribe(self, path):
        return self._load().transcribe(path)

    async def extract(self, file, hints=None):
        with _TemporaryUpload(file, "audio") as path:
            result = await asyncio.to_thread(self._transcribe, path)
        return _as_contract(result)
