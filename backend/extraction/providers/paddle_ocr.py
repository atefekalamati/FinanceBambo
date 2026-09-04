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
import time
from pathlib import Path

#: PaddleOCR's own language code for Persian. `ar` also recognises the script but is trained
#: on Arabic text and misreads the Persian-only letters -- گ چ پ ژ -- which appear in most
#: material names.
DEFAULT_LANGUAGE = "fa"

PROVIDER = "paddleocr"


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
    def _flatten(raw):
        """PaddleOCR's output as `(text, confidence)` pairs, whichever major produced it.

          2.x  `[[[box, (text, score)], ...]]`                  one tuple per line
          3.x  `[{"rec_texts": [...], "rec_scores": [...]}]`    parallel arrays

        Detecting the shape is cheaper than pinning a version and is the only way one
        provider serves an existing 2.x deployment and a fresh 3.x one.
        """
        if not raw:
            return []
        out = []
        for page in raw:
            texts = page.get("rec_texts") if hasattr(page, "get") else None
            if texts is not None:                                  # 3.x
                scores = page.get("rec_scores") or []
                for index, text in enumerate(texts):
                    if text is None:
                        continue
                    out.append((str(text),
                                float(scores[index]) if index < len(scores) else 0.0))
                continue
            for entry in page or []:                               # 2.x
                try:
                    text, score = entry[1]
                except (TypeError, IndexError, ValueError, KeyError):
                    continue
                if text is not None:
                    out.append((str(text), float(score)))
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

        engine = self._load()
        started = time.monotonic()
        try:
            raw = self._run(engine, path)
        except Exception as error:                       # noqa: BLE001
            raise ProviderUnavailable(
                "PaddleOCR failed to read the image: %s" % error) from error
        elapsed = round(time.monotonic() - started, 3)

        lines = self._flatten(raw)
        text = "\n".join(item for item, _ in lines)
        # The page confidence is the mean of the line confidences. Low-confidence lines are
        # KEPT, not dropped: dropping one would leave a reader with text that silently has
        # a hole in it.
        confidence = round(sum(score for _, score in lines) / len(lines), 4) if lines else 0.0
        return {
            "text": text,
            "confidence": confidence,
            "provider": PROVIDER,
            "language": self._language,
            "lineCount": len(lines),
            "processingSeconds": elapsed,
        }
