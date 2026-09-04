# -*- coding: utf-8 -*-
"""The self-hosted extraction providers, without loading a model.

PaddleOCR and Whisper are injected. That is not a convenience: a test that downloaded a
model would take minutes, need a network, and pass or fail for reasons unrelated to this
code. What is under test is everything around the model -- validation, Persian parsing,
confidence, failure handling, and the rule that nothing is ever invented.

The rule these tests exist to protect: a value the document does not contain never appears
in the output. An invoice with a quantity and a total but no unit price yields a quantity and
a total, and a warning. It does not yield a division.
"""

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction.base import ExtractedField, ExtractionResult, ProviderUnavailable
from extraction.paddle_ocr import PaddleOCRProvider
from extraction.parsing import find_unit, normalize, parse_invoice_text, to_decimal
from extraction.validation import (MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, UnsupportedUpload,
                                   validate_upload)
from extraction.whisper_voice import WhisperProvider

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 40
WAV = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 40
MP3 = b"ID3\x03" + b"\x00" * 60
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 40
OGG = b"OggS" + b"\x00" * 60
EXE = b"MZ\x90\x00" + b"\x00" * 60


class UploadValidationTests(unittest.TestCase):
    def test_each_supported_format_is_accepted(self):
        for head, name, kind in ((JPEG, "a.jpg", "image"), (PNG, "a.png", "image"),
                                 (WEBP, "a.webp", "image"), (MP3, "a.mp3", "audio"),
                                 (M4A, "a.m4a", "audio"), (WAV, "a.wav", "audio"),
                                 (OGG, "a.ogg", "audio")):
            with self.subTest(name):
                self.assertEqual(kind, validate_upload(name, None, 1024, head)[0])

    def test_an_executable_renamed_to_jpg_is_refused(self):
        # The declared type and the extension are both supplied by the uploader. The bytes
        # are not.
        with self.assertRaises(UnsupportedUpload) as caught:
            validate_upload("invoice.jpg", "image/jpeg", 1024, EXE)
        self.assertIn("اجرایی", str(caught.exception))

    def test_an_unrecognised_format_is_refused(self):
        with self.assertRaises(UnsupportedUpload):
            validate_upload("invoice.pdf", "application/pdf", 1024, b"%PDF-1.7\n")

    def test_an_oversized_image_is_refused_with_the_limit_named(self):
        with self.assertRaises(UnsupportedUpload) as caught:
            validate_upload("a.jpg", "image/jpeg", MAX_IMAGE_BYTES + 1, JPEG)
        self.assertIn("10", str(caught.exception))

    def test_an_oversized_audio_file_is_refused(self):
        with self.assertRaises(UnsupportedUpload) as caught:
            validate_upload("a.mp3", "audio/mpeg", MAX_AUDIO_BYTES + 1, MP3)
        self.assertIn("25", str(caught.exception))

    def test_the_audio_limit_is_larger_than_the_image_limit(self):
        self.assertEqual(1024, validate_upload("a.mp3", None, MAX_IMAGE_BYTES + 1, MP3)
                         and 1024)

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(UnsupportedUpload):
            validate_upload("a.jpg", "image/jpeg", 0, JPEG)

    def test_webp_and_wav_share_a_prefix_and_are_still_told_apart(self):
        self.assertEqual("image", validate_upload("a.webp", None, 10, WEBP)[0])
        self.assertEqual("audio", validate_upload("a.wav", None, 10, WAV)[0])


class PersianParsingTests(unittest.TestCase):
    def test_persian_and_arabic_digits_both_become_numbers(self):
        self.assertEqual(Decimal("500"), to_decimal("۵۰۰"))
        self.assertEqual(Decimal("500"), to_decimal("٥٠٠"))
        self.assertEqual(Decimal("1250000"), to_decimal("1,250,000"))
        self.assertEqual(Decimal("1250000"), to_decimal("۱٬۲۵۰٬۰۰۰"))

    def test_arabic_letter_forms_are_folded(self):
        self.assertEqual(normalize("كيلوگرم"), normalize("کیلوگرم"))

    def test_the_longest_unit_wins(self):
        # "متر" is a prefix of "مترمکعب". Matching the short one would report cubic metres
        # of concrete as linear metres.
        self.assertEqual("m3", find_unit("۲۰ مترمکعب بتن")[0])
        self.assertEqual("m2", find_unit("۱۵ مترمربع قالب")[0])
        self.assertEqual("m", find_unit("۱۰ متر لوله")[0])

    def test_a_quantity_with_its_unit_is_read(self):
        fields, _ = parse_invoice_text("خرید ۵۰۰ کیلوگرم میلگرد ۱۴", Decimal("0.9"))
        values = {key: value for key, value, _ in fields}
        self.assertEqual("500", values["quantity"])
        self.assertEqual("kg", values["unit"])

    def test_a_unit_price_is_read_when_the_document_names_it(self):
        fields, _ = parse_invoice_text("قیمت واحد 850000 ریال", Decimal("0.9"))
        values = {key: value for key, value, _ in fields}
        self.assertEqual("850000", values["unitPrice"])
        self.assertEqual("IRR", values["currency"])

    def test_a_missing_unit_price_is_never_divided_out(self):
        # The document has a quantity and a total. Dividing would produce a number nobody
        # wrote, and the reviewer could not tell it from one that was read.
        fields, warnings = parse_invoice_text(
            "مقدار ۵۰۰ کیلوگرم\nجمع کل 425000000 ریال", Decimal("0.9"))
        values = {key: value for key, value, _ in fields}
        self.assertIn("quantity", values)
        self.assertIn("totalAmount", values)
        self.assertNotIn("unitPrice", values)
        self.assertTrue(any("قیمت واحد" in w for w in warnings))

    def test_a_currency_is_reported_as_written_and_never_converted(self):
        rial, _ = parse_invoice_text("جمع کل 8500000 ریال", Decimal("0.9"))
        toman, _ = parse_invoice_text("جمع کل 850000 تومان", Decimal("0.9"))
        self.assertEqual("IRR", dict((k, v) for k, v, _ in rial)["currency"])
        self.assertEqual("IRT", dict((k, v) for k, v, _ in toman)["currency"])
        # The amounts differ by a factor of ten and are reported exactly as read.
        self.assertEqual("8500000", dict((k, v) for k, v, _ in rial)["totalAmount"])
        self.assertEqual("850000", dict((k, v) for k, v, _ in toman)["totalAmount"])

    def test_two_conflicting_totals_lower_the_confidence_rather_than_picking_one(self):
        fields, warnings = parse_invoice_text(
            "جمع کل 1000000\nمبلغ کل 2000000", Decimal("0.9"))
        confidence = {key: at for key, _, at in fields}["totalAmount"]
        self.assertLess(confidence, Decimal("0.9"))
        self.assertTrue(any("قطعی نیست" in w for w in warnings))

    def test_a_jalali_date_is_read(self):
        fields, _ = parse_invoice_text("تاریخ 1405/06/12", Decimal("0.9"))
        self.assertEqual("1405-06-12", dict((k, v) for k, v, _ in fields)["invoiceDate"])

    def test_text_with_nothing_financial_yields_no_fields_and_says_so(self):
        fields, warnings = parse_invoice_text("سلام حال شما چطور است", Decimal("0.9"))
        self.assertEqual((), fields)
        self.assertTrue(any("پیدا نشد" in w for w in warnings))

    def test_a_quantity_with_no_unit_is_flagged(self):
        _, warnings = parse_invoice_text("تعداد ۲۵", Decimal("0.9"))
        self.assertTrue(any("واحد" in w for w in warnings))


class ResultContractTests(unittest.TestCase):
    def test_the_contract_shape_is_what_the_finance_schema_accepts(self):
        from app.finance.schemas.extractions import ProviderExtractionResult
        result = ExtractionResult(
            raw_text="خرید ۵۰۰ کیلوگرم میلگرد",
            fields=(ExtractedField("quantity", "500", Decimal("0.9")),
                    ExtractedField("unit", "kg", Decimal("0.9"))),
            confidence=Decimal("0.91"), provider_name="paddleocr-local",
            language="fa", processing_seconds=Decimal("1.2"))
        parsed = ProviderExtractionResult.model_validate(result.as_contract())
        keys = {field.key for field in parsed.fields}
        self.assertIn("quantity", keys)
        self.assertIn("_rawText", keys)
        self.assertIn("_provider", keys)
        self.assertIn("_processingSeconds", keys)

    def test_provider_metadata_cannot_collide_with_a_parsed_field(self):
        # A document containing the word "confidence" must not overwrite the provider's own.
        result = ExtractionResult(raw_text="x",
                                  fields=(ExtractedField("confidence", "9", Decimal("0.5")),),
                                  confidence=Decimal("0.5"))
        keys = [entry["key"] for entry in result.as_contract()["fields"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("confidence", keys)
        self.assertIn("_rawText", keys)

    def test_a_confidence_outside_zero_to_one_is_refused(self):
        for bad in (Decimal("-0.1"), Decimal("1.5")):
            with self.assertRaises(ValueError):
                ExtractedField("quantity", "1", bad)

    def test_a_blank_key_is_refused(self):
        with self.assertRaises(ValueError):
            ExtractedField("   ", "1", Decimal("0.5"))


class FakeOCR:
    """Stands in for a loaded PaddleOCR engine."""

    def __init__(self, lines=None, fail=False):
        self.lines, self.fail = lines or [], fail

    def ocr(self, path, cls=True):
        if self.fail:
            raise RuntimeError("model exploded")
        return [[[None, (text, score)] for text, score in self.lines]]


class PaddleOCRProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.image = Path(BACKEND_ROOT) / "build" / "extraction_test.jpg"
        self.image.parent.mkdir(parents=True, exist_ok=True)
        self.image.write_bytes(JPEG)

    def tearDown(self):
        self.image.unlink(missing_ok=True)

    async def test_a_persian_invoice_image_yields_fields_and_raw_text(self):
        engine = FakeOCR([("فاکتور خرید بتن", 0.95),
                          ("مقدار ۲۰ مترمکعب", 0.92),
                          ("قیمت واحد 3200000 ریال", 0.88)])
        result = await PaddleOCRProvider(engine=engine).extract_text(self.image)
        values = {item.key: item.value for item in result.fields}
        self.assertEqual("20", values["quantity"])
        self.assertEqual("m3", values["unit"])
        self.assertEqual("3200000", values["unitPrice"])
        self.assertIn("مترمکعب", result.raw_text)
        self.assertGreater(result.confidence, Decimal("0.8"))
        self.assertEqual("paddleocr-local", result.provider_name)

    async def test_a_low_confidence_line_is_kept_and_flagged_not_dropped(self):
        engine = FakeOCR([("مقدار ۲۰ مترمکعب", 0.10)])
        result = await PaddleOCRProvider(engine=engine).extract_text(self.image)
        self.assertIn("مترمکعب", result.raw_text)
        self.assertTrue(any("اطمینان پایین" in w for w in result.warnings))

    async def test_an_image_with_no_text_completes_with_a_warning(self):
        result = await PaddleOCRProvider(engine=FakeOCR([])).extract_text(self.image)
        self.assertEqual("", result.raw_text)
        self.assertEqual(Decimal(0), result.confidence)
        self.assertTrue(any("تشخیص داده نشد" in w for w in result.warnings))

    async def test_a_model_failure_is_reported_as_unavailable_not_as_empty(self):
        with self.assertRaises(ProviderUnavailable):
            await PaddleOCRProvider(engine=FakeOCR(fail=True)).extract_text(self.image)

    async def test_a_missing_file_is_reported_before_the_model_is_touched(self):
        with self.assertRaises(ProviderUnavailable):
            await PaddleOCRProvider(engine=FakeOCR()).extract_text(
                self.image.parent / "absent.jpg")

    async def test_the_port_method_returns_the_finance_contract(self):
        from app.finance.schemas.extractions import ProviderExtractionResult
        engine = FakeOCR([("مقدار ۲۰ مترمکعب", 0.9)])
        raw = await PaddleOCRProvider(engine=engine).extract(str(self.image), {})
        ProviderExtractionResult.model_validate(raw)


#: A stand-in ffmpeg path. Whisper shells out to ffmpeg for every input format, WAV
#: included, so a provider with no ffmpeg refuses before the model is reached. That is
#: correct behaviour and has its own test; these doubles supply a path so the rest can run.
FFMPEG = "ffmpeg"


class FakeWhisper:
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail = payload, fail

    def transcribe(self, path, **kwargs):
        if self.fail:
            raise RuntimeError("model exploded")
        return self.payload


class WhisperProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.audio = Path(BACKEND_ROOT) / "build" / "extraction_test.wav"
        self.audio.parent.mkdir(parents=True, exist_ok=True)
        self.audio.write_bytes(WAV)

    def tearDown(self):
        self.audio.unlink(missing_ok=True)

    async def test_persian_speech_yields_fields_and_a_transcript(self):
        model = FakeWhisper({"text": "خرید پانصد کیلوگرم میلگرد ۱۴", "language": "fa",
                             "segments": [{"avg_logprob": -0.2}]})
        result = await WhisperProvider(model=model, ffmpeg=FFMPEG).transcribe(self.audio)
        self.assertIn("میلگرد", result.raw_text)
        self.assertEqual("fa", result.language)
        self.assertEqual("whisper-local", result.provider_name)
        self.assertGreater(result.confidence, Decimal("0.5"))

    async def test_a_spoken_quantity_in_digits_is_read(self):
        model = FakeWhisper({"text": "مقدار ۲۰ مترمکعب بتن", "language": "fa",
                             "segments": [{"avg_logprob": -0.1}]})
        result = await WhisperProvider(model=model, ffmpeg=FFMPEG).transcribe(self.audio)
        values = {item.key: item.value for item in result.fields}
        self.assertEqual("20", values["quantity"])
        self.assertEqual("m3", values["unit"])

    async def test_silence_completes_with_a_warning_rather_than_failing(self):
        model = FakeWhisper({"text": "  ", "language": "fa", "segments": []})
        result = await WhisperProvider(model=model, ffmpeg=FFMPEG).transcribe(self.audio)
        self.assertEqual("", result.raw_text)
        self.assertEqual(Decimal(0), result.confidence)
        self.assertTrue(any("تشخیص داده نشد" in w for w in result.warnings))

    async def test_a_non_persian_transcript_is_flagged(self):
        model = FakeWhisper({"text": "hello there", "language": "en",
                             "segments": [{"avg_logprob": -0.3}]})
        result = await WhisperProvider(model=model, ffmpeg=FFMPEG).transcribe(self.audio)
        self.assertTrue(any("فارسی" in w for w in result.warnings))

    async def test_a_transcription_failure_is_reported_as_unavailable(self):
        with self.assertRaises(ProviderUnavailable):
            await WhisperProvider(model=FakeWhisper(fail=True), ffmpeg=FFMPEG).transcribe(self.audio)

    async def test_a_missing_audio_file_is_reported(self):
        with self.assertRaises(ProviderUnavailable):
            await WhisperProvider(model=FakeWhisper({}), ffmpeg=FFMPEG).transcribe(
                self.audio.parent / "absent.wav")

    async def test_missing_ffmpeg_is_reported_rather_than_crashing(self):
        m4a = self.audio.parent / "extraction_test.m4a"
        m4a.write_bytes(M4A)
        try:
            provider = WhisperProvider(model=FakeWhisper({}), ffmpeg=None)
            provider._ffmpeg_path = lambda: (_ for _ in ()).throw(
                ProviderUnavailable("ffmpeg is not on PATH"))
            with self.assertRaises(ProviderUnavailable):
                await provider.transcribe(m4a)
        finally:
            m4a.unlink(missing_ok=True)

    async def test_no_quantity_is_invented_from_an_unclear_transcript(self):
        model = FakeWhisper({"text": "یه مقدار میلگرد خریدیم", "language": "fa",
                             "segments": [{"avg_logprob": -0.9}]})
        result = await WhisperProvider(model=model, ffmpeg=FFMPEG).transcribe(self.audio)
        values = {item.key: item.value for item in result.fields}
        self.assertNotIn("quantity", values)
        self.assertNotIn("unitPrice", values)

    async def test_the_port_method_returns_the_finance_contract(self):
        from app.finance.schemas.extractions import ProviderExtractionResult
        model = FakeWhisper({"text": "خرید ۵۰۰ کیلوگرم میلگرد", "language": "fa",
                             "segments": [{"avg_logprob": -0.2}]})
        raw = await WhisperProvider(model=model, ffmpeg=FFMPEG).extract(str(self.audio), {})
        ProviderExtractionResult.model_validate(raw)


class BoundaryTests(unittest.TestCase):
    def test_the_deployable_finance_module_never_imports_the_providers(self):
        # The whole reason this package sits beside app/finance rather than inside it.
        import subprocess
        offenders = subprocess.run(
            [sys.executable, "-c",
             "import pathlib,re,sys;"
             "bad=[str(p) for p in pathlib.Path('app').rglob('*.py')"
             " if re.search(r'^\\s*(from|import)\\s+(extraction|paddleocr|whisper)\\b',"
             "               p.read_text(encoding='utf-8'), re.M)];"
             "print('\\n'.join(bad))"],
            cwd=BACKEND_ROOT, capture_output=True, text=True)
        self.assertEqual("", offenders.stdout.strip(),
                         "app/finance must not import an extraction implementation")

    def test_neither_provider_reaches_the_network(self):
        """No provider may import a network client.

        Matched on import statements, not on substrings: `openai-whisper` is the PyPI name of
        the *local* Whisper package and appears in an installation hint, which a substring
        search flagged as an OpenAI API call. A test that cannot tell those apart would
        eventually be silenced rather than believed.
        """
        import ast
        for module in ("extraction/paddle_ocr.py", "extraction/whisper_voice.py",
                       "extraction/parsing.py", "extraction/base.py",
                       "extraction/validation.py"):
            tree = ast.parse((BACKEND_ROOT / module).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            for forbidden in ("requests", "httpx", "urllib", "aiohttp", "socket",
                              "openai", "boto3", "http"):
                with self.subTest(module=module, package=forbidden):
                    self.assertNotIn(forbidden, imported,
                                     "%s must stay self-hosted" % module)


if __name__ == "__main__":
    unittest.main()
