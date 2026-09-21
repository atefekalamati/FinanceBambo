# -*- coding: utf-8 -*-
"""The provider path the running host actually takes, pinned.

WHY THIS FILE EXISTS

There are two PaddleOCR providers in this repository and two Whisper providers:

    extraction/paddle_ocr.py            extraction/providers/paddle_ocr.py
    extraction/whisper_voice.py         extraction/providers/whisper_voice.py

`tests/test_extraction_providers.py` imports the LEFT pair. `ImageExtractionAdapter` and
`VoiceExtractionAdapter` -- the objects `devhost.app.extraction_providers()` hands to
`FinanceExtractionService` -- import the RIGHT pair. The two have diverged: the left ones
return an `ExtractionResult` of `ExtractedField`s, the right ones return a plain
`{"text", "confidence", "provider"}` dict. So a green provider suite said nothing about the
code a real upload runs through.

This file tests the right-hand pair and the adapter that loads it, and it fails if the
production wiring ever moves to a different module. No model is loaded anywhere here: the
providers take an injectable engine, and the adapters take an injectable provider.
"""

import asyncio
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction.adapters import (RAW_TEXT_KEY, ImageExtractionAdapter,
                                 VoiceExtractionAdapter)


class WiringTests(unittest.TestCase):
    """Which module the host would import, asserted by importing it the same way."""

    def test_the_image_adapter_loads_the_providers_package_not_the_legacy_module(self):
        adapter = ImageExtractionAdapter()
        provider = adapter._load()
        self.assertEqual("extraction.providers.paddle_ocr", type(provider).__module__,
                         "production loads extraction/providers/paddle_ocr.py; a test that "
                         "exercises extraction/paddle_ocr.py proves nothing about it")
        self.assertEqual("paddleocr-local", adapter.adapter_name)

    def test_the_voice_adapter_loads_the_providers_package_not_the_legacy_module(self):
        adapter = VoiceExtractionAdapter()
        provider = adapter._load()
        self.assertEqual("extraction.providers.whisper_voice", type(provider).__module__)
        self.assertEqual("whisper-local", adapter.adapter_name)

    def test_the_host_hands_the_service_these_two_adapters(self):
        """`extraction_providers()` under EXTRACTION_PROVIDER=self_hosted.

        Asserted by type rather than by reading the source, so moving the construction
        somewhere else does not quietly stop this from being checked.
        """
        import os

        from devhost import app as host

        previous = os.environ.get("EXTRACTION_PROVIDER")
        os.environ["EXTRACTION_PROVIDER"] = "self_hosted"
        try:
            image, voice = host.extraction_providers()
        finally:
            if previous is None:
                os.environ.pop("EXTRACTION_PROVIDER", None)
            else:
                os.environ["EXTRACTION_PROVIDER"] = previous
        self.assertIsInstance(image, ImageExtractionAdapter)
        self.assertIsInstance(voice, VoiceExtractionAdapter)


class _Recogniser:
    """Stands in for the model. The adapter's contract is what is under test, not paddle."""

    def __init__(self, text, confidence=0.9):
        self._text, self._confidence = text, confidence
        self.paths = []

    def read(self, path):
        self.paths.append(path)
        return {"text": self._text, "confidence": self._confidence,
                "provider": "paddleocr"}

    def transcribe(self, path):
        self.paths.append(path)
        return {"text": self._text, "confidence": self._confidence, "provider": "whisper"}


INVOICE = "\n".join([
    "فاکتور فروش",
    "شماره صورتحساب: 8842",
    "تاریخ صدور: 1404/06/22",
    "فروشنده: شرکت نمونه",
    "مشتری: پروژه مسکونی آفتاب",
    "مبلغ قابل پرداخت: 5,280,000 ریال",
])


class ProductionContractTests(unittest.TestCase):
    """One upload, end to end through the real adapter, with the model stubbed out."""

    def _fields(self, adapter):
        answer = asyncio.run(adapter.extract(INVOICE.encode("utf-8")))
        return {field["key"]: field for field in answer["fields"]}

    def test_the_adapter_delivers_raw_text_and_the_parser_candidates_beside_it(self):
        fields = self._fields(ImageExtractionAdapter(provider=_Recogniser(INVOICE)))
        self.assertIn(RAW_TEXT_KEY, fields, "the reviewer must always see what was read")
        self.assertEqual(INVOICE, fields[RAW_TEXT_KEY]["extractedValue"])
        self.assertEqual("8842", fields["invoiceNumber"]["extractedValue"])
        self.assertEqual("1404/06/22", fields["invoiceDate"]["extractedValue"])
        self.assertEqual("شرکت نمونه", fields["supplierName"]["extractedValue"])
        self.assertEqual("5280000", fields["totalAmount"]["extractedValue"])

    def test_a_field_the_text_does_not_state_is_absent_rather_than_blank(self):
        """A blank field in a review form invites somebody to type a number into it."""
        fields = self._fields(ImageExtractionAdapter(provider=_Recogniser("سلام")))
        for key in ("invoiceNumber", "totalAmount", "supplierName", "taxAmount"):
            self.assertNotIn(key, fields)

    def test_empty_ocr_output_still_creates_reviewable_evidence(self):
        fields = self._fields(ImageExtractionAdapter(provider=_Recogniser("   ")))
        self.assertEqual("   ", fields[RAW_TEXT_KEY]["extractedValue"])
        self.assertIn("ocrWarnings", fields)

    def test_every_confidence_the_adapter_emits_is_inside_the_column_it_is_stored_in(self):
        """The schema enforces 0..1; a provider outside it must be clamped, not fatal."""
        fields = self._fields(
            ImageExtractionAdapter(provider=_Recogniser(INVOICE, confidence=4.2)))
        for key, field in fields.items():
            self.assertGreaterEqual(field["confidence"], 0.0, key)
            self.assertLessEqual(field["confidence"], 1.0, key)

    def test_the_voice_adapter_runs_the_same_parser_over_a_transcript(self):
        fields = self._fields(VoiceExtractionAdapter(provider=_Recogniser(INVOICE)))
        self.assertEqual("8842", fields["invoiceNumber"]["extractedValue"])
        self.assertEqual(INVOICE, fields[RAW_TEXT_KEY]["extractedValue"])

    def test_disabled_ai_never_constructs_a_provider(self):
        with patch.dict(os.environ, {"FINANCE_AI_EXTRACTION_ENABLED": "false",
                                  "AVALAI_API_KEY": "legacy-key"}):
            with patch("extraction.providers.avalai.AvalAIProvider") as provider:
                fields = self._fields(ImageExtractionAdapter(provider=_Recogniser(INVOICE)))
        provider.assert_not_called()
        self.assertNotIn("aiWarnings", fields)

    def test_enabled_ai_without_key_keeps_rule_fields_and_names_unavailability(self):
        with patch.dict(os.environ, {"FINANCE_AI_EXTRACTION_ENABLED": "true",
                                  "FINANCE_AI_API_KEY": ""}):
            fields = self._fields(ImageExtractionAdapter(provider=_Recogniser(INVOICE)))
        self.assertEqual(INVOICE, fields[RAW_TEXT_KEY]["extractedValue"])
        self.assertEqual("8842", fields["invoiceNumber"]["extractedValue"])
        self.assertIn("provider unavailable", fields["aiWarnings"]["extractedValue"][0])

    def test_enabled_ai_uses_configured_key_and_preserves_unknown_fields(self):
        with patch.dict(os.environ, {"FINANCE_AI_EXTRACTION_ENABLED": "true",
                                  "FINANCE_AI_PROVIDER": "avalai",
                                  "FINANCE_AI_API_KEY": "test-key",
                                  "FINANCE_AI_MODEL": "test-model"}):
            with patch("extraction.providers.avalai.AvalAIProvider") as provider:
                provider.return_value.extract.return_value = {
                    "supplierName": ("wrong supplier", 0.99),
                    "customInvoiceField": ("source evidence", 0.8)}
                fields = self._fields(ImageExtractionAdapter(provider=_Recogniser(INVOICE)))
        provider.assert_called_once_with(key="test-key", model="test-model")
        self.assertEqual("شرکت نمونه", fields["supplierName"]["extractedValue"])
        self.assertEqual("source evidence", fields["customInvoiceField"]["extractedValue"])


class DeterministicPrecedenceTests(unittest.TestCase):
    """The rule the whole design rests on: a model may fill a gap, never overwrite."""

    def test_the_model_is_never_asked_for_a_field_the_parser_read(self):
        import extraction.adapters as adapters

        asked = {}

        def _spy(text, already_emitted, transcript=None, metadata=None):
            asked["already_emitted"] = set(already_emitted)
            # What a model would answer if it were allowed to contradict the document.
            return [{"key": "supplierName", "extractedValue": "شرکت دیگری",
                     "confidence": 0.99, "editedByUser": False},
                    # A field this text genuinely does not state, so it is the model's to
                    # offer. `buyerName` would NOT do here: the parser reads it from
                    # «مشتری», which is the point of the first assertion, not the second.
                    {"key": "taxAmount", "extractedValue": "480000",
                     "confidence": 0.7, "editedByUser": False}]

        original = adapters._ai_fields
        adapters._ai_fields = _spy
        try:
            fields = {f["key"]: f for f in asyncio.run(
                ImageExtractionAdapter(provider=_Recogniser(INVOICE)).extract(b"x"))["fields"]}
        finally:
            adapters._ai_fields = original

        self.assertIn("supplierName", asked["already_emitted"],
                      "the parser found it, so the model must be told it is taken")
        # And the value that survives is the parser's, even though this spy deliberately
        # ignored `already_emitted` the way a misbehaving provider would. `_first_wins`
        # is what makes that structural rather than a courtesy of the AI function.
        self.assertEqual("شرکت نمونه", fields["supplierName"]["extractedValue"],
                         "a rule that can be read beats a model that cannot")
        self.assertEqual("480000", fields["taxAmount"]["extractedValue"],
                         "but a field the parser could not read is the model's to offer")
        self.assertNotIn("taxAmount", asked["already_emitted"],
                         "and it was offered precisely because nothing had claimed it")


if __name__ == "__main__":
    unittest.main()
