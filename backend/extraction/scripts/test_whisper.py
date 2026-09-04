# -*- coding: utf-8 -*-
r"""Transcribe one Persian audio file with the local provider and print JSON.

LOCAL DEVELOPMENT ONLY. Touches no database and is on no deployment path. Runs standalone:
its only import from this repository is the provider beside it.

    cd backend
    ai-extraction-env\Scripts\python extraction\scripts\test_whisper.py extraction\samples\voice.mp3

`language="fa"` and `temperature=0` are set by the PROVIDER, not here. A test script that
configured the model differently from the real caller would prove the wrong thing.

Exit codes:
    0  speech was transcribed
    1  the provider ran but transcribed nothing
    2  the file is missing or is not audio
    3  the provider could not run (package missing, ffmpeg missing, model not downloaded)
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extraction.providers.whisper_voice import (ProviderUnavailable,     # noqa: E402
                                                WhisperProvider)

#: Byte signatures. `RIFF....WAVE` and WebP share the RIFF prefix, so the tag is checked.
SIGNATURES = ((b"ID3", "mp3"), (b"\xff\xfb", "mp3"), (b"\xff\xf3", "mp3"),
              (b"OggS", "ogg"), (b"RIFF", "wav"))


def emit(payload, code=0):
    # cp1252 cannot encode Persian; without this the script dies printing its own result.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    raise SystemExit(code)


def looks_like_audio(head):
    for signature, kind in SIGNATURES:
        if head.startswith(signature):
            if kind == "wav" and head[8:12] != b"WAVE":
                continue
            return kind
    if head[4:12] in (b"ftypM4A ", b"ftypmp42") or head[4:8] == b"ftyp":
        return "m4a"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model", default="small",
                        help="tiny is fast but not accurate enough for Persian numerals")
    parser.add_argument("--device", default=None, help="cuda, to use a GPU")
    parser.add_argument("--ffmpeg", default=None,
                        help="path to ffmpeg.exe when it is not on PATH")
    arguments = parser.parse_args()

    if not arguments.audio.is_file():
        emit({"error": "file not found", "path": str(arguments.audio),
              "provider": "whisper"}, 2)

    kind = looks_like_audio(arguments.audio.read_bytes()[:16])
    if kind is None:
        emit({"error": "not an mp3, m4a, wav or ogg (checked by bytes, not by extension)",
              "provider": "whisper"}, 2)

    # Reported before the model loads. A missing ffmpeg is the most common setup failure and
    # otherwise surfaces from inside Whisper's own loader as [WinError 2], which names
    # nothing. Checked for EVERY format, not only the ones needing conversion -- Whisper
    # shells out to ffmpeg even for a WAV, which is how this was found.
    if arguments.ffmpeg is None and shutil.which("ffmpeg") is None:
        emit({"error": "ffmpeg is not on PATH; Whisper needs it for every input format",
              "provider": "whisper",
              "hint": "pass --ffmpeg <path>, or see extraction/samples/README.md"}, 3)

    try:
        result = WhisperProvider(model_name=arguments.model, device=arguments.device,
                                 ffmpeg=arguments.ffmpeg).transcribe(arguments.audio)
    except ProviderUnavailable as failure:
        emit({"error": str(failure), "provider": "whisper"}, 3)

    emit({**result, "detectedFormat": kind, "file": arguments.audio.name},
         0 if result["text"].strip() else 1)


if __name__ == "__main__":
    main()
