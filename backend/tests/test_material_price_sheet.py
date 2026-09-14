# -*- coding: utf-8 -*-
"""The workbook layer: which worksheets may be read, and what stops one being read.

The failure this guards against is not a crash. It is a sheet that lost a column and was
read anyway -- whichever column looked numeric becoming the price. So the tests here are
mostly about refusing, and about refusing loudly enough to name what is missing.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.services.material_price_sheet import (ATTRIBUTE_HEADERS, REQUIRED_HEADERS,
                                                       WORKSHEET_ALLOWLIST, check_headers,
                                                       read_headers, read_workbook,
                                                       read_worksheet)

HEADER = ("source", "محصول", "واحد - وزن", "قیمت", "تاریخ آپدیت ورک فلو", "productId")
ROW = ("Mashhad Foolad", "میلگرد آجدار 8 A3", "کیلو", 95500.0, "1405-06-22", "REBAR-1")


def sheet(header=HEADER, *rows):
    return [header, *(rows or (ROW,))]


class HeaderTests(unittest.TestCase):
    def test_the_export_pads_worksheets_with_empty_columns_and_those_are_not_columns(self):
        """Every worksheet in the real export is padded to 25 or 26 cells with None."""
        padded = HEADER + (None,) * 20
        self.assertEqual(HEADER, read_headers(padded))

    def test_a_gap_in_the_middle_is_kept_because_it_shifts_every_column_after_it(self):
        headers = read_headers(("source", None, "قیمت"))
        self.assertEqual(("source", None, "قیمت"), headers)

    def test_a_worksheet_missing_a_required_column_is_refused_by_name(self):
        for missing in REQUIRED_HEADERS:
            with self.subTest(missing=missing):
                headers = tuple(h for h in HEADER if h != missing)
                problem = check_headers("steel -Rebar", headers)
                self.assertIsNotNone(problem, "%r must stop the worksheet" % missing)
                self.assertIn(missing, problem)

    def test_a_renamed_price_column_is_a_missing_price_column(self):
        headers = tuple("price" if h == "قیمت" else h for h in HEADER)
        problem = check_headers("steel -Rebar", headers)
        self.assertIn("قیمت", problem)

    def test_a_new_column_does_not_stop_the_worksheet(self):
        problem = check_headers("steel -Rebar", HEADER + ("یک ستون تازه",))
        self.assertIsNone(problem, "an extra column is not a reason to refuse a sheet")

    def test_a_repeated_column_is_refused_because_the_winner_would_be_a_coin_toss(self):
        problem = check_headers("steel -Rebar", HEADER + ("قیمت",))
        self.assertIn("repeats", problem)
        self.assertIn("قیمت", problem)

    def test_an_absent_optional_column_is_simply_absent(self):
        headers = tuple(h for h in HEADER if h != "واحد - وزن")
        self.assertIsNone(check_headers("steel -Rebar", headers))


class WorksheetTests(unittest.TestCase):
    def test_a_worksheet_is_read_and_its_rows_decided(self):
        result = read_worksheet("steel -Rebar", sheet())
        self.assertTrue(result.read, result.reason)
        self.assertEqual(1, len(result.accepted))
        self.assertEqual(0, len(result.rejected))

    def test_an_empty_worksheet_is_refused_not_read_as_zero_prices(self):
        result = read_worksheet("steel -Rebar", [])
        self.assertFalse(result.read)
        self.assertIn("empty", result.reason)

    def test_a_header_with_no_rows_under_it_is_refused(self):
        """This is the shape a sheet has while somebody is clearing it."""
        result = read_worksheet("steel -Rebar", [HEADER])
        self.assertFalse(result.read)
        self.assertIn("no data rows", result.reason)

    def test_a_blank_spacer_row_is_skipped_and_is_not_a_rejection(self):
        result = read_worksheet("steel -Rebar", sheet(HEADER, ROW, (None,) * 6, ROW))
        self.assertTrue(result.read)
        self.assertEqual(2, len(result.rows))
        self.assertEqual(0, len(result.rejected))

    def test_a_short_row_does_not_crash_and_its_missing_cells_are_absent(self):
        result = read_worksheet("steel -Rebar", sheet(HEADER, ("Mashhad Foolad", "میلگرد")))
        self.assertTrue(result.read)
        self.assertEqual(1, len(result.rejected), "a row with no price must be rejected")

    def test_a_bad_row_does_not_take_the_good_rows_with_it(self):
        bad = ("Mashhad Foolad", "میلگرد", "کیلو", None, "1405-06-22", "REBAR-2")
        result = read_worksheet("steel -Rebar", sheet(HEADER, ROW, bad))
        self.assertEqual(1, len(result.accepted))
        self.assertEqual(1, len(result.rejected))
        self.assertIsNone(result.rejected[0].price_irr, "and it carries no price, not a zero")

    def test_the_row_number_is_the_worksheet_row_a_person_would_look_at(self):
        result = read_worksheet("steel -Rebar", sheet(HEADER, ROW, ROW))
        self.assertEqual([2, 3], [row.row_number for row in result.rows])


class WorkbookTests(unittest.TestCase):
    def full(self, **overrides):
        book = {title: sheet() for title in WORKSHEET_ALLOWLIST}
        book.update(overrides)
        return book

    def test_the_allowlist_is_the_seven_worksheets_that_were_measured(self):
        self.assertEqual(7, len(WORKSHEET_ALLOWLIST))
        self.assertIn("Pipe-table", WORKSHEET_ALLOWLIST)

    def test_a_complete_workbook_is_complete(self):
        result = read_workbook(self.full())
        self.assertTrue(result.complete, [w.reason for w in result.refused])
        self.assertEqual((), result.missing_titles)

    def test_a_worksheet_that_disappeared_makes_the_workbook_incomplete(self):
        book = self.full()
        del book["brick"]
        result = read_workbook(book)
        self.assertFalse(result.complete)
        self.assertEqual(("brick",), result.missing_titles)

    def test_one_unreadable_worksheet_makes_the_whole_workbook_incomplete(self):
        broken = [tuple(h for h in HEADER if h != "قیمت"), ("Mashhad Foolad", "x", "کیلو", "d", "id")]
        result = read_workbook(self.full(**{"Pipe-table": broken}))
        self.assertFalse(result.complete, "five good worksheets and one refused is not a success")
        self.assertEqual(1, len(result.refused))
        self.assertIn("قیمت", result.refused[0].reason)

    def test_an_emptied_worksheet_makes_the_workbook_incomplete(self):
        """A temporarily empty sheet must never publish an empty price set."""
        result = read_workbook(self.full(**{"brick": [HEADER]}))
        self.assertFalse(result.complete)

    def test_a_new_worksheet_is_reported_rather_than_swept_up(self):
        result = read_workbook(self.full(**{"cement-table": sheet()}))
        self.assertEqual(("cement-table",), result.unknown_titles)
        self.assertTrue(result.complete, "an extra worksheet does not invalidate the seven")
        self.assertNotIn("cement-table", [w.title for w in result.worksheets])

    def test_every_attribute_header_the_sheet_uses_is_in_the_attribute_list(self):
        for header in ("وزن", "وزن - کیلوگرم", "طول", "ضخامت", "ابعاد", "تعداد شاخه",
                       "کد", "واحد - وزن", "قیمت در هر مترمربع"):
            with self.subTest(header=header):
                self.assertIn(header, ATTRIBUTE_HEADERS)


if __name__ == "__main__":
    unittest.main()
