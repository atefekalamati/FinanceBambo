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
import io
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



#: A page above this is downscaled before it is sent. Vision models tile large images and
#: charge by tile, and a construction invoice photographed at 12 megapixels carries no more
#: readable text than the same page at 2. Measured: gpt-4o spent 1,512 prompt tokens on
#: these scans, gpt-4o-mini 37,045 for the same bytes.
VISION_MAX_PIXELS = 2200
VISION_JPEG_QUALITY = 85


def _accepts_image(provider):
    """Whether this provider's `extract_invoice` takes an image.

    Asked rather than assumed, because `ExtractionProvider` is a Protocol and anything
    satisfying the two-argument form is a legitimate provider. A vision call to one that
    predates vision would be a TypeError at the worst possible moment -- inside an
    extraction, after the OCR has already been paid for.
    """
    import inspect

    try:
        return "image" in inspect.signature(provider.extract_invoice).parameters
    except (TypeError, ValueError):
        return False


def _image_for_vision(path):
    """The page as JPEG bytes, downscaled if it is larger than a model needs.

    Returns None rather than raising. Preparing the image is an enhancement to the
    extraction, not a precondition for it: a page that cannot be re-encoded still has its
    OCR text, its parser candidates and its layout reading, and losing all of that because
    a thumbnailer failed would be a poor trade.

    The ORIGINAL on disk is never touched. This reads it and returns a copy in memory --
    uploads are content-addressed by sha256 and a rewritten file would no longer be the
    file that was uploaded.
    """
    try:
        from PIL import Image

        with Image.open(path) as page:
            page.load()
            if page.mode not in ("RGB", "L"):
                page = page.convert("RGB")
            if max(page.size) > VISION_MAX_PIXELS:
                scale = VISION_MAX_PIXELS / float(max(page.size))
                page = page.resize((max(1, int(page.width * scale)),
                                    max(1, int(page.height * scale))),
                                   Image.LANCZOS)
            buffer = io.BytesIO()
            page.save(buffer, format="JPEG", quality=VISION_JPEG_QUALITY, optimize=True)
            return buffer.getvalue()
    except Exception:                                            # noqa: BLE001
        LOG.warning("invoice page could not be prepared for vision; text extraction stands",
                    exc_info=True)
        return None


def _fusion_fields(structured, ai_emitted, already_emitted):
    """The two readings compared, as fields a draft carries and a reviewer reads.

    Neither reading is edited here and neither is chosen. `fusion` records where they
    agree, where they differ, and where only one of them spoke; `financial_checks` asks
    whether each reading is internally consistent. Both answers ride on the draft so the
    person reviewing sees WHY a row is flagged, not merely that it is.
    """
    if "extractionSource" not in {field["key"] for field in ai_emitted}:
        return []                       # no vision reading happened; nothing to compare

    from . import financial_checks, fusion

    def values(fields):
        return {field["key"]: field["extractedValue"] for field in fields}

    ocr_side = values(structured)
    vision_side = values(ai_emitted)
    report = fusion.fuse(ocr_side, vision_side,
                         ocr_items=ocr_side.get("items"),
                         vision_items=vision_side.get("items"))
    checks = financial_checks.validate(vision_side, vision_side.get("items") or [])

    emitted = []
    for key, value in (("fusionResult", report), ("validationResult", checks)):
        if key not in already_emitted:
            emitted.append({"key": key, "extractedValue": value,
                            "confidence": 1.0, "editedByUser": False})
    if report["requiresReview"] or checks["requiresReview"]:
        emitted.extend(_warning_fields(
            "fusionWarnings",
            (["فیلدهای ناسازگار: %s" % "، ".join(report["conflictFields"])]
             if report["conflictFields"] else [])
            + (["ردیف‌های ناسازگار: %s" % report["conflictRows"]]
               if report["conflictRows"] else [])
            + [entry["message"] for entry in checks["checks"]
               if entry.get("message")],
            "fusion-requires-review"))
    return emitted

def _as_contract(result, image=None, media_type="image/jpeg"):
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
    # The page's own geometry, read only where the text-only parser found no table. It is
    # a SECOND reading of the same page, not a replacement: everything above still stands,
    # and this adds `tableRows` where a table could be reconstructed from positions that
    # the flattened text no longer contains.
    fields.extend(_layout_fields(result.get("lines"), {f["key"] for f in fields}))
    ai = _ai_fields(text, {field["key"] for field in fields},
                    transcript=result.get("transcript"),
                    metadata=result.get("metadata"),
                    # With a page in hand the model is always worth asking. `_needs_ai`
                    # gates the TEXT reading, where a clean parse makes a second opinion
                    # redundant; a vision reading is a different witness and is the whole
                    # reason the image was kept this far.
                    needs_ai=image is not None or _needs_ai(structured, confidence),
                    image=image, media_type=media_type)
    fields.extend(ai)
    fields.extend(_fusion_fields(structured, ai, {f["key"] for f in fields}))
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


def _ai_fields(text, already_emitted, transcript=None, metadata=None, needs_ai=True,
               image=None, media_type="image/jpeg"):
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
        # The PAGE when one is available, the transcription otherwise. A provider built
        # before vision existed still accepts the two-argument call, so an older or
        # third-party provider keeps working -- it simply never sees an image.
        if image is not None and _accepts_image(provider):
            candidate = provider.extract_invoice(
                text, {"transcript": transcript, "metadata": metadata},
                image=image, media_type=media_type)
        else:
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


#: The keys the layout reading contributes. Named so the set is visible in one place and
#: so `_first_wins` can be reasoned about: none of these collide with a parser key.
LAYOUT_KEYS = ("tableRows", "tablePageKind", "tableConfidence", "tableColumnSource")


def _layout_fields(raw_lines, already_emitted):
    """Line items rebuilt from where the words sit, when the text alone could not.

    WHY THIS RUNS ONLY AS A FALLBACK

    `invoice_parser` reads a table out of the text when the recogniser emitted it in
    reading order, which is the common case and is well tested. Geometry is the answer for
    the pages where that fails -- a detector that returns cells column-first leaves text
    with no table left in it, and no amount of parsing recovers an order that is gone.

    Running it second means no page that works today changes: `items` from the parser is
    already in `already_emitted`, and this never replaces it.

    WHAT IT REFUSES TO DO

    A reconstruction whose cells are mostly unreadable is kept as a diagnosis and NOT
    offered as values. On the audited three-page invoice the recogniser returned `'ld'bdd`
    and `xl` where product names and amounts belong; turning those into line items would
    put invented-looking data on a financial draft, which is worse than reporting that the
    table could not be read. The structural rule in `layout._is_line_item` and the
    confidence band both have to pass.
    """
    if not raw_lines:
        return []
    try:
        from extraction import layout
    except ImportError:                                        # noqa: BLE001
        return []
    try:
        table = layout.reconstruct(raw_lines)
    except Exception:                                          # noqa: BLE001
        LOG.exception("layout reconstruction failed; the rest of the extraction stands")
        return []
    if table is None:
        # A page that yielded no items still says what it was and why. "This is a summary
        # page" and "this table could not be read" are different answers, and a reviewer
        # looking at an empty item list cannot tell them apart from silence.
        try:
            kind, reason = layout.diagnose(raw_lines)
        except Exception:                                      # noqa: BLE001
            return []
        if reason == layout.NO_TABLE_EMPTY:
            return []
        return [{"key": "tablePageKind", "extractedValue": kind,
                 "confidence": 1.0, "editedByUser": False}] + _warning_fields(
            "layoutWarnings", ["no line items were read from this page (%s)" % reason],
            "layout-" + reason.replace("_", "-"))

    emitted = [{"key": "tablePageKind", "extractedValue": table.page_kind,
                "confidence": 1.0, "editedByUser": False},
               {"key": "tableConfidence", "extractedValue": round(table.confidence, 4),
                "confidence": 1.0, "editedByUser": False},
               {"key": "tableColumnSource", "extractedValue": table.column_source,
                "confidence": 1.0, "editedByUser": False}]
    if not table.trustworthy:
        # Said out loud rather than silently dropped, so a reviewer knows a table WAS
        # found and why its contents are not being offered.
        emitted.extend(_warning_fields(
            "layoutWarnings",
            ["a table of %d rows was reconstructed from the page layout, but its cells "
             "average %.2f confidence and were not used" % (len(table.rows),
                                                            table.confidence)],
            "layout-low-confidence"))
        return emitted
    emitted.append({"key": "tableRows", "extractedValue": table.rows,
                    "confidence": min(1.0, max(0.0, table.confidence)),
                    "editedByUser": False})
    if "items" in already_emitted:
        # The parser already read this table from the text. Its reading is the tested one
        # and it stands; the reconstruction still travels, because a reviewer comparing
        # the two is exactly who `tableRows` is for.
        return emitted

    items = _items_from_table(table)
    if items:
        emitted.append({"key": "items", "extractedValue": items,
                        "confidence": min(1.0, max(0.0, table.confidence)),
                        "editedByUser": False})
    return emitted


def _items_from_table(table):
    """`tableRows` in the shape the parser emits, or `[]` when nothing survives.

    WHY THE PARSER'S OWN RULES AND NOT NEW ONES

    Every money cell goes through `strict_amount`, which is what the text path uses. It
    refuses `135,00,0` rather than stripping the separators out of it, and that refusal is
    the reason a mangled figure does not become a confident wrong number. A second reader
    with its own idea of what a number looks like would be a second answer to a question
    this codebase has already settled.

    WHAT AN UNREADABLE CELL BECOMES

    None, and a warning on the item saying which cell and why -- never a zero, and never
    the raw text passed off as a value. `null` in a review form is a question; `0` is an
    assertion that something cost nothing.

    An item keeps its description even when every number on the row failed. A reviewer who
    can see «سیمان تیپ ۲» beside three empty fields is being told something useful; a row
    dropped entirely tells them nothing.
    """
    from decimal import Decimal

    from extraction.invoice_parser import strict_amount
    from extraction.parsing import find_unit, normalize, to_decimal

    items = []
    for row in table.rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        warnings = []

        def money(role):
            raw = (row.get(role) or "").strip()
            if not raw:
                return None
            value, problem = strict_amount(raw)
            if value is None:
                warnings.append({"code": "INVOICE_CELL_UNREADABLE",
                                 "message": "the %s cell does not form a number (%s)"
                                            % (role, problem),
                                 "evidence": raw})
            return _decimal_text(value)

        # Quantity is `to_decimal`, not `strict_amount`: a quantity cell reads «12 عدد» and
        # the unit beside the number is ordinary there, while in a money cell it would mean
        # the figure was misread. Different cells, different strictness, both deliberate.
        quantity_raw = (row.get("quantity") or "").strip()
        quantity = to_decimal(quantity_raw) if quantity_raw else None
        if quantity_raw and quantity is None:
            warnings.append({"code": "INVOICE_CELL_UNREADABLE",
                             "message": "the quantity cell does not form a number",
                             "evidence": quantity_raw})

        # The matched WORD, exactly as `_item_from_block` stores it -- «پاکت», not `bag`.
        # These items sit beside the parser's own in one field, and a reviewer reading the
        # list should not be able to tell which reader produced which row. The registry
        # code is settled later, by the layer that converts.
        unit_cell = (row.get("unit") or "").strip()
        _code, unit_word = find_unit(unit_cell) if unit_cell else (None, None)
        unit = unit_word or (unit_cell or None)
        if unit_cell and unit_word is None:
            warnings.append({"code": "INVOICE_UNIT_UNKNOWN",
                             "message": "the unit is not one this system knows; it is "
                                        "reported as the sheet wrote it",
                             "evidence": unit_cell})

        unit_price = money("unit_price")
        amount = money("amount")
        # The same cross-check `_item_from_block` makes. Both figures are reported as read
        # -- neither is corrected to agree with the other, because which one is wrong is
        # not something this can know.
        if quantity is not None and unit_price is not None and amount is not None:
            if quantity * Decimal(unit_price) != Decimal(amount):
                warnings.append({
                    "code": "INVOICE_ITEM_ARITHMETIC_MISMATCH",
                    "message": "quantity x unitPrice does not equal the stated amount; "
                               "both values are reported as read.",
                    "evidence": "%s x %s != %s" % (quantity, unit_price, amount)})

        items.append({"name": normalize(name),
                      "quantity": _decimal_text(quantity),
                      "unit": unit,
                      "unitPrice": unit_price,
                      "amount": amount,
                      "warnings": warnings})
    return items


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
            # The page itself, read before the temporary file goes away. Until now the
            # image ended here and everything downstream saw only a transcription -- which
            # is why a 0.45-confidence scan produced nothing a reader could use. Held as
            # bytes rather than a path because the provider posts it, and a path that has
            # been deleted is not a page.
            image = _image_for_vision(path)
        return _as_contract(result, image=image, media_type="image/jpeg")


class VoiceExtractionAdapter:
    """`InvoiceVoiceExtractor` over a speech provider, then over the invoice reader.

    TWO STAGES, KEPT APART

        audio  ->  speech provider  ->  transcript      (this file knows no invoices)
        transcript  ->  invoice reader  ->  fields      (this file knows no audio)

    They are separate calls to separate models because they answer separate questions, and
    a single model asked to do both would give one confidence for two different acts. The
    transcript is kept whichever way the second stage goes -- see below.

    WHICH SPEECH PROVIDER

    Whatever is injected. Nothing here names AvalAI or Whisper; `devhost` decides from
    configuration and this adapter cannot tell which answered. That is what lets the model
    change without touching anything that reasons about invoices.
    """

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
        return _as_contract_voice(result, hints)


#: What a voice draft records about where its numbers came from. `source` is named here
#: rather than derived from `provider_adapter`, because the adapter name says WHICH
#: transcriber ran and a reviewer is asking WHICH KIND OF INPUT this was.
VOICE_SOURCE_KEY = "source"
VOICE_SOURCE = "voice"
TRANSCRIPT_KEY = "voiceTranscript"
SPEECH_PROVIDER_KEY = "speechProvider"


def _as_contract_voice(result, hints=None):
    """A transcript, plus whatever the invoice reader could take from it.

    THE TRANSCRIPT SURVIVES EVERYTHING. It is emitted before the reader is asked and is
    never replaced by what the reader decided -- so the question "what did the speaker
    actually say" always has an answer, including when the structuring stage is switched
    off, unavailable, or wrong.

    That matters most in the case this exists for: a speaker who states an amount that a
    scanned invoice contradicts. The transcript is the only evidence the two disagree, and
    a pipeline that discarded it after structuring would destroy that evidence and leave
    two numbers with no way to tell which came from whom.
    """
    # `_as_contract` answers with the whole payload -- `{"fields": [...]}` -- because that
    # is what the service reads. The fields are taken out, added to, and put back in the
    # same envelope: returning a bare list here would be off-contract and the service would
    # reject the entire extraction.
    contract = _as_contract(result)
    fields = contract["fields"]
    emitted = {field["key"] for field in fields}

    text = "" if result.get("text") is None else str(result["text"])
    confidence = result.get("confidence")

    provenance = [
        {"key": VOICE_SOURCE_KEY, "extractedValue": VOICE_SOURCE,
         "confidence": 1.0, "editedByUser": False},
        # The transcript again under its own key. `rawText` is the generic slot every
        # adapter fills; this one says it is SPEECH, which is what a reviewer comparing a
        # spoken amount against a printed one needs to find.
        {"key": TRANSCRIPT_KEY, "extractedValue": text,
         # The speech provider's own confidence when it reports one, and NOT a number
         # invented here when it does not: AvalAI returns no per-segment probability, and
         # a fabricated figure would be read as measured.
         "confidence": 0.0 if confidence is None else min(1.0, max(0.0, float(confidence))),
         "editedByUser": False},
    ]
    if result.get("provider"):
        provenance.append({"key": SPEECH_PROVIDER_KEY,
                           "extractedValue": "%s%s" % (
                               result["provider"],
                               "/" + result["model"] if result.get("model") else ""),
                           "confidence": 1.0, "editedByUser": False})
    fields.extend(field for field in provenance if field["key"] not in emitted)

    if not text.strip():
        return contract

    # Stage two, and the same reader the image path uses -- not a second one. `needs_ai`
    # is unconditional here because a transcript has no deterministic parser to try first:
    # for an image, rules run before the model and the model only fills gaps; for speech
    # there are no rules, so the reader is the only candidate source there is.
    fields.extend(_ai_fields(text, {field["key"] for field in fields},
                             transcript=text, metadata=None, needs_ai=True))
    return contract
