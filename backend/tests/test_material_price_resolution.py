# -*- coding: utf-8 -*-
"""Which of the four ways a price can be unusable this one is -- and never a zero.

A reader shown nothing cannot tell a missing price from a missing unit from a missing
mapping. A reader shown a zero is being told the thing is free. So every case here checks
two things: that the price is withheld, and that the status says which case it is.
"""

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.services.material_price_resolution import (UNIT_ALIASES, canonical_unit,
                                                            convert_unit_price, resolve)


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


class UnitNameTests(unittest.TestCase):
    def test_the_sheet_and_the_registry_spell_kilogram_differently_and_both_are_read(self):
        for spelling in ("کیلو", "کیلوگرم", "kg", "KG", "Kilogram"):
            with self.subTest(spelling=spelling):
                self.assertEqual("kg", canonical_unit(spelling))

    def test_an_unstated_unit_is_none_not_a_default(self):
        for blank in (None, "", "   "):
            with self.subTest(blank=repr(blank)):
                self.assertIsNone(canonical_unit(blank))

    def test_an_unknown_unit_stays_unknown_rather_than_becoming_a_guess(self):
        self.assertEqual("فرغون", canonical_unit("فرغون"))
        self.assertNotEqual("kg", canonical_unit("فرغون"))


class ConversionTests(unittest.TestCase):
    def test_a_unit_price_converts_inversely_which_is_the_whole_point(self):
        """1000 Toman per kilogram is 1 Toman per gram -- divided, not multiplied."""
        self.assertEqual(Decimal("1"), convert_unit_price(Decimal("1000"), Decimal("1000")))

    def test_kilogram_to_gram_and_back_agree(self):
        per_kg = Decimal("955000")
        per_g = convert_unit_price(per_kg, Decimal("1000"))
        self.assertEqual(Decimal("955"), per_g)
        self.assertEqual(per_kg, convert_unit_price(per_g, Decimal("0.001")))

    def test_a_zero_or_negative_factor_is_refused_rather_than_dividing(self):
        for bad in (Decimal("0"), Decimal("-2")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    convert_unit_price(Decimal("100"), bad)

    def test_an_absent_factor_converts_nothing(self):
        self.assertIsNone(convert_unit_price(Decimal("100"), None))
        self.assertIsNone(convert_unit_price(None, Decimal("10")))


class ResolutionTests(unittest.TestCase):
    def test_a_price_in_the_unit_asked_for_needs_no_conversion(self):
        price, status, reason, factor, note = resolve(observation(), display_unit="kg")
        self.assertEqual(Decimal("955000"), price)
        self.assertEqual("resolved", status)
        self.assertIsNone(reason)
        self.assertIsNone(factor, "nothing was converted, so nothing is claimed to be")

    def test_a_missing_price_is_unresolved_and_never_zero(self):
        price, status, reason, _, _ = resolve(
            observation(normalized_price_irr=None, validation_status="rejected",
                        validation_reasons=["price is blank"]), display_unit="kg")
        self.assertIsNone(price, "a missing price must stay missing")
        self.assertEqual("unresolved_price", status)
        self.assertIn("blank", reason)

    def test_a_missing_factor_withholds_the_price_rather_than_relabelling_it(self):
        price, status, reason, _, _ = resolve(
            observation(), display_unit="piece", conversion_lookup=lambda a, b: None)
        self.assertIsNone(price, "kg to piece needs a weight this product never stated")
        self.assertEqual("unresolved_unit", status)
        self.assertIn("kg", reason)
        self.assertIn("piece", reason)

    def test_a_price_with_no_stated_basis_is_not_relabelled_into_one(self):
        """Six of the seven categories state no unit. That is not permission to assume."""
        price, status, reason, _, _ = resolve(
            observation(source_unit=None), display_unit="kg")
        self.assertIsNone(price)
        self.assertEqual("unresolved_unit", status)
        self.assertIn("states no unit", reason)

    def test_a_present_factor_converts_and_says_exactly_what_it_did(self):
        price, status, _, factor, note = resolve(
            observation(), display_unit="g", conversion_lookup=lambda a, b: Decimal("1000"))
        self.assertEqual("resolved", status)
        self.assertEqual(Decimal("955"), price)
        self.assertEqual(Decimal("1000"), factor)
        self.assertIn("dividing", note)

    def test_an_old_price_is_stale_but_is_still_shown(self):
        """Stale is not missing: the last known valid price is kept, and labelled."""
        price, status, reason, _, _ = resolve(
            observation(workflow_date_gregorian=date(2026, 8, 1)), display_unit="kg",
            as_of=date(2026, 9, 14), stale_after_days=7)
        self.assertEqual(Decimal("955000"), price, "a stale price is preserved, not dropped")
        self.assertEqual("stale", status)
        self.assertIn("2026-08-01", reason)

    def test_a_fresh_price_is_not_called_stale(self):
        _, status, _, _, _ = resolve(observation(), display_unit="kg",
                                     as_of=date(2026, 9, 14), stale_after_days=7)
        self.assertEqual("resolved", status)

    def test_no_display_unit_means_no_conversion_and_no_complaint(self):
        """Before anybody has chosen a unit, the price is shown as the sheet states it."""
        price, status, _, factor, _ = resolve(observation(), display_unit=None)
        self.assertEqual(Decimal("955000"), price)
        self.assertEqual("resolved", status)
        self.assertIsNone(factor)

    def test_every_alias_maps_to_something_this_module_also_knows(self):
        """An alias pointing at a spelling nothing else uses is a silent dead end."""
        targets = set(UNIT_ALIASES.values())
        for alias, target in UNIT_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIn(target, targets)
                self.assertEqual(target, canonical_unit(alias))


if __name__ == "__main__":
    unittest.main()
