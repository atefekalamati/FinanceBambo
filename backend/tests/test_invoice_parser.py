# -*- coding: utf-8 -*-
"""What the invoice parser may and may not conclude from recognised text.

The parser fills a review form. Every assertion here is about the line between reading a
value and inventing one, because a field that arrives pre-filled with a plausible wrong
number is worse than an empty one: the reviewer sees a filled form either way.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction.adapters import RAW_TEXT_KEY, _as_contract
from extraction.invoice_parser import (AMBIGUOUS, EXACT, TOTAL_MATCH, TOTAL_MISMATCH,
                                       TOTAL_UNVERIFIABLE, parse_invoice, strict_amount)
from extraction.parsing import normalize

#: The recognised text the real fixture produced, verbatim -- glued headers, Arabic
#: letter forms, flattened table cells and the corrupted Persian total included.
REAL_OCR = """فاكتور فروش
فروشنده شركت تست بامبو
خريدار پروژه تراس پلاس
INVOICE NO: INV-1405-001
شماره فاكتور-
DATE: 1405/06/12
تاريخ: 1405/06/12
مبلغ كلريال
قيمت واحدريال
واحد
تعداد
شرح كالا
50,000,000
5,000,000
مترمكعب
10
بتن آماده
85,000,000
85,000
کیلوگرم
1000
میلگرد
TOTAL: 135,000,000 IRR
جمع كل:135,00,0 ريال
مهر و امضاى فروشنده
TEST FIXTURE - NOT A REAL INVOICE"""

HEADER = "مبلغ كل\nقيمت واحد\nواحد\nتعداد\nشرح كالا"


def table(*rows):
    return "\n".join([HEADER] + [line for row in rows for line in row])


class NormalizationTests(unittest.TestCase):
    def test_persian_digits_become_ascii(self):
        self.assertEqual("135000000", normalize("۱۳۵۰۰۰۰۰۰"))

    def test_arabic_digits_become_ascii(self):
        self.assertEqual("135000000", normalize("١٣٥٠٠٠٠٠٠"))

    def test_arabic_letter_forms_are_folded_to_persian(self):
        # ي/ك and ی/ک are indistinguishable in most fonts; matching only one would make a
        # field depend on the vendor's keyboard.
        self.assertEqual("کیلوگرم", normalize("كيلوگرم"))

    def test_directional_and_zero_width_noise_is_removed(self):
        self.assertEqual("ریال", normalize("‏ریال‎").strip())

    def test_persian_thousands_separator_is_read(self):
        self.assertEqual(Decimal("135000000"), strict_amount("۱۳۵٬۰۰۰٬۰۰۰")[0])

    def test_ascii_thousands_separator_is_read(self):
        self.assertEqual(Decimal("135000000"), strict_amount("135,000,000")[0])

    def test_broken_grouping_is_refused_not_repaired(self):
        # The rule the whole module exists for: 135,00,0 is not 135,000,000, and it is
        # not 135000 either. It is a misread.
        value, reason = strict_amount("135,00,0")
        self.assertIsNone(value)
        self.assertEqual("malformed_grouping", reason)

    def test_a_plain_run_of_digits_is_a_number(self):
        self.assertEqual(Decimal("1000"), strict_amount("1000")[0])


class LabelledFieldTests(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_invoice(REAL_OCR)

    def test_the_english_invoice_number_is_read_exactly(self):
        self.assertEqual("INV-1405-001", self.parsed.invoice_number.value)
        self.assertEqual(EXACT, self.parsed.invoice_number.certainty)

    def test_a_persian_labelled_invoice_number_is_read_too(self):
        parsed = parse_invoice("شماره فاکتور: INV-77\nشرح کالا")
        self.assertEqual("INV-77", parsed.invoice_number.value)

    def test_the_jalali_date_is_read_from_a_labelled_line(self):
        self.assertEqual("1405/06/12", self.parsed.invoice_date.value)

    def test_a_date_with_no_label_is_not_taken_as_the_invoice_date(self):
        parsed = parse_invoice("1405/06/12\nشرح کالا")
        self.assertIsNone(parsed.invoice_date.value)

    def test_the_supplier_is_read(self):
        self.assertEqual("شرکت تست بامبو", self.parsed.supplier_name.value)

    def test_the_buyer_is_read(self):
        self.assertEqual("پروژه تراس پلاس", self.parsed.buyer_name.value)

    def test_a_label_with_nothing_after_it_yields_no_field(self):
        parsed = parse_invoice("فروشنده\nخریدار")
        self.assertIsNone(parsed.supplier_name.value)

    def test_a_field_the_text_never_states_is_absent_not_blank(self):
        parsed = parse_invoice("فاکتور فروش")
        self.assertIsNone(parsed.buyer_name.value)
        self.assertEqual("NOT_FOUND", parsed.buyer_name.certainty)


class TableTests(unittest.TestCase):
    def test_alternate_product_price_and_amount_headers_create_a_candidate_item(self):
        text = "مبلغ\nقیمت\nواحد\nتعداد\nمحصول\n120000\n1200\nعدد\n100\nآجر"
        parsed = parse_invoice(text)
        self.assertEqual(1, len(parsed.items))
        self.assertEqual("آجر", parsed.items[0].name)
        self.assertEqual(Decimal("120000"), parsed.items[0].amount)

    def test_a_flattened_persian_table_reconstructs_both_items(self):
        parsed = parse_invoice(REAL_OCR)
        self.assertEqual(2, len(parsed.items))
        first, second = parsed.items
        self.assertEqual(("بتن آماده", Decimal("10"), "مترمکعب",
                          Decimal("5000000"), Decimal("50000000")),
                         (first.name, first.quantity, first.unit,
                          first.unit_price, first.amount))
        self.assertEqual(("میلگرد", Decimal("1000"), "کیلوگرم",
                          Decimal("85000"), Decimal("85000000")),
                         (second.name, second.quantity, second.unit,
                          second.unit_price, second.amount))

    def test_one_item_is_read_as_readily_as_two(self):
        parsed = parse_invoice(table(["50,000,000", "5,000,000", "مترمکعب", "10",
                                      "بتن آماده"]))
        self.assertEqual(1, len(parsed.items))

    def test_without_a_header_row_no_item_is_invented(self):
        parsed = parse_invoice("50,000,000\n5,000,000\nمترمکعب\n10\nبتن آماده")
        self.assertEqual([], parsed.items)
        self.assertIn("INVOICE_TABLE_NOT_RECOGNISED",
                      [w["code"] for w in parsed.warnings])

    def test_a_block_whose_description_is_a_number_is_refused(self):
        parsed = parse_invoice(table(["1", "2", "مترمکعب", "3", "4"]))
        self.assertEqual([], parsed.items)
        self.assertIn("INVOICE_ROW_AMBIGUOUS", [w["code"] for w in parsed.warnings])

    def test_leftover_cells_are_reported_rather_than_padded_into_an_item(self):
        parsed = parse_invoice(table(["50,000,000", "5,000,000", "مترمکعب", "10",
                                      "بتن آماده"]) + "\nمیلگرد")
        self.assertEqual(1, len(parsed.items))
        self.assertIn("INVOICE_ROW_INCOMPLETE", [w["code"] for w in parsed.warnings])

    def test_the_unit_word_is_reported_as_written(self):
        parsed = parse_invoice(REAL_OCR)
        self.assertEqual("مترمکعب", parsed.items[0].unit)


class ArithmeticTests(unittest.TestCase):
    def test_a_consistent_row_carries_no_arithmetic_warning(self):
        parsed = parse_invoice(REAL_OCR)
        self.assertEqual((), parsed.items[0].warnings)

    def test_a_mismatched_row_is_warned_about_and_left_unchanged(self):
        parsed = parse_invoice(table(["99,000,000", "5,000,000", "مترمکعب", "10",
                                      "بتن آماده"]))
        item = parsed.items[0]
        self.assertEqual(Decimal("99000000"), item.amount, "the value is not corrected")
        self.assertEqual("INVOICE_ITEM_ARITHMETIC_MISMATCH", item.warnings[0]["code"])


class TotalTests(unittest.TestCase):
    def test_the_items_reconcile_with_the_stated_total(self):
        self.assertEqual(TOTAL_MATCH, parse_invoice(REAL_OCR).validation_status)

    def test_a_corrupt_persian_total_never_overrides_a_clean_one(self):
        parsed = parse_invoice(REAL_OCR)
        self.assertEqual(Decimal("135000000"), parsed.total_amount.value)
        self.assertIn("INVOICE_TOTAL_UNREADABLE", [w["code"] for w in parsed.warnings])

    def test_a_total_that_disagrees_with_the_items_is_reported_not_reconciled(self):
        parsed = parse_invoice(table(["50,000,000", "5,000,000", "مترمکعب", "10",
                                      "بتن آماده"]) + "\nTOTAL: 90,000,000 IRR")
        self.assertEqual(TOTAL_MISMATCH, parsed.validation_status)
        self.assertEqual(Decimal("90000000"), parsed.total_amount.value)

    def test_items_with_no_stated_total_are_unverifiable(self):
        parsed = parse_invoice(table(["50,000,000", "5,000,000", "مترمکعب", "10",
                                      "بتن آماده"]))
        self.assertEqual(TOTAL_UNVERIFIABLE, parsed.validation_status)
        self.assertIn("INVOICE_TOTAL_MISSING", [w["code"] for w in parsed.warnings])

    def test_two_different_totals_leave_the_field_empty(self):
        parsed = parse_invoice("TOTAL: 100,000 IRR\nجمع کل: 200,000 ریال")
        self.assertIsNone(parsed.total_amount.value)
        self.assertEqual(AMBIGUOUS, parsed.total_amount.certainty)


class CurrencyTests(unittest.TestCase):
    def test_irr_is_read_from_the_total_line(self):
        self.assertEqual("IRR", parse_invoice(REAL_OCR).currency.value)

    def test_the_persian_word_for_rial_is_read(self):
        self.assertEqual("IRR", parse_invoice("جمع کل: 500,000 ریال").currency.value)

    def test_tomans_are_preserved_and_never_converted(self):
        parsed = parse_invoice("جمع کل: 500,000 تومان")
        self.assertEqual("IRT", parsed.currency.value)
        self.assertEqual(Decimal("500000"), parsed.total_amount.value,
                         "the number is reported as written, not multiplied by ten")

    def test_currency_is_never_inferred_from_magnitude(self):
        parsed = parse_invoice(table(["50,000,000", "5,000,000", "مترمکعب", "10",
                                      "بتن آماده"]))
        self.assertIsNone(parsed.currency.value)


class RobustnessTests(unittest.TestCase):
    def test_mixed_persian_and_english_text_is_handled(self):
        parsed = parse_invoice(REAL_OCR)
        self.assertEqual("INV-1405-001", parsed.invoice_number.value)
        self.assertEqual("شرکت تست بامبو", parsed.supplier_name.value)

    def test_noise_lines_do_not_become_items(self):
        parsed = parse_invoice(REAL_OCR)
        names = [item.name for item in parsed.items]
        self.assertNotIn("TEST FIXTURE - NOT A REAL INVOICE", names)
        self.assertNotIn("مهر و امضاى فروشنده", names)

    def test_empty_text_yields_a_warning_and_no_fields(self):
        parsed = parse_invoice("")
        self.assertEqual([], parsed.items)
        self.assertEqual("INVOICE_TEXT_EMPTY", parsed.warnings[0]["code"])

    def test_no_parsed_money_value_is_a_float(self):
        parsed = parse_invoice(REAL_OCR)
        for value in [parsed.total_amount.value] + [i.amount for i in parsed.items] \
                + [i.unit_price for i in parsed.items] + [i.quantity for i in parsed.items]:
            self.assertNotIsInstance(value, float)
            self.assertIsInstance(value, Decimal)


class ContractIntegrationTests(unittest.TestCase):
    """What the extraction flow actually hands the draft."""

    def result(self, text="x", confidence=0.9):
        return _as_contract({"text": text, "confidence": confidence})

    def keys(self, text):
        return [f["key"] for f in self.result(text)["fields"]]

    def test_raw_text_is_always_preserved_beside_the_structured_fields(self):
        fields = self.result(REAL_OCR)["fields"]
        raw = [f for f in fields if f["key"] == RAW_TEXT_KEY]
        self.assertEqual(1, len(raw))
        self.assertIn("INV-1405-001", raw[0]["extractedValue"])

    def test_the_structured_fields_reach_the_contract(self):
        keys = self.keys(REAL_OCR)
        for expected in ("invoiceNumber", "invoiceDate", "supplierName", "buyerName",
                         "items", "totalAmount", "currency", "validationStatus"):
            self.assertIn(expected, keys)

    def test_money_crosses_the_contract_as_a_string_never_a_float(self):
        fields = {f["key"]: f["extractedValue"] for f in self.result(REAL_OCR)["fields"]}
        self.assertEqual("135000000", fields["totalAmount"])
        self.assertIsInstance(fields["totalAmount"], str)
        for item in fields["items"]:
            for key in ("quantity", "unitPrice", "amount"):
                self.assertIsInstance(item[key], str)

    def test_text_the_parser_cannot_structure_still_delivers_its_raw_text(self):
        self.assertEqual([RAW_TEXT_KEY, "validationStatus", "parserWarnings"],
                         self.keys("some unstructured note"))

    def test_empty_recognition_preserves_raw_text_and_warns(self):
        fields = {field["key"]: field for field in self.result("")["fields"]}
        self.assertEqual("", fields[RAW_TEXT_KEY]["extractedValue"])
        self.assertIn("ocrWarnings", fields)

    def test_nothing_here_confirms_or_creates_anything(self):
        # The contract carries candidates only: every field arrives unedited, and there is
        # no confirmed value for a human to be bypassed by.
        for field in self.result(REAL_OCR)["fields"]:
            self.assertFalse(field["editedByUser"])
            self.assertNotIn("confirmedValue", field)


if __name__ == "__main__":
    unittest.main()
