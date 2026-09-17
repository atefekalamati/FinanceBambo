# -*- coding: utf-8 -*-
"""Whether the invoice rules read an invoice they were not written against.

WHY THIS FILE EXISTS

`generated_invoice.png` was drawn to carry the labels the parser already knew, so a test
against it shows the parser reading its own template. That is worth having and it is not
evidence of generality: a fixture built from the same assumptions as the code always
passes.

The text below is the REAL OCR output of `letterhead_invoice.png`, a second layout that
follows a supplier invoice's conventions instead -- seller in the letterhead with no
«فروشنده» label, «شماره:» rather than «شماره فاکتور:», a six-column table with a «ردیف»
row-number column, and a three-line money block. It is pasted verbatim, OCR damage
included, because the damage is the point: a parser is judged on what the recogniser
actually hands it.

WHAT IT PINS

  * The payable total is read out of the cell BELOW its label. OCR flattens a ruled row
    into two lines, and reading only the label's own line lost 566,500,000 while
    reporting INVOICE_TOTAL_MISSING.
  * Every field the rules cannot reach is a MISS with a warning, never a wrong value.
    That is the property that makes the misses tolerable: a reviewer is told, and the
    model fills the gap afterwards.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction.invoice_parser import parse_invoice

#: Verbatim PaddleOCR output for extraction/test_data/letterhead_invoice.png.
LETTERHEAD_OCR = """فراز سازه پارس
فاكتور فروش
تامين مصالح ساختمانى
شماره: 1403/1125
تهران، بزرگراه فتح، خيابان صنايع، بلاك 
تاريخ: 1403/08/15
تلفن: 55234678-021
خريدار شركت توسعه بنا كيان
شماره اقتصادى
نشاني تهران، منطقه ، بلوار پزوهش، پلاك
مبلغ كلريال
قيمت واحدريال
تعداد
واحد
شرح كالا
رديف
120,000,000
1,200,000
100
پاکت
سيمان تيپ ٢پاكتى
1
360,000,000
72,000
5,000
كيلوگرم
ميلگرد آجدار
2
11,000,000
550,000
20
متر مكعب
ماسه شسته
3
9,000,000
450,000
20
متر مكعب
شن نخودى
15,000,000
3,000
5,000
ك
ات ا م
|s
و ميعلي
000'000'STS
ا ر   ومه 
51,500,000
مبلغ كل قابل پرداخت
566,500,000
مبلغ به حروف پانصد و شصت و شش ميليون وپانصد هزار ريال
TEST FIXTURE - NOT A REAL INVOICE"""


class LetterheadLayoutTests(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_invoice(LETTERHEAD_OCR)

    def test_the_payable_total_is_read_from_the_cell_below_its_label(self):
        """The one number the document is about, one line away from its heading."""
        self.assertEqual(Decimal("566500000"), self.parsed.total_amount.value)
        self.assertIn("مبلغ کل قابل پرداخت", self.parsed.total_amount.evidence)
        self.assertIn("566,500,000", self.parsed.total_amount.evidence,
                      "the evidence must name BOTH lines, or nobody can check the join")

    def test_the_labelled_fields_this_layout_shares_are_read(self):
        self.assertEqual("1403/08/15", self.parsed.invoice_date.value)
        self.assertEqual("شرکت توسعه بنا کیان", self.parsed.buyer_name.value)

    def test_a_seller_with_no_label_is_a_miss_not_a_guess(self):
        """«فراز سازه پارس» is the first line of the page and nothing says it is the seller.

        Taking the top line would read the buyer's letterhead on any invoice printed the
        other way round, so the rules decline and the field stays empty for the model and
        the reviewer.
        """
        self.assertIsNone(self.parsed.supplier_name.value)

    def test_an_unknown_number_label_is_a_miss_not_a_wrong_number(self):
        """This invoice says «شماره:»; «شماره اقتصادی» is two lines away.

        Matching a bare «شماره» would make the economic-registration number the invoice
        number on a great many invoices, which is worse than returning nothing.
        """
        self.assertIsNone(self.parsed.invoice_number.value)

    def test_nothing_was_invented(self):
        """Every field is either right or absent. None is populated with a wrong value."""
        self.assertEqual(Decimal("566500000"), self.parsed.total_amount.value)
        for candidate in (self.parsed.supplier_name, self.parsed.invoice_number):
            self.assertIsNone(candidate.value)

    def test_the_rows_it_could_not_read_are_reported(self):
        """A silent drop would let a reviewer think the table was read."""
        codes = {warning["code"] for warning in self.parsed.warnings}
        self.assertTrue(codes, "a partially read table must say so")


class OriginalLayoutStillReadsTests(unittest.TestCase):
    """The change above must not cost the template the parser was written for."""

    TEMPLATE_OCR = """فاكتور فروش
فروشنده: شرکت تست بامبو
خریدار: پروژه تراس پلاس
شماره فاکتور: INV-1405-001
تاریخ: 1405/06/12
جمع کل: 135,000,000 ریال"""

    def test_a_label_and_value_on_one_line_still_wins(self):
        parsed = parse_invoice(self.TEMPLATE_OCR)
        self.assertEqual("INV-1405-001", parsed.invoice_number.value)
        self.assertEqual("شرکت تست بامبو", parsed.supplier_name.value)
        self.assertEqual(Decimal("135000000"), parsed.total_amount.value)


if __name__ == "__main__":
    unittest.main()
