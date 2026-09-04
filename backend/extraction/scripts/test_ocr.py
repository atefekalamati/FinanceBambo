# -*- coding: utf-8 -*-
r"""Read one invoice image with the local OCR provider and print JSON.

LOCAL DEVELOPMENT ONLY. Touches no database and is on no deployment path. Runs standalone:
its only import from this repository is the provider beside it.

    cd backend
    ai-extraction-env\Scripts\python extraction\scripts\test_ocr.py extraction\samples\invoice.jpg

Exit codes:
    0  text was read
    1  the provider ran but read nothing
    2  the file is missing or is not an image
    3  the provider could not run (package missing, model not downloaded)
"""

import argparse
import json
import sys
from pathlib import Path

# The extraction package's parent, so `extraction.providers...` resolves whatever the
# working directory is.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extraction.providers.paddle_ocr import (PaddleOCRProvider,          # noqa: E402
                                             ProviderUnavailable)

#: Byte signatures, because an extension is a claim and the bytes are not. Kept here rather
#: than imported so this script stays runnable on its own.
SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"RIFF", "webp"),          # RIFF....WEBP; the WEBP tag is checked below
)


def emit(payload, code=0):
    # The Windows console defaults to cp1252, which cannot encode Persian. Without this the
    # script dies on its own output AFTER the model has done the work -- a UnicodeEncodeError
    # that reads like an OCR failure.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    raise SystemExit(code)


def looks_like_an_image(head):
    for signature, kind in SIGNATURES:
        if head.startswith(signature):
            if kind == "webp" and head[8:12] != b"WEBP":
                continue
            return kind
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", type=Path)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--lang", default="fa")
    arguments = parser.parse_args()

    if not arguments.image.is_file():
        emit({"error": "file not found", "path": str(arguments.image),
              "provider": "paddleocr"}, 2)

    kind = looks_like_an_image(arguments.image.read_bytes()[:16])
    if kind is None:
        emit({"error": "not a jpg, png or webp (checked by bytes, not by extension)",
              "provider": "paddleocr"}, 2)

    try:
        result = PaddleOCRProvider(language=arguments.lang,
                                   use_gpu=arguments.gpu).read(arguments.image)
    except ProviderUnavailable as failure:
        emit({"error": str(failure), "provider": "paddleocr"}, 3)

    emit({**result, "detectedFormat": kind, "file": arguments.image.name},
         0 if result["text"].strip() else 1)


if __name__ == "__main__":
    main()
