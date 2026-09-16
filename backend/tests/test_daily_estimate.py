# -*- coding: utf-8 -*-
"""The two answers a line gives, and every reason one of them is missing.

Pure arithmetic, so every case is stated exactly rather than arranged. The cases are the
ones the specification numbers, in its order, so a reader can follow one to the other.

THE WORKED EXAMPLE the specification gives, and which several cases below use:

    1 branch = 22 kg, price 92,560 IRR/branch  ->  4,207.27... IRR/kg

The direction matters more than the precision: multiplying by 22 instead of dividing gives
2,036,320 IRR/kg, which is 484 times the truth and looks like an ordinary large number.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.daily_estimate import (
    CONVERSION_RULE_REQUIRED, CONVERTIBLE_BY_REGISTRY, DAILY_PRICE_MISSING,
    DAILY_PRICE_UNIT_MISSING, INCOMPATIBLE, MATCHED, QUANTITY_MISSING, READY,
    UNIT_SELECTION_REQUIRED, calculate_daily_estimate, effective_daily_quantity,
    initial_cost, match_units)


def rule(factor="22", from_unit="branch", to_unit="kg", **over):
    """An approved factor rule as the resolver hands it to the domain."""
    return dict({"id": "rule-1", "version": 1, "conversion_method": "factor",
                 "factor_value": Decimal(factor), "from_unit": from_unit,
                 "to_unit": to_unit}, **over)


def estimate(**over):
    return calculate_daily_estimate(**dict(
        {"quantity": Decimal("100"), "daily_quantity": None,
         "initial_unit_price_irr": Decimal("50000"),
         "authoritative_initial_cost_irr": None,
         "daily_unit_price_irr": Decimal("92560"),
         "resource_unit": "kg", "daily_price_unit": "kg", "conversion_rule": None}, **over))


# ------------------------------------------------------------------ 16.1 quantity

class QuantityTests(unittest.TestCase):
    def test_1_daily_quantity_overrides_quantity(self):
        value, source = effective_daily_quantity(Decimal("100"), Decimal("80"))
        self.assertEqual(Decimal("80"), value)
        self.assertEqual("daily_quantity", source)

    def test_2_a_daily_quantity_of_zero_overrides_quantity(self):
        # The trap: `if daily_quantity:` turns a stated zero into a fallback to 100, which
        # is the opposite of what the person entering it meant.
        value, source = effective_daily_quantity(Decimal("100"), Decimal("0"))
        self.assertEqual(Decimal("0"), value)
        self.assertEqual("daily_quantity", source)

    def test_3_a_null_daily_quantity_falls_back_to_quantity(self):
        value, source = effective_daily_quantity(Decimal("100"), None)
        self.assertEqual(Decimal("100"), value)
        self.assertEqual("quantity", source)

    def test_4_neither_quantity_reports_quantity_missing(self):
        answer = estimate(quantity=None, daily_quantity=None)
        self.assertEqual(QUANTITY_MISSING, answer.calculation_status)
        self.assertIsNone(answer.daily_estimated_cost_irr)
        self.assertIsNone(answer.effective_daily_quantity)

    def test_7_a_zero_daily_quantity_produces_a_real_zero_cost(self):
        # Zero is a valid answer and the only way a daily cost may legitimately be zero.
        answer = estimate(daily_quantity=Decimal("0"))
        self.assertEqual(READY, answer.calculation_status)
        self.assertEqual(Decimal("0"), answer.daily_estimated_cost_irr)

    def test_a_missing_input_is_null_and_never_zero(self):
        for over in ({"quantity": None, "daily_quantity": None},
                     {"daily_unit_price_irr": None},
                     {"resource_unit": None},
                     {"daily_price_unit": None}):
            answer = estimate(**over)
            self.assertIsNone(answer.daily_estimated_cost_irr, over)


# --------------------------------------------------------------- 16.2 same unit

class SameUnitTests(unittest.TestCase):
    def test_10_kg_and_kg_are_an_identity_not_a_conversion(self):
        answer = estimate(resource_unit="kg", daily_price_unit="kg")
        self.assertEqual(MATCHED, answer.unit_match_status)
        self.assertFalse(answer.unit_mismatch)
        self.assertEqual(Decimal("1"), answer.conversion_multiplier)

    def test_12_the_same_unit_calculation_is_quantity_times_price(self):
        answer = estimate(quantity=Decimal("100"), daily_unit_price_irr=Decimal("92560"))
        self.assertEqual(Decimal("9256000"), answer.daily_estimated_cost_irr)

    def test_12b_the_daily_quantity_is_what_is_multiplied(self):
        answer = estimate(quantity=Decimal("100"), daily_quantity=Decimal("80"),
                          daily_unit_price_irr=Decimal("92560"))
        self.assertEqual(Decimal("7404800"), answer.daily_estimated_cost_irr)


# ---------------------------------------------------------- 16.3 registry conversion

class RegistryConversionTests(unittest.TestCase):
    def test_13_kg_to_ton_uses_the_registry_and_needs_no_rule(self):
        answer = estimate(resource_unit="kg", daily_price_unit="ton",
                          daily_unit_price_irr=Decimal("1000000"))
        self.assertEqual(CONVERTIBLE_BY_REGISTRY, answer.unit_match_status)
        self.assertEqual("unit_registry", "unit_registry")
        self.assertIsNone(answer.applied_conversion_rule_id)

    def test_14_the_price_direction_is_inverse_to_the_quantity_direction(self):
        # A tonne is 1000 kg, so a price PER tonne is a thousandth per kilogram.
        answer = estimate(resource_unit="kg", daily_price_unit="ton",
                          daily_unit_price_irr=Decimal("1000000"))
        self.assertEqual(Decimal("1000"), answer.converted_daily_unit_price_irr)

    def test_15_decimal_precision_is_exact(self):
        answer = estimate(quantity=Decimal("3"), resource_unit="g",
                          daily_price_unit="kg", daily_unit_price_irr=Decimal("10000"))
        self.assertEqual(Decimal("10"), answer.converted_daily_unit_price_irr)
        self.assertEqual(Decimal("30"), answer.daily_estimated_cost_irr)


# ------------------------------------------------------- 16.4 unresolved mismatch

class UnresolvedMismatchTests(unittest.TestCase):
    def test_16_branch_to_kg_without_a_rule_refuses_and_says_where_to_go(self):
        answer = estimate(resource_unit="kg", daily_price_unit="branch")
        self.assertEqual(CONVERSION_RULE_REQUIRED, answer.calculation_status)
        self.assertIsNone(answer.daily_estimated_cost_irr)
        self.assertIsNone(answer.converted_daily_unit_price_irr)
        self.assertTrue(answer.unit_mismatch)
        self.assertTrue(answer.conversion_rule_required)
        self.assertEqual("define_conversion_rule", answer.action_required)
        self.assertEqual("project_financial_settings", answer.action_target)

    def test_16b_the_refusal_carries_a_sentence_the_person_can_act_on(self):
        answer = estimate(resource_unit="kg", daily_price_unit="branch")
        self.assertIn("تنظیمات مالی پروژه", answer.user_message_fa)
        self.assertIn("branch", answer.calculation_reason)
        self.assertIn("kg", answer.calculation_reason)

    def test_16c_a_factor_of_one_is_never_applied_to_hide_a_mismatch(self):
        answer = estimate(resource_unit="kg", daily_price_unit="branch")
        self.assertIsNone(answer.conversion_multiplier)

    def test_20_a_missing_resource_unit_asks_for_a_unit_not_for_a_rule(self):
        answer = estimate(resource_unit=None)
        self.assertEqual(UNIT_SELECTION_REQUIRED, answer.calculation_status)
        self.assertTrue(answer.unit_selection_required)
        self.assertEqual("select_unit", answer.action_required)

    def test_21_a_missing_daily_price_unit_is_its_own_answer(self):
        answer = estimate(daily_price_unit=None)
        self.assertEqual(DAILY_PRICE_UNIT_MISSING, answer.calculation_status)
        self.assertIsNone(answer.daily_estimated_cost_irr)

    def test_a_crossing_nobody_could_measure_says_so_differently(self):
        # There is no number of kilograms in an hour. «ناسازگار» means stop asking;
        # «قانون تبدیل لازم است» means go and measure the product.
        answer = estimate(resource_unit="kg", daily_price_unit="hour")
        self.assertEqual(INCOMPATIBLE, answer.calculation_status)
        self.assertIsNone(answer.action_required)

    def test_10_4_a_missing_daily_price_still_reports_the_initial_estimate(self):
        answer = estimate(daily_unit_price_irr=None)
        self.assertEqual(DAILY_PRICE_MISSING, answer.calculation_status)
        self.assertIsNone(answer.daily_estimated_cost_irr)
        # The estimate is a different answer and survives.
        self.assertEqual(Decimal("5000000"), answer.initial_estimated_cost_irr)


# ------------------------------------------------------------- 16.5 factor rules

class FactorRuleTests(unittest.TestCase):
    def test_22_23_a_branch_of_22_kilograms_prices_the_kilogram(self):
        answer = estimate(resource_unit="kg", daily_price_unit="branch",
                          daily_unit_price_irr=Decimal("92560"), conversion_rule=rule())
        self.assertEqual(READY, answer.calculation_status)
        self.assertEqual(Decimal("4207.27272727"), answer.converted_daily_unit_price_irr)

    def test_24_the_direction_is_division_and_not_multiplication(self):
        answer = estimate(resource_unit="kg", daily_price_unit="branch",
                          daily_unit_price_irr=Decimal("92560"), conversion_rule=rule())
        # Multiplying would give 2,036,320 -- 484 times the truth, and plausible-looking.
        self.assertNotEqual(Decimal("2036320"), answer.converted_daily_unit_price_irr)
        self.assertLess(answer.converted_daily_unit_price_irr, Decimal("92560"))

    def test_23b_the_cost_is_the_quantity_times_the_converted_price(self):
        answer = estimate(quantity=Decimal("100"), resource_unit="kg",
                          daily_price_unit="branch", daily_unit_price_irr=Decimal("92560"),
                          conversion_rule=rule())
        self.assertEqual(Decimal("420727"), answer.daily_estimated_cost_irr)

    def test_the_applied_rule_is_named_in_the_answer(self):
        answer = estimate(resource_unit="kg", daily_price_unit="branch",
                          conversion_rule=rule(factor="22", id="r-9", version=3))
        self.assertEqual("r-9", answer.applied_conversion_rule_id)
        self.assertEqual(3, answer.applied_conversion_rule_version)
        self.assertEqual(Decimal("22"), answer.conversion_multiplier)

    def test_a_formula_rule_is_storable_and_not_yet_applied(self):
        # The schema is formula-ready; nothing evaluates one, and a half-evaluated formula
        # is worse than an honest refusal.
        answer = estimate(resource_unit="kg", daily_price_unit="branch",
                          conversion_rule=rule(conversion_method="formula",
                                               factor_value=None))
        self.assertEqual(CONVERSION_RULE_REQUIRED, answer.calculation_status)
        self.assertIsNone(answer.daily_estimated_cost_irr)

    def test_a_factor_that_is_not_a_usable_number_refuses(self):
        for bad in (None, Decimal("0"), Decimal("-3")):
            answer = estimate(resource_unit="kg", daily_price_unit="branch",
                              conversion_rule=rule(factor_value=bad))
            self.assertEqual(CONVERSION_RULE_REQUIRED, answer.calculation_status, bad)

    def test_25_the_reverse_crossing_is_the_mathematical_inverse(self):
        # A line measured in branches, priced per kilogram: 1 kg = 1/22 branch.
        answer = estimate(resource_unit="branch", daily_price_unit="kg",
                          daily_unit_price_irr=Decimal("4207.27272727"),
                          conversion_rule=rule(factor=Decimal(1) / Decimal(22),
                                               from_unit="kg", to_unit="branch"))
        self.assertEqual(READY, answer.calculation_status)
        self.assertAlmostEqual(Decimal("92560"), answer.converted_daily_unit_price_irr,
                               delta=Decimal("0.01"))


# ------------------------------------------------------------- 16.6 initial cost

class InitialCostTests(unittest.TestCase):
    def test_33_an_authoritative_mpp_cost_is_the_total_and_is_not_multiplied_again(self):
        cost, source, _price, _ps = initial_cost(Decimal("100"), Decimal("50000"),
                                                 Decimal("3140000000"))
        self.assertEqual(Decimal("3140000000"), cost)
        self.assertEqual("mpp_assignment_cost", source)

    def test_34_with_no_stated_cost_the_total_is_quantity_times_rate(self):
        cost, source, _price, _ps = initial_cost(Decimal("100"), Decimal("50000"), None)
        self.assertEqual(Decimal("5000000"), cost)
        self.assertEqual("quantity_times_unit_price", source)

    def test_35_the_rate_can_be_derived_from_a_total_and_a_quantity(self):
        cost, _cs, price, source = initial_cost(Decimal("100"), None, Decimal("5000000"))
        self.assertEqual(Decimal("5000000"), cost)
        self.assertEqual(Decimal("50000"), price)
        self.assertEqual("derived_from_mpp_cost_and_quantity", source)

    def test_36_a_zero_quantity_never_becomes_a_division(self):
        cost, _cs, price, source = initial_cost(Decimal("0"), None, Decimal("5000000"))
        self.assertEqual(Decimal("5000000"), cost)
        self.assertIsNone(price)
        self.assertIsNone(source)

    def test_a_stated_rate_is_not_overwritten_by_a_derived_one(self):
        _cost, _cs, price, source = initial_cost(Decimal("100"), Decimal("777"),
                                                 Decimal("5000000"))
        self.assertEqual(Decimal("777"), price)
        self.assertEqual("recorded", source)

    def test_the_estimate_and_the_daily_figure_are_separate_answers(self):
        answer = estimate(quantity=Decimal("100"), initial_unit_price_irr=Decimal("50000"),
                          daily_unit_price_irr=Decimal("92560"))
        self.assertEqual(Decimal("5000000"), answer.initial_estimated_cost_irr)
        self.assertEqual(Decimal("9256000"), answer.daily_estimated_cost_irr)
        self.assertNotEqual(answer.initial_estimated_cost_irr,
                            answer.daily_estimated_cost_irr)


class UnitMatchingTests(unittest.TestCase):
    def test_the_status_vocabulary_is_exhaustive_for_the_cases_named(self):
        self.assertEqual(MATCHED, match_units("kg", "kg"))
        self.assertEqual(CONVERTIBLE_BY_REGISTRY, match_units("kg", "ton"))
        self.assertEqual(UNIT_SELECTION_REQUIRED, match_units(None, "kg"))
        self.assertEqual(DAILY_PRICE_UNIT_MISSING, match_units("kg", None))
        self.assertEqual(CONVERSION_RULE_REQUIRED, match_units("kg", "branch"))
        self.assertEqual(INCOMPATIBLE, match_units("kg", "hour"))
        self.assertEqual("conversion_rule_available", match_units("kg", "branch", rule()))

    def test_a_unit_outside_the_registry_is_not_a_unit(self):
        # «واحد» and «مترمرکعب» are what this schedule actually carries; neither is a code
        # the system can convert, and treating them as one would be inventing a vocabulary.
        self.assertEqual(UNIT_SELECTION_REQUIRED, match_units("unit", "kg"))
        self.assertEqual(UNIT_SELECTION_REQUIRED, match_units("مترمرکعب", "kg"))


if __name__ == "__main__":
    unittest.main()
