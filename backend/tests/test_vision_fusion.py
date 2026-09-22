# -*- coding: utf-8 -*-
"""Two readings of one page, and what the pipeline is allowed to conclude from them.

The numbers in these tests are the real ones. Ground truth for the audited BAMBO
invoices was established by reading the images: row 7 is 544,222,000 and row 8 is
317,453,000. What the models returned for those same rows was 544,322,000 and
3,174,535,000 -- one digit wrong, and one digit inserted.

That is the failure this whole layer exists for. A hundred million rial, in a number
that looks exactly as plausible as the right one, is not something a reviewer catches by
reading carefully. It is caught by noticing that the two readings disagree.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction import financial_checks, fusion


class NumberReadingTests(unittest.TestCase):
    """Two spellings of one number are one number."""

    def test_persian_and_ascii_digits_are_the_same_value(self):
        self.assertEqual(544222000, fusion.as_number("۵۴۴,۲۲۲,۰۰۰"))
        self.assertEqual(544222000, fusion.as_number("544222000"))
        self.assertEqual(544222000, fusion.as_number("544,222,000"))

    def test_arabic_digits_and_arabic_separators_are_read(self):
        self.assertEqual(317453000, fusion.as_number("٣١٧٬٤٥٣٬٠٠٠"))

    def test_a_decimal_quantity_survives(self):
        self.assertEqual(8.7, fusion.as_number("۸.۷"))

    def test_something_that_is_not_a_number_is_not_guessed_into_one(self):
        for value in ("پیش فاکتور", "", "  ", None, "12/34/56", "1,2,3.4.5"):
            with self.subTest(repr(value)):
                self.assertIsNone(fusion.as_number(value))


class AgreementTests(unittest.TestCase):
    def test_the_same_number_written_two_ways_is_agreement(self):
        verdict = fusion.compare_field("totalPrice", "۵۴۴,۲۲۲,۰۰۰", "544222000")
        self.assertEqual(fusion.AGREED, verdict["status"])
        self.assertFalse(verdict["requiresReview"])
        self.assertEqual("۵۴۴,۲۲۲,۰۰۰", verdict["value"])

    def test_one_digit_apart_is_a_conflict_and_both_values_survive(self):
        """The measured failure: 544,322,000 read for 544,222,000."""
        verdict = fusion.compare_field("totalPrice", "544222000", "544322000")
        self.assertEqual(fusion.CONFLICT, verdict["status"])
        self.assertTrue(verdict["conflict"])
        self.assertTrue(verdict["requiresReview"])
        self.assertIsNone(verdict["value"], "a conflict must not resolve to a value")
        self.assertEqual(["544222000", "544322000"],
                         [source["value"] for source in verdict["sources"]])

    def test_an_inserted_digit_is_a_conflict(self):
        """317,453,000 came back as 3,174,535,000 -- ten times over, and not caught by eye."""
        verdict = fusion.compare_field("totalPrice", "317453000", "3174535000")
        self.assertEqual(fusion.CONFLICT, verdict["status"])

    def test_item_names_differing_only_in_digit_script_agree(self):
        self.assertEqual(fusion.AGREED,
                         fusion.compare_field("name", "آیتم ۳", "آیتم 3")["status"])

    def test_silence_from_one_reader_is_not_agreement(self):
        """Every vision model invented an invoice number these pages do not carry.

        OCR was correctly silent. Treating that as confirmation would promote the
        invention into an agreed value.
        """
        verdict = fusion.compare_field("invoiceNumber", None, "12345")
        self.assertEqual(fusion.SINGLE_SOURCE, verdict["status"])
        self.assertTrue(verdict["requiresReview"])
        self.assertIsNone(verdict["value"])

    def test_neither_reader_seeing_anything_asks_nobody(self):
        verdict = fusion.compare_field("invoiceNumber", None, None)
        self.assertEqual(fusion.ABSENT, verdict["status"])
        self.assertFalse(verdict["requiresReview"])


class ItemComparisonTests(unittest.TestCase):
    def test_rows_are_compared_by_position_and_disagreement_is_kept(self):
        ocr = [{"name": "آیتم ۷", "quantity": "1", "unit": "عدد",
                "unitPrice": "544222000", "totalPrice": "544222000"}]
        vision = [{"name": "آیتم ۷", "quantity": "1", "unit": "عدد",
                   "unitPrice": "544322000", "totalPrice": "544322000"}]
        report = fusion.compare_items(ocr, vision)
        row = report["rows"][0]
        self.assertTrue(row["conflict"])
        self.assertEqual(fusion.AGREED, row["fields"]["name"]["status"])
        self.assertEqual(fusion.CONFLICT, row["fields"]["totalPrice"]["status"])

    def test_a_row_only_one_reader_saw_is_reported_not_dropped(self):
        report = fusion.compare_items([{"name": "آیتم ۱"}],
                                      [{"name": "آیتم ۱"}, {"name": "آیتم ۲"}])
        self.assertEqual(2, len(report["rows"]))
        self.assertFalse(report["rowCountAgrees"])
        self.assertTrue(report["rows"][1]["requiresReview"])


class FusionReportTests(unittest.TestCase):
    def test_a_page_both_readers_agree_on_needs_nobody(self):
        header = {"supplierName": "گروه مهندسی نما برتر", "currency": "IRR",
                  "invoiceNumber": None, "invoiceDate": None, "totalAmount": None}
        report = fusion.fuse(header, dict(header), ocr_items=[], vision_items=[])
        self.assertFalse(report["requiresReview"])
        self.assertIn("supplierName", report["agreedFields"])
        self.assertEqual([], report["conflictFields"])

    def test_one_disagreement_marks_the_whole_page(self):
        report = fusion.fuse({"totalAmount": "7610526000"},
                             {"totalAmount": "76105426000"})
        self.assertTrue(report["requiresReview"])
        self.assertEqual(["totalAmount"], report["conflictFields"])


class ArithmeticTests(unittest.TestCase):
    """The page checking itself -- the one signal that needs no ground truth."""

    def test_the_audited_rows_reconcile(self):
        """Row 13 and row 15 of the real invoice, verbatim."""
        for row in ({"quantity": "3", "unitPrice": "511727000",
                     "totalPrice": "1535181000"},
                    {"quantity": "8.7", "unitPrice": "25000000",
                     "totalPrice": "217500000"}):
            with self.subTest(row["totalPrice"]):
                self.assertTrue(financial_checks.check_row_arithmetic(row)["ok"])

    def test_a_misread_price_breaks_the_identity(self):
        result = financial_checks.check_row_arithmetic(
            {"quantity": "3", "unitPrice": "511727000", "totalPrice": "1535181999"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["requiresReview"])

    def test_the_brief_s_own_example_is_flagged(self):
        result = financial_checks.check_row_arithmetic(
            {"quantity": "20", "unitPrice": "1000000", "totalPrice": "500000"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["requiresReview"])

    def test_a_row_missing_a_number_is_not_checked_rather_than_passed(self):
        self.assertIsNone(financial_checks.check_row_arithmetic(
            {"quantity": "3", "unitPrice": None, "totalPrice": "1535181000"}))


class DateAndAmountTests(unittest.TestCase):
    def test_the_real_invoice_date_is_accepted(self):
        self.assertTrue(financial_checks.check_date("1403/09/21")["ok"])

    def test_the_hallucinated_years_are_refused(self):
        """A model returned 1442, which is 2063."""
        for year in ("1442/02", "1420/03/21"):
            with self.subTest(year):
                self.assertFalse(financial_checks.check_date(year)["ok"])

    def test_an_amount_far_outside_range_is_flagged(self):
        self.assertFalse(
            financial_checks.check_amount_plausible("3174535000000")["ok"])

    def test_a_real_line_amount_passes(self):
        self.assertTrue(financial_checks.check_amount_plausible("1535181000")["ok"])


class ValidateTests(unittest.TestCase):
    def test_a_consistent_reading_asks_for_no_review(self):
        rows = [{"quantity": "3", "unitPrice": "511727000", "totalPrice": "1535181000"}]
        report = financial_checks.validate({"invoiceDate": "1403/09/21"}, rows)
        self.assertFalse(report["requiresReview"])
        self.assertGreater(report["checksRun"], 0)

    def test_an_inconsistent_reading_says_which_check_failed(self):
        rows = [{"quantity": "20", "unitPrice": "1000000", "totalPrice": "500000"}]
        report = financial_checks.validate({}, rows)
        self.assertTrue(report["requiresReview"])
        self.assertEqual(1, report["failed"])
        self.assertEqual("row_arithmetic",
                         [c for c in report["checks"] if c.get("requiresReview")][0]["check"])

    def test_nothing_is_ever_corrected(self):
        """The module reports. Deciding which stated number is wrong is not its job."""
        rows = [{"quantity": "20", "unitPrice": "1000000", "totalPrice": "500000"}]
        financial_checks.validate({}, rows)
        self.assertEqual("500000", rows[0]["totalPrice"])


if __name__ == "__main__":
    unittest.main()
