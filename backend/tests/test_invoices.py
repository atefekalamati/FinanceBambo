import sys,unittest
from datetime import date,datetime,timezone
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.domain.invoices import Invoice,actual_cost,calculate_invoice
from app.finance.schemas.invoices import CorrectiveInvoiceCreate,InvoiceConfirm,InvoiceCreate,InvoicePatch,InvoiceVoid
from app.finance.security.guards import FinanceScope
from app.finance.services.invoices import FinanceInvoiceService,InvoiceAlreadyConfirmed,StaleInvoice,invoice_code
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
 def test_direct_general_cost_amount_is_exact_and_mutually_exclusive(self):
  command=InvoiceCreate(invoiceDate="2026-08-08",vendorName="V",idempotencyKey="gc",lines=[{"resourceId":"11111111-1111-4111-8111-111111111111","lineAmountIrr":"12000001"}])
  self.assertEqual(Decimal("12000001"),command.lines[0].line_amount_irr)
  with self.assertRaises(ValueError):InvoiceCreate(invoiceDate="2026-08-08",vendorName="V",idempotencyKey="bad",lines=[{"resourceId":"11111111-1111-4111-8111-111111111111","lineAmountIrr":"100","unitPriceIrr":"100"}])

ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
OTHER=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
ORG=UUID("11111111-1111-4111-8111-111111111111")
INVOICE_ID=UUID("22222222-2222-4222-8222-222222222222")
NOW=datetime(2026,8,8,tzinfo=timezone.utc)
def invoice(status="draft",version=1,submitted_by=ACTOR):
 return Invoice(INVOICE_ID,ORG,"p1","N-1",date(2026,8,8),"Vendor",None,"manual",status,Decimal(0),Decimal(0),Decimal(0),Decimal(0),Decimal(100),"create-key",version,submitted_by,ACTOR if status=="confirmed" else None,NOW if status=="confirmed" else None,NOW,[])
class FakeInvoiceRepo:
 def __init__(self,value):self.value=value;self.confirm_key=None;self.confirm_calls=0;self.by_key={};self.reversed=False
 async def get(self,_scope,_id):return self.value
 async def update_draft(self,_scope,value,description,status,_audit,_at):
  self.value=replace(value,description=description,status=status or "draft",version=value.version+1);return self.value
 async def confirmation_matches(self,_scope,_id,key):return self.confirm_key==key
 async def confirm(self,scope,value,key,_audit,at):
  self.confirm_calls+=1;self.confirm_key=key
  self.value=Invoice(value.id,value.organization_id,value.project_id,value.invoice_number,value.invoice_date,value.vendor_name,value.description,value.source,"confirmed",value.discount_irr,value.tax_irr,value.shipping_irr,value.other_costs_irr,value.final_amount_irr,value.idempotency_key,value.version+1,value.submitted_by,scope.actor_user_id,at,value.created_at,value.lines)
  return self.value
 async def get_by_idempotency(self,_scope,key):return self.by_key.get(key)
 async def duplicate(self,*_args):return None
 async def has_reversal(self,_scope,_id):return self.reversed
 async def create(self,_scope,value,_audit,_reason,_action="invoice.created"):
  self.value=value;self.by_key[value.idempotency_key]=value
  if value.source=="reversal":self.reversed=True
  return value
 async def valid_line_links(self,_scope,_lines):return True
 async def are_general_costs(self,_scope,_ids):return True
class SimilarInvoiceRepo(FakeInvoiceRepo):
 def __init__(self,value):super().__init__(value);self.action=None
 async def duplicate(self,*_args):return "similar"
 async def create(self,_scope,value,_audit,_reason,_action="invoice.created"):
  self.action=_action;return value
class InvoiceLifecycleTests(unittest.IsolatedAsyncioTestCase):
 def test_actual_cost_ignores_draft_and_applies_linked_document_sign(self):
  confirmed=invoice("confirmed",3);draft=invoice("draft",1);reversal=replace(invoice("voided",1),financial_effect_sign=-1,original_invoice_id=INVOICE_ID)
  self.assertEqual(Decimal(0),actual_cost([confirmed,draft,reversal]))
 async def test_duplicate_warning_override_has_explicit_audit_action(self):
  repo=SimilarInvoiceRepo(invoice());service=FinanceInvoiceService(repo,clock=lambda:NOW)
  command=InvoiceCreate(invoiceDate="2026-08-08",vendorName="Vendor",idempotencyKey="new-key",duplicateReason="reviewed duplicate",lines=[{"resourceId":"33333333-3333-4333-8333-333333333333","unitPriceIrr":"100"}])
  await service.create(FinanceScope(ORG,"p1",ACTOR),command)
  self.assertEqual("invoice.duplicate_warning_overridden",repo.action)
 async def test_missing_invoice_number_gets_stable_f_code_from_invoice_id(self):
  repo=FakeInvoiceRepo(invoice());service=FinanceInvoiceService(repo,id_factory=lambda:INVOICE_ID,clock=lambda:NOW)
  command=InvoiceCreate(invoiceDate="2026-08-08",vendorName="Vendor",idempotencyKey="auto-code",lines=[{"resourceId":"33333333-3333-4333-8333-333333333333","unitPriceIrr":"100"}])
  created=await service.create(FinanceScope(ORG,"p1",ACTOR),command)
  self.assertEqual(invoice_code(INVOICE_ID),created.invoice_number)
 async def test_explicit_invoice_number_is_preserved(self):
  repo=FakeInvoiceRepo(invoice());service=FinanceInvoiceService(repo,id_factory=lambda:INVOICE_ID,clock=lambda:NOW)
  command=InvoiceCreate(invoiceNumber="F-MANUAL-1",invoiceDate="2026-08-08",vendorName="Vendor",idempotencyKey="manual-code",lines=[{"resourceId":"33333333-3333-4333-8333-333333333333","unitPriceIrr":"100"}])
  created=await service.create(FinanceScope(ORG,"p1",ACTOR),command)
  self.assertEqual("F-MANUAL-1",created.invoice_number)
 async def test_direct_general_cost_amount_is_not_zeroed(self):
  repo=SimilarInvoiceRepo(invoice());service=FinanceInvoiceService(repo,clock=lambda:NOW)
  command=InvoiceCreate(invoiceDate="2026-08-08",vendorName="Vendor",idempotencyKey="gc-direct",duplicateReason="reviewed",lines=[{"resourceId":"33333333-3333-4333-8333-333333333333","lineAmountIrr":"8750001"}])
  created=await service.create(FinanceScope(ORG,"p1",ACTOR),command)
  self.assertEqual((Decimal("8750001"),Decimal("8750001")),(created.final_amount_irr,created.lines[0]["raw_amount_irr"]))
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
 async def test_a_competing_confirmation_is_still_rejected(self):
  scope=FinanceScope(ORG,"p1",ACTOR)
  repo=FakeInvoiceRepo(invoice("confirmed",3));repo.confirm_key="first"
  with self.assertRaises(InvoiceAlreadyConfirmed):await FinanceInvoiceService(repo).confirm(scope,INVOICE_ID,InvoiceConfirm(expectedVersion=2,idempotencyKey="second"))

 async def test_somebody_elses_invoice_may_be_confirmed_by_an_authorized_caller(self):
  """Confirming is authorized, not personal.

  The old rule let only the submitter confirm, which meant an invoice waiting on somebody
  on leave could not be confirmed by anyone -- and, read as a control, it said the opposite
  of what it did: it REQUIRED the same person to raise and approve. Who may confirm is
  `finance.manage_invoice`, settled at the route before this code runs; what this service
  still owes is the lifecycle, and what the repository still records is who actually did it.
  """
  scope=FinanceScope(ORG,"p1",ACTOR)
  repo=FakeInvoiceRepo(invoice("awaitingConfirmation",2,OTHER))
  confirmed=await FinanceInvoiceService(repo).confirm(scope,INVOICE_ID,InvoiceConfirm(expectedVersion=2,idempotencyKey="key"))
  self.assertEqual("confirmed",confirmed.status)
  self.assertEqual(OTHER,confirmed.submitted_by)
  # The actor is recorded as the confirmer, so the trail still names two different people.
  self.assertEqual(ACTOR,confirmed.confirmed_by)
 async def test_confirm_requires_awaiting_state_and_current_version(self):
  service=FinanceInvoiceService(FakeInvoiceRepo(invoice("draft",1)))
  with self.assertRaises(StaleInvoice):await service.confirm(FinanceScope(ORG,"p1",ACTOR),INVOICE_ID,InvoiceConfirm(expectedVersion=1,idempotencyKey="key"))
 async def test_void_creates_one_linked_negative_reversal_and_is_idempotent(self):
  repo=FakeInvoiceRepo(invoice("confirmed",3));service=FinanceInvoiceService(repo,clock=lambda:NOW);scope=FinanceScope(ORG,"p1",ACTOR)
  command=InvoiceVoid(expectedVersion=3,idempotencyKey="void-1",reason="duplicate bill")
  reversal=await service.void(scope,INVOICE_ID,command);repeated=await service.void(scope,INVOICE_ID,command)
  self.assertEqual(("reversal","voided",-1,INVOICE_ID),(reversal.source,reversal.status,reversal.financial_effect_sign,reversal.original_invoice_id))
  self.assertIs(reversal,repeated)
 async def test_corrective_is_linked_immutable_effective_document(self):
  repo=FakeInvoiceRepo(invoice("confirmed",3));service=FinanceInvoiceService(repo,clock=lambda:NOW);scope=FinanceScope(ORG,"p1",ACTOR)
  command=CorrectiveInvoiceCreate(invoiceDate="2026-08-09",vendorName="Vendor",idempotencyKey="correct-1",financialEffectSign=-1,reason="price correction",lines=[{"resourceId":"33333333-3333-4333-8333-333333333333","unitPriceIrr":"20"}])
  corrected=await service.corrective(scope,INVOICE_ID,command)
  self.assertEqual(("corrective","corrected",-1,INVOICE_ID),(corrected.source,corrected.status,corrected.financial_effect_sign,corrected.original_invoice_id))

 async def test_editing_a_confirmed_invoice_reports_the_reason_not_a_stale_version(self):
  # STALE_VERSION tells the client to refresh and retry, which can never succeed here:
  # a confirmed document is corrected through the void/corrective workflow instead.
  repo=FakeInvoiceRepo(invoice("confirmed",3));service=FinanceInvoiceService(repo,clock=lambda:NOW)
  scope=FinanceScope(ORG,"p1",ACTOR)
  with self.assertRaises(InvoiceAlreadyConfirmed) as caught:
   await service.update(scope,INVOICE_ID,InvoicePatch(description="edit",expectedVersion=3))
  self.assertEqual(("INVOICE_ALREADY_CONFIRMED",409),(caught.exception.code,caught.exception.status))
  self.assertIsNone(repo.saved if hasattr(repo,"saved") else None)

