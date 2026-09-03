# -*- coding: utf-8 -*-
"""Whisper, running locally. No audio and no transcript leaves this machine.

LOCAL DEVELOPMENT ONLY. No database, no Finance import, no API contract.

    audio -> ffmpeg (16 kHz mono WAV) -> Whisper -> {"text", "language", "provider"}

Two settings that matter more than they look:

**`language="fa"` is pinned rather than detected.** Whisper's detector works from the first
thirty seconds, and a short recording that opens with a number -- "پانصد کیلو" -- is
frequently detected as Arabic or Urdu, which then transcribes the rest in the wrong script.
The recordings this reads are invoice descriptions in Persian; saying so is more accurate
than detecting it.

**`temperature=0`.** Whisper's default sampling introduces randomness, so the same file
transcribes differently on two runs. For a number that may become money, a transcript that
changes when you retry is worse than one that is consistently wrong -- at least the second
can be recognised as wrong.
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

DEFAULT_MODEL = "small"
LANGUAGE = "fa"
PROVIDER = "whisper"

#: Whisper reads 16 kHz mono. `-vn` drops any video stream, which m4a containers can carry.
_FFMPEG_ARGS = ("-vn", "-ac", "1", "-ar", "16000", "-f", "wav")


class ProviderUnavailable(RuntimeError):
    """The model or ffmpeg could not run. Not raised for "the audio was silent"."""


class WhisperProvider:
    """Transcribes one audio file. Nothing else."""

    def __init__(self, model_name=DEFAULT_MODEL, device=None, model=None,
                 ffmpeg=None, language=LANGUAGE):
        self._model_name = model_name
        self._device = device
        self._model = model                # injectable, so a test never loads a model
        self._ffmpeg = ffmpeg              # injectable, so a test never shells out
        self._language = language

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            import whisper
        except ImportError as error:
            raise ProviderUnavailable(
                "openai-whisper is not installed in this environment; install "
                "requirements-ai.txt into ai-extraction-env") from error
        try:
            self._model = whisper.load_model(self._model_name, device=self._device)
        except Exception as error:                        # noqa: BLE001
            raise ProviderUnavailable(
                "Whisper failed to load %s: %s" % (self._model_name, error)) from error
        return self._model

    def _ffmpeg_path(self):
        """The ffmpeg binary, and -- when it was given explicitly -- put it on PATH.

        Whisper does not take an ffmpeg path. Its own loader runs `ffmpeg` by name in a
        subprocess for EVERY input, so knowing where the binary is does not help it: a
        provider handed `--ffmpeg C:\\...\\ffmpeg.exe` still died with
        `[WinError 2] The system cannot find the file specified` thrown from inside the
        model. The directory is prepended to PATH for this process only, which is the one
        thing that actually reaches Whisper's subprocess.
        """
        if self._ffmpeg is not None:
            binary = Path(self._ffmpeg)
            folder = str(binary.parent)
            if binary.is_file() and folder not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
            return str(binary)
        found = shutil.which("ffmpeg")
        if found is None:
            raise ProviderUnavailable(
                "ffmpeg is not on PATH; Whisper cannot decode audio without it. "
                "winget installs it without adding it to PATH -- see samples/README.md")
        return found

    def _to_wav(self, source):
        """A 16 kHz mono WAV, converting only when the input is not already one.

        Returns `(path, is_temporary)`.

        ffmpeg is checked even for a WAV that needs no conversion. Whisper's own loader
        shells out to ffmpeg for EVERY input regardless of format, so skipping the check
        here produced `[WinError 2] The system cannot find the file specified` from inside
        the model -- an error that names nothing and reads like a corrupt recording.
        """
        binary = self._ffmpeg_path()
        if source.suffix.lower() == ".wav":
            return source, False
        target = Path(tempfile.gettempdir()) / ("bambo_voice_%s.wav" % source.stem[:40])
        result = subprocess.run(
            [binary, "-y", "-i", str(source), *_FFMPEG_ARGS, str(target)],
            capture_output=True)
        if result.returncode != 0 or not target.is_file():
            raise ProviderUnavailable(
                "ffmpeg could not convert %s (exit %s)" % (source.name, result.returncode))
        return target, True

    @staticmethod
    def _confidence(raw):
        """A 0..1 figure from Whisper's per-segment log-probabilities.

        Whisper reports no confidence directly. `avg_logprob` is a log probability per
        segment; exponentiating it gives a usable number. It is a rough signal and is
        treated as one -- it decides nothing, it only travels with the text.

        Known limitation, measured: on a pure tone with no speech at all, Whisper produced
        hallucinated repetition and reported 0.91. High confidence here is not evidence.
        """
        segments = raw.get("segments") or []
        scores = [s.get("avg_logprob") for s in segments if s.get("avg_logprob") is not None]
        if not scores:
            return 0.5 if str(raw.get("text") or "").strip() else 0.0
        import math
        return round(min(1.0, max(0.0, math.exp(sum(scores) / len(scores)))), 4)

    def transcribe(self, audio_path):
        """`{"text", "language", "provider"}` for one audio file.

        Silence is NOT an error: it returns empty text. Only a model or ffmpeg that could
        not run raises.
        """
        source = Path(audio_path)
        if not source.is_file():
            raise ProviderUnavailable("audio file is missing: %s" % source.name)

        # BEFORE loading the model: `_ffmpeg_path` is what puts an explicitly-given ffmpeg
        # on PATH, and Whisper's loader needs it there for every format, WAV included.
        self._ffmpeg_path()
        model = self._load()
        converted, temporary = self._to_wav(source)
        started = time.monotonic()
        try:
            raw = model.transcribe(str(converted), language=self._language,
                                   temperature=0, fp16=False)
        except Exception as error:                        # noqa: BLE001
            raise ProviderUnavailable("Whisper failed to transcribe: %s" % error) from error
        finally:
            if temporary:
                try:
                    converted.unlink()
                except OSError:
                    pass

        text = str(raw.get("text") or "").strip()
        return {
            "text": text,
            # What Whisper reports, which is what was pinned unless the model overrode it.
            "language": raw.get("language") or self._language,
            "provider": PROVIDER,
            "confidence": self._confidence(raw),
            "model": self._model_name,
            "processingSeconds": round(time.monotonic() - started, 3),
        }
