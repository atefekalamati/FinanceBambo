# -*- coding: utf-8 -*-
"""Rebuilding a table from where the words sit.

WHAT WAS LOST AND WHERE

PaddleOCR returns the position of every line it reads. `PaddleOCRProvider._flatten` read
past it -- 2.x's `entry[0]` was skipped to reach `entry[1]`, and 3.x's `rec_polys` was
never asked for -- so an invoice arrived as N strings joined by newlines. A five-column
table flattened that way is a column of fragments in detector order, and "which price
belongs to which product" has no answer left in it. `INVOICE_TABLE_NOT_RECOGNISED` was
the honest report of text that genuinely had no table in it any more.

These tests are built on synthetic geometry rather than on images, deliberately. The
question here is whether positions are turned into rows, columns and cells correctly, and
that question has an exact answer that does not move when a model is upgraded. The real
invoices are exercised in `test_invoice_layout_real_pages.py`, which skips when the images
are not present.

Coordinates below are a Persian invoice's: x grows to the right, the description column is
on the RIGHT because the page reads right to left, and money is on the left.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction import layout


def line(text, left, top, right, bottom, confidence=0.9):
    return {"text": text, "confidence": confidence, "box": (left, top, right, bottom)}


#: Column centres for a five-column invoice, right to left as the page reads.
NAME_X, UNIT_X, QTY_X, PRICE_X, AMOUNT_X = 900, 700, 560, 380, 160


def row_at(y, name, unit, quantity, price, amount, confidence=0.9):
    """One table row, each cell centred under its column."""
    def cell(text, centre, width=120):
        return line(text, centre - width / 2, y, centre + width / 2, y + 28, confidence)
    return [cell(name, NAME_X, 220), cell(unit, UNIT_X), cell(quantity, QTY_X),
            cell(price, PRICE_X), cell(amount, AMOUNT_X)]


HEADER = [line("شرح کالا", 800, 100, 1000, 128),
          line("واحد", 650, 100, 750, 128),
          line("تعداد", 510, 100, 610, 128),
          line("مبلغ واحد ریال", 300, 100, 460, 128),
          line("مبلغ کل ریال", 90, 100, 230, 128)]

BODY = (row_at(160, "سیمان تیپ ۲", "پاکت", "۱۰۰", "۱٬۲۰۰٬۰۰۰", "۱۲۰٬۰۰۰٬۰۰۰")
        + row_at(220, "میلگرد آجدار ۱۴", "کیلوگرم", "۵۰۰۰", "۷۲٬۰۰۰", "۳۶۰٬۰۰۰٬۰۰۰")
        + row_at(280, "ماسه شسته", "مترمکعب", "۲۰", "۵۵۰٬۰۰۰", "۱۱٬۰۰۰٬۰۰۰"))


class NormalisationTests(unittest.TestCase):
    def test_persian_and_arabic_digits_both_become_ascii(self):
        """One page mixes them. The audited invoice has U+06F5 and U+0665 inside one number."""
        self.assertEqual("12345", layout.normalize("۱۲۳٤٥"))

    def test_arabic_letters_fold_to_persian(self):
        """The recogniser returns ي and ك because its model is trained on Arabic. A
        vocabulary written in Persian would match none of it."""
        self.assertEqual("کیلوگرم", layout.normalize("كيلوگرم"))

    def test_zero_width_joiners_and_double_spaces_go(self):
        self.assertEqual("مبلغ کل", layout.normalize("مبلغ‌ کل "))


class HeadingTests(unittest.TestCase):
    def test_each_heading_names_its_column(self):
        for text, expected in (("شرح کالا", "name"), ("عنوان", "name"),
                               ("واحد", "unit"), ("تعداد", "quantity"),
                               ("مقدار", "quantity"), ("مبلغ واحد ریال", "unit_price"),
                               ("فی", "unit_price"), ("مبلغ کل ریال", "amount"),
                               ("ردیف", "row_number")):
            with self.subTest(text):
                self.assertEqual(expected, layout.role_of(text))

    def test_unit_price_is_not_read_as_the_unit_column(self):
        """«واحد» is a substring of «مبلغ واحد». Matching it there would make the unit
        column and the unit-price column the same one, and every row would lose a field."""
        self.assertEqual("unit_price", layout.role_of("مبلغ واحد ریال"))
        self.assertEqual("unit_price", layout.role_of("قیمت واحد"))

    def test_ordinary_prose_names_no_column(self):
        self.assertIsNone(layout.role_of("با تشکر از خرید شما"))
        self.assertIsNone(layout.role_of(""))


class RowGroupingTests(unittest.TestCase):
    def test_lines_that_overlap_vertically_are_one_row(self):
        rows = layout.group_rows(layout.lines_from(BODY))
        self.assertEqual(3, len(rows))
        self.assertEqual(5, len(rows[0]))

    def test_a_row_is_ordered_right_to_left(self):
        """Reading order on a Persian page. A caller sorting ascending would mirror every
        row and put the amount where the description belongs."""
        rows = layout.group_rows(layout.lines_from(BODY))
        self.assertEqual("سیمان تیپ ۲", rows[0][0].text)
        self.assertEqual("۱۲۰٬۰۰۰٬۰۰۰", rows[0][-1].text)

    def test_a_slightly_skewed_scan_still_groups(self):
        """A scan is never level. Rounding y to a grid merges rows at one end of the page
        or splits them at the other; overlap does neither."""
        skewed = [line("سیمان", 880, 160, 1000, 190),
                  line("پاکت", 650, 166, 750, 196),
                  line("۱۰۰", 510, 172, 610, 202)]
        self.assertEqual(1, len(layout.group_rows(layout.lines_from(skewed))))

    def test_a_line_with_no_box_is_dropped_rather_than_placed_at_the_origin(self):
        """(0, 0) would sort it to the top-left and attach it to whichever row is there."""
        entries = BODY + [{"text": "بی‌مکان", "confidence": 0.9, "box": None}]
        self.assertEqual(len(BODY), len(layout.lines_from(entries)))


class TableReconstructionTests(unittest.TestCase):
    def test_a_headed_table_is_rebuilt_cell_by_cell(self):
        table = layout.reconstruct(HEADER + BODY)
        self.assertIsNotNone(table)
        self.assertEqual("header", table.column_source)
        self.assertEqual(3, len(table.rows))
        self.assertEqual(
            {"name": "سیمان تیپ ۲", "unit": "پاکت", "quantity": "۱۰۰",
             "unit_price": "۱٬۲۰۰٬۰۰۰", "amount": "۱۲۰٬۰۰۰٬۰۰۰"},
            table.rows[0])

    def test_the_columns_are_reported_in_reading_order(self):
        table = layout.reconstruct(HEADER + BODY)
        order = layout.columns_right_to_left(
            {role: x for role, x in zip(("name", "unit", "quantity", "unit_price",
                                         "amount"),
                                        (NAME_X, UNIT_X, QTY_X, PRICE_X, AMOUNT_X))})
        self.assertEqual(["name", "unit", "quantity", "unit_price", "amount"], order)
        self.assertEqual({"name", "unit", "quantity", "unit_price", "amount"},
                         table.roles)

    def test_a_table_whose_header_was_never_read_is_still_rebuilt(self):
        """The audited invoice's heading band is shaded and the recogniser returned
        nothing for it, while the table below was perfectly visible. Columns are then
        inferred from the body: a unit column by its words, money columns by their sizes,
        the description by being the widest text."""
        table = layout.reconstruct(BODY)
        self.assertIsNotNone(table)
        self.assertEqual("inferred", table.column_source)
        self.assertEqual(3, len(table.rows))
        self.assertIn("unit", table.roles)
        self.assertEqual("پاکت", table.rows[0]["unit"])

    def test_the_larger_money_column_is_the_line_total(self):
        """A line total is quantity times rate and is therefore the bigger of the two on
        essentially every invoice. Getting this backwards swaps every price."""
        table = layout.reconstruct(BODY)
        self.assertEqual("۱۲۰٬۰۰۰٬۰۰۰", table.rows[0]["amount"])
        self.assertEqual("۱٬۲۰۰٬۰۰۰", table.rows[0]["unit_price"])

    def test_a_page_with_no_table_reconstructs_nothing(self):
        prose = [line("با تشکر از خرید شما", 400, 100, 900, 130),
                 line("شرایط پرداخت نقدی است", 400, 160, 900, 190)]
        self.assertIsNone(layout.reconstruct(prose))

    def test_an_empty_page_reconstructs_nothing(self):
        self.assertIsNone(layout.reconstruct([]))
        self.assertIsNone(layout.reconstruct(None))


class LineItemRuleTests(unittest.TestCase):
    """A row is an item when it names something AND says what it cost."""

    def test_a_row_with_only_a_description_is_not_an_item(self):
        """A wrapped continuation, or a stray mark. Admitting it turns five real products
        into twenty-nine rows of noise."""
        self.assertFalse(layout._is_line_item({"name": "ادامهٔ شرح"}))

    def test_a_row_with_only_a_number_is_not_an_item(self):
        """A page number, or a total belonging to the summary."""
        self.assertFalse(layout._is_line_item({"amount": "۱۲۰٬۰۰۰"}))

    def test_a_row_with_a_description_and_an_amount_is_an_item(self):
        self.assertTrue(layout._is_line_item({"name": "سیمان", "amount": "۱۲۰٬۰۰۰"}))

    def test_a_description_with_a_rate_but_no_total_is_still_an_item(self):
        self.assertTrue(layout._is_line_item({"name": "سیمان", "unit_price": "۱٬۲۰۰"}))


class PageKindTests(unittest.TestCase):
    def test_a_totals_page_is_classified_as_a_summary(self):
        rows = layout.group_rows(layout.lines_from([
            line("جمع کل", 800, 100, 950, 130),
            line("۵۶۶٬۵۰۰٬۰۰۰", 300, 100, 500, 130),
            line("تخفیف", 800, 160, 950, 190),
            line("۰", 300, 160, 500, 190),
            line("مالیات بر ارزش افزوده", 750, 220, 990, 250),
            line("۵۰٬۰۰۰٬۰۰۰", 300, 220, 500, 250)]))
        index, anchors = layout.find_header(rows)
        self.assertEqual(layout.SUMMARY_PAGE, layout.classify(rows, index, anchors))

    def test_a_summary_page_yields_no_line_items(self):
        """Its rows are headings paired with figures, which read like item data and are
        not. Page 3 of the audited invoice is exactly this."""
        self.assertIsNone(layout.reconstruct([
            line("جمع کل", 800, 100, 950, 130),
            line("۵۶۶٬۵۰۰٬۰۰۰", 300, 100, 500, 130),
            line("تخفیف", 800, 160, 950, 190),
            line("۰", 300, 160, 500, 190),
            line("مالیات", 800, 220, 950, 250),
            line("۵۰٬۰۰۰٬۰۰۰", 300, 220, 500, 250)]))

    def test_a_table_page_is_classified_as_one(self):
        rows = layout.group_rows(layout.lines_from(HEADER + BODY))
        index, anchors = layout.find_header(rows)
        self.assertEqual(layout.TABLE_PAGE, layout.classify(rows, index, anchors))


class ConfidenceBandTests(unittest.TestCase):
    """The mission's rule: high extracts a value, medium offers a draft, low keeps raw text."""

    def test_the_three_bands(self):
        self.assertEqual(layout.CONFIDENCE_HIGH, layout.confidence_band(0.91))
        self.assertEqual(layout.CONFIDENCE_MEDIUM, layout.confidence_band(0.60))
        self.assertEqual(layout.CONFIDENCE_LOW, layout.confidence_band(0.40))

    def test_a_confident_reconstruction_may_be_used(self):
        self.assertTrue(layout.reconstruct(HEADER + BODY).trustworthy)

    def test_an_unreadable_reconstruction_is_kept_but_not_offered(self):
        """The audited pages returned `'ld'bdd` and `xl` where a name and an amount
        belong. The table is real; its contents are not usable, and turning them into
        line items would put invented-looking data on a financial draft."""
        murky = (row_at(160, "سیمان", "پاکت", "۱۰۰", "۱٬۲۰۰", "۱۲۰٬۰۰۰", confidence=0.3)
                 + row_at(220, "ماسه", "مترمکعب", "۲۰", "۵۵۰", "۱۱٬۰۰۰", confidence=0.3))
        table = layout.reconstruct(murky)
        self.assertIsNotNone(table, "the reconstruction is kept as a diagnosis")
        self.assertFalse(table.trustworthy)
        self.assertEqual(layout.CONFIDENCE_LOW, table.band)


class DiagnosisTests(unittest.TestCase):
    """A page with no items says which kind of nothing it is.

    Three situations used to look identical to a reviewer -- a summary page, a table whose
    columns could not be found, and a page nothing was positioned on. An empty item list
    with no explanation is the same experience as the failure this work replaced.
    """

    def test_a_reconstructed_table_reports_no_reason(self):
        kind, reason = layout.diagnose(HEADER + BODY)
        self.assertEqual(layout.TABLE_PAGE, kind)
        self.assertIsNone(reason, "a table came out, so there is nothing to explain")

    def test_a_summary_page_says_it_is_a_summary(self):
        kind, reason = layout.diagnose([
            line("جمع کل", 800, 100, 950, 130),
            line("۵۶۶٬۵۰۰٬۰۰۰", 300, 100, 500, 130),
            line("تخفیف", 800, 160, 950, 190),
            line("۰", 300, 160, 500, 190),
            line("مالیات", 800, 220, 950, 250),
            line("۵۰٬۰۰۰٬۰۰۰", 300, 220, 500, 250)])
        self.assertEqual(layout.SUMMARY_PAGE, kind)
        self.assertEqual(layout.NO_TABLE_SUMMARY, reason)

    def test_a_page_with_no_columns_says_so(self):
        kind, reason = layout.diagnose([
            line("با تشکر از خرید شما", 400, 100, 900, 130),
            line("شرایط پرداخت نقدی است", 400, 160, 900, 190)])
        self.assertEqual(layout.NO_TABLE_NO_COLUMNS, reason)

    def test_a_page_with_nothing_positioned_says_so(self):
        self.assertEqual((layout.UNKNOWN_PAGE, layout.NO_TABLE_EMPTY),
                         layout.diagnose([]))
        self.assertEqual((layout.UNKNOWN_PAGE, layout.NO_TABLE_EMPTY),
                         layout.diagnose([{"text": "بی‌مکان", "confidence": 0.9,
                                           "box": None}]))


if __name__ == "__main__":
    unittest.main()
