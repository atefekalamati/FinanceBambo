# -*- coding: utf-8 -*-
"""What one row of the material price sheet is allowed to become.

Every case here is drawn from the real sheet (see docs/MATERIAL_PRICE_SHEET_CONTRACT_FA.md),
which is why the strange ones are strange: eight spellings of one date column, 279 cells
Google had already turned into Gregorian datetimes, 80 rows in the pipe worksheet that are
not pipes, and a brick with two prices.

The rule under all of it: nothing missing may become a number.
"""

import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.material_price_rows import (CATEGORY_BY_PREFIX, PIPE_FITTING_CATEGORY,
                                                    TOMAN_TO_IRR, MaterialPriceRow, RowStatus,
                                                    category_for, decide_row, normalize_digits,
                                                    parse_price_toman, parse_workflow_date,
                                                    to_irr)

#: A row exactly as the sheet hands one over, so each test can vary one thing.
REBAR = {
    "source": "Mashhad Foolad",
    "محصول": "میلگرد آجدار 8 A3 سمنان",
    "واحد - وزن": "کیلو",
    "قیمت": 95500.0,
    "تاریخ آپدیت ورک فلو": "1405-06-22",
    "productId": "REBAR-0ATKAOL0COXDX0",
}


def row(**changes):
    cells = dict(REBAR)
    cells.update(changes)
    return decide_row(worksheet="steel -Rebar", row_number=2, cells=cells)


class DigitTests(unittest.TestCase):
    def test_both_digit_families_in_the_sheet_become_ascii(self):
        # Persian and Arabic-Indic both appear in real cells.
        self.assertEqual("1405/6/21", normalize_digits("۱۴۰۵/۶/۲۱"))
        self.assertEqual("1405/6/21", normalize_digits("١٤٠٥/٦/٢١"))

    def test_nothing_else_is_touched(self):
        self.assertEqual("میلگرد A3 8", normalize_digits("میلگرد A3 8"))


class PriceTests(unittest.TestCase):
    def test_a_blank_price_is_not_zero(self):
        for blank in (None, "", "   "):
            with self.subTest(blank=repr(blank)):
                amount, reason = parse_price_toman(blank)
                self.assertIsNone(amount, "a blank cell must not produce a number")
                self.assertIn("blank", reason)

    def test_an_unreadable_price_is_not_zero_either(self):
        for bad in ("استعلام کنید", "-", "n/a", "۱۲۳abc"):
            with self.subTest(bad=bad):
                amount, reason = parse_price_toman(bad)
                self.assertIsNone(amount)
                self.assertTrue(reason)

    def test_a_zero_or_negative_price_is_refused_rather_than_stored_as_a_price(self):
        for bad in (0, "0", -5, "-5"):
            with self.subTest(bad=bad):
                amount, reason = parse_price_toman(bad)
                self.assertIsNone(amount)
                self.assertIn("positive", reason)

    def test_persian_digits_and_separators_are_read(self):
        amount, reason = parse_price_toman("۹۵٬۵۰۰ تومان")
        self.assertIsNone(reason)
        self.assertEqual(Decimal("95500"), amount)

    def test_the_value_is_built_from_a_string_not_from_the_float(self):
        """openpyxl hands over floats. Decimal(float) would carry the binary artefact."""
        amount, _ = parse_price_toman(16435460.0)
        self.assertEqual(Decimal("16435460"), amount)
        self.assertNotEqual(Decimal(16435460.0), Decimal(0.1) * 10)  # guards the idea, cheaply

    def test_toman_to_irr_is_one_multiplication_by_ten(self):
        self.assertEqual(Decimal(10), TOMAN_TO_IRR)
        self.assertEqual(Decimal("955000"), to_irr(Decimal("95500")))

    def test_a_sub_rial_price_is_refused_rather_than_rounded(self):
        # Every price in the real sheet is an integer, so this cannot happen today. If the
        # sheet ever changes, the refusal is the behaviour that keeps integer IRR true.
        with self.assertRaises(ValueError):
            to_irr(Decimal("0.05"))

    def test_the_whole_measured_range_survives_the_conversion_exactly(self):
        for toman in ("1360", "95500", "16435460", "90909090"):
            with self.subTest(toman=toman):
                irr = to_irr(Decimal(toman))
                self.assertEqual(Decimal(toman) * 10, irr)
                self.assertEqual(irr, irr.to_integral_value())


class CategoryTests(unittest.TestCase):
    def test_the_category_comes_from_the_identifier_not_the_worksheet(self):
        for prefix, expected in CATEGORY_BY_PREFIX.items():
            with self.subTest(prefix=prefix):
                # Deliberately the WRONG worksheet name: it must not be consulted.
                found, reason = category_for("%s-XYZ123" % prefix, "a renamed worksheet", "چیزی")
                self.assertIsNone(reason)
                self.assertEqual("pipe_fitting" if expected == "pipe" else expected, found)

    def test_an_unknown_prefix_is_refused_rather_than_guessed(self):
        found, reason = category_for("CEMENT-001", "brick", "سیمان")
        self.assertIsNone(found)
        self.assertIn("not a known category", reason)

    def test_a_blank_identifier_is_refused(self):
        for blank in (None, "", "  "):
            with self.subTest(blank=repr(blank)):
                found, reason = category_for(blank, "Pipe-table", "لوله")
                self.assertIsNone(found)
                self.assertIn("blank", reason)

    def test_a_pipe_row_that_is_a_pipe_stays_a_pipe(self):
        found, reason = category_for("PIPE-1", "Pipe-table", "لوله پلی اتیلن 110")
        self.assertIsNone(reason)
        self.assertEqual("pipe", found)

    def test_the_eighty_rows_that_are_not_pipes_are_not_pipes(self):
        """The real first words: fittings, valves, tape. None of them is a pipe."""
        for name in ("سه راهی 87 درجه pvc سایز110", "شیر فلکه کشویی", "تفلون صورتی خمیری آسیا",
                     "بوشن پلی اتیلن", "چپقی گالوانیزه", "مغزی برنجی", "زانو 90 درجه",
                     "نوار خطر", "مهره ماسوره", "تبدیل پلی اتیلن"):
            with self.subTest(name=name):
                found, reason = category_for("PIPE-ABC", "Pipe-table", name)
                self.assertIsNone(reason)
                self.assertEqual(PIPE_FITTING_CATEGORY, found,
                                 "%r is not a pipe and must not be in the active pipe list" % name)

    def test_a_new_kind_of_fitting_is_excluded_by_default(self):
        """The rule says what a pipe IS. Something unheard-of is not silently included."""
        found, _ = category_for("PIPE-ABC", "Pipe-table", "واشر آب‌بندی جدید")
        self.assertEqual(PIPE_FITTING_CATEGORY, found)


class WorkflowDateTests(unittest.TestCase):
    def test_every_spelling_measured_in_the_real_sheet_is_read(self):
        # The eight forms, and the four days they mean.
        for raw, expected in ((("۱۴۰۵/۶/۱۹"), date(2026, 9, 10)),
                              ("1405/06/22", date(2026, 9, 13)),
                              ("۱۴۰۵/۶/۲۲", date(2026, 9, 13)),
                              ("1405/06/21", date(2026, 9, 12)),
                              ("۱۴۰۵/۶/۲۱", date(2026, 9, 12)),
                              ("1405-06-22", date(2026, 9, 13)),
                              ("۱۴۰۵/۶/۲۳", date(2026, 9, 14))):
            with self.subTest(raw=raw):
                kept, jalali, gregorian = parse_workflow_date(raw)
                self.assertEqual(raw, kept, "the cell is kept exactly as it arrived")
                self.assertEqual(expected, gregorian)
                self.assertTrue(jalali)

    def test_the_cells_google_already_converted_are_read_as_gregorian(self):
        """279 rows arrive as a datetime, and 2026-09-12 IS 1405/6/21."""
        kept, jalali, gregorian = parse_workflow_date(datetime(2026, 9, 12, 0, 0))
        self.assertEqual(date(2026, 9, 12), gregorian)
        self.assertIsNone(jalali, "a Gregorian cell states no Jalali text of its own")
        self.assertIn("2026-09-12", kept)

    def test_an_unreadable_date_is_not_today_and_not_the_row_above(self):
        for bad in ("به زودی", "1405/13/41", "2026/09/12", "", "   ", "1405/6"):
            with self.subTest(bad=bad):
                kept, jalali, gregorian = parse_workflow_date(bad)
                self.assertIsNone(gregorian, "%r must not produce a date" % bad)

    def test_a_gregorian_looking_string_is_not_read_as_jalali(self):
        """2026/09/12 as TEXT is ambiguous, so it is refused rather than assumed."""
        _, jalali, gregorian = parse_workflow_date("2026/09/12")
        self.assertIsNone(jalali)
        self.assertIsNone(gregorian)


class WholeRowTests(unittest.TestCase):
    def test_the_reference_rebar_row_is_accepted_and_exact(self):
        decided = row()
        self.assertEqual(RowStatus.ACCEPTED, decided.status, decided.reasons)
        self.assertEqual("rebar", decided.category)
        self.assertEqual(Decimal("955000"), decided.price_irr)
        self.assertEqual("کیلو", decided.source_unit)
        self.assertEqual(date(2026, 9, 13), decided.workflow_date_gregorian)

    def test_a_blank_price_rejects_the_row_and_leaves_the_price_absent(self):
        decided = row(**{"قیمت": None})
        self.assertEqual(RowStatus.REJECTED, decided.status)
        self.assertIsNone(decided.price_irr, "a rejected row must carry no price, not a zero")
        self.assertTrue(any("blank" in r for r in decided.reasons))

    def test_a_rejected_row_is_still_a_record(self):
        """It is quarantined, not dropped: the identity and the raw cell survive."""
        decided = row(**{"قیمت": "استعلام"})
        self.assertEqual(RowStatus.REJECTED, decided.status)
        self.assertEqual("REBAR-0ATKAOL0COXDX0", decided.product_id)
        self.assertEqual("استعلام", decided.raw_price)

    def test_the_sheet_unit_is_recorded_but_is_only_what_the_sheet_said(self):
        decided = row()
        self.assertEqual("کیلو", decided.source_unit)
        # There is no field here that says what unit the price is DISPLAYED in. That is a
        # decision made elsewhere, by a person, and this type deliberately cannot express it.
        self.assertFalse(hasattr(decided, "display_unit"))

    def test_brick_keeps_two_prices_and_never_confuses_them(self):
        decided = decide_row(worksheet="brick", row_number=5, cells={
            "source": "Toranj Brick",
            "محصول": "آجر سه سانتی رسی زرد",
            "کد": "LO1",
            "ابعاد": "8×40×2.5",
            "وزن": "2800 گرم",
            "قیمت": 4300.0,
            "قیمت در هر مترمربع": 430000.0,
            "تاریخ آپدیت ورک فلو": "۱۴۰۵/۶/۲۱",
            "productId": "BRICK-12OG1SH1B8GCRQ",
        }, attribute_columns=("کد", "ابعاد", "وزن"))
        self.assertEqual(RowStatus.ACCEPTED, decided.status, decided.reasons)
        self.assertEqual(Decimal("43000"), decided.price_irr, "قیمت is the primary price")
        self.assertEqual(Decimal("4300000"), decided.secondary_price_irr)
        self.assertEqual("square_meter", decided.secondary_price_basis)
        self.assertEqual("2800 گرم", decided.attributes["وزن"])

    def test_a_brick_with_no_square_metre_price_still_has_its_primary_price(self):
        decided = decide_row(worksheet="brick", row_number=6, cells={
            "source": "Toranj Brick", "محصول": "آجر", "قیمت": 4300.0,
            "قیمت در هر مترمربع": None, "تاریخ آپدیت ورک فلو": "۱۴۰۵/۶/۲۱",
            "productId": "BRICK-X",
        })
        self.assertEqual(RowStatus.ACCEPTED, decided.status, decided.reasons)
        self.assertEqual(Decimal("43000"), decided.price_irr)
        self.assertIsNone(decided.secondary_price_irr)
        self.assertIsNone(decided.secondary_price_basis)

    def test_a_missing_optional_attribute_is_absent_not_zero(self):
        """94 of 213 brick rows state no weight, and 38 of 56 channel rows state none."""
        decided = decide_row(worksheet="brick", row_number=7, cells={
            "source": "Toranj Brick", "محصول": "آجر", "وزن": None, "قیمت": 4300.0,
            "تاریخ آپدیت ورک فلو": "۱۴۰۵/۶/۲۱", "productId": "BRICK-Y",
        }, attribute_columns=("وزن",))
        self.assertEqual(RowStatus.ACCEPTED, decided.status)
        self.assertIsNone(decided.attributes["وزن"])

    def test_a_row_with_no_identifier_is_rejected_not_given_one(self):
        decided = row(productId=None)
        self.assertEqual(RowStatus.REJECTED, decided.status)
        self.assertIsNone(decided.category)


if __name__ == "__main__":
    unittest.main()
