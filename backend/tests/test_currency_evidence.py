# -*- coding: utf-8 -*-
"""A currency is recorded only when the document states one.

WHAT WENT WRONG

On `page2.jpg` the vision model answered `currency: TOMAN`. The page prints neither
`تومان` nor `ریال` anywhere -- the human-read ground truth records currency as null and
says so explicitly. The model was not reading the page; it was applying what Iranian
invoices usually say.

It arrived at confidence 0.855, above the review UI's 0.8 threshold, so nobody would have
been asked about it. And the two candidate answers are a factor of ten apart, which makes
a guessed currency a factor-of-ten error on every amount the invoice carries.

THE RULE

`find_currency` already answers "does this text state a currency" -- it is what the
deterministic parser uses. The same function is now the evidence test for the model's
answer: state one and the claim stands, state none and none is recorded. Deterministic,
and not a politely worded prompt.

Nothing is converted. `تومان` and `ریال` map to different codes and neither is rewritten
into the other; that is a financial decision for a layer that knows the unit rather than
guesses it.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction import adapters
from extraction.adapters import _as_contract, _as_contract_voice, _currency_without_evidence
from extraction.parsing import CURRENCIES, find_currency


def ai_field(key, value, confidence=0.9):
    return {"key": key, "extractedValue": value, "confidence": confidence,
            "editedByUser": False}


class TheEvidenceTestTests(unittest.TestCase):
    """`_currency_without_evidence` on its own, with no model and no page."""

    def test_a_currency_the_text_does_not_state_is_dropped(self):
        fields, warnings = _currency_without_evidence(
            [ai_field("currency", "TOMAN"), ai_field("supplierName", "نما برتر")],
            "فاکتور شماره ۱۲ مبلغ ۵۴۴۲۲۲۰۰۰")
        self.assertEqual(["supplierName"], [f["key"] for f in fields])
        self.assertEqual(1, len(warnings))
        self.assertEqual("currencyWarnings", warnings[0]["key"])

    def test_a_currency_the_text_states_is_kept(self):
        fields, warnings = _currency_without_evidence(
            [ai_field("currency", "IRR")], "قیمت آن ۵۴۴,۲۲۲,۰۰۰ ریال است")
        self.assertEqual(["currency"], [f["key"] for f in fields])
        self.assertEqual([], warnings)

    def test_toman_in_the_text_is_evidence_too(self):
        fields, warnings = _currency_without_evidence(
            [ai_field("currency", "IRT")], "جمع کل: ۵۴,۴۲۲,۲۰۰ تومان")
        self.assertEqual(["currency"], [f["key"] for f in fields])
        self.assertEqual([], warnings)

    def test_a_model_that_claimed_no_currency_is_left_alone(self):
        given = [ai_field("supplierName", "نما برتر")]
        fields, warnings = _currency_without_evidence(given, "no currency word here")
        self.assertIs(given, fields)
        self.assertEqual([], warnings)

    def test_nothing_is_converted_between_the_two(self):
        # The model's own code travels unchanged when the document supports having one.
        # Rewriting IRT to IRR here would multiply every amount on the invoice by ten.
        fields, _ = _currency_without_evidence(
            [ai_field("currency", "IRT")], "مبلغ ۱۰۰ ریال")
        self.assertEqual("IRT", fields[0]["extractedValue"],
                         "the reading is reported as given; conversion is not extraction")

    def test_the_vocabulary_is_the_parsers_own_and_not_a_second_list(self):
        self.assertEqual({"IRR", "IRT"}, set(CURRENCIES.values()))
        self.assertEqual("IRR", find_currency("مبلغ ۱۰۰ ریال")[0])
        self.assertIsNone(find_currency("مبلغ ۱۰۰")[0])


class ThroughTheWholeContractTests(unittest.TestCase):
    """The same rule where it actually runs, with the reader stubbed."""

    def setUp(self):
        self._original = adapters._ai_fields
        self.addCleanup(lambda: setattr(adapters, "_ai_fields", self._original))

    def stub(self, *fields):
        adapters._ai_fields = lambda *a, **k: [dict(f) for f in fields]

    def values(self, contract):
        return {f["key"]: f["extractedValue"] for f in contract["fields"]}

    def test_an_image_reading_cannot_invent_the_currency(self):
        # page2.jpg, in miniature: amounts present, no currency word anywhere.
        self.stub(ai_field("currency", "TOMAN"), ai_field("totalAmount", "544222000"))
        contract = _as_contract({"text": "آیتم ۷ مبلغ ۵۴۴,۲۲۲,۰۰۰", "confidence": 0.9},
                                image=bytes([0xFF, 0xD8, 0xFF]))
        values = self.values(contract)
        self.assertNotIn("currency", values)
        self.assertIn("currencyWarnings", values)
        self.assertEqual("544222000", values["totalAmount"],
                         "only the currency is refused; the reading stands")

    def test_an_image_reading_keeps_a_currency_the_page_prints(self):
        self.stub(ai_field("currency", "IRR"))
        contract = _as_contract({"text": "جمع کل ۵۴۴,۲۲۲,۰۰۰ ریال", "confidence": 0.9},
                                image=bytes([0xFF, 0xD8, 0xFF]))
        self.assertEqual("IRR", self.values(contract)["currency"])

    def test_a_spoken_currency_is_evidence(self):
        # voice1.wav says «ریال» out loud, so the transcript states one.
        self.stub(ai_field("currency", "IRR"))
        contract = _as_contract_voice({"text": "قیمت آن صد و هفت میلیون ریال است",
                                       "provider": "avalai", "model": "m",
                                       "confidence": None})
        self.assertEqual("IRR", self.values(contract)["currency"])

    def test_a_recording_that_names_no_currency_records_none(self):
        self.stub(ai_field("currency", "TOMAN"))
        contract = _as_contract_voice({"text": "قیمت آن صد و هفت میلیون است",
                                       "provider": "avalai", "model": "m",
                                       "confidence": None})
        values = self.values(contract)
        self.assertNotIn("currency", values)
        self.assertIn("currencyWarnings", values)

    def test_the_refusal_is_visible_to_the_reviewer_rather_than_silent(self):
        self.stub(ai_field("currency", "TOMAN"))
        contract = _as_contract({"text": "مبلغ ۱۰۰", "confidence": 0.9})
        warning, = [f for f in contract["fields"] if f["key"] == "currencyWarnings"]
        message = warning["extractedValue"][0]
        self.assertEqual("currency-unevidenced", message["source"])
        self.assertIn("does not state", message["message"])

    def test_every_key_is_still_unique(self):
        self.stub(ai_field("currency", "TOMAN"), ai_field("supplierName", "x"))
        contract = _as_contract({"text": "مبلغ ۱۰۰", "confidence": 0.9})
        keys = [f["key"] for f in contract["fields"]]
        self.assertEqual(len(keys), len(set(keys)))


class TheGuardIsNotAPromptTests(unittest.TestCase):
    def test_no_prompt_was_enlarged_to_carry_this_rule(self):
        """The rule is enforced in code, so it cannot be argued with.

        A model told 'do not guess the currency' complies most of the time, and the times
        it does not look exactly like the times it does.
        """
        import inspect

        from extraction.providers import llm_invoice

        source = inspect.getsource(llm_invoice)
        self.assertNotIn("do not guess the currency", source.lower())
        self.assertIn("find_currency", inspect.getsource(adapters._currency_without_evidence))


if __name__ == "__main__":
    unittest.main()
