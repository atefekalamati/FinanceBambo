# -*- coding: utf-8 -*-
"""Pricing an MSP activity from the materials somebody says it consumes.

The worked case throughout is «کانال‌کنی»: 500 cubic metres of trenching, an activity the
schedule describes without naming a single material. A Finance user adds what it uses, and
the two ways of saying how much are the thing most worth pinning:

    per_msp_unit    80 kg of rebar PER cubic metre -> 500 x 80 = 40,000 kg
    total_quantity  1,200 metres of pipe for the WHOLE trench -> 1,200 m

Those differ by a factor of 500 on the same number, and nothing in the figures says which
was meant. It is the user's statement and this module never guesses it.

The rest is about totals that are honest: a row where one material is unpriced reports the
resolved total AND says it is partial, and never reports zero for the part it could not
price.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.item_price_components import (INCOMPATIBLE, NEEDS_COMPONENTS,
                                                      NEEDS_FACTOR, NEEDS_PRODUCT,
                                                      NEEDS_UNIT, NEEDS_USAGE_QUANTITY,
                                                      NO_PRICE, PARTIALLY_UNRESOLVED,
                                                      PER_MSP_UNIT, READY, STATUS_LABELS,
                                                      TOTAL_QUANTITY, UNKNOWN_SOURCE_UNIT,
                                                      aggregate_row, price_component)

#: The activity every test below prices: «کانال‌کنی», 500 cubic metres.
TRENCH_QUANTITY = Decimal("500")


def component(**over):
    """One material of the line. Rebar per cubic metre unless a test says otherwise."""
    return dict({
        "component_id": "c1",
        "provider_item_id": "11111111-1111-4111-8111-111111111111",
        "selected_unit": "kg",
        "usage_mode": PER_MSP_UNIT,
        "usage_quantity": "80",
    }, **over)


def priced(price="1014600", source="kg", quantity=TRENCH_QUANTITY, factor=None, **over):
    return price_component(component=component(**over), price_irr=price,
                           source_unit=source, msp_quantity=quantity, factor=factor)


class TheTwoUsageModesTests(unittest.TestCase):
    def test_per_msp_unit_multiplies_by_the_activity_quantity(self):
        # 80 kg per cubic metre, 500 cubic metres -> 40,000 kg.
        result = priced()
        self.assertEqual(READY, result.status)
        self.assertEqual(Decimal("40000"), result.quantity)
        self.assertEqual(Decimal("1014600"), result.unit_price_irr)
        self.assertEqual(Decimal("40584000000"), result.cost_irr)

    def test_total_quantity_is_the_whole_line_however_big_it_is(self):
        # 1,200 metres of pipe for the whole trench, whatever the trench measures.
        result = priced(usage_mode=TOTAL_QUANTITY, usage_quantity="1200",
                        selected_unit="m", price="50000", source="m")
        self.assertEqual(READY, result.status)
        self.assertEqual(Decimal("1200"), result.quantity)
        self.assertEqual(Decimal("60000000"), result.cost_irr)

    def test_the_same_number_means_two_different_things(self):
        """The distinction cannot be inferred, so it must be stored. This proves why.

        The same usage figure, the same price, the same line -- and the two modes differ by
        the activity quantity, which is 500 here.
        """
        per_unit = priced(usage_quantity="2")
        total = priced(usage_quantity="2", usage_mode=TOTAL_QUANTITY)
        self.assertEqual(Decimal("1000"), per_unit.quantity)
        self.assertEqual(Decimal("2"), total.quantity)
        self.assertEqual(per_unit.quantity, total.quantity * TRENCH_QUANTITY)

    def test_a_total_quantity_prices_even_with_no_activity_quantity(self):
        # It does not depend on the activity's measure, so a schedule that states none
        # must not stop it.
        result = priced(usage_mode=TOTAL_QUANTITY, usage_quantity="1200", quantity=None)
        self.assertEqual(READY, result.status)
        self.assertEqual(Decimal("1200"), result.quantity)

    def test_per_unit_with_no_activity_quantity_states_the_price_and_no_cost(self):
        result = priced(quantity=None)
        self.assertEqual(NEEDS_USAGE_QUANTITY, result.status)
        self.assertIsNotNone(result.unit_price_irr, "the unit price is still known")
        self.assertIsNone(result.cost_irr, "the cost is unknown, and not zero")
        self.assertIn("برنامهٔ زمان‌بندی", result.reason)


class TheConversionTests(unittest.TestCase):
    def test_a_same_dimension_crossing_converts_the_price_inversely(self):
        # A price divides where a quantity multiplies: 1,000/kg is 1/g.
        result = priced(selected_unit="g", price="1000", source="kg", usage_quantity="1")
        self.assertEqual(READY, result.status)
        self.assertEqual(Decimal("1"), result.unit_price_irr)

    def test_a_product_measurement_crosses_a_dimension(self):
        # Pipe quoted per branch, used by the metre: 6 metres in a branch.
        result = priced(selected_unit="m", price="600000", source="branch",
                        usage_mode=TOTAL_QUANTITY, usage_quantity="1200", factor="6")
        self.assertEqual(READY, result.status)
        self.assertEqual(Decimal("100000"), result.unit_price_irr)
        self.assertEqual(Decimal("120000000"), result.cost_irr)

    def test_a_crossing_with_no_measurement_asks_for_one(self):
        result = priced(selected_unit="m", price="600000", source="branch")
        self.assertEqual(NEEDS_FACTOR, result.status)
        self.assertEqual("نیازمند ضریب تبدیل", result.reason)
        self.assertIsNone(result.cost_irr)

    def test_a_crossing_nobody_could_measure_is_incompatible(self):
        result = priced(selected_unit="kg", price="1000", source="hour")
        self.assertEqual(INCOMPATIBLE, result.status)
        self.assertEqual("تبدیل واحد ناسازگار است", result.reason)

    def test_the_usage_factor_is_not_a_unit_conversion(self):
        """«80 kg per m3» is a fact about this activity, not about these units.

        The registry is never asked to cross m3 and kg -- the usage figure does that, and
        it is a number a person entered. Proof: the component's units are kg to kg, and
        the activity's own unit plays no part in the conversion at all.
        """
        result = priced()
        self.assertEqual("kg", result.source_unit)
        self.assertEqual("kg", result.selected_unit)
        self.assertIsNone(result.factor_applied, "no unit factor was needed or used")
        self.assertEqual(Decimal("80"), result.usage_quantity)


class WhatOneComponentRefusesTests(unittest.TestCase):
    def test_no_product(self):
        result = priced(provider_item_id=None)
        self.assertEqual(NEEDS_PRODUCT, result.status)
        self.assertEqual("نیازمند انتخاب محصول قیمت روز", result.reason)

    def test_no_selected_unit(self):
        self.assertEqual(NEEDS_UNIT, priced(selected_unit="").status)

    def test_a_unit_outside_the_registry_is_not_a_unit(self):
        self.assertEqual(NEEDS_UNIT, priced(selected_unit="furlong").status)

    def test_no_usage_quantity(self):
        result = priced(usage_quantity=None)
        self.assertEqual(NEEDS_USAGE_QUANTITY, result.status)
        self.assertEqual("نیازمند مقدار مصرف مصالح", result.reason)

    def test_no_usage_mode(self):
        result = priced(usage_mode=None)
        self.assertEqual(NEEDS_USAGE_QUANTITY, result.status)
        self.assertIn("نحوهٔ مصرف", result.reason)

    def test_no_price(self):
        result = priced(price=None)
        self.assertEqual(NO_PRICE, result.status)
        self.assertEqual("قیمت روز معتبر وجود ندارد", result.reason)

    def test_a_price_whose_own_unit_is_unknown(self):
        result = priced(source=None)
        self.assertEqual(UNKNOWN_SOURCE_UNIT, result.status)
        self.assertEqual("واحد قیمت مبدأ مشخص نیست", result.reason)

    def test_a_usage_of_zero_is_an_answer_and_prices_to_a_real_zero(self):
        # "this line uses none of it" is something somebody can mean. Absent is not.
        result = priced(usage_quantity="0")
        self.assertEqual(READY, result.status)
        self.assertEqual(Decimal(0), result.cost_irr)

    def test_no_refusal_ever_reports_a_cost(self):
        for result in (priced(provider_item_id=None), priced(selected_unit=""),
                       priced(usage_quantity=None), priced(price=None),
                       priced(source=None), priced(selected_unit="m", source="branch"),
                       priced(selected_unit="kg", source="hour")):
            with self.subTest(status=result.status):
                self.assertNotEqual(READY, result.status)
                self.assertIsNone(result.cost_irr)
                self.assertTrue(result.reason)
                self.assertIsNone(result.as_dict()["component_daily_cost_irr"])


class TheRowTotalTests(unittest.TestCase):
    def test_a_line_with_no_components_asks_for_materials(self):
        row = aggregate_row([])
        self.assertEqual(NEEDS_COMPONENTS, row["status"])
        self.assertEqual("نیازمند افزودن مصالح", row["reason"])
        self.assertIsNone(row["daily_item_cost_irr"])
        self.assertEqual(0, row["component_count"])

    def test_the_total_is_the_sum_of_the_components(self):
        """«کانال‌کنی» with rebar and pipe, the two modes side by side.

            rebar  500 m3 x 80 kg/m3 = 40,000 kg x 1,014,600 = 40,584,000,000
            pipe   1,200 m (total)   =  1,200 m  x    50,000 =     60,000,000
                                                        sum = 40,644,000,000
        """
        rebar = priced()
        pipe = priced(component_id="c2", usage_mode=TOTAL_QUANTITY, usage_quantity="1200",
                      selected_unit="m", price="50000", source="m")
        row = aggregate_row([rebar, pipe])
        self.assertEqual(READY, row["status"])
        self.assertEqual(Decimal("40644000000"), Decimal(row["daily_item_cost_irr"]))
        self.assertEqual((2, 2, 0), (row["component_count"], row["ready_component_count"],
                                     row["unresolved_component_count"]))

    def test_one_unresolved_component_does_not_erase_the_others(self):
        rebar = priced()
        unpriceable = priced(component_id="c2", selected_unit="m", source="branch")
        row = aggregate_row([rebar, unpriceable])
        self.assertEqual(PARTIALLY_UNRESOLVED, row["status"])
        self.assertEqual("بخشی از اجزای قیمت‌گذاری ناقص است", row["status_label"])
        # The resolved half is real and is reported.
        self.assertEqual(Decimal("40584000000"), Decimal(row["daily_item_cost_irr"]))
        self.assertEqual((2, 1, 1), (row["component_count"], row["ready_component_count"],
                                     row["unresolved_component_count"]))

    def test_a_partial_row_says_which_answer_is_missing(self):
        row = aggregate_row([priced(), priced(component_id="c2", selected_unit="m",
                                              source="branch")])
        self.assertIn("بخشی از اجزای قیمت‌گذاری ناقص است", row["reason"])
        self.assertIn("نیازمند ضریب تبدیل", row["reason"],
                      "the reader is told what to do, not just that something is wrong")

    def test_a_row_where_nothing_resolved_reports_no_total(self):
        # Not zero. A row whose every material is unpriced has no cost, and «۰» would say
        # the activity is free.
        row = aggregate_row([priced(price=None),
                             priced(component_id="c2", usage_quantity=None)])
        self.assertIsNone(row["daily_item_cost_irr"])
        self.assertNotEqual(PARTIALLY_UNRESOLVED, row["status"],
                            "with nothing resolved it is not partial, it is that failure")
        self.assertEqual(0, row["ready_component_count"])

    def test_distinct_reasons_are_listed_once(self):
        row = aggregate_row([priced(), priced(component_id="c2", price=None),
                             priced(component_id="c3", price=None)])
        self.assertEqual(1, row["reason"].count("قیمت روز معتبر وجود ندارد"))

    def test_a_zero_cost_component_still_counts_as_ready(self):
        row = aggregate_row([priced(usage_quantity="0")])
        self.assertEqual(READY, row["status"])
        self.assertEqual(Decimal(0), Decimal(row["daily_item_cost_irr"]))


class TheVocabularyTests(unittest.TestCase):
    def test_every_status_the_specification_names_has_a_label(self):
        self.assertEqual(
            {"آماده", "نیازمند افزودن مصالح", "نیازمند انتخاب نوع محصول",
             "نیازمند انتخاب محصول قیمت روز", "نیازمند انتخاب واحد",
             "نیازمند مقدار مصرف مصالح", "واحد قیمت مبدأ مشخص نیست",
             "نیازمند ضریب تبدیل", "تبدیل واحد ناسازگار است",
             "قیمت روز معتبر وجود ندارد", "بخشی از اجزای قیمت‌گذاری ناقص است"},
            set(STATUS_LABELS.values()))

    def test_money_is_whole_rials_so_the_page_can_render_it(self):
        # `AGENTS.md`: monetary values are integer-IRR strings and every fractional form is
        # rejected, including one with a zero fractional part.
        body = priced(price="1014600", usage_quantity="0.333").as_dict()
        for field in ("converted_daily_unit_price_irr", "component_daily_cost_irr"):
            with self.subTest(field=field):
                self.assertRegex(body[field], r"^-?\d+$")


if __name__ == "__main__":
    unittest.main()
