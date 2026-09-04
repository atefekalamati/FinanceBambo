# -*- coding: utf-8 -*-
"""PaddleOCR, running locally. No file and no text leaves the server.

The model is loaded once and reused: PaddleOCR spends several seconds building its detection
and recognition graphs, and paying that per invoice would make every upload feel broken. It
is loaded on first use rather than at import, so a deployment that never processes an image
never pays for it and never needs the package installed.

The OCR call itself is blocking and CPU-bound, so it runs in a worker thread. Without that
it would hold the event loop for the length of a recognition and stall every other request
in the process.
"""

import asyncio
import time
from decimal import Decimal
from pathlib import Path

from .base import ExtractedField, ExtractionResult, ProviderUnavailable
from .parsing import parse_invoice_text

#: PaddleOCR's own language code for Persian. `ar` also recognises the script but is trained
#: on Arabic text and misreads the Persian-only letters -- گ چ پ ژ -- which appear in most
#: material names.
DEFAULT_LANGUAGE = "fa"


class PaddleOCRProvider:
    """`InvoiceImageExtractor` backed by a local PaddleOCR model."""

    adapter_name = "paddleocr-local"

    def __init__(self, language=DEFAULT_LANGUAGE, use_gpu=False, engine=None,
                 minimum_confidence=Decimal("0.30")):
        self._language = language
        self._use_gpu = use_gpu
        self._engine = engine          # injectable, so tests never load a model
        self._lock = asyncio.Lock()
        self._minimum = Decimal(minimum_confidence)

    async def _load(self):
        """The model, loaded once. Concurrent first calls wait rather than loading twice."""
        if self._engine is not None:
            return self._engine
        async with self._lock:
            if self._engine is not None:
                return self._engine
            try:
                from paddleocr import PaddleOCR
            except ImportError as error:
                raise ProviderUnavailable(
                    "paddleocr is not installed in this environment; see "
                    "docs/EXTRACTION_SELF_HOSTED_SETUP_FA.md") from error
            try:
                self._engine = await asyncio.to_thread(PaddleOCR, **self._options(PaddleOCR))
            except Exception as error:                       # noqa: BLE001
                raise ProviderUnavailable("PaddleOCR failed to initialise: %s" % error) from error
            return self._engine

    def _options(self, factory):
        """Constructor arguments this installed PaddleOCR actually accepts.

        The 2.x and 3.x constructors share almost nothing: `use_angle_cls` became
        `use_textline_orientation`, and `use_gpu` and `show_log` were removed outright --
        3.x takes `device="gpu"` instead. Pinning either spelling makes the provider fail on
        the other version for a reason that reads as a model error, so the signature is
        inspected and only what it names is passed.

        Version 3.7 is what installs on CPython 3.12; 2.x is what most existing deployments
        have. Both are supported rather than one being declared correct.
        """
        import inspect
        accepted = set(inspect.signature(factory.__init__).parameters)
        options = {}
        if "lang" in accepted:
            options["lang"] = self._language
        # Rotated text detection. Same feature, renamed between majors.
        if "use_textline_orientation" in accepted:
            options["use_textline_orientation"] = True
        elif "use_angle_cls" in accepted:
            options["use_angle_cls"] = True
        if "use_gpu" in accepted:
            options["use_gpu"] = self._use_gpu
        elif "device" in accepted and self._use_gpu:
            options["device"] = "gpu"
        if "show_log" in accepted:
            options["show_log"] = False
        return options

    @staticmethod
    def _flatten(raw):
        """PaddleOCR's output as `(text, confidence)` pairs, whichever major produced it.

        The two versions return different structures for the same information:

          2.x  `[[[box, (text, score)], ...]]`  -- one list per image, one tuple per line
          3.x  `[{"rec_texts": [...], "rec_scores": [...], ...}]`  -- parallel arrays

        Both are read. Detecting the shape is cheaper than pinning a version and is the only
        way the same provider serves an existing 2.x deployment and a fresh 3.x one.
        """
        if not raw:
            return []
        out = []
        for page in raw:
            # 3.x: a result object or dict with parallel arrays.
            texts = getattr(page, "get", lambda *_: None)("rec_texts") \
                if hasattr(page, "get") else None
            if texts is not None:
                scores = page.get("rec_scores") or []
                for index, text in enumerate(texts):
                    if text is None:
                        continue
                    score = scores[index] if index < len(scores) else 0
                    out.append((str(text), Decimal(str(score))))
                continue
            # 2.x: a list of [box, (text, score)] entries.
            for entry in page or []:
                try:
                    text, score = entry[1]
                except (TypeError, IndexError, ValueError, KeyError):
                    continue
                if text is None:
                    continue
                out.append((str(text), Decimal(str(score))))
        return out

    async def _run(self, engine, path):
        """Call whichever recognition method this version exposes.

        2.x takes `ocr(img, cls=True)`; 3.x dropped the second argument and added
        `predict()`. Passing 2.x's signature to 3.x raises a TypeError that reads like a
        model failure, which is how this was found.
        """
        import inspect
        if hasattr(engine, "predict"):
            return await asyncio.to_thread(engine.predict, str(path))
        parameters = inspect.signature(engine.ocr).parameters
        if "cls" in parameters:
            return await asyncio.to_thread(engine.ocr, str(path), True)
        return await asyncio.to_thread(engine.ocr, str(path))

    async def extract_text(self, file_path) -> ExtractionResult:
        path = Path(file_path)
        if not path.is_file():
            raise ProviderUnavailable("image file is missing: %s" % path.name)
        engine = await self._load()
        started = time.monotonic()
        try:
            raw = await self._run(engine, path)
        except Exception as error:                            # noqa: BLE001
            raise ProviderUnavailable("PaddleOCR failed to read the image: %s" % error) from error
        elapsed = Decimal(str(round(time.monotonic() - started, 3)))

        lines = self._flatten(raw)
        warnings = []
        # Low-confidence lines are kept, not dropped. Dropping one would leave the reviewer
        # with a form missing a value and nothing saying a value had been missed.
        weak = [text for text, score in lines if score < self._minimum]
        if weak:
            warnings.append("%d خط با اطمینان پایین خوانده شد؛ متن خام را ببینید." % len(weak))
        text = "\n".join(item for item, _ in lines)
        if not text.strip():
            warnings.append("هیچ متنی در تصویر تشخیص داده نشد.")
            page_confidence = Decimal(0)
        else:
            page_confidence = (sum((score for _, score in lines), Decimal(0))
                               / Decimal(len(lines))).quantize(Decimal("0.0001"))

        parsed, parse_warnings = parse_invoice_text(text, page_confidence)
        return ExtractionResult(
            raw_text=text,
            fields=tuple(ExtractedField(key, value, at) for key, value, at in parsed),
            confidence=page_confidence,
            provider_name=self.adapter_name,
            language=self._language,
            processing_seconds=elapsed,
            warnings=tuple(warnings) + parse_warnings)

    async def extract(self, file, hints=None) -> dict:
        """The `InvoiceImageExtractor` port. `file` carries a filesystem path."""
        path = getattr(file, "path", None) or getattr(file, "local_path", None) or file
        return (await self.extract_text(path)).as_contract()
