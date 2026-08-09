import sys,unittest
from datetime import date,datetime,timezone
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.domain.invoices import Invoice,calculate_invoice
from app.finance.schemas.invoices import InvoiceConfirm,InvoiceCreate,InvoicePatch
from app.finance.security.guards import FinanceScope
from app.finance.services.invoices import FinanceInvoiceService,InvoiceAlreadyConfirmed,InvoiceConfirmationForbidden,StaleInvoice
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

ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
OTHER=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
ORG=UUID("11111111-1111-4111-8111-111111111111")
INVOICE_ID=UUID("22222222-2222-4222-8222-222222222222")
NOW=datetime(2026,8,8,tzinfo=timezone.utc)
def invoice(status="draft",version=1,submitted_by=ACTOR):
 return Invoice(INVOICE_ID,ORG,"p1","N-1",date(2026,8,8),"Vendor",None,"manual",status,Decimal(0),Decimal(0),Decimal(0),Decimal(0),Decimal(100),"create-key",version,submitted_by,ACTOR if status=="confirmed" else None,NOW if status=="confirmed" else None,NOW,[])
class FakeInvoiceRepo:
 def __init__(self,value):self.value=value;self.confirm_key=None;self.confirm_calls=0
 async def get(self,_scope,_id):return self.value
 async def update_draft(self,_scope,value,description,status,_audit,_at):
  self.value=replace(value,description=description,status=status or "draft",version=value.version+1);return self.value
 async def confirmation_matches(self,_scope,_id,key):return self.confirm_key==key
 async def confirm(self,scope,value,key,_audit,at):
  self.confirm_calls+=1;self.confirm_key=key
  self.value=Invoice(value.id,value.organization_id,value.project_id,value.invoice_number,value.invoice_date,value.vendor_name,value.description,value.source,"confirmed",value.discount_irr,value.tax_irr,value.shipping_irr,value.other_costs_irr,value.final_amount_irr,value.idempotency_key,value.version+1,value.submitted_by,scope.actor_user_id,at,value.created_at,value.lines)
  return self.value
class InvoiceLifecycleTests(unittest.IsolatedAsyncioTestCase):
 async def test_submit_then_confirm_and_repeat_same_key_returns_same_outcome(self):
  repo=FakeInvoiceRepo(invoice());service=FinanceInvoiceService(repo,clock=lambda:NOW);scope=FinanceScope(ORG,"p1",ACTOR)
  awaiting=await service.update(scope,INVOICE_ID,InvoicePatch(expectedVersion=1,status="awaitingConfirmation"))
  self.assertEqual(("awaitingConfirmation",2),(awaiting.status,awaiting.version))
  confirmed=await service.confirm(scope,INVOICE_ID,InvoiceConfirm(expectedVersion=2,idempotencyKey="confirm-1"))
  repeated=await service.confirm(scope,INVOICE_ID,InvoiceConfirm(expectedVersion=2,idempotencyKey="confirm-1"))
  self.assertEqual("confirmed",confirmed.status);self.assertIs(confirmed,repeated);self.assertEqual(1,repo.confirm_calls)
 async def test_submit_without_description_field_preserves_draft_description(self):
  current=replace(invoice(),description="keep me")
  repo=FakeInvoiceRepo(current);service=FinanceInvoiceService(repo,clock=lambda:NOW)
  awaiting=await service.update(FinanceScope(ORG,"p1",ACTOR),INVOICE_ID,InvoicePatch(expectedVersion=1,status="awaitingConfirmation"))
  self.assertEqual("keep me",awaiting.description)
 async def test_competing_confirmation_and_wrong_submitter_are_rejected(self):
  scope=FinanceScope(ORG,"p1",ACTOR)
  repo=FakeInvoiceRepo(invoice("confirmed",3));repo.confirm_key="first"
  with self.assertRaises(InvoiceAlreadyConfirmed):await FinanceInvoiceService(repo).confirm(scope,INVOICE_ID,InvoiceConfirm(expectedVersion=2,idempotencyKey="second"))
  wrong=FakeInvoiceRepo(invoice("awaitingConfirmation",2,OTHER))
  with self.assertRaises(InvoiceConfirmationForbidden):await FinanceInvoiceService(wrong).confirm(scope,INVOICE_ID,InvoiceConfirm(expectedVersion=2,idempotencyKey="key"))
 async def test_confirm_requires_awaiting_state_and_current_version(self):
  service=FinanceInvoiceService(FakeInvoiceRepo(invoice("draft",1)))
  with self.assertRaises(StaleInvoice):await service.confirm(FinanceScope(ORG,"p1",ACTOR),INVOICE_ID,InvoiceConfirm(expectedVersion=1,idempotencyKey="key"))
