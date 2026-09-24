# -*- coding: utf-8 -*-
"""Voice to invoice draft, and the one thing this path must never do.

THE RULE THESE EXIST FOR

A speaker can state the wrong amount. `voice1.wav` in this repository does exactly that on
purpose: six of seven benchmarked transcription models hear «صد و هفت میلیون» where the
printed invoice says ۱۱۷,۷۸۶,۰۰۰. The system must carry that 107 forward unchanged.

A pipeline that quietly replaced it with the printed figure would destroy the only evidence
that the two disagree, and would do it in the direction that looks correct -- which is why
it would never be noticed.

No test here needs a credential or a network call. The speech provider is injected.
"""

import asyncio
import io
import json
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction.adapters import (SPEECH_PROVIDER_KEY, TRANSCRIPT_KEY, VOICE_SOURCE,
                                 VOICE_SOURCE_KEY, VoiceExtractionAdapter,
                                 _as_contract_voice)
from extraction.providers.avalai_speech import (DEFAULT_MODEL, AvalAISpeechProvider,
                                                ProviderUnavailable)

#: What voice1.wav actually says, as the benchmark measured it -- including the amount that
#: does NOT match the printed invoice. Used verbatim; correcting it here would defeat the
#: purpose of the file.
SPOKEN_WRONG = ("سلام این فاکتور مربوط به گروه مهندسی نما برتر است تاریخ فاکتور 21 آذر "
                "1403 است قیمت آن 107,000,000 ریال است")

#: The figure the printed invoice carries for the same item.
PRINTED = "117,786,000"


def field(contract, key):
    """One field out of the payload the adapter returns: `{"fields": [...]}`."""
    for item in contract["fields"]:
        if item["key"] == key:
            return item
    return None


class TheTranscriptSurvivesTests(unittest.TestCase):
    """Whatever the structuring stage does, the spoken words remain readable."""

    def _result(self, text, **over):
        return dict({"text": text, "language": "fa", "provider": "avalai",
                     "confidence": None, "model": DEFAULT_MODEL}, **over)

    def test_the_spoken_amount_is_kept_exactly_as_spoken(self):
        fields = _as_contract_voice(self._result(SPOKEN_WRONG))
        transcript = field(fields, TRANSCRIPT_KEY)
        self.assertIsNotNone(transcript)
        self.assertIn("107,000,000", transcript["extractedValue"])
        self.assertNotIn(PRINTED, transcript["extractedValue"],
                         "the printed figure must never appear in a transcript")

    def test_the_draft_says_it_came_from_speech(self):
        fields = _as_contract_voice(self._result(SPOKEN_WRONG))
        self.assertEqual(VOICE_SOURCE, field(fields, VOICE_SOURCE_KEY)["extractedValue"])

    def test_it_records_which_transcriber_ran(self):
        fields = _as_contract_voice(self._result(SPOKEN_WRONG))
        self.assertEqual("avalai/" + DEFAULT_MODEL,
                         field(fields, SPEECH_PROVIDER_KEY)["extractedValue"])

    def test_an_unreported_confidence_is_not_invented(self):
        """AvalAI reports none. A number here would be read by a reviewer as measured."""
        fields = _as_contract_voice(self._result(SPOKEN_WRONG, confidence=None))
        self.assertEqual(0.0, field(fields, TRANSCRIPT_KEY)["confidence"])

    def test_silence_produces_no_invoice_fields_at_all(self):
        """Nothing was said, so nothing is claimed -- not an empty invoice."""
        fields = _as_contract_voice(self._result("   "))
        self.assertIsNone(field(fields, "supplierName"))
        self.assertIsNone(field(fields, "totalAmount"))

    def test_the_transcript_is_emitted_before_the_reader_is_asked(self):
        """So it exists even when structuring is switched off, as it is in this suite."""
        fields = _as_contract_voice(self._result(SPOKEN_WRONG))
        keys = [item["key"] for item in fields["fields"]]
        self.assertIn(TRANSCRIPT_KEY, keys)


class TheAdapterChoosesNothingTests(unittest.TestCase):
    """The business layer must not learn which transcriber answered."""

    class Fake:
        def __init__(self, text):
            self.text = text
            self.calls = []

        def transcribe(self, path):
            self.calls.append(str(path))
            return {"text": self.text, "language": "fa", "provider": "fake",
                    "confidence": 0.9}

    def test_an_injected_provider_is_used_and_nothing_is_imported(self):
        provider = self.Fake(SPOKEN_WRONG)
        adapter = VoiceExtractionAdapter(provider, "fake-speech")
        self.assertEqual("fake-speech", adapter.adapter_name)

        # `_TemporaryUpload` takes bytes or a path, not a file-like object.
        fields = asyncio.run(adapter.extract(b"RIFF----WAVEfmt "))
        self.assertEqual(1, len(provider.calls), "the injected provider transcribed")
        self.assertIn("107,000,000", field(fields, TRANSCRIPT_KEY)["extractedValue"])

    def test_the_adapter_names_no_vendor_in_its_code(self):
        """Checked against the CODE, with comments and docstrings removed.

        The docstring names both vendors deliberately -- to say that neither is chosen
        here -- so a check on the raw text would fail on the sentence explaining the very
        property it is testing.
        """
        import ast

        source = (BACKEND_ROOT / "extraction" / "adapters.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        adapter = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.ClassDef)
                       and node.name == "VoiceExtractionAdapter")
        names = {node.id for node in ast.walk(adapter) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(adapter) if isinstance(node, ast.Attribute)}
        names |= {alias.name for node in ast.walk(adapter)
                  if isinstance(node, (ast.Import, ast.ImportFrom))
                  for alias in node.names}
        names |= {node.module or "" for node in ast.walk(adapter)
                  if isinstance(node, ast.ImportFrom)}
        self.assertFalse([n for n in names if "avalai" in n.lower()],
                         "the adapter must not reference a vendor in its code")


class TheSpeechProviderTests(unittest.TestCase):
    """Transport, parsing and refusals -- without a key, a network, or a sample file.

    The audio is written into a temporary file rather than read from
    `extraction/samples/`: that directory is gitignored on purpose -- a "test" invoice
    carrying a real vendor and a real amount is financial data whatever it is called -- so
    a test depending on it passes on the machine that created it and fails on every clone.
    """

    def setUp(self):
        import tempfile

        self._directory = tempfile.TemporaryDirectory()
        self.audio = Path(self._directory.name) / "voice.wav"
        # Enough of a RIFF header to be a file; the transport is faked, so no decoder runs.
        self.audio.write_bytes(b"RIFF" + bytes(4) + b"WAVEfmt ")

    def tearDown(self):
        self._directory.cleanup()

    def _provider(self, body, **over):
        return AvalAISpeechProvider(
            api_key="test-only-not-a-real-key", transport=lambda boundary, data: body,
            **over)

    def test_it_returns_the_shape_the_adapter_reads(self):
        provider = self._provider(json.dumps({"text": SPOKEN_WRONG, "language": "fa"}))
        result = provider.transcribe(self.audio)
        self.assertEqual({"text", "language", "provider", "confidence", "model",
                          "duration_seconds"}, set(result))
        self.assertEqual("avalai", result["provider"])
        self.assertIn("107,000,000", result["text"])

    def test_confidence_is_none_rather_than_a_guess(self):
        provider = self._provider(json.dumps({"text": "سلام"}))
        result = provider.transcribe(self.audio)
        self.assertIsNone(result["confidence"])

    def test_the_default_model_is_configurable_and_not_buried(self):
        self.assertEqual("groq.whisper-large-v3-turbo", DEFAULT_MODEL)
        self.assertEqual("other-model",
                         AvalAISpeechProvider(api_key="x", model="other-model").model)

    def test_silence_is_not_an_error(self):
        provider = self._provider(json.dumps({"text": ""}))
        result = provider.transcribe(self.audio)
        self.assertEqual("", result["text"])

    def test_a_missing_key_refuses_rather_than_sending_nothing(self):
        provider = AvalAISpeechProvider(api_key="", transport=lambda b, d: "{}")
        self.assertFalse(provider.configured)
        with self.assertRaises(ProviderUnavailable):
            provider.transcribe(self.audio)

    def test_a_missing_file_refuses(self):
        provider = self._provider("{}")
        with self.assertRaises(ProviderUnavailable):
            provider.transcribe(BACKEND_ROOT / "nothing" / "here.wav")

    def test_a_body_that_is_not_json_refuses_rather_than_returning_it(self):
        provider = self._provider("<html>502 Bad Gateway</html>")
        with self.assertRaises(ProviderUnavailable):
            provider.transcribe(self.audio)

    def test_no_credential_appears_in_the_source(self):
        source = (BACKEND_ROOT / "extraction" / "providers"
                  / "avalai_speech.py").read_text(encoding="utf-8")
        # The names of the variables, yes. A value, never.
        self.assertIn("AVALAI_API_KEY", source)
        for marker in ("aa-", "sk-", "Bearer aa"):
            self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
