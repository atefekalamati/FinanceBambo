# -*- coding: utf-8 -*-
"""The two units this module keeps apart, and the rules that keep them apart.

    source_unit   what a price is PER -- a commercial basis, read from the sheet
    weight_kg     what a product weighs -- a physical attribute, always kilograms

They are different questions and this file asks them separately, because conflating them is
how a price per branch gets multiplied by a weight per metre.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.material_price_rows import (SOURCE_UNIT_HEADERS, RowStatus,
                                                    decide_row)
from app.finance.domain.material_specs import (KILOGRAMS_PER, SPEC_COLUMNS, extract_specs,
                                               to_kilograms)
from app.finance.services.material_price_resolution import canonical_unit, resolve
from app.finance.services.material_price_sheet import check_headers

#: The five columns every worksheet is required to carry, before the unit is added.
CORE = ("source", "محصول", "قیمت", "تاریخ آپدیت ورک فلو", "productId")


def cells(**changes):
    """One sheet row, as the importer receives it."""
    row = {"source": "Mashhad Foolad", "محصول": "میلگرد آجدار 8 A3", "قیمت": 95500.0,
           "تاریخ آپدیت ورک فلو": "1405-06-22", "productId": "REBAR-1",
           "واحد": "کیلو"}
    row.update(changes)
    return {k: v for k, v in row.items() if v is not _ABSENT}


_ABSENT = object()


class PricingUnitHeaderTests(unittest.TestCase):
    """One column, two spellings, and the six worksheets that were lost to the difference."""

    def test_both_spellings_the_workbook_uses_are_accepted(self):
        for heading in SOURCE_UNIT_HEADERS:
            with self.subTest(heading):
                self.assertIsNone(check_headers("any", CORE + (heading,)))

    def test_the_two_spellings_are_exactly_these_two(self):
        """Measured on the live workbook: `واحد` heads the column on I-beam, Angle,
        Channel, Hollow, Pipe and brick; `واحد - وزن` heads it on Rebar alone."""
        self.assertEqual(("واحد", "واحد - وزن"), SOURCE_UNIT_HEADERS)

    def test_a_worksheet_with_no_pricing_unit_column_keeps_source_price(self):
        self.assertIsNone(check_headers("Pipe-table", CORE))

    def test_stating_it_twice_is_refused_because_the_winner_would_be_a_coin_toss(self):
        problem = check_headers("any", CORE + SOURCE_UNIT_HEADERS)
        self.assertIn("states the pricing unit twice", problem)


class PricingUnitRowTests(unittest.TestCase):
    def test_a_row_that_states_a_unit_keeps_exactly_what_it_stated(self):
        """Stored raw. Turning `کیلو` into `kg` is a reading, and the reading belongs to
        the layer that resolves it, not to the record of what the sheet said."""
        decided = decide_row(worksheet="steel -Rebar", row_number=2, cells=cells())
        self.assertEqual(RowStatus.ACCEPTED, decided.status, decided.reasons)
        self.assertEqual("کیلو", decided.source_unit)

    def test_either_spelling_reaches_the_same_field(self):
        for heading in SOURCE_UNIT_HEADERS:
            with self.subTest(heading):
                row = {k: v for k, v in cells().items() if k not in SOURCE_UNIT_HEADERS}
                row[heading] = "عدد"
                decided = decide_row(worksheet="x", row_number=2, cells=row)
                self.assertEqual(RowStatus.ACCEPTED, decided.status, decided.reasons)
                self.assertEqual("عدد", decided.source_unit)

    def test_a_row_with_no_pricing_unit_is_retained_but_not_given_one(self):
        decided = decide_row(worksheet="brick", row_number=2, cells=cells(**{"واحد": None}))
        self.assertEqual(RowStatus.ACCEPTED, decided.status)
        self.assertIsNone(decided.source_unit)
        outcome = resolve({"normalized_price_irr": decided.price_irr,
                           "validation_status": "valid", "source_unit": None})
        self.assertEqual("unresolved_unit", outcome.status)
        self.assertIsNone(outcome.price)

    def test_a_blank_unit_cell_is_the_same_as_no_cell(self):
        for blank in ("", "   "):
            with self.subTest(repr(blank)):
                decided = decide_row(worksheet="brick", row_number=2,
                                     cells=cells(**{"واحد": blank}))
                self.assertEqual(RowStatus.ACCEPTED, decided.status)
                self.assertIsNone(decided.source_unit)

    def test_every_unit_the_live_workbook_states_resolves_to_a_registry_code(self):
        """The whole observed vocabulary, and what each becomes. Four spellings, two codes;
        nothing in the sheet needs a unit this system cannot name."""
        self.assertEqual({"کیلو": "kg", "کیلوگرم": "kg", "kg": "kg", "عدد": "each"},
                         {raw: canonical_unit(raw)
                          for raw in ("کیلو", "کیلوگرم", "kg", "عدد")})


class WeightInKilogramsTests(unittest.TestCase):
    """A physical attribute, in one unit, or absent."""

    def test_grams_become_kilograms(self):
        self.assertEqual(Decimal("1.150"), to_kilograms(Decimal("1150"), "g"))

    def test_kilograms_are_unchanged(self):
        self.assertEqual(Decimal("27"), to_kilograms(Decimal("27"), "kg"))

    def test_tonnes_become_kilograms(self):
        self.assertEqual(Decimal("2000"), to_kilograms(Decimal("2"), "ton"))

    def test_a_weight_with_no_unit_becomes_nothing(self):
        """The 84 Angle and Channel listings. `None` is the answer, not the input."""
        self.assertIsNone(to_kilograms(Decimal("27"), None))

    def test_a_unit_outside_the_vocabulary_becomes_nothing_rather_than_itself(self):
        self.assertIsNone(to_kilograms(Decimal("27"), "stone"))
        self.assertIsNone(to_kilograms(Decimal("27"), ""))

    def test_the_conversion_table_is_the_whole_conversion(self):
        self.assertEqual({"g": Decimal("0.001"), "kg": Decimal(1), "ton": Decimal(1000)},
                         KILOGRAMS_PER)


class WeightExtractionTests(unittest.TestCase):
    def test_a_sheet_that_states_grams_yields_kilograms(self):
        values, _ = extract_specs("brick", {"وزن": "1150 گرم"})
        self.assertEqual(Decimal("1150"), values["weight_value"])
        self.assertEqual(Decimal("1.150"), values["weight_kg"])

    def test_a_column_name_that_states_kilograms_is_evidence_like_any_other(self):
        values, _ = extract_specs("ibeam", {"وزن - کیلوگرم": "190.0"})
        self.assertEqual(Decimal("190.0"), values["weight_value"])
        self.assertEqual(Decimal("190"), values["weight_kg"])

    def test_a_bare_number_yields_no_weight_and_says_why(self):
        values, _ = extract_specs("channel", {"وزن": "24.0"})
        self.assertEqual(Decimal("24.0"), values["weight_value"])
        self.assertNotIn("weight_kg", values)
        self.assertEqual("weight", values["spec_conflicts"][0]["field"])
        self.assertIn("no unit", values["spec_conflicts"][0]["reason"])

    def test_no_unit_column_survives_in_the_published_specification(self):
        """The source number and derived kilograms survive; generic unit columns do not."""
        self.assertIn("weight_value", SPEC_COLUMNS)
        self.assertIn("weight_kg", SPEC_COLUMNS)
        for gone in ("weight_unit", "length_unit", "width_unit",
                     "height_unit", "thickness_unit", "diameter_unit"):
            self.assertNotIn(gone, SPEC_COLUMNS)


class TheTwoUnitsAreNotTheSameUnitTests(unittest.TestCase):
    def test_a_pricing_unit_is_not_a_weight_and_the_sheet_proves_it(self):
        """Pipe and brick price per `عدد`. Reading the pricing column as a weight -- which
        its Rebar heading `واحد - وزن` invites -- would make 125 listings weigh 'each'."""
        decided = decide_row(worksheet="Pipe-table", row_number=2,
                             cells=cells(**{"واحد": "عدد", "productId": "PIPE-1",
                                            "محصول": "لوله پلی اتیلن 110"}))
        self.assertEqual("عدد", decided.source_unit)
        self.assertEqual("each", canonical_unit(decided.source_unit))
        self.assertIsNone(to_kilograms(Decimal("1"), decided.source_unit))

    def test_a_weight_does_not_reach_the_pricing_unit(self):
        values, _ = extract_specs("brick", {"وزن": "1150 گرم"})
        self.assertNotIn("source_unit", values)


if __name__ == "__main__":
    unittest.main()
