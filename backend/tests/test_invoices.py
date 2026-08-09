import sys,unittest
from decimal import Decimal
from pathlib import Path
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.domain.invoices import calculate_invoice
from app.finance.schemas.invoices import InvoiceCreate
class InvoiceTests(unittest.TestCase):
 def test_round_half_up_and_proportional_adjustments_last_line_remainder(self):
  result=calculate_invoice([("2.5","101"),("1","100")],discount=Decimal("10"),tax=Decimal("7"),shipping=Decimal("3"),other=Decimal("0"))
  self.assertEqual([Decimal("253"),Decimal("100")],[x.raw for x in result.lines])
  self.assertEqual(Decimal("353"),result.raw_total);self.assertEqual(Decimal("353"),result.final_total)
  self.assertEqual(Decimal("10"),sum(x.discount for x in result.lines))
 def test_fractional_irr_and_empty_lines_are_rejected(self):
  with self.assertRaises(ValueError):InvoiceCreate(invoiceDate="2026-08-08",vendorName="V",source="manual",idempotencyKey="k",lines=[])
  with self.assertRaises(ValueError):InvoiceCreate(invoiceDate="2026-08-08",vendorName="V",source="manual",idempotencyKey="k",lines=[{"resourceId":"11111111-1111-4111-8111-111111111111","quantity":"1","unit":"kg","unitPriceIrr":"100.5"}])
 def test_direct_adjustment_goes_only_to_selected_line(self):
  result=calculate_invoice([("1","100"),("1","50")],tax=Decimal("15"),direct_targets={"tax":1})
  self.assertEqual([Decimal("0"),Decimal("15")],[x.tax for x in result.lines])
  self.assertEqual(Decimal("165"),result.final_total)
 def test_duplicate_direct_allocation_kind_is_rejected(self):
  base={"invoiceDate":"2026-08-08","vendorName":"V","idempotencyKey":"k","lines":[{"resourceId":"11111111-1111-4111-8111-111111111111","unitPriceIrr":"100"}]}
  base["directAdjustmentAllocations"]=[{"kind":"tax","generalCostLineIndex":0},{"kind":"tax","generalCostLineIndex":0}]
  with self.assertRaises(ValueError):InvoiceCreate(**base)
