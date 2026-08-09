from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
from ..domain.invoices import Invoice,calculate_invoice
from ..domain.resources import FinanceRecordNotFound
from ..domain.errors import FinanceDomainError
class DuplicateInvoice(FinanceDomainError):status=409;code="DUPLICATE_INVOICE"
class StaleInvoice(FinanceDomainError):status=409;code="STALE_VERSION"
class InvoiceAlreadyConfirmed(FinanceDomainError):status=409;code="INVOICE_ALREADY_CONFIRMED"
class InvoiceConfirmationForbidden(FinanceDomainError):status=403;code="FINANCE_FORBIDDEN"
class InvoiceOperationConflict(FinanceDomainError):status=409;code="INVOICE_ALREADY_CONFIRMED"
class InvoiceValidationError(FinanceDomainError):status=422;code="VALIDATION_ERROR"
class FinanceInvoiceService:
 def __init__(self,repo,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.ids=id_factory;self.clock=clock
 async def list(self,s):return await self.repo.list(s)
 async def get(self,s,i):
  v=await self.repo.get(s,i)
  if v is None:raise FinanceRecordNotFound("invoice not found")
  return v
 async def get_by_idempotency(self,s,key):return await self.repo.get_by_idempotency(s,key)
 async def prepare_extracted(self,s,c,source,idempotency_key,at):
  if s.actor_user_id is None:raise PermissionError("actor required")
  lines,calc=await self._calculate_lines(s,c)
  return Invoice(self.ids(),s.organization_id,s.project_id,c.invoice_number,c.invoice_date,c.vendor_name,c.description,source,"confirmed",c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,calc.final_total,idempotency_key,1,s.actor_user_id,s.actor_user_id,at,at,lines)
 async def create(self,s,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  lines,calc=await self._calculate_lines(s,c)
  duplicate=await self.repo.duplicate(s,c.idempotency_key,c.vendor_name,c.invoice_number,c.invoice_date,calc.final_total)
  if duplicate!="similar" and duplicate is not None:return duplicate
  if duplicate=="similar" and not (c.duplicate_reason and c.duplicate_reason.strip()):raise DuplicateInvoice("similar invoice requires reason")
  invoice=Invoice(self.ids(),s.organization_id,s.project_id,c.invoice_number,c.invoice_date,c.vendor_name,c.description,c.source,"draft",c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,calc.final_total,c.idempotency_key,1,s.actor_user_id,None,None,self.clock(),lines)
  return await self.repo.create(s,invoice,self.ids(),c.duplicate_reason)
 async def _calculate_lines(self,s,c):
  if not await self.repo.valid_line_links(s,c.lines):raise InvoiceValidationError("each line must reference a matching estimate line or a general_cost resource")
  targets={x.kind:x.general_cost_line_index for x in c.direct_adjustment_allocations}
  if targets:
   resource_ids=[c.lines[i].resource_id for i in targets.values()]
   if not await self.repo.are_general_costs(s,resource_ids):raise InvoiceValidationError("direct adjustment target must be a general_cost resource")
  pairs=[(Decimal(1) if x.quantity is None else x.quantity,Decimal(0) if x.unit_price_irr is None else x.unit_price_irr) for x in c.lines]
  calc=calculate_invoice(pairs,c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,targets)
  lines=[]
  for command,value in zip(c.lines,calc.lines):lines.append({**command.model_dump(),"raw_amount_irr":value.raw,"allocated_discount_irr":value.discount,"allocated_tax_irr":value.tax,"allocated_shipping_irr":value.shipping,"allocated_other_costs_irr":value.other,"final_line_amount_irr":value.final})
  return lines,calc
 async def update(self,s,invoice_id,c):
  current=await self.get(s,invoice_id)
  if current.status!="draft":raise StaleInvoice("only draft invoice can be edited")
  if current.version!=c.expected_version:raise StaleInvoice("stale invoice version")
  description=c.description if "description" in c.model_fields_set else current.description
  try:return await self.repo.update_draft(s,current,description,c.status,self.ids(),self.clock())
  except ValueError as error:raise StaleInvoice("stale invoice version") from error
 async def confirm(self,s,invoice_id,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  current=await self.get(s,invoice_id)
  if current.submitted_by!=s.actor_user_id:raise InvoiceConfirmationForbidden("only the submitting user can confirm this invoice")
  if current.status=="confirmed":
   repeated=await self.repo.confirmation_matches(s,invoice_id,c.idempotency_key)
   if repeated:return current
   raise InvoiceAlreadyConfirmed("invoice is already confirmed")
  if current.status!="awaitingConfirmation" or current.version!=c.expected_version:raise StaleInvoice("invoice is not awaiting confirmation or version is stale")
  try:return await self.repo.confirm(s,current,c.idempotency_key,self.ids(),self.clock())
  except ValueError as error:raise StaleInvoice("competing confirmation or stale version") from error
 async def void(self,s,invoice_id,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  repeated=await self.repo.get_by_idempotency(s,c.idempotency_key)
  if repeated is not None:return repeated
  original=await self.get(s,invoice_id)
  if original.status!="confirmed" or original.version!=c.expected_version:raise InvoiceOperationConflict("only the current confirmed invoice can be voided")
  if await self.repo.has_reversal(s,invoice_id):raise InvoiceOperationConflict("invoice already has a reversal")
  at=self.clock();reversal=Invoice(self.ids(),s.organization_id,s.project_id,original.invoice_number,original.invoice_date,original.vendor_name,c.reason,"reversal","voided",original.discount_irr,original.tax_irr,original.shipping_irr,original.other_costs_irr,original.final_amount_irr,c.idempotency_key,1,s.actor_user_id,s.actor_user_id,at,at,original.lines,-1,original.id)
  try:return await self.repo.create(s,reversal,self.ids(),c.reason,"invoice.voided")
  except ValueError as error:raise InvoiceOperationConflict("invoice already has a reversal") from error
 async def corrective(self,s,invoice_id,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  repeated=await self.repo.get_by_idempotency(s,c.idempotency_key)
  if repeated is not None:return repeated
  original=await self.get(s,invoice_id)
  if original.status!="confirmed" or await self.repo.has_reversal(s,invoice_id):raise InvoiceOperationConflict("corrective invoice requires a non-voided confirmed original")
  lines,calc=await self._calculate_lines(s,c);at=self.clock()
  correction=Invoice(self.ids(),s.organization_id,s.project_id,c.invoice_number,c.invoice_date,c.vendor_name,c.description,"corrective","corrected",c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,calc.final_total,c.idempotency_key,1,s.actor_user_id,s.actor_user_id,at,at,lines,c.financial_effect_sign,original.id)
  try:return await self.repo.create(s,correction,self.ids(),c.reason,"invoice.corrected")
  except ValueError as error:
   repeated=await self.repo.get_by_idempotency(s,c.idempotency_key)
   if repeated is not None:return repeated
   raise InvoiceOperationConflict("corrective invoice conflict") from error
