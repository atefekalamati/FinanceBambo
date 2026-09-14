from dataclasses import dataclass
from datetime import date,datetime
from decimal import Decimal,ROUND_HALF_UP
from uuid import UUID
from .errors import FinanceDomainError
Q=Decimal("1")
@dataclass(frozen=True)
class CalculatedLine:
 raw:Decimal;discount:Decimal;tax:Decimal;shipping:Decimal;other:Decimal;final:Decimal
@dataclass(frozen=True)
class InvoiceCalculation:
 lines:list[CalculatedLine];raw_total:Decimal;final_total:Decimal
def _allocate(total,raws):
 if not raws:return []
 if sum(raws)==0:return [Decimal(0)]*(len(raws)-1)+[total]
 out=[]
 for raw in raws[:-1]:out.append((total*raw/sum(raws)).quantize(Q,rounding=ROUND_HALF_UP))
 return out+[total-sum(out)]
def _direct_or_proportional(total,raws,target):
 if target is None:return _allocate(total,raws)
 if target<0 or target>=len(raws):raise ValueError("adjustment target line is out of range")
 out=[Decimal(0)]*len(raws);out[target]=total;return out
def calculate_invoice(items,discount=Decimal(0),tax=Decimal(0),shipping=Decimal(0),other=Decimal(0),direct_targets=None):
 raws=[(Decimal(q)*Decimal(p)).quantize(Q,rounding=ROUND_HALF_UP) for q,p in items]
 targets=direct_targets or {}
 ds,ts,ss,os=(_direct_or_proportional(x,raws,targets.get(k)) for k,x in (("discount",discount),("tax",tax),("shipping",shipping),("other",other)))
 lines=[CalculatedLine(r,d,t,s,o,r-d+t+s+o) for r,d,t,s,o in zip(raws,ds,ts,ss,os)]
 return InvoiceCalculation(lines,sum(raws),sum(x.final for x in lines))
class DuplicateInvoiceError(FinanceDomainError):status=409;code="DUPLICATE_INVOICE"
@dataclass(frozen=True)
class Invoice:
 #: `invoice_seq` is the invoice's number within its project: 1 for the first, and one
 #: more for each after it. It is None only between constructing an invoice and writing
 #: it, because the number is allocated by the database inside the writing transaction --
 #: an invoice that exists always has one. The zero-padded form readers see is built at
 #: the API boundary by `format_invoice_number`; the padding is presentation and is not
 #: stored, which is why a project's four-hundredth invoice needs no migration.
 id:UUID;organization_id:UUID;project_id:str;invoice_seq:int|None;invoice_date:date;vendor_name:str;description:str|None;source:str;status:str;discount_irr:Decimal;tax_irr:Decimal;shipping_irr:Decimal;other_costs_irr:Decimal;final_amount_irr:Decimal;idempotency_key:str;version:int;submitted_by:UUID;confirmed_by:UUID|None;confirmed_at:datetime|None;created_at:datetime;lines:list;financial_effect_sign:int=1;original_invoice_id:UUID|None=None
 #: The number this invoice was ISSUED with, for the documents that predate per-project
 #: numbering. Read from the old `invoice_number` column and never written: the create path
 #: leaves that column empty, so only historical rows carry one. It exists so an issued
 #: document keeps being called what it was called -- see `format_invoice_number` below.
 legacy_invoice_number:str|None=None

#: Three digits is what a reader of this system expects to see, and it is the shortest
#: width that makes a list of numbers line up. It is a floor, not a ceiling: the
#: thousandth invoice prints as 2000 rather than being refused or truncated.
INVOICE_NUMBER_WIDTH=3
def format_invoice_number(invoice_seq,legacy=None):
 """The number as a reader sees it.

 A document that was issued with a number keeps it, exactly as it was written: that string
 is on paper, in somebody's email and against a payment, and changing what the screen calls
 it would break every one of those references at once.

 Everything created since per-project numbering arrived has no such string, and is called
 by its sequence padded to three digits: 1 -> "001", 42 -> "042", 2000 -> "2000".
 """
 if isinstance(legacy,str) and legacy.strip():return legacy.strip()
 return None if invoice_seq is None else format(int(invoice_seq),"0%dd"%INVOICE_NUMBER_WIDTH)
def actual_cost(invoices):
 return sum((x.final_amount_irr*x.financial_effect_sign for x in invoices if x.status in {"confirmed","voided","corrected"}),Decimal(0))
