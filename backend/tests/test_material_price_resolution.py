# -*- coding: utf-8 -*-
"""Which of the ways a price can be unusable this one is -- and never a zero.

A reader shown nothing cannot tell a missing price from a missing unit from a missing
factor from a missing mapping. A reader shown a zero is being told the thing is free. So
every case here checks two things: that the price is withheld, and that the status says
which case it is.

The statuses this file exercises are the ones the API publishes, so a rename in one place
fails here rather than reaching a screen as an untranslated word.
"""

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.unit_registry import UNIT_REGISTRY
from app.finance.services.material_price_resolution import (ALL_STATUSES, INACTIVE,
                                                            INCOMPATIBLE_UNIT, INVALID_SOURCE,
                                                            MISSING_FACTOR, RESOLVED,
                                                            SHEET_UNIT_SPELLINGS, STALE,
                                                            UNRESOLVED_MAPPING,
                                                            UNRESOLVED_PRICE, UNRESOLVED_UNIT,
                                                            canonical_unit, resolve)


def observation(**changes):
    row = {
        "normalized_price_irr": Decimal("955000"),
        "validation_status": "valid",
        "validation_reasons": [],
        "source_unit": "کیلو",
        "workflow_date_gregorian": date(2026, 9, 13),
    }
    row.update(changes)
    return row


class VocabularyTests(unittest.TestCase):
    """The spellings map onto the registry and nowhere else."""

    def test_every_sheet_spelling_resolves_to_a_real_finance_unit(self):
        for spelling, code in SHEET_UNIT_SPELLINGS.items():
            with self.subTest(spelling=spelling):
                self.assertIn(code, UNIT_REGISTRY,
                              "%r maps to %r, which is not a Finance unit" % (spelling, code))
                self.assertEqual(code, canonical_unit(spelling))

    def test_the_sheet_word_for_kilogram_is_read(self):
        for spelling in ("کیلو", "کیلوگرم", "kg", "KG"):
            with self.subTest(spelling=spelling):
                self.assertEqual("kg", canonical_unit(spelling))

    def test_a_spelling_the_registry_cannot_name_returns_nothing(self):
        """Returning the raw text would let it travel on looking like a unit code."""
        for unknown in ("فرغون", "piece-ish", "???"):
            with self.subTest(unknown=unknown):
                self.assertIsNone(canonical_unit(unknown))

    def test_an_unstated_unit_is_none_and_not_a_default(self):
        for blank in (None, "", "   "):
            with self.subTest(blank=repr(blank)):
                self.assertIsNone(canonical_unit(blank))


class ResolutionTests(unittest.TestCase):
    def test_a_price_already_in_the_unit_asked_for_needs_no_conversion(self):
        outcome = resolve(observation(), display_unit="kg")
        self.assertEqual(RESOLVED, outcome.status)
        self.assertEqual(Decimal("955000"), outcome.price)
        self.assertIsNone(outcome.conversion_factor,
                          "nothing was converted, so nothing is claimed to be")
        self.assertTrue(outcome.usable)

    def test_a_dimension_conversion_happens_and_explains_itself(self):
        outcome = resolve(observation(), display_unit="g")
        self.assertEqual(RESOLVED, outcome.status)
        self.assertEqual(Decimal("955.00000000"), outcome.price)
        self.assertEqual(Decimal("1000"), outcome.conversion_factor)
        self.assertEqual("dimension", outcome.factor_origin)
        self.assertIn("تقسیم", outcome.conversion_note)

    def test_a_missing_price_is_unresolved_and_never_zero(self):
        outcome = resolve(observation(normalized_price_irr=None,
                                      validation_reasons=["price is blank"]),
                          display_unit="kg")
        self.assertEqual(UNRESOLVED_PRICE, outcome.status)
        self.assertIsNone(outcome.price)
        self.assertIn("blank", outcome.reason)
        self.assertFalse(outcome.usable)

    def test_a_row_rejected_at_import_says_so_rather_than_looking_merely_empty(self):
        outcome = resolve(observation(validation_status="rejected",
                                      normalized_price_irr=None,
                                      validation_reasons=["price is not a number"]),
                          display_unit="kg")
        self.assertEqual(INVALID_SOURCE, outcome.status)
        self.assertIsNone(outcome.price)

    def test_a_price_with_no_stated_basis_is_not_relabelled_into_one(self):
        """Six of the seven categories state no unit. That is not permission to assume."""
        outcome = resolve(observation(source_unit=None), display_unit="kg")
        self.assertEqual(UNRESOLVED_UNIT, outcome.status)
        self.assertIsNone(outcome.price)
        self.assertIn("واحدی", outcome.reason)

    def test_a_crossing_that_needs_a_product_factor_is_refused_by_name(self):
        outcome = resolve(observation(source_unit="عدد"), display_unit="kg")
        self.assertEqual(MISSING_FACTOR, outcome.status)
        self.assertIsNone(outcome.price, "the price is withheld, not relabelled")
        self.assertIn("همین کالا", outcome.reason)

    def test_a_stored_product_factor_makes_the_crossing_possible(self):
        # "this brick weighs 2.8 kg", stored by a person against this listing.
        outcome = resolve(observation(source_unit="عدد", normalized_price_irr=Decimal("28000")),
                          display_unit="kg", product_factor=(Decimal("2.8"), "manual"))
        self.assertEqual(RESOLVED, outcome.status)
        self.assertEqual(Decimal("10000.00000000"), outcome.price)
        self.assertEqual("manual", outcome.factor_origin)
        self.assertIn("ضریب ثبت‌شده", outcome.conversion_note)

    def test_branch_to_kilogram_needs_a_factor_and_says_which_units(self):
        outcome = resolve(observation(source_unit="شاخه"), display_unit="kg")
        self.assertEqual(MISSING_FACTOR, outcome.status)
        self.assertIn("شاخه", outcome.reason)
        self.assertIn("کیلوگرم", outcome.reason)

    def test_an_unapproved_mapping_withholds_the_price_when_one_is_required(self):
        outcome = resolve(observation(), display_unit="kg", mapping_required=True,
                          mapping_approved=False)
        self.assertEqual(UNRESOLVED_MAPPING, outcome.status)
        self.assertIsNone(outcome.price)

    def test_an_approved_mapping_lets_the_price_through(self):
        outcome = resolve(observation(), display_unit="kg", mapping_required=True,
                          mapping_approved=True)
        self.assertEqual(RESOLVED, outcome.status)

    def test_an_old_price_is_stale_but_is_still_shown_and_still_usable(self):
        outcome = resolve(observation(workflow_date_gregorian=date(2026, 8, 1)),
                          display_unit="kg", as_of=date(2026, 9, 14), stale_after_days=7)
        self.assertEqual(STALE, outcome.status)
        self.assertEqual(Decimal("955000"), outcome.price, "a stale price is preserved")
        self.assertTrue(outcome.usable, "stale is a label, not a refusal")
        self.assertIn("2026-08-01", outcome.reason)

    def test_a_fresh_price_is_not_called_stale(self):
        outcome = resolve(observation(), display_unit="kg", as_of=date(2026, 9, 14),
                          stale_after_days=7)
        self.assertEqual(RESOLVED, outcome.status)

    def test_an_inactive_listing_resolves_to_inactive_and_no_price(self):
        outcome = resolve(observation(), display_unit="kg", active=False)
        self.assertEqual(INACTIVE, outcome.status)
        self.assertIsNone(outcome.price)
        self.assertFalse(outcome.usable)

    def test_no_chosen_unit_means_the_price_is_shown_as_the_sheet_states_it(self):
        outcome = resolve(observation(), display_unit=None)
        self.assertEqual(RESOLVED, outcome.status)
        self.assertEqual(Decimal("955000"), outcome.price)
        self.assertIsNone(outcome.conversion_factor)

    def test_no_status_is_ever_a_price_of_zero(self):
        """The property, over every refusal this module can produce."""
        cases = (
            resolve(observation(normalized_price_irr=None), display_unit="kg"),
            resolve(observation(validation_status="rejected"), display_unit="kg"),
            resolve(observation(source_unit=None), display_unit="kg"),
            resolve(observation(source_unit="عدد"), display_unit="kg"),
            resolve(observation(), display_unit="kg", mapping_required=True),
            resolve(observation(), display_unit="kg", active=False),
        )
        for outcome in cases:
            with self.subTest(status=outcome.status):
                self.assertIn(outcome.status, ALL_STATUSES)
                self.assertNotEqual(Decimal("0"), outcome.price)
                self.assertIsNone(outcome.price)
                self.assertTrue(outcome.reason, "a refusal without a reason is a blank cell")


if __name__ == "__main__":
    unittest.main()
