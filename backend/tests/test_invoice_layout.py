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


class TableBecomesLineItemsTests(unittest.TestCase):
    """The last step of the pipeline: a reconstructed table reaches the draft as items.

    `tableRows` was being produced and consumed by nobody. These pin the conversion, and
    in particular that it goes through the PARSER's number rules rather than a second set
    of its own -- a mangled figure must be refused here exactly as it is refused on the
    text path.
    """

    def items(self, lines):
        from extraction import adapters
        table = layout.reconstruct(lines)
        self.assertIsNotNone(table)
        return adapters._items_from_table(table)

    def test_a_clean_table_becomes_items_in_the_parser_s_own_shape(self):
        items = self.items(HEADER + BODY)
        self.assertEqual(3, len(items))
        self.assertEqual({"name": "سیمان تیپ 2", "quantity": "100", "unit": "پاکت",
                          "unitPrice": "1200000", "amount": "120000000",
                          "warnings": []},
                         items[0])

    def test_the_unit_is_the_word_the_sheet_wrote_not_a_registry_code(self):
        """These sit in one field beside the parser's own items. A reviewer should not be
        able to tell which reader produced which row."""
        self.assertEqual("کیلوگرم", self.items(HEADER + BODY)[1]["unit"])

    def test_a_mangled_amount_becomes_null_and_says_why(self):
        """`۱۲۰٬۰۰,۰` is not 120,000. Stripping the separators would produce a confident
        wrong number, which is the failure `strict_amount` exists to prevent."""
        items = self.items(HEADER + row_at(160, "سیمان", "پاکت", "۱۰۰",
                                           "۱٬۲۰۰٬۰۰۰", "۱۲۰٬۰۰,۰"))
        self.assertIsNone(items[0]["amount"], "never a repaired number")
        self.assertEqual("INVOICE_CELL_UNREADABLE", items[0]["warnings"][0]["code"])

    def test_a_row_with_no_number_anywhere_never_reaches_the_conversion(self):
        """The structural gate runs first and is the stricter of the two.

        A row naming something with no digits in either money cell is not an item -- it is
        a wrapped description or a stray mark -- so it is dropped in `layout` before this
        code sees it. The neighbouring real row is unaffected, which is the point: one bad
        row does not cost the table.
        """
        items = self.items(HEADER + row_at(160, "سیمان تیپ ۲", "پاکت", "x", "y", "z")
                           + row_at(220, "ماسه", "مترمکعب", "۲۰", "۵۵۰٬۰۰۰", "۱۱٬۰۰۰٬۰۰۰"))
        self.assertEqual(["ماسه"], [i["name"] for i in items])

    def test_an_item_keeps_its_description_when_a_figure_is_unreadable(self):
        """A reviewer seeing «سیمان» beside one empty field is being told something
        useful. Dropping the row would tell them nothing."""
        items = self.items(HEADER + row_at(160, "سیمان تیپ ۲", "پاکت", "۱۰۰",
                                           "۱٬۲۰۰٬۰۰۰", "۱۲۰٬۰۰,۰"))
        self.assertEqual("سیمان تیپ 2", items[0]["name"])
        self.assertEqual("1200000", items[0]["unitPrice"], "the readable figure survives")
        self.assertIsNone(items[0]["amount"])

    def test_an_arithmetic_mismatch_is_reported_and_neither_figure_is_corrected(self):
        """Which of the two is wrong is not something this can know."""
        items = self.items(HEADER + row_at(160, "سیمان", "پاکت", "۱۰۰",
                                           "۱٬۲۰۰٬۰۰۰", "۹۹٬۰۰۰"))
        self.assertEqual("1200000", items[0]["unitPrice"])
        self.assertEqual("99000", items[0]["amount"], "reported as read")
        self.assertEqual("INVOICE_ITEM_ARITHMETIC_MISMATCH",
                         items[0]["warnings"][0]["code"])

    def test_an_unknown_unit_is_kept_as_written_and_flagged(self):
        # «طاقه» is a real trade unit and is not in the registry, which is exactly the
        # case this covers. «حلقه» would NOT do: it is a known unit and would match.
        items = self.items(HEADER + row_at(160, "داربست", "طاقه", "۱۰",
                                           "۵۰۰٬۰۰۰", "۵٬۰۰۰٬۰۰۰"))
        self.assertEqual("طاقه", items[0]["unit"], "kept as the sheet wrote it")
        self.assertIn("INVOICE_UNIT_UNKNOWN",
                      [w["code"] for w in items[0]["warnings"]])

    def test_a_row_with_no_description_produces_no_item(self):
        from extraction import adapters
        self.assertEqual([], adapters._items_from_table(
            type("T", (), {"rows": [{"amount": "۱۲۰٬۰۰۰"}]})()))


if __name__ == "__main__":
    unittest.main()


class AvalAIProviderSelectionTests(unittest.TestCase):
    """`FINANCE_AI_PROVIDER=avalai` reaches AvalAI, and no key is ever logged.

    `build_extraction_provider` used to accept the literal string "openai" and nothing
    else, so an operator following the AvalAI setup notes got a warning in a log nobody
    reads and a pipeline that quietly did without its second reader. AvalAI is a gateway
    in front of the same chat-completions API, so this is a table entry rather than a
    second client.
    """

    KEYS = ("FINANCE_AI_EXTRACTION_ENABLED", "FINANCE_AI_PROVIDER", "FINANCE_AI_API_KEY",
            "FINANCE_AI_MODEL", "FINANCE_AI_BASE_URL", "AVALAI_API_KEY", "AVALAI_MODEL",
            "AVALAI_BASE_URL")

    def setUp(self):
        import os
        self.saved = {name: os.environ.get(name) for name in self.KEYS}
        for name in self.KEYS:
            os.environ.pop(name, None)

    def tearDown(self):
        import os
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def enable(self, provider, **extra):
        import os
        os.environ["FINANCE_AI_EXTRACTION_ENABLED"] = "true"
        os.environ["FINANCE_AI_PROVIDER"] = provider
        os.environ.update(extra)
        from extraction.providers import llm_invoice
        return llm_invoice

    def test_avalai_is_reached_with_its_own_key_and_gateway(self):
        llm = self.enable("avalai", AVALAI_API_KEY="k" * 20)
        provider = llm.build_extraction_provider()
        self.assertIsNotNone(provider, "avalai used to be refused as unsupported")
        self.assertEqual("https://api.avalai.ir/v1", provider._base_url)
        self.assertEqual("gpt-4o-mini", provider._model)
        self.assertTrue(llm.provider_configured())

    def test_avalai_accepts_the_shared_finance_key_too(self):
        """A host that configures every provider through the one Finance variable keeps
        working; AVALAI_API_KEY is preferred because it is the name the notes use."""
        llm = self.enable("avalai", FINANCE_AI_API_KEY="k" * 20)
        self.assertIsNotNone(llm.build_extraction_provider())

    def test_openai_is_unchanged(self):
        llm = self.enable("openai", FINANCE_AI_API_KEY="k" * 20)
        self.assertEqual("https://api.openai.com/v1",
                         llm.build_extraction_provider()._base_url)

    def test_an_unknown_provider_is_refused_rather_than_guessed(self):
        llm = self.enable("gemini", FINANCE_AI_API_KEY="k" * 20)
        self.assertIsNone(llm.build_extraction_provider())
        self.assertFalse(llm.provider_configured())

    def test_no_key_means_off_and_not_a_crash(self):
        llm = self.enable("avalai")
        self.assertIsNone(llm.build_extraction_provider())
        self.assertFalse(llm.provider_configured())

    def test_disabled_beats_every_other_setting(self):
        import os
        llm = self.enable("avalai", AVALAI_API_KEY="k" * 20)
        os.environ["FINANCE_AI_EXTRACTION_ENABLED"] = "false"
        self.assertIsNone(llm.build_extraction_provider())

    def test_no_credential_reaches_the_log(self):
        """The warning names the VARIABLES to set, never a value."""
        import logging
        llm = self.enable("avalai")
        with self.assertLogs("extraction.providers.llm_invoice", level="WARNING") as logs:
            llm.build_extraction_provider()
        joined = " ".join(logs.output)
        self.assertIn("AVALAI_API_KEY", joined, "an operator needs the variable name")
        self.assertNotIn("k" * 20, joined)
