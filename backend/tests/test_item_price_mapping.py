# -*- coding: utf-8 -*-
"""Pricing a schedule item from a daily market price, and refusing to when it cannot.

The two examples in the specification are the first two tests, verbatim:

    1000 toman/kg is 1 toman/g
    92,560 toman/branch at 22 kg/branch is 4,207.27 toman/kg

Both are DIVISIONS, because a unit price is money per unit: going to a smaller unit makes
the number smaller, not larger. A quantity converts the other way, and getting the two
confused produces a figure wrong by the square of the factor while still looking like money.

The rest of this file is about the answers that are not numbers. Every one of them is a
status with a Persian reason, and none of them is zero.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.item_price_mapping import (INCOMPATIBLE, NEEDS_FACTOR,
                                                   NEEDS_PRODUCT, NEEDS_UNIT, NO_PRICE,
                                                   READY, STATUS_LABELS, STATUS_REASONS,
                                                   price_item)


def mapping(unit="kg", item="11111111-1111-4111-8111-111111111111"):
    return {"provider_item_id": item, "selected_unit": unit}


class TheSpecifiedExamplesTests(unittest.TestCase):
    def test_a_thousand_toman_per_kilogram_is_one_per_gram(self):
        priced = price_item(mapping=mapping("g"), price_irr="1000",
                            source_unit="kg", quantity=None)
        self.assertEqual(READY, priced.status)
        self.assertEqual(Decimal("1"), priced.unit_price_irr.normalize())

    def test_a_branch_price_becomes_a_kilogram_price_through_the_measured_factor(self):
        """92,560 per branch, 22 kg in a branch -> 4,207.27 per kg, stored whole.

        The specification states the example in TOMAN and this module works in rials, so
        the same figure arrives here as 4,207.2727 and is stored as 4,207 -- money is whole
        rials everywhere in Finance, and a whole rial is a tenth of a toman, so the toman
        figure the specification names is preserved to 4,207.3.
        """
        priced = price_item(mapping=mapping("kg"), price_irr="92560",
                            source_unit="branch", quantity=None, factor="22")
        self.assertEqual(READY, priced.status)
        self.assertEqual(Decimal("4207"), priced.unit_price_irr)
        self.assertEqual(Decimal("22"), priced.factor_applied)

    def test_money_leaves_whole_so_the_page_can_render_it(self):
        r"""A fractional string is not money to `irrToToman`, which matches ^-?\d+$.

        This was found in acceptance: the API sent `913600.00000000`, the formatter
        returned an em dash, and the row showed «آماده» beside a blank price -- claiming to
        be priced and showing nothing.
        """
        for priced in (price_item(mapping=mapping("kg"), price_irr="913600",
                                  source_unit="kg", quantity="2299"),
                       price_item(mapping=mapping("g"), price_irr="1000",
                                  source_unit="kg", quantity="5000"),
                       price_item(mapping=mapping("kg"), price_irr="92560",
                                  source_unit="branch", quantity="3", factor="22")):
            with self.subTest(unit=priced.selected_unit):
                for field in ("converted_daily_unit_price_irr", "daily_item_cost_irr"):
                    text = priced.as_dict()[field]
                    self.assertRegex(text, r"^-?\d+$",
                                     "%s must be a whole number of rials" % field)

    def test_the_price_divides_where_a_quantity_would_multiply(self):
        # The direction test, stated on its own so it cannot be satisfied by accident.
        to_smaller = price_item(mapping=mapping("g"), price_irr="1000",
                                source_unit="kg", quantity=None)
        to_larger = price_item(mapping=mapping("ton"), price_irr="1000",
                               source_unit="kg", quantity=None)
        self.assertLess(to_smaller.unit_price_irr, Decimal("1000"))
        self.assertGreater(to_larger.unit_price_irr, Decimal("1000"))


class TheItemCostTests(unittest.TestCase):
    def test_the_cost_is_the_quantity_times_the_converted_price(self):
        priced = price_item(mapping=mapping("kg"), price_irr="1014600",
                            source_unit="kg", quantity="2299")
        self.assertEqual(READY, priced.status)
        self.assertEqual(Decimal("2332565400"), priced.item_cost_irr.normalize())

    def test_the_quantity_is_converted_by_the_price_not_by_itself(self):
        # 1000/kg -> 1/g, and 5000 g of it is 5000, not 5,000,000.
        priced = price_item(mapping=mapping("g"), price_irr="1000",
                            source_unit="kg", quantity="5000")
        self.assertEqual(Decimal("5000"), priced.item_cost_irr.normalize())

    def test_a_missing_quantity_leaves_the_cost_null_and_the_price_stated(self):
        # The schedule states no quantity for most rows. That is not a pricing failure and
        # must not make the whole row unresolved -- nor may the cost become zero.
        priced = price_item(mapping=mapping("kg"), price_irr="1014600",
                            source_unit="kg", quantity=None)
        self.assertEqual(READY, priced.status)
        self.assertIsNotNone(priced.unit_price_irr)
        self.assertIsNone(priced.item_cost_irr)

    def test_a_zero_quantity_is_a_real_zero_cost(self):
        # Zero is a number somebody wrote. It is not the same as nothing.
        priced = price_item(mapping=mapping("kg"), price_irr="1014600",
                            source_unit="kg", quantity="0")
        self.assertEqual(Decimal(0), priced.item_cost_irr)

    def test_money_never_becomes_a_float(self):
        priced = price_item(mapping=mapping("kg"), price_irr="1014600",
                            source_unit="kg", quantity="0.1")
        self.assertIsInstance(priced.unit_price_irr, Decimal)
        self.assertIsInstance(priced.item_cost_irr, Decimal)
        self.assertIsInstance(priced.as_dict()["daily_item_cost_irr"], str)


class WhatItRefusesTests(unittest.TestCase):
    def test_no_mapping_asks_for_the_product(self):
        priced = price_item(mapping=None, price_irr="1000", source_unit="kg", quantity="1")
        self.assertEqual(NEEDS_PRODUCT, priced.status)
        self.assertEqual("محصول قیمت روز انتخاب نشده", priced.reason)
        self.assertIsNone(priced.unit_price_irr)
        self.assertIsNone(priced.item_cost_irr)

    def test_no_selected_unit_asks_for_the_unit(self):
        priced = price_item(mapping=mapping(""), price_irr="1000",
                            source_unit="kg", quantity="1")
        self.assertEqual(NEEDS_UNIT, priced.status)
        self.assertEqual("واحد رسمی انتخاب نشده", priced.reason)

    def test_a_unit_outside_the_registry_is_not_a_unit(self):
        priced = price_item(mapping=mapping("furlong"), price_irr="1000",
                            source_unit="kg", quantity="1")
        self.assertEqual(NEEDS_UNIT, priced.status)

    def test_a_crossing_with_no_approved_factor_asks_for_one(self):
        priced = price_item(mapping=mapping("kg"), price_irr="92560",
                            source_unit="branch", quantity="10")
        self.assertEqual(NEEDS_FACTOR, priced.status)
        self.assertEqual("ضریب تبدیل لازم است", priced.reason)
        self.assertIsNone(priced.unit_price_irr)

    def test_a_crossing_nobody_could_measure_is_incompatible_not_missing_a_factor(self):
        # There is no number of kilograms in an hour, so asking for a factor would be
        # asking for something that cannot exist. The two statuses mean different things.
        priced = price_item(mapping=mapping("kg"), price_irr="1000",
                            source_unit="hour", quantity="1")
        self.assertEqual(INCOMPATIBLE, priced.status)
        self.assertEqual("تبدیل واحد ناسازگار است", priced.reason)

    def test_no_price_says_so_rather_than_pricing_at_zero(self):
        priced = price_item(mapping=mapping("kg"), price_irr=None,
                            source_unit="kg", quantity="10")
        self.assertEqual(NO_PRICE, priced.status)
        self.assertEqual("قیمت روز معتبر وجود ندارد", priced.reason)
        self.assertIsNone(priced.item_cost_irr)

    def test_a_price_whose_own_unit_is_unknown_is_not_converted(self):
        priced = price_item(mapping=mapping("kg"), price_irr="1000",
                            source_unit=None, quantity="1")
        self.assertEqual(NEEDS_UNIT, priced.status)
        self.assertIsNone(priced.unit_price_irr)

    def test_a_zero_factor_is_not_a_factor(self):
        # Dividing by it would raise; treating it as approved would price everything at
        # infinity. It is the absence of a measurement.
        priced = price_item(mapping=mapping("kg"), price_irr="92560",
                            source_unit="branch", quantity="1", factor="0")
        self.assertEqual(NEEDS_FACTOR, priced.status)

    def test_every_refusal_states_a_persian_reason_and_no_number(self):
        for priced in (price_item(mapping=None, price_irr="1", source_unit="kg", quantity="1"),
                       price_item(mapping=mapping(""), price_irr="1", source_unit="kg", quantity="1"),
                       price_item(mapping=mapping("kg"), price_irr="1", source_unit="branch", quantity="1"),
                       price_item(mapping=mapping("kg"), price_irr="1", source_unit="hour", quantity="1"),
                       price_item(mapping=mapping("kg"), price_irr=None, source_unit="kg", quantity="1")):
            with self.subTest(status=priced.status):
                self.assertNotEqual(READY, priced.status)
                self.assertTrue(priced.reason, "a refusal with no reason is not actionable")
                self.assertIsNone(priced.unit_price_irr)
                self.assertIsNone(priced.item_cost_irr)
                body = priced.as_dict()
                self.assertIsNone(body["converted_daily_unit_price_irr"])
                self.assertIsNone(body["daily_item_cost_irr"])


class TheVocabularyTests(unittest.TestCase):
    def test_every_status_has_a_label_and_a_reason(self):
        for status in (READY, NEEDS_PRODUCT, NEEDS_UNIT, NEEDS_FACTOR, INCOMPATIBLE, NO_PRICE):
            with self.subTest(status=status):
                self.assertIn(status, STATUS_LABELS)
                self.assertIn(status, STATUS_REASONS)

    def test_the_labels_are_the_ones_the_page_is_specified_to_show(self):
        self.assertEqual(
            {"آماده", "نیازمند انتخاب نوع قلم", "نیازمند انتخاب واحد",
             "نیازمند ضریب تبدیل", "ناسازگار", "بدون قیمت روز"},
            set(STATUS_LABELS.values()))

    def test_only_the_ready_status_carries_no_reason(self):
        self.assertEqual("", STATUS_REASONS[READY])
        for status, reason in STATUS_REASONS.items():
            if status != READY:
                with self.subTest(status=status):
                    self.assertTrue(reason.strip())


if __name__ == "__main__":
    unittest.main()
