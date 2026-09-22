# -*- coding: utf-8 -*-
"""PaddleOCR, running locally. No image and no text leaves this machine.

LOCAL DEVELOPMENT ONLY. No database, no Finance import, no API contract.

The model is loaded once and reused: PaddleOCR spends several seconds building its
detection and recognition graphs, and paying that per invoice would make every upload feel
broken. It is loaded on first use rather than at import, so a process that never reads an
image never pays for it and never needs the package installed.

    from extraction.providers.paddle_ocr import PaddleOCRProvider
    PaddleOCRProvider().read("invoice.jpg")
    # {"text": "...", "confidence": 0.79, "provider": "paddleocr"}
"""

import inspect
import threading
import time
from pathlib import Path

#: PaddleOCR's own language code for Persian. `ar` also recognises the script but is trained
#: on Arabic text and misreads the Persian-only letters -- گ چ پ ژ -- which appear in most
#: material names.
DEFAULT_LANGUAGE = "fa"

PROVIDER = "paddleocr"

#: One recognition at a time, per process.
#:
#: The engine is built once and reused, and `ImageExtractionAdapter` calls it through
#: `asyncio.to_thread` -- so two extractions in a row run on two DIFFERENT threads of the
#: default executor pool against the SAME predictor. PaddleOCR's predictor is not
#: re-entrant, and what comes back from that is a bare "Unknown exception" from the
#: native layer, surfaced to the caller as 503.
#:
#: Measured before this lock: three sequential extractions through the real endpoint took
#: five attempts -- files two and three each failed once and succeeded on retry. Nothing
#: was corrupted, because the failure happens inside recognition and no draft is written,
#: but a person pressing "extract" saw an error more often than not.
#:
#: Module level, not per instance: the adapter builds its own provider objects, and a lock
#: that each of them owned separately would not serialise anything.
_ENGINE_LOCK = threading.Lock()


class ProviderUnavailable(RuntimeError):
    """The model could not run. Never raised for "the image contained no text"."""


class PaddleOCRProvider:
    """Reads an image and returns text with a confidence. Nothing else."""

    def __init__(self, language=DEFAULT_LANGUAGE, use_gpu=False, engine=None):
        self._language = language
        self._use_gpu = use_gpu
        self._engine = engine          # injectable, so a test never loads a model

    # ---------------------------------------------------------------- model construction
    def _options(self, factory):
        """Constructor arguments this installed PaddleOCR actually accepts.

        The 2.x and 3.x constructors share almost nothing: `use_angle_cls` became
        `use_textline_orientation`, and `use_gpu` and `show_log` were removed outright --
        3.x takes `device="gpu"` instead. Pinning either spelling makes the provider fail on
        the other version with an error that reads like a model fault, so the signature is
        inspected and only what it names is passed.
        """
        accepted = set(inspect.signature(factory.__init__).parameters)
        options = {}
        if "lang" in accepted:
            options["lang"] = self._language
        if "use_textline_orientation" in accepted:      # 3.x
            options["use_textline_orientation"] = True
        elif "use_angle_cls" in accepted:               # 2.x
            options["use_angle_cls"] = True
        if "use_gpu" in accepted:                       # 2.x
            options["use_gpu"] = self._use_gpu
        elif "device" in accepted and self._use_gpu:    # 3.x
            options["device"] = "gpu"
        if "show_log" in accepted:
            options["show_log"] = False
        return options

    def _load(self):
        if self._engine is not None:
            return self._engine
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise ProviderUnavailable(
                "paddleocr is not installed in this environment; install "
                "requirements-ai.txt into ai-extraction-env") from error
        try:
            self._engine = PaddleOCR(**self._options(PaddleOCR))
        except Exception as error:                       # noqa: BLE001
            raise ProviderUnavailable("PaddleOCR failed to initialise: %s" % error) from error
        return self._engine

    # ------------------------------------------------------------------- reading a result
    @staticmethod
    def _box(polygon):
        """A quadrilateral as `(left, top, right, bottom)`, or None if it is unreadable.

        PaddleOCR returns four corner points, and a line on a scanned page is never quite
        axis-aligned. The bounding rectangle is what the layout work needs: rows are found
        by comparing vertical centres and columns by horizontal ones, and neither question
        is made more accurate by the skew.

        None rather than a guess when the shape is not what was expected. A box invented
        for a line would place that line somewhere it never was, and the whole point of
        keeping geometry is that the position is evidence.
        """
        try:
            points = [(float(point[0]), float(point[1])) for point in polygon]
        except (TypeError, IndexError, ValueError):
            # 3.x `rec_boxes` is already a flat [x0, y0, x1, y1] rather than four points.
            try:
                flat = [float(value) for value in polygon]
            except (TypeError, ValueError):
                return None
            if len(flat) != 4:
                return None
            return (min(flat[0], flat[2]), min(flat[1], flat[3]),
                    max(flat[0], flat[2]), max(flat[1], flat[3]))
        if not points:
            return None
        xs = [x for x, _y in points]
        ys = [y for _x, y in points]
        return (min(xs), min(ys), max(xs), max(ys))

    @classmethod
    def _flatten(cls, raw):
        """PaddleOCR's output as `(text, confidence, box)` triples, whichever major produced it.

          2.x  `[[[box, (text, score)], ...]]`                  one tuple per line
          3.x  `[{"rec_texts": [...], "rec_scores": [...],
                  "rec_polys": [...]}]`                         parallel arrays

        Detecting the shape is cheaper than pinning a version and is the only way one
        provider serves an existing 2.x deployment and a fresh 3.x one.

        THE BOX IS NEW AND IT IS THE POINT

        Both majors have always returned where each line sits, and this method used to
        read past it -- 2.x's `entry[0]` was skipped to reach `entry[1]`, and 3.x's
        `rec_polys` was never asked for. So an invoice arrived as 72 strings joined by
        newlines, and a table became a column of fragments in reading order with no way to
        tell which price belonged to which product. `INVOICE_TABLE_NOT_RECOGNISED` was the
        honest answer to text that genuinely had no table left in it.

        `box` may be None for a line whose geometry could not be read. Callers must treat
        that as "position unknown" rather than as (0, 0): a line placed at the origin would
        sort to the top-left and silently join the wrong row.
        """
        if not raw:
            return []
        out = []
        for page in raw:
            texts = page.get("rec_texts") if hasattr(page, "get") else None
            if texts is not None:                                  # 3.x
                scores = page.get("rec_scores") or []
                # `rec_polys` is the recognised line's own quadrilateral. `rec_boxes` is
                # the same thing as a rectangle and is accepted as a fallback, because
                # which of the two a build populates has varied across 3.x point releases.
                polygons = page.get("rec_polys")
                if polygons is None or len(polygons) == 0:
                    polygons = page.get("rec_boxes")
                for index, text in enumerate(texts):
                    if text is None:
                        continue
                    box = None
                    if polygons is not None and index < len(polygons):
                        box = cls._box(polygons[index])
                    out.append((str(text),
                                float(scores[index]) if index < len(scores) else 0.0,
                                box))
                continue
            for entry in page or []:                               # 2.x
                try:
                    text, score = entry[1]
                except (TypeError, IndexError, ValueError, KeyError):
                    continue
                if text is None:
                    continue
                box = None
                try:
                    box = cls._box(entry[0])
                except (TypeError, IndexError, KeyError):
                    box = None
                out.append((str(text), float(score), box))
        return out

    def _run(self, engine, path):
        """Call whichever recognition method this version exposes.

        2.x takes `ocr(img, cls=True)`; 3.x dropped the second argument and added
        `predict()`. Passing 2.x's signature to 3.x raises a TypeError that reads like a
        model failure, which is how this was found.
        """
        if hasattr(engine, "predict"):
            return engine.predict(str(path))
        if "cls" in inspect.signature(engine.ocr).parameters:
            return engine.ocr(str(path), True)
        return engine.ocr(str(path))

    def read(self, image_path):
        """`{"text", "confidence", "provider"}` for one image.

        An image with no readable text is NOT an error: it returns empty text and a
        confidence of 0. Only a model that could not run raises.
        """
        path = Path(image_path)
        if not path.is_file():
            raise ProviderUnavailable("image file is missing: %s" % path.name)

        started = time.monotonic()
        # Loading and recognising are both inside the lock. Loading because two threads
        # arriving at once would otherwise each build an engine, and recognising because
        # the predictor cannot be re-entered -- see `_ENGINE_LOCK`.
        try:
            with _ENGINE_LOCK:
                raw = self._run(self._load(), path)
        except ProviderUnavailable:
            raise
        except Exception as error:                       # noqa: BLE001
            raise ProviderUnavailable(
                "PaddleOCR failed to read the image: %s" % error) from error
        elapsed = round(time.monotonic() - started, 3)

        lines = self._flatten(raw)
        text = "\n".join(item for item, _score, _box in lines)
        # The page confidence is the mean of the line confidences. Low-confidence lines are
        # KEPT, not dropped: dropping one would leave a reader with text that silently has
        # a hole in it.
        confidence = (round(sum(score for _t, score, _b in lines) / len(lines), 4)
                      if lines else 0.0)
        return {
            "text": text,
            "confidence": confidence,
            "provider": PROVIDER,
            "language": self._language,
            "lineCount": len(lines),
            "processingSeconds": elapsed,
            # ADDITIVE. Every key above means exactly what it meant before, so a caller
            # that only wants the text is unaffected. This one carries each recognised
            # line with its own confidence and its place on the page, which is what
            # `extraction.layout` reconstructs a table from.
            "lines": [{"text": item, "confidence": score, "box": box}
                      for item, score, box in lines],
        }
