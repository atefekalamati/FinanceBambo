from dataclasses import dataclass
from datetime import date,datetime
from decimal import Decimal,ROUND_HALF_UP
from uuid import UUID
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
class DuplicateInvoiceError(Exception):pass
@dataclass(frozen=True)
class Invoice:
 id:UUID;organization_id:UUID;project_id:str;invoice_number:str|None;invoice_date:date;vendor_name:str;description:str|None;source:str;status:str;discount_irr:Decimal;tax_irr:Decimal;shipping_irr:Decimal;other_costs_irr:Decimal;final_amount_irr:Decimal;idempotency_key:str;version:int;submitted_by:UUID;created_at:datetime;lines:list
