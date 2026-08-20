import sys
import unittest
from pathlib import Path
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.schemas.conversions import ConversionCreate
from app.finance.schemas.invoices import InvoiceCreate, InvoiceLineCreate
from app.finance.schemas.prices import PriceCreate
from app.finance.schemas.progress import ProgressOverrideCreate
from app.finance.schemas.resources import EstimateLineCreate, EstimateRevisionCreate
from app.finance.schemas.settings import FinanceSettingsPatch


RESOURCE_ID = UUID("33333333-3333-4333-8333-333333333333")
SNAPSHOT_ID = UUID("44444444-4444-4444-8444-444444444444")


def assert_rejected(testcase, schema, field, value, base):
    payload = {**base, field: value}
    with testcase.assertRaises(ValidationError):
        schema(**payload)


class NumericValidationTests(unittest.TestCase):
    def test_money_accepts_integer_and_numeric_string(self):
        invoice = InvoiceCreate(
            invoiceDate="2026-08-08",
            vendorName="Vendor",
            idempotencyKey="k",
            taxIrr=100,
            discountIrr="25",
            lines=[{"resourceId": str(RESOURCE_ID), "unitPriceIrr": "1000"}],
        )
        self.assertEqual(("100", "25", "1000"), (str(invoice.tax_irr), str(invoice.discount_irr), str(invoice.lines[0].unit_price_irr)))

    def test_money_rejects_non_numeric_shapes_and_tokens(self):
        base = {
            "invoiceDate": "2026-08-08",
            "vendorName": "Vendor",
            "idempotencyKey": "k",
            "lines": [{"resourceId": str(RESOURCE_ID), "unitPriceIrr": "1000"}],
        }
        for value in ("abc", "۱۲abc", "1000abc", "10 میلیون", "null", "", True, {"x": 1}, [1], "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                assert_rejected(self, InvoiceCreate, "taxIrr", value, base)

    def test_irr_fractional_and_negative_rules_are_preserved(self):
        base = {"invoiceDate": "2026-08-08", "vendorName": "Vendor", "idempotencyKey": "k"}
        with self.assertRaises(ValidationError):
            InvoiceCreate(**base, lines=[{"resourceId": str(RESOURCE_ID), "unitPriceIrr": "100.5"}])
        with self.assertRaises(ValidationError):
            InvoiceCreate(**base, taxIrr="-1", lines=[{"resourceId": str(RESOURCE_ID), "unitPriceIrr": "100"}])

    def test_direct_amount_requires_positive_exact_irr(self):
        base = {"invoiceDate": "2026-08-08", "vendorName": "Vendor", "idempotencyKey": "k"}
        self.assertEqual("100", str(InvoiceCreate(**base, lines=[{"resourceId": str(RESOURCE_ID), "lineAmountIrr": "100"}]).lines[0].line_amount_irr))
        with self.assertRaises(ValidationError):
            InvoiceCreate(**base, lines=[{"resourceId": str(RESOURCE_ID), "lineAmountIrr": "0"}])
        with self.assertRaises(ValidationError):
            InvoiceCreate(**base, lines=[{"resourceId": str(RESOURCE_ID), "lineAmountIrr": "100.1"}])

    def test_price_estimate_settings_progress_and_conversion_strict_numbers(self):
        valid_cases = (
            (PriceCreate, "unitPriceIrr", "1200", {"scopeKind": "project", "effectiveFrom": "2026-08-08", "reason": "r"}),
            (EstimateLineCreate, "originalQuantity", "12.3456", {"resourceId": str(RESOURCE_ID), "originalUnitPriceIrr": "100", "source": "manual_entry"}),
            (EstimateRevisionCreate, "newQuantity", "13.5", {"reason": "r"}),
            (FinanceSettingsPatch, "grossBuiltArea", "123.4567", {"effectiveFrom": "2026-08-08", "reason": "r", "expectedRevision": 0}),
            (ProgressOverrideCreate, "overrideValue", "9.25", {"progressSnapshotId": str(SNAPSHOT_ID), "reason": "r"}),
            (ConversionCreate, "factor", "1000.00000001", {"scopeKind": "project", "sourceUnit": "ton", "targetUnit": "kg", "dimension": "mass", "effectiveFrom": "2026-08-08", "reason": "r"}),
        )
        for schema, field, value, base in valid_cases:
            with self.subTest(schema=schema.__name__, field=field):
                self.assertIsNotNone(schema(**{**base, field: value}))
                for bad in ("abc", "1000abc", "null", "", True, {"x": 1}, [1], "NaN", "Infinity"):
                    assert_rejected(self, schema, field, bad, base)

    def test_decimal_precision_rules_are_preserved(self):
        with self.assertRaises(ValidationError):
            EstimateLineCreate(resourceId=str(RESOURCE_ID), originalQuantity="1.12345", source="manual_entry")
        with self.assertRaises(ValidationError):
            ConversionCreate(scopeKind="project", sourceUnit="ton", targetUnit="kg", dimension="mass", factor="1.123456789", effectiveFrom="2026-08-08", reason="r")
        with self.assertRaises(ValidationError):
            FinanceSettingsPatch(grossBuiltArea="1.12345", effectiveFrom="2026-08-08", reason="r", expectedRevision=0)
        # invoice_lines.quantity is numeric(18,4): a finer quantity would be silently rounded by
        # the column while the line amount stayed derived from the unrounded value.
        with self.assertRaises(ValidationError):
            InvoiceLineCreate(resourceId=str(RESOURCE_ID), quantity="12.00001", unit="each", unitPriceIrr="1200000")
        with self.assertRaises(ValidationError):
            InvoiceLineCreate(resourceId=str(RESOURCE_ID), quantity="12345678901234567890.1", unit="each", unitPriceIrr="1")
        self.assertEqual(Decimal("12.0001"),
            InvoiceLineCreate(resourceId=str(RESOURCE_ID), quantity="12.0001", unit="each", unitPriceIrr="1200000").quantity)


if __name__ == "__main__":
    unittest.main()
