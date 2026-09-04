# -*- coding: utf-8 -*-
"""Whisper, running locally. No audio and no transcript leaves the server.

Two details that matter more than they look:

**The language is pinned to Persian rather than detected.** Whisper's detector works from
the first thirty seconds, and a short recording that opens with a number -- "پانصد کیلو" --
is frequently detected as Arabic or Urdu, which then transcribes the rest in the wrong
script. The recordings this reads are invoice descriptions in Persian; saying so is more
accurate than detecting it.

**`temperature=0`.** Whisper's default sampling introduces randomness, so the same file
transcribes differently on two runs. For a number that becomes money, a transcript that
changes when you retry is worse than one that is consistently wrong -- at least the second
can be recognised as wrong.
"""

import asyncio
import shutil
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from .base import ExtractedField, ExtractionResult, ProviderUnavailable
from .parsing import parse_invoice_text

DEFAULT_MODEL = "small"
LANGUAGE = "fa"

#: Whisper reads 16 kHz mono. ffmpeg converts anything else, and m4a/ogg in particular need
#: it -- Whisper's own loader shells out to ffmpeg regardless, so requiring it is not an
#: extra dependency, only an explicit one.
_FFMPEG_ARGS = ("-vn", "-ac", "1", "-ar", "16000", "-f", "wav")


class WhisperProvider:
    """`InvoiceVoiceExtractor` backed by a local Whisper model."""

    adapter_name = "whisper-local"

    def __init__(self, model_name=DEFAULT_MODEL, device=None, model=None,
                 ffmpeg=None, language=LANGUAGE):
        self._model_name = model_name
        self._device = device
        self._model = model                # injectable, so tests never load a model
        self._ffmpeg = ffmpeg              # injectable, so tests never shell out
        self._language = language
        self._lock = asyncio.Lock()

    async def _load(self):
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is not None:
                return self._model
            try:
                import whisper
            except ImportError as error:
                raise ProviderUnavailable(
                    "openai-whisper is not installed in this environment; see "
                    "docs/EXTRACTION_SELF_HOSTED_SETUP_FA.md") from error
            try:
                self._model = await asyncio.to_thread(
                    whisper.load_model, self._model_name, device=self._device)
            except Exception as error:                        # noqa: BLE001
                raise ProviderUnavailable("Whisper failed to load %s: %s"
                                          % (self._model_name, error)) from error
            return self._model

    def _ffmpeg_path(self):
        if self._ffmpeg is not None:
            return self._ffmpeg
        found = shutil.which("ffmpeg")
        if found is None:
            raise ProviderUnavailable(
                "ffmpeg is not on PATH; Whisper cannot decode audio without it")
        return found

    async def _to_wav(self, source: Path) -> tuple[Path, bool]:
        """A 16 kHz mono WAV, converting only when the input is not already one.

        Returns the path and whether it is a temporary file the caller must delete.

        ffmpeg is checked even for a WAV that needs no conversion. Whisper's own loader
        shells out to ffmpeg for every input regardless of format, so skipping the check
        here produced `[WinError 2] The system cannot find the file specified` from inside
        the model -- an error that names nothing and reads like a corrupt recording.
        """
        binary = self._ffmpeg_path()
        if source.suffix.lower() == ".wav":
            return source, False
        target = Path(tempfile.gettempdir()) / ("finance_voice_%s.wav" % source.stem[:40])
        result = await asyncio.to_thread(
            subprocess.run, [binary, "-y", "-i", str(source), *_FFMPEG_ARGS, str(target)],
            capture_output=True)
        if result.returncode != 0 or not target.is_file():
            raise ProviderUnavailable(
                "ffmpeg could not convert %s (exit %s)" % (source.name, result.returncode))
        return target, True

    async def transcribe(self, file_path) -> ExtractionResult:
        source = Path(file_path)
        if not source.is_file():
            raise ProviderUnavailable("audio file is missing: %s" % source.name)
        model = await self._load()
        converted, temporary = await self._to_wav(source)
        started = time.monotonic()
        try:
            raw = await asyncio.to_thread(
                model.transcribe, str(converted), language=self._language,
                temperature=0, fp16=False)
        except Exception as error:                            # noqa: BLE001
            raise ProviderUnavailable("Whisper failed to transcribe: %s" % error) from error
        finally:
            if temporary:
                try:
                    converted.unlink()
                except OSError:
                    pass
        elapsed = Decimal(str(round(time.monotonic() - started, 3)))

        text = str(raw.get("text") or "").strip()
        language = raw.get("language") or self._language
        confidence = self._confidence(raw)
        warnings = []
        if not text:
            warnings.append("هیچ گفتاری در فایل صوتی تشخیص داده نشد.")
        if language != self._language:
            warnings.append("زبان تشخیص‌داده‌شده %s بود، نه فارسی." % language)

        parsed, parse_warnings = parse_invoice_text(text, confidence)
        return ExtractionResult(
            raw_text=text,
            fields=tuple(ExtractedField(key, value, at) for key, value, at in parsed),
            confidence=confidence,
            provider_name=self.adapter_name,
            language=language,
            processing_seconds=elapsed,
            warnings=tuple(warnings) + parse_warnings)

    @staticmethod
    def _confidence(raw) -> Decimal:
        """A confidence from Whisper's per-segment log-probabilities.

        Whisper reports no confidence directly. `avg_logprob` is a log probability per
        segment; exponentiating it gives a usable 0..1 figure. It is a rough signal and is
        treated as one -- it decides nothing here, it only travels with the text so a
        reviewer knows whether to look closely.
        """
        segments = raw.get("segments") or []
        scores = [segment.get("avg_logprob") for segment in segments
                  if segment.get("avg_logprob") is not None]
        if not scores:
            return Decimal("0.5") if str(raw.get("text") or "").strip() else Decimal(0)
        import math
        average = sum(scores) / len(scores)
        return Decimal(str(round(min(1.0, max(0.0, math.exp(average))), 4)))

    async def extract(self, file, hints=None) -> dict:
        """The `InvoiceVoiceExtractor` port. `file` carries a filesystem path."""
        path = getattr(file, "path", None) or getattr(file, "local_path", None) or file
        return (await self.transcribe(path)).as_contract()
