# -*- coding: utf-8 -*-
"""AvalAI as a second reader of invoice text.

WHAT IS BEING PROTECTED

The pipeline worked before this provider existed and must keep working when it fails.
Every failure path here returns NO fields rather than raising: the OCR text and the
deterministic parser's candidates are already assembled by the time AvalAI is asked, and
losing them because a second opinion was unavailable would make the extraction less
reliable for having gained a provider.

The other half is the one that matters for money. The model fills gaps; it does not
arbitrate. A field `invoice_parser` produced is never asked of the model and never
overwritten by it, because a rule that can be read beats a model that cannot.

No test here reaches the network. `_post` is injected.
"""

import json
import sys
import unittest
import urllib.error
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction.providers.avalai import (AvalAIProvider, ProviderResponseInvalid,
                                         ProviderUnavailable, describe, parse_fields)


def answer(payload):
    """A 200 whose assistant message is `payload` serialised."""
    body = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}
    return 200, json.dumps(body, ensure_ascii=False).encode("utf-8")


def provider(post, key="test-key", sleep=None):
    return AvalAIProvider(key=key, post=post, sleep=sleep or (lambda _s: None))


class ConfigurationTests(unittest.TestCase):
    def test_no_key_means_the_provider_is_off(self):
        subject = AvalAIProvider(key=None)
        # os.environ may carry one on a developer machine; force the off case.
        subject._key = None
        self.assertFalse(subject.configured)
        with self.assertRaises(ProviderUnavailable) as caught:
            subject.extract("فاکتور")
        self.assertIn("AVALAI_API_KEY", str(caught.exception))

    def test_describe_never_returns_the_key(self):
        import os
        key = "sk-secret-value-nobody-should-see"
        os.environ["AVALAI_API_KEY"] = key
        try:
            told = describe()
            self.assertTrue(told["configured"])
            self.assertEqual(len(key), told["keyLength"],
                             "the length is the only thing about the key that is safe")
            self.assertNotIn("secret", json.dumps(told))
        finally:
            os.environ.pop("AVALAI_API_KEY", None)

    def test_the_key_travels_only_in_the_authorization_header(self):
        seen = {}

        def post(url, payload, key, timeout):
            seen["payload"] = json.dumps(payload, ensure_ascii=False)
            seen["key"] = key
            return answer({})

        provider(post).extract("فاکتور شماره ۱۲۳")
        self.assertEqual("test-key", seen["key"])
        self.assertNotIn("test-key", seen["payload"],
                         "the key must never appear in the request body")


class RequestTests(unittest.TestCase):
    def test_the_model_is_given_the_text_the_fields_and_nothing_invented(self):
        seen = {}

        def post(url, payload, key, timeout):
            seen.update(payload=payload, url=url)
            return answer({})

        provider(post).extract("جمع کل: ۱۳۵۰۰۰۰",
                               transcript="صد و سی و پنج هزار",
                               metadata={"fileName": "inv.jpg"})
        content = seen["payload"]["messages"][1]["content"]
        self.assertIn("جمع کل: ۱۳۵۰۰۰۰", content)
        self.assertIn("صد و سی و پنج هزار", content)
        self.assertIn("inv.jpg", content)
        self.assertIn("invoiceNumber", content)
        self.assertIn("totalAmount", content)
        self.assertEqual(0, seen["payload"]["temperature"],
                         "the same invoice must not read differently on a retry")
        self.assertTrue(seen["url"].endswith("/chat/completions"))

    def test_speech_and_scan_are_kept_separable(self):
        """A model told which is which can weigh them; one handed a blob cannot."""
        seen = {}

        def post(url, payload, key, timeout):
            seen["content"] = payload["messages"][1]["content"]
            return answer({})

        provider(post).extract("from the image", transcript="from the microphone")
        self.assertIn("RECOGNISED FROM THE IMAGE", seen["content"])
        self.assertIn("TRANSCRIBED FROM SPEECH", seen["content"])

    def test_nothing_to_read_costs_no_request(self):
        def post(*_a, **_k):
            raise AssertionError("no request should have been made")

        self.assertEqual({}, provider(post).extract("", transcript=""))


class ResponseTests(unittest.TestCase):
    def test_a_clean_answer_becomes_value_and_confidence(self):
        fields = provider(lambda *_a: answer({
            "invoiceNumber": {"value": "۱۲۳۴", "confidence": 0.95},
            "totalAmount": {"value": "1350000", "confidence": 0.8}})).extract("x")
        self.assertEqual(("۱۲۳۴", 0.95), fields["invoiceNumber"])
        self.assertEqual(("1350000", 0.8), fields["totalAmount"])

    def test_a_field_the_model_could_not_find_is_dropped_not_blanked(self):
        fields = provider(lambda *_a: answer({
            "invoiceNumber": {"value": None, "confidence": 0},
            "supplierName": {"value": "   ", "confidence": 0.4}})).extract("x")
        self.assertEqual({}, fields, "null and blank are both 'not stated'")

    def test_a_value_with_no_confidence_is_refused(self):
        """Showing it would present a guess as something somebody vouched for."""
        fields = provider(lambda *_a: answer({
            "invoiceNumber": {"value": "۱۲۳۴"},
            "supplierName": {"value": "آهن‌آنلاین", "confidence": "high"},
            "totalAmount": {"value": "100", "confidence": True}})).extract("x")
        self.assertEqual({}, fields)

    def test_confidence_is_clamped_to_the_column_the_schema_allows(self):
        fields = provider(lambda *_a: answer({
            "a": {"value": "x", "confidence": 5},
            "b": {"value": "y", "confidence": -2}})).extract("x")
        self.assertEqual(1.0, fields["a"][1])
        self.assertEqual(0.0, fields["b"][1])

    def test_a_code_fence_is_tolerated(self):
        """Models add them. Losing six good fields to three backticks would be silly."""
        self.assertEqual(
            {"invoiceNumber": ("۱۲۳۴", 0.9)},
            parse_fields('```json\n{"invoiceNumber": {"value": "۱۲۳۴", "confidence": 0.9}}\n```'))

    def test_persian_digits_are_returned_as_printed(self):
        fields = parse_fields('{"invoiceDate": {"value": "۱۴۰۵/۰۶/۲۲", "confidence": 0.9}}')
        self.assertEqual("۱۴۰۵/۰۶/۲۲", fields["invoiceDate"][0])

    def test_prose_instead_of_json_is_an_invalid_response(self):
        with self.assertRaises(ProviderResponseInvalid):
            parse_fields("I found an invoice number of 1234.")

    def test_an_envelope_with_no_message_is_an_invalid_response(self):
        with self.assertRaises(ProviderResponseInvalid):
            provider(lambda *_a: (200, b'{"choices": []}')).extract("x")

    def test_a_non_json_body_is_an_invalid_response(self):
        with self.assertRaises(ProviderResponseInvalid):
            provider(lambda *_a: (200, b"<html>login</html>")).extract("x")


class FailureTests(unittest.TestCase):
    def test_a_timeout_is_retried_then_reported(self):
        attempts = []

        def post(*_a):
            attempts.append(1)
            raise TimeoutError("too slow")

        with self.assertRaises(ProviderUnavailable):
            provider(post).extract("x")
        self.assertEqual(3, len(attempts), "two retries, then give up")

    def test_a_server_error_is_retried(self):
        attempts = []

        def post(*_a):
            attempts.append(1)
            return (503, b"upstream busy") if len(attempts) < 3 else answer(
                {"invoiceNumber": {"value": "۹۹", "confidence": 0.7}})

        self.assertEqual(("۹۹", 0.7), provider(post).extract("x")["invoiceNumber"])
        self.assertEqual(3, len(attempts))

    def test_a_bad_request_is_not_retried(self):
        """Repeating a 400 changes nothing; repeating a 401 gets an account limited."""
        for status in (400, 401, 403):
            attempts = []

            def post(*_a, _status=status):
                attempts.append(1)
                return _status, b"nope"

            with self.subTest(status):
                with self.assertRaises(ProviderUnavailable):
                    provider(post).extract("x")
                self.assertEqual(1, len(attempts))

    def test_an_implausibly_large_answer_is_refused(self):
        from extraction.providers.avalai import MAX_RESPONSE_BYTES
        with self.assertRaises(ProviderResponseInvalid):
            provider(lambda *_a: (200, b"x" * (MAX_RESPONSE_BYTES + 2))).extract("x")

    def test_the_failure_message_never_carries_the_key(self):
        def post(*_a):
            return 401, b"invalid api key"

        with self.assertRaises(ProviderUnavailable) as caught:
            provider(post, key="sk-do-not-leak").extract("x")
        self.assertNotIn("sk-do-not-leak", str(caught.exception))


class CompositionTests(unittest.TestCase):
    """How AvalAI's candidates reach the draft, and what they may not touch."""

    def setUp(self):
        import os
        self.saved = os.environ.get("AVALAI_API_KEY")
        os.environ["AVALAI_API_KEY"] = "test-key"

    def tearDown(self):
        import os
        if self.saved is None:
            os.environ.pop("AVALAI_API_KEY", None)
        else:
            os.environ["AVALAI_API_KEY"] = self.saved

    def contract(self, monkey):
        from extraction import adapters
        original = adapters._ai_fields
        adapters._ai_fields = monkey
        try:
            return adapters._as_contract({"text": "جمع کل: 1350000", "confidence": 0.9})
        finally:
            adapters._ai_fields = original

    def test_the_parsers_own_fields_are_never_asked_of_the_model(self):
        seen = {}

        def monkey(text, already_emitted, **_k):
            seen["already"] = set(already_emitted)
            return []

        self.contract(monkey)
        self.assertIn("rawText", seen["already"])
        self.assertIn("validationStatus", seen["already"],
                      "whatever the parser produced is off the table for the model")

    def test_an_ai_candidate_for_a_field_the_parser_found_is_dropped(self):
        import extraction.providers.avalai as avalai
        original = avalai.AvalAIProvider
        class Stub:
            configured = True
            def __init__(self, *_a, **_k): pass
            def extract(self, *_a, **_k):
                return {"rawText": ("hijacked", 1.0), "supplierName": ("آهن‌آنلاین", 0.9)}
        avalai.AvalAIProvider = Stub
        try:
            from extraction.adapters import _ai_fields as real
            import os
            from unittest.mock import patch
            with patch.dict(os.environ, {"FINANCE_AI_EXTRACTION_ENABLED": "true",
                                      "FINANCE_AI_API_KEY": "test-key"}):
                fields = real("some text", {"rawText"})
        finally:
            avalai.AvalAIProvider = original
        self.assertEqual(["supplierName"], [f["key"] for f in fields],
                         "the model may not overwrite a field the parser produced")

    def test_an_unavailable_model_costs_no_fields_and_no_exception(self):
        import extraction.providers.avalai as avalai
        original = avalai.AvalAIProvider
        class Stub:
            configured = True
            def __init__(self, *_a, **_k): pass
            def extract(self, *_a, **_k):
                raise avalai.ProviderUnavailable("gateway down")
        avalai.AvalAIProvider = Stub
        try:
            from extraction.adapters import _as_contract
            import os
            from unittest.mock import patch
            with patch.dict(os.environ, {"FINANCE_AI_EXTRACTION_ENABLED": "true",
                                      "FINANCE_AI_API_KEY": "test-key"}):
                answer = _as_contract({"text": "جمع کل: 1350000", "confidence": 0.9})
        finally:
            avalai.AvalAIProvider = original
        keys = [f["key"] for f in answer["fields"]]
        self.assertIn("rawText", keys, "the OCR text survives a failed second opinion")
        self.assertIn("aiWarnings", keys)

    def test_ai_candidates_arrive_less_certain_than_a_parsed_field(self):
        from extraction.adapters import AI_CONFIDENCE_WEIGHT
        self.assertLess(AI_CONFIDENCE_WEIGHT, 1.0)


if __name__ == "__main__":
    unittest.main()
