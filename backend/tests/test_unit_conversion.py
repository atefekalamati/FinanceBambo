# -*- coding: utf-8 -*-
"""Conversion between units, and the far longer list of conversions that are refused.

The one that would hurt most if it were wrong is the inverse: a price per kilogram turned
into a price per gram must be DIVIDED by a thousand, not multiplied. Getting that backwards
is a factor of a million in a price, and it would look plausible on screen.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.unit_conversion import (PRICE_PRECISION, RATIO_TO_BASE,
                                                ConversionRefused, apply_product_factor,
                                                can_convert, convert_quantity,
                                                convert_unit_price, quantity_factor)
from app.finance.domain.unit_registry import UNIT_REGISTRY


class RegistryAgreementTests(unittest.TestCase):
    """The two files must describe the same units, or one of them is a second vocabulary."""

    def test_every_unit_with_a_ratio_is_a_unit_the_registry_defines(self):
        for unit in RATIO_TO_BASE:
            with self.subTest(unit=unit):
                self.assertIn(unit, UNIT_REGISTRY,
                              "%r has a ratio but is not a Finance unit" % unit)

    def test_each_dimension_has_exactly_one_base(self):
        """A dimension with two units at ratio 1 has no base; one with none cannot convert."""
        bases = {}
        for unit, ratio in RATIO_TO_BASE.items():
            if ratio == 1:
                bases.setdefault(UNIT_REGISTRY[unit].dimension, []).append(unit)
        # count deliberately has three units at ratio 1: each, branch and bag are all one
        # countable thing. That is a statement about counting, not a missing base.
        for dimension, units in bases.items():
            with self.subTest(dimension=dimension):
                if dimension == "count":
                    self.assertEqual({"each", "branch", "bag"}, set(units))
                else:
                    self.assertEqual(1, len(units), "%s has bases %s" % (dimension, units))

    def test_the_units_the_price_sheet_needs_are_all_present(self):
        for unit in ("g", "kg", "ton", "mm", "cm", "m", "m2", "m3", "each", "branch"):
            with self.subTest(unit=unit):
                self.assertIn(unit, UNIT_REGISTRY)


class DirectConversionTests(unittest.TestCase):
    def test_the_conversions_the_brief_lists_as_automatic(self):
        for source, target, factor in (("kg", "g", "1000"), ("g", "kg", "0.001"),
                                       ("ton", "kg", "1000"), ("kg", "ton", "0.001"),
                                       ("m", "cm", "100"), ("cm", "m", "0.01"),
                                       ("m", "mm", "1000"), ("mm", "cm", "0.1"),
                                       ("m2", "cm2", "10000"), ("cm2", "m2", "0.0001"),
                                       ("m3", "liter", "1000"), ("liter", "m3", "0.001")):
            with self.subTest(pair="%s->%s" % (source, target)):
                self.assertEqual(Decimal(factor), quantity_factor(source, target))

    def test_a_quantity_is_multiplied(self):
        self.assertEqual(Decimal("2000"), convert_quantity(Decimal("2"), "kg", "g"))
        self.assertEqual(Decimal("0.5"), convert_quantity(Decimal("500"), "g", "kg"))

    def test_the_same_unit_converts_to_itself_without_touching_the_number(self):
        self.assertEqual(Decimal("955000"), convert_unit_price(Decimal("955000"), "kg", "kg"))

    def test_a_round_trip_returns_the_number_that_went_in(self):
        """Every ratio is a power of ten, so this is exact rather than nearly exact."""
        for source, target in (("kg", "g"), ("m", "mm"), ("m2", "cm2"), ("m3", "liter")):
            with self.subTest(pair="%s->%s" % (source, target)):
                start = Decimal("1234.5678")
                there = convert_quantity(start, source, target)
                back = convert_quantity(there, target, source)
                self.assertEqual(start, back)


class InversePriceTests(unittest.TestCase):
    """The case that matters most, in the brief's own numbers."""

    def test_a_thousand_toman_per_kilogram_is_one_toman_per_gram(self):
        self.assertEqual(Decimal("1"), convert_unit_price(Decimal("1000"), "kg", "g"))

    def test_ten_thousand_rial_per_kilogram_is_ten_rial_per_gram(self):
        self.assertEqual(Decimal("10"), convert_unit_price(Decimal("10000"), "kg", "g"))

    def test_the_price_goes_the_opposite_way_to_the_quantity(self):
        """Stated as a property, so no future edit can quietly make them agree."""
        for source, target in (("kg", "g"), ("m", "cm"), ("ton", "kg"), ("m3", "liter")):
            with self.subTest(pair="%s->%s" % (source, target)):
                factor = quantity_factor(source, target)
                quantity = convert_quantity(Decimal("100"), source, target)
                price = convert_unit_price(Decimal("100"), source, target)
                self.assertEqual(Decimal("100") * factor, quantity)
                self.assertEqual(Decimal("100") / factor, price)
                if factor > 1:
                    self.assertGreater(quantity, price,
                                       "more of a smaller unit, each one cheaper")

    def test_a_converted_price_keeps_eight_places(self):
        self.assertEqual(PRICE_PRECISION.as_tuple().exponent,
                         convert_unit_price(Decimal("1"), "kg", "g").as_tuple().exponent)

    def test_no_float_ever_reaches_the_arithmetic(self):
        """A float argument is converted through its string, not taken as a binary value."""
        self.assertEqual(Decimal("0.1"), convert_unit_price(100.0, "kg", "g"))


class RefusalTests(unittest.TestCase):
    """Everything the brief says must not happen automatically."""

    def test_the_crossings_that_need_a_fact_about_a_product(self):
        for source, target in (("each", "kg"), ("kg", "each"), ("branch", "kg"),
                               ("branch", "m"), ("bag", "kg"), ("m", "kg"),
                               ("m3", "ton"), ("each", "m2")):
            with self.subTest(pair="%s->%s" % (source, target)):
                self.assertFalse(can_convert(source, target))
                with self.assertRaises(ConversionRefused) as caught:
                    quantity_factor(source, target)
                self.assertIn("dimension", str(caught.exception))

    def test_a_working_day_is_not_assumed_to_be_any_number_of_hours(self):
        with self.assertRaises(ConversionRefused) as caught:
            quantity_factor("day", "hour")
        self.assertTrue(str(caught.exception))

    def test_a_unit_the_registry_does_not_know_is_refused_by_name(self):
        for unknown in ("فرغون", "piece", "kilo", ""):
            with self.subTest(unknown=unknown):
                with self.assertRaises(ConversionRefused) as caught:
                    quantity_factor(unknown, "kg")
                self.assertIn("registry", str(caught.exception))

    def test_piece_is_not_a_finance_unit_even_though_it_reads_like_one(self):
        """The Finance word for a countable thing is `each`. `piece` is not a synonym here."""
        self.assertNotIn("piece", UNIT_REGISTRY)


class ProductFactorTests(unittest.TestCase):
    def test_a_stored_factor_converts_a_price_the_same_inverse_way(self):
        # "this brick weighs 2.8 kg": a price per piece becomes a price per kg by dividing.
        self.assertEqual(Decimal("10000"),
                         apply_product_factor(Decimal("28000"), Decimal("2.8")))

    def test_a_zero_or_negative_factor_is_refused_rather_than_dividing(self):
        for bad in (Decimal("0"), Decimal("-1")):
            with self.subTest(bad=bad):
                with self.assertRaises(ConversionRefused):
                    apply_product_factor(Decimal("100"), bad)

    def test_an_absent_factor_converts_nothing(self):
        self.assertIsNone(apply_product_factor(Decimal("100"), None))
        self.assertIsNone(apply_product_factor(None, Decimal("2")))


if __name__ == "__main__":
    unittest.main()
