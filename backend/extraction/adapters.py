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
#: Structured fields are a later, separate piece of work with its own tests. It belongs
#: after a real Persian invoice has been measured, not before.
RAW_TEXT_KEY = "rawText"

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
    text = str(result.get("text") or "").strip()
    if not text:
        return {"fields": []}
    confidence = result.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    # The column is 0..1 and the schema enforces it. A provider that reported something
    # outside that range is clamped rather than allowed to fail the whole extraction.
    confidence = min(1.0, max(0.0, confidence))
    return {"fields": [{"key": RAW_TEXT_KEY, "extractedValue": text,
                        "confidence": confidence, "editedByUser": False}]}


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
