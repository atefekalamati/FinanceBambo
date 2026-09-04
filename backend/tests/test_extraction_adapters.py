# -*- coding: utf-8 -*-
"""The seam between the AI providers and Finance's extraction ports.

No database, no model, no network. The providers are doubles: what is under test is the
adapter -- the port shape it presents, the file it hands the provider, the contract it
returns, and what it does when the provider fails.

The rule these tests exist to protect: **a number no document contained never reaches a
draft.** An empty transcription produces no fields, not a blank one; a provider that raises
fails the extraction rather than yielding an empty success.
"""

import asyncio
import sys
import threading
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.adapters.ports import InvoiceImageExtractor, InvoiceVoiceExtractor
from app.finance.schemas.extractions import ProviderExtractionResult
from extraction.adapters import (RAW_TEXT_KEY, ImageExtractionAdapter,
                                 VoiceExtractionAdapter, _suffix)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 30
WAV = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 30
MP3 = b"ID3\x03" + b"\x00" * 40
OGG = b"OggS" + b"\x00" * 40
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 30


class FakeOCR:
    """Synchronous, like the real one. Records the path it was given."""

    def __init__(self, result=None, error=None):
        self._result, self._error = result, error
        self.seen_path = None
        self.seen_thread = None

    def read(self, path):
        self.seen_path = Path(path)
        self.seen_thread = threading.current_thread().name
        if self._error is not None:
            raise self._error
        return self._result


class FakeWhisper(FakeOCR):
    def transcribe(self, path):
        return self.read(path)


def run(coroutine):
    return asyncio.run(coroutine)


class PortShapeTests(unittest.TestCase):
    def test_both_adapters_satisfy_the_finance_ports(self):
        """Checked structurally, because the ports are not `@runtime_checkable`.

        `isinstance` against them raises rather than answering, and making them
        runtime-checkable to please a test would change a production contract for the
        test's convenience. What the service actually requires is asserted instead:
        `adapter_name`, and an `extract` that is a coroutine function of (file, hints).

        This is the mismatch the adapter exists for -- `PaddleOCRProvider.read` and
        `WhisperProvider.transcribe` are the wrong names and synchronous besides.
        """
        import inspect
        for adapter, port in ((ImageExtractionAdapter(FakeOCR()), InvoiceImageExtractor),
                              (VoiceExtractionAdapter(FakeWhisper()), InvoiceVoiceExtractor)):
            with self.subTest(port=port.__name__):
                self.assertIsInstance(getattr(adapter, "adapter_name", None), str)
                self.assertTrue(inspect.iscoroutinefunction(adapter.extract))
                parameters = list(inspect.signature(adapter.extract).parameters)
                self.assertEqual(["file", "hints"], parameters)
                # And the port really does name those two methods, so the shape above is
                # the port's requirement rather than one this test invented.
                self.assertIn("extract", dir(port))

    def test_each_adapter_names_itself(self):
        # The service stores this on the draft as the provider of record.
        self.assertEqual("paddleocr-local", ImageExtractionAdapter(FakeOCR()).adapter_name)
        self.assertEqual("whisper-local", VoiceExtractionAdapter(FakeWhisper()).adapter_name)

    def test_the_name_can_be_overridden_without_subclassing(self):
        self.assertEqual("ocr-v2",
                         ImageExtractionAdapter(FakeOCR(), adapter_name="ocr-v2").adapter_name)


class OutputMappingTests(unittest.TestCase):
    def test_ocr_text_becomes_one_field_the_service_accepts(self):
        provider = FakeOCR({"text": "جمع کل ۶۴٬۰۰۰٬۰۰۰ ریال", "confidence": 0.83,
                            "provider": "paddleocr"})
        payload = run(ImageExtractionAdapter(provider).extract(JPEG, {}))

        # Validated by the real schema, not by hand: that is what the service does, and
        # `ApiModel` forbids extra keys, so `text`/`provider` passed through would fail.
        parsed = ProviderExtractionResult.model_validate(payload)
        self.assertEqual(1, len(parsed.fields))
        field = parsed.fields[0]
        self.assertEqual(RAW_TEXT_KEY, field.key)
        self.assertEqual("جمع کل ۶۴٬۰۰۰٬۰۰۰ ریال", field.extracted_value)
        self.assertAlmostEqual(0.83, field.confidence, places=4)
        self.assertFalse(field.edited_by_user, "nothing is edited before a human sees it")

    def test_whisper_text_maps_the_same_way(self):
        provider = FakeWhisper({"text": "پانصد کیلوگرم میلگرد", "confidence": 0.7,
                                "language": "fa", "provider": "whisper"})
        payload = run(VoiceExtractionAdapter(provider).extract(MP3, {}))
        parsed = ProviderExtractionResult.model_validate(payload)
        self.assertEqual([RAW_TEXT_KEY], [f.key for f in parsed.fields])
        self.assertEqual("پانصد کیلوگرم میلگرد", parsed.fields[0].extracted_value)

    def test_the_provider_metadata_is_not_smuggled_into_the_contract(self):
        """`language`, `provider`, `model` and the rest have no place in a draft field.

        They are facts about the run, not about the invoice, and the schema forbids them.
        """
        provider = FakeOCR({"text": "x", "confidence": 0.5, "provider": "paddleocr",
                            "language": "fa", "lineCount": 3, "processingSeconds": 9.1})
        payload = run(ImageExtractionAdapter(provider).extract(JPEG, {}))
        self.assertEqual({"fields"}, set(payload))
        ProviderExtractionResult.model_validate(payload)

    def test_nothing_read_yields_no_field_at_all(self):
        """An empty draft field is an invitation to type a number into it.

        "Read nothing" and "read an empty string" are one fact, and neither is a value.
        """
        for empty in ("", "   ", None):
            with self.subTest(empty=empty):
                payload = run(ImageExtractionAdapter(
                    FakeOCR({"text": empty, "confidence": 0.9})).extract(JPEG, {}))
                self.assertEqual({"fields": []}, payload)
                self.assertEqual([], ProviderExtractionResult.model_validate(payload).fields)

    def test_a_confidence_outside_the_range_is_clamped_not_fatal(self):
        """The column is 0..1. A provider reporting 1.4 should not fail the extraction."""
        for reported, expected in ((1.4, 1.0), (-0.2, 0.0), ("bad", 0.0), (None, 0.0)):
            with self.subTest(reported=reported):
                payload = run(ImageExtractionAdapter(
                    FakeOCR({"text": "x", "confidence": reported})).extract(JPEG, {}))
                parsed = ProviderExtractionResult.model_validate(payload)
                self.assertAlmostEqual(expected, parsed.fields[0].confidence, places=4)

    def test_no_invoice_value_is_ever_invented(self):
        """The adapter must not parse a quantity or a price out of the text.

        Deciding which number is the quantity and which is the total is a judgement, and a
        wrong one is indistinguishable from a right one once it fills a field.
        """
        payload = run(ImageExtractionAdapter(FakeOCR(
            {"text": "مقدار ۵۰۰ کیلوگرم\nجمع کل 425000000 ریال", "confidence": 0.9}
        )).extract(JPEG, {}))
        self.assertEqual([RAW_TEXT_KEY], [f["key"] for f in payload["fields"]])


class FileHandlingTests(unittest.TestCase):
    def test_stored_bytes_reach_the_provider_as_a_real_file(self):
        """`FileStorage.get` returns BYTES; both models want a path on disk."""
        provider = FakeOCR({"text": "x", "confidence": 0.5})
        run(ImageExtractionAdapter(provider).extract(JPEG, {}))
        self.assertIsNotNone(provider.seen_path)
        self.assertEqual(".jpg", provider.seen_path.suffix)

    def test_the_temporary_file_is_removed_afterwards(self):
        provider = FakeOCR({"text": "x", "confidence": 0.5})
        run(ImageExtractionAdapter(provider).extract(JPEG, {}))
        self.assertFalse(provider.seen_path.exists(), "a temporary upload must not survive")

    def test_the_temporary_file_is_removed_even_when_the_provider_raises(self):
        provider = FakeOCR(error=RuntimeError("model exploded"))
        with self.assertRaises(RuntimeError):
            run(ImageExtractionAdapter(provider).extract(JPEG, {}))
        self.assertFalse(provider.seen_path.exists())

    def test_the_suffix_comes_from_the_bytes(self):
        """Both libraries pick a decoder from the extension, so it cannot be `.tmp`."""
        for content, kind, expected in ((JPEG, "image", ".jpg"), (PNG, "image", ".png"),
                                        (WEBP, "image", ".webp"), (MP3, "audio", ".mp3"),
                                        (OGG, "audio", ".ogg"), (WAV, "audio", ".wav"),
                                        (M4A, "audio", ".m4a")):
            with self.subTest(expected=expected):
                self.assertEqual(expected, _suffix(content, kind))

    def test_webp_and_wav_share_a_prefix_and_are_still_told_apart(self):
        # Both begin `RIFF`; only the tag at offset 8 separates them.
        self.assertEqual(".webp", _suffix(WEBP, "image"))
        self.assertEqual(".wav", _suffix(WAV, "audio"))

    def test_an_unrecognised_shape_still_gets_a_usable_extension(self):
        """The upload endpoint already validated these bytes. A second, stricter opinion
        here would refuse a file Finance has already accepted."""
        self.assertEqual(".jpg", _suffix(b"\x00\x01\x02\x03", "image"))
        self.assertEqual(".mp3", _suffix(b"\x00\x01\x02\x03", "audio"))

    def test_a_path_from_storage_is_used_in_place_rather_than_copied(self):
        """Another FileStorage may hand back a path. It should not be rewritten."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            handle.write(JPEG)
        existing = Path(handle.name)
        try:
            provider = FakeOCR({"text": "x", "confidence": 0.5})
            run(ImageExtractionAdapter(provider).extract(str(existing), {}))
            self.assertEqual(existing, provider.seen_path)
            self.assertTrue(existing.exists(), "a file we did not create must survive")
        finally:
            existing.unlink(missing_ok=True)

    def test_something_that_is_neither_bytes_nor_a_path_is_refused(self):
        with self.assertRaises(TypeError):
            run(ImageExtractionAdapter(FakeOCR()).extract(object(), {}))


class FailureTests(unittest.TestCase):
    def test_a_provider_failure_propagates_rather_than_becoming_an_empty_success(self):
        """The service turns any exception into AIExtractionFailed and marks the file
        `failed`. Swallowing it here would produce a draft with no fields that looks like a
        blank invoice instead of a broken run."""
        for error in (RuntimeError("model unavailable"), OSError("disk gone"),
                      ValueError("bad image")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    run(ImageExtractionAdapter(FakeOCR(error=error)).extract(JPEG, {}))

    def test_a_voice_provider_failure_propagates_too(self):
        with self.assertRaises(RuntimeError):
            run(VoiceExtractionAdapter(
                FakeWhisper(error=RuntimeError("ffmpeg missing"))).extract(MP3, {}))


class ThreadingTests(unittest.TestCase):
    async def _extract(self, adapter):
        return await adapter.extract(JPEG, {})

    def test_the_blocking_call_leaves_the_event_loop(self):
        """`asyncio.to_thread`, asserted by where the provider actually ran.

        The model call blocks for seconds to minutes. On the event loop it would stall every
        other request in the process, so the proof is that it executed on another thread.
        """
        provider = FakeOCR({"text": "x", "confidence": 0.5})

        async def main():
            await ImageExtractionAdapter(provider).extract(JPEG, {})
            return threading.current_thread().name

        loop_thread = asyncio.run(main())
        self.assertIsNotNone(provider.seen_thread)
        self.assertNotEqual(loop_thread, provider.seen_thread,
                            "the synchronous model call must not run on the event loop")


if __name__ == "__main__":
    unittest.main()
