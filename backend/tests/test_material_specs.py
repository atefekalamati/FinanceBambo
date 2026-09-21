# -*- coding: utf-8 -*-
"""What may be read out of a worksheet cell, and what must not be.

Every fixture here is a value shape MEASURED in `bambo_canonical_test`, not an invented
one. The two that shaped the whole module:

    «وزن - کیلوگرم» on ibeam holds a number on 69 rows and «وارداتی» or «ترک-کره» on 34.
    «وزن» states «گرم» on brick and states nothing at all on angle.

A parser that coerced either would produce a plausible, wrong number.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.material_specs import (SPEC_MAP, WEIGHT_BASES, conflicts_with,
                                               extract_specs, normalize_digits,
                                               parse_number, parse_number_with_unit,
                                               to_metres)


class NumberParsingTests(unittest.TestCase):
    def test_13_persian_and_arabic_digits_are_normalized(self):
        self.assertEqual("1405", normalize_digits("۱۴۰۵"))
        self.assertEqual("1405", normalize_digits("١٤٠٥"))
        self.assertEqual("2.5", normalize_digits("۲٫۵"))
        self.assertEqual(Decimal("2.5"), parse_number("۲٫۵"))

    def test_a_bare_number_is_a_number(self):
        self.assertEqual(Decimal("27"), parse_number("27"))
        self.assertEqual(Decimal("2.5"), parse_number("2.5"))
        self.assertEqual(Decimal("190"), parse_number("190.0"))

    def test_text_in_a_numeric_column_is_refused_not_salvaged(self):
        # Real values from the ibeam sheet's «وزن - کیلوگرم» column.
        for text in ("وارداتی", "ترک-کره", "", None, "-", "ناموجود", "تماس بگیرید"):
            self.assertIsNone(parse_number(text), text)

    def test_nan_and_infinity_are_not_measurements(self):
        # `numeric` accepts both; neither is a weight.
        for text in ("NaN", "nan", "Infinity", "-Infinity", "inf"):
            self.assertIsNone(parse_number(text), text)

    def test_a_number_that_carries_no_unit_keeps_none(self):
        # «27» in a column called «وزن» is a kilogram or a gram, and the difference is a
        # factor of a thousand. Neither may be assumed.
        value, unit = parse_number_with_unit("27")
        self.assertEqual(Decimal("27"), value)
        self.assertIsNone(unit)

    def test_a_unit_the_cell_states_is_read(self):
        self.assertEqual((Decimal("6"), "m"), parse_number_with_unit("6 متر"))
        self.assertEqual((Decimal("12"), "m"), parse_number_with_unit("12 متری"))
        self.assertEqual((Decimal("1150"), "g"), parse_number_with_unit("1150 گرم"))
        self.assertEqual((Decimal("27"), "kg"), parse_number_with_unit("27 کیلو"))

    def test_a_unit_the_column_name_declares_is_used_only_when_declared(self):
        self.assertEqual((Decimal("190"), "kg"),
                         parse_number_with_unit("190.0", default_unit="kg"))
        self.assertEqual((Decimal("190"), None), parse_number_with_unit("190.0"))

    def test_a_trailing_word_this_module_cannot_name_leaves_the_unit_null(self):
        # The number is still what the sheet says. The unit is not.
        value, unit = parse_number_with_unit("6 فوت")
        self.assertEqual(Decimal("6"), value)
        self.assertIsNone(unit)

    def test_length_normalizes_only_through_the_registry_ratios(self):
        self.assertEqual(Decimal("6"), to_metres(Decimal("6"), "m"))
        self.assertEqual(Decimal("0.006"), to_metres(Decimal("6"), "mm"))
        self.assertEqual(Decimal("0.06"), to_metres(Decimal("6"), "cm"))
        self.assertIsNone(to_metres(Decimal("6"), None))
        self.assertIsNone(to_metres(Decimal("6"), "kg"))


class ExtractionTests(unittest.TestCase):
    def test_16_17_18_an_angle_yields_weight_length_and_thickness(self):
        values, _ = extract_specs("angle", {
            "ضخامت": "5.0", "طول": "6 متر", "وزن": "27.0", "تعداد شاخه": "80.0"})
        self.assertEqual(Decimal("5.0"), values["thickness_value"])
        self.assertEqual(Decimal("6"), values["length_value"])
        # The unit «متر» was read and is recorded where it survives: `length_m`. Since 0033
        # there is no `length_unit` column to put it in -- it said 'm' on every row that
        # ever had one, beside a value already normalised to metres.
        self.assertNotIn("length_unit", values)
        self.assertEqual(Decimal("6"), values["length_m"])
        # And NO weight. The angle worksheet writes its weight as a bare `27.0` with no
        # unit anywhere on the row, so there is nothing to state kilograms from -- the 48
        # angle listings in the database are exactly this case. Reading it as 27 kg because
        # the neighbouring worksheets use kilograms is the guess this model exists to
        # refuse; the number is reported as a conflict instead.
        self.assertEqual(Decimal("27.0"), values["weight_value"])
        self.assertNotIn("weight_kg", values)
        self.assertEqual([{"field": "weight", "raw": "27.0", "unit": None,
                           "reason": "weight has no unit, so it cannot be stated in kilograms"}],
                         values["spec_conflicts"])
        self.assertEqual(Decimal("80.0"), values["branch_count"])

    def test_19_a_weight_no_sheet_gives_a_basis_for_is_marked_unknown(self):
        # An unknown basis is a value a conversion must refuse, not one it may use. Asked
        # of a sheet that states the unit, because a weight with no unit does not reach a
        # basis at all -- see the angle case above.
        values, _ = extract_specs("brick", {"وزن": "1150 گرم"})
        self.assertEqual("unknown", values["weight_basis"])
        self.assertIn("unknown", WEIGHT_BASES)
        self.assertNotIn("weight_per_branch_kg", values)
        self.assertNotIn("weight_per_meter_kg", values)

    def test_a_weight_stated_in_grams_is_stored_in_kilograms(self):
        """1150 g is 1.15 kg. The sheet's unit is READ, used, and then spent.

        Storing `1150` beside a `g` was what 0034 removed: two fields meant a reader could
        take the first and miss the second, and 1150 kg of brick is a brick the size of a
        car.
        """
        values, _ = extract_specs("brick", {"وزن": "1150 گرم"})
        self.assertEqual(Decimal("1150"), values["weight_value"])
        self.assertEqual(Decimal("1.150"), values["weight_kg"])
        self.assertNotIn("weight_unit", values)

    def test_a_weight_whose_cell_states_no_unit_yields_no_weight_at_all(self):
        """The 84 rows. A number with no unit is not a weight, it is a number."""
        values, _ = extract_specs("angle", {"وزن": "27.0"})
        self.assertEqual(Decimal("27.0"), values["weight_value"])
        self.assertNotIn("weight_kg", values)
        self.assertEqual("unknown", values["weight_basis"])
        self.assertEqual("weight", values["spec_conflicts"][0]["field"])

    def test_an_origin_in_the_weight_column_becomes_a_manufacturer(self):
        # 34 of 103 ibeam rows do this. Coercing would have produced a null weight and
        # lost the only thing the cell actually said.
        values, leftovers = extract_specs("ibeam", {"وزن - کیلوگرم": "وارداتی"})
        self.assertEqual("وارداتی", values["manufacturer"])
        self.assertNotIn("weight_kg", values)
        self.assertEqual({}, leftovers)

    def test_a_number_in_that_same_column_is_a_weight_in_kilograms(self):
        """Here the COLUMN NAME states the unit, which is evidence like any other."""
        values, _ = extract_specs("ibeam", {"وزن - کیلوگرم": "190.0"})
        self.assertEqual(Decimal("190"), values["weight_kg"])
        self.assertNotIn("weight_unit", values)

    def test_dimensions_stay_text_because_nobody_declared_the_order(self):
        # «7×33×2.5» -- width first or thickness first is the difference between a 7mm
        # brick and a 2.5mm one, and no sheet says which.
        values, _ = extract_specs("brick", {"ابعاد": "7×33×2.5"})
        self.assertEqual("7×33×2.5", values["dimensions_text"])
        for derived in ("width_value", "height_value", "thickness_value"):
            self.assertNotIn(derived, values)

    def test_21_an_unclaimed_key_stays_in_metadata(self):
        values, leftovers = extract_specs("brick", {
            "کد": "LP1", "قیمت در هر مترمربع": "526500.0", "چیز تازه": "۵"})
        self.assertEqual("LP1", values["product_code"])
        # A price is not a specification, and an unrecognised column is not lost.
        self.assertEqual({"قیمت در هر مترمربع": "526500.0", "چیز تازه": "۵"}, leftovers)

    def test_15_20_a_sheet_that_states_nothing_yields_nothing(self):
        # pipe and pipe_fitting -- 2,296 of the 3,707 listings -- carry no metadata at all.
        values, leftovers = extract_specs("pipe", {})
        self.assertEqual({}, values)
        self.assertEqual({}, leftovers)
        # And a missing specification is absent, never zero.
        values, _ = extract_specs("angle", {"ضخامت": ""})
        self.assertNotIn("thickness_value", values)

    def test_a_category_with_no_declaration_extracts_nothing(self):
        values, leftovers = extract_specs("rebar", {"واحد - وزن": "کیلو"})
        self.assertEqual({}, values)
        self.assertEqual({"واحد - وزن": "کیلو"}, leftovers)

    def test_an_unknown_category_is_not_guessed_at(self):
        values, leftovers = extract_specs("something_new", {"وزن": "27"})
        self.assertEqual({}, values)
        self.assertEqual({"وزن": "27"}, leftovers)

    def test_the_declaration_only_names_columns_the_schema_has(self):
        allowed = {
            "product_code", "manufacturer", "grade", "product_type", "dimensions_text",
            "length_value", "width_value", "height_value", "thickness_value",
            "diameter_value", "weight_value", "branch_count", "pieces_per_package",
            "coverage_m2", "volume_m3"}
        for category, rules in SPEC_MAP.items():
            for key, rule in rules.items():
                self.assertIn(rule["column"], allowed, "%s/%s" % (category, key))
                if rule.get("text_column"):
                    self.assertIn(rule["text_column"], allowed, "%s/%s" % (category, key))


class ConflictTests(unittest.TestCase):
    def test_23_a_different_value_is_a_finding_not_an_overwrite(self):
        # Yesterday 22, today 220. A parser or a source has gone wrong far more often than
        # a product has changed weight by a factor of ten.
        found = conflicts_with({"weight_value": Decimal("22")}, {"weight_value": Decimal("220")})
        self.assertEqual({"weight_value": {"stored": "22", "incoming": "220"}}, found)

    def test_a_null_existing_value_may_be_populated(self):
        self.assertEqual({}, conflicts_with({"weight_value": None},
                                            {"weight_value": Decimal("22")}))
        self.assertEqual({}, conflicts_with({}, {"weight_value": Decimal("22")}))

    def test_the_same_value_written_differently_is_not_a_conflict(self):
        self.assertEqual({}, conflicts_with({"weight_value": Decimal("22.0")},
                                            {"weight_value": Decimal("22")}))
        self.assertEqual({}, conflicts_with({"dimensions_text": " 7×33×2.5 "},
                                            {"dimensions_text": "7×33×2.5"}))

    def test_every_disagreeing_column_is_reported_not_only_the_first(self):
        found = conflicts_with(
            {"weight_value": Decimal("22"), "length_value": Decimal("6"),
             "product_code": "LP1"},
            {"weight_value": Decimal("220"), "length_value": Decimal("12"),
             "product_code": "LP1"})
        self.assertEqual({"weight_value", "length_value"}, set(found))


if __name__ == "__main__":
    unittest.main()
