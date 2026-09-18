from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
from ..domain.invoices import Invoice,calculate_invoice
from ..domain.resources import FinanceRecordNotFound
from ..domain.errors import FinanceDomainError
from ..schemas.invoices import PATCH_PLAIN_FIELDS
class DuplicateInvoice(FinanceDomainError):status=409;code="DUPLICATE_INVOICE"
class StaleInvoice(FinanceDomainError):status=409;code="STALE_VERSION"
class InvoiceAlreadyConfirmed(FinanceDomainError):status=409;code="INVOICE_ALREADY_CONFIRMED"
class InvoiceOperationConflict(FinanceDomainError):status=409;code="INVOICE_ALREADY_CONFIRMED"
class InvoiceValidationError(FinanceDomainError):status=422;code="VALIDATION_ERROR"
# `invoice_code` and `resolve_invoice_number` used to live here. They are gone: the number
# is not the service's to decide any more. It is allocated by the database inside the
# transaction that writes the invoice, which is the only place it can be decided correctly
# when two people are entering invoices at the same moment.
#: The two states a document can be corrected in. `awaitingConfirmation` is here because
#: it is the state a reader is IN when they find the mistake.
EDITABLE_STATUSES=frozenset({"draft","awaitingConfirmation"})


@dataclass(frozen=True)
class _Restated:
 """A patch, wearing the shape `_calculate_lines` reads.

 It exists so the correction path can hand the create path's calculator exactly what a
 create hands it, with no branch inside the calculator for "this one came from a patch".
 The calculator reads six attributes; this carries those six and nothing else.
 """

 lines:list
 direct_adjustment_allocations:list
 discount_irr:Decimal
 tax_irr:Decimal
 shipping_irr:Decimal
 other_costs_irr:Decimal


class FinanceInvoiceService:
 def __init__(self,repo,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.ids=id_factory;self.clock=clock
 async def list(self,s,page=1,page_size=50,query=None,status=None,source=None,invoice_date_from=None,invoice_date_to=None):return await self.repo.list(s,page,page_size,query,status,source,invoice_date_from,invoice_date_to)
 async def get(self,s,i):
  v=await self.repo.get(s,i)
  if v is None:raise FinanceRecordNotFound("invoice not found")
  return v
 async def get_by_idempotency(self,s,key):return await self.repo.get_by_idempotency(s,key)
 async def prepare_extracted(self,s,c,source,idempotency_key,at):
  if s.actor_user_id is None:raise PermissionError("actor required")
  lines,calc=await self._calculate_lines(s,c)
  duplicate=await self.repo.duplicate(s,idempotency_key,c.vendor_name,c.invoice_date,calc.final_total)
  if duplicate is not None and not (c.duplicate_reason and c.duplicate_reason.strip()):raise DuplicateInvoice("similar extracted invoice requires reason")
  # No number yet: `confirm_with_invoice` allocates it in the transaction that writes it.
  return Invoice(self.ids(),s.organization_id,s.project_id,None,c.invoice_date,c.vendor_name,c.description,source,"confirmed",c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,calc.final_total,idempotency_key,1,s.actor_user_id,s.actor_user_id,at,at,lines)
 async def create(self,s,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  lines,calc=await self._calculate_lines(s,c)
  duplicate=await self.repo.duplicate(s,c.idempotency_key,c.vendor_name,c.invoice_date,calc.final_total)
  if duplicate!="similar" and duplicate is not None:return duplicate
  if duplicate=="similar" and not (c.duplicate_reason and c.duplicate_reason.strip()):raise DuplicateInvoice("similar invoice requires reason")
  invoice=Invoice(self.ids(),s.organization_id,s.project_id,None,c.invoice_date,c.vendor_name,c.description,c.source,"draft",c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,calc.final_total,c.idempotency_key,1,s.actor_user_id,None,None,self.clock(),lines)
  action="invoice.duplicate_warning_overridden" if duplicate=="similar" else "invoice.created"
  return await self.repo.create(s,invoice,self.ids(),c.duplicate_reason,action)
 async def _calculate_lines(self,s,c):
  if not await self.repo.valid_line_links(s,c.lines):raise InvoiceValidationError("each line must reference a matching estimate line or a general_cost resource")
  direct_amount_resource_ids=[x.resource_id for x in c.lines if x.line_amount_irr is not None]
  if direct_amount_resource_ids and not await self.repo.are_general_costs(s,direct_amount_resource_ids):raise InvoiceValidationError("direct line amount requires a general_cost resource")
  targets={x.kind:x.general_cost_line_index for x in c.direct_adjustment_allocations}
  if targets:
   resource_ids=[c.lines[i].resource_id for i in targets.values()]
   if not await self.repo.are_general_costs(s,resource_ids):raise InvoiceValidationError("direct adjustment target must be a general_cost resource")
  pairs=[(Decimal(1),x.line_amount_irr) if x.line_amount_irr is not None else (Decimal(1) if x.quantity is None else x.quantity,Decimal(0) if x.unit_price_irr is None else x.unit_price_irr) for x in c.lines]
  calc=calculate_invoice(pairs,c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,targets)
  lines=[]
  for command,value in zip(c.lines,calc.lines):lines.append({**command.model_dump(),"raw_amount_irr":value.raw,"allocated_discount_irr":value.discount,"allocated_tax_irr":value.tax,"allocated_shipping_irr":value.shipping,"allocated_other_costs_irr":value.other,"final_line_amount_irr":value.final})
  return lines,calc
 async def update(self,s,invoice_id,c):
  """Correct a document before anybody approves it.

  BOTH unconfirmed states are editable, and that is the fix this exists for. An extracted
  invoice is moved to `awaitingConfirmation` to be looked at, and looking at it is exactly
  when the wrong quantity is noticed -- so the state in which errors are FOUND used to be
  the state in which they could not be corrected, and the only way forward was to discard
  the document and type it again.

  A CONFIRMED invoice is still untouchable here. It has a number, it has been approved and
  the reports count it; correcting it is void-and-reissue, which leaves both versions
  readable. That is a different act with a different audit trail, not a stricter version
  of this one.
  """
  current=await self.get(s,invoice_id)
  # Not a stale version: retrying with a fresher one would fail identically, and
  # STALE_VERSION tells the client to refresh and try again.
  if current.status not in EDITABLE_STATUSES:raise InvoiceAlreadyConfirmed("only an unconfirmed invoice can be edited directly")
  if current.version!=c.expected_version:raise StaleInvoice("stale invoice version")
  sent=c.model_fields_set
  header={name:(getattr(c,name) if name in sent else getattr(current,name)) for name in PATCH_PLAIN_FIELDS}
  money={name:(getattr(c,name) if name in sent else getattr(current,name)) for name in ("discount_irr","tax_irr","shipping_irr","other_costs_irr")}
  lines=None;final_amount=current.final_amount_irr
  if c.lines is not None:
   # The SAME distribution the create path uses, given the same shape of command. Not a
   # second implementation that agrees with it today: an invoice whose tax was spread one
   # way when it was created and another way when it was corrected would be two documents
   # with one number.
   restated=_Restated(c.lines,c.direct_adjustment_allocations or [],**money)
   lines,calc=await self._calculate_lines(s,restated)
   final_amount=calc.final_total
  try:return await self.repo.update_editable(s,current,header,money,lines,final_amount,c.status,self.ids(),self.clock())
  except ValueError as error:raise StaleInvoice("stale invoice version") from error
 async def confirm(self,s,invoice_id,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  current=await self.get(s,invoice_id)
  # Confirming is not personal, it is authorized. The rule used to be "only the submitter
  # may confirm", which made an invoice unconfirmable the moment the person who entered it
  # was on leave, and -- worse -- described a SEGREGATION of duty while doing the opposite:
  # it required the same person to raise and approve. What matters is that the caller holds
  # finance.manage_invoice for this project, which the route gate has already established,
  # and that the actual confirming actor is recorded below.
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
  # The reversal does NOT reuse the original's number. It used to, and that made one
  # number name two documents with opposite signs -- so "invoice 7" was a question with
  # two answers, one of which cancelled the other. A void is its own document and takes
  # the project's next number, allocated by `repo.create` like any other.
  at=self.clock();reversal=Invoice(self.ids(),s.organization_id,s.project_id,None,original.invoice_date,original.vendor_name,c.reason,"reversal","voided",original.discount_irr,original.tax_irr,original.shipping_irr,original.other_costs_irr,original.final_amount_irr,c.idempotency_key,1,s.actor_user_id,s.actor_user_id,at,at,original.lines,-1,original.id)
  try:return await self.repo.create(s,reversal,self.ids(),c.reason,"invoice.voided")
  except ValueError as error:raise InvoiceOperationConflict("invoice already has a reversal") from error
 async def corrective(self,s,invoice_id,c):
  if s.actor_user_id is None:raise PermissionError("actor required")
  repeated=await self.repo.get_by_idempotency(s,c.idempotency_key)
  if repeated is not None:return repeated
  original=await self.get(s,invoice_id)
  if original.status!="confirmed" or await self.repo.has_reversal(s,invoice_id):raise InvoiceOperationConflict("corrective invoice requires a non-voided confirmed original")
  lines,calc=await self._calculate_lines(s,c);at=self.clock()
  correction=Invoice(self.ids(),s.organization_id,s.project_id,None,c.invoice_date,c.vendor_name,c.description,"corrective","corrected",c.discount_irr,c.tax_irr,c.shipping_irr,c.other_costs_irr,calc.final_total,c.idempotency_key,1,s.actor_user_id,s.actor_user_id,at,at,lines,c.financial_effect_sign,original.id)
  try:return await self.repo.create(s,correction,self.ids(),c.reason,"invoice.corrected")
  except ValueError as error:
   repeated=await self.repo.get_by_idempotency(s,c.idempotency_key)
   if repeated is not None:return repeated
   raise InvoiceOperationConflict("corrective invoice conflict") from error
