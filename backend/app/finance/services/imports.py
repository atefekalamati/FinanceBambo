import hashlib,io
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from uuid import uuid4
from openpyxl import load_workbook
from ..domain.resources import FinanceRecordNotFound
from ..domain.errors import FinanceDomainError

class ImportValidationError(FinanceDomainError):
 status=422;code="VALIDATION_ERROR"
class ImportConflict(FinanceDomainError):
 status=409;code="STALE_VERSION"

HEADERS={"prices":("resourceCode","unitPrice","currency","effectiveFrom","scope"),"estimate":("resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source")}
def parse_excel(content:bytes,kind:str,currency_unit:str|None=None):
 try:wb=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
 except Exception as exc:raise ImportValidationError("invalid Excel workbook") from exc
 ws=wb.active
 rows=ws.iter_rows(values_only=True);header=tuple("" if x is None else str(x).strip() for x in next(rows,()))
 errors=[];normalized=[]
 missing=[x for x in HEADERS[kind] if x not in header]
 if missing:return [],[{"row":1,"field":x,"reason":"required_column"} for x in missing]
 positions={x:header.index(x) for x in HEADERS[kind]}
 for number,row in enumerate(rows,2):
  if not any(x is not None and str(x).strip() for x in row):continue
  item={k:(row[i] if i<len(row) else None) for k,i in positions.items()}
  for key in ("resourceCode",):
   if item[key] is None or not str(item[key]).strip():errors.append({"row":number,"field":key,"reason":"required"})
  try:
   amount_key="unitPrice" if kind=="prices" else "originalQuantity";value=Decimal(str(item[amount_key]));item[amount_key]=format(value,"f")
   if kind=="prices" and ((item["currency"] not in ("IRR","TOMAN")) or item["currency"]!=currency_unit):errors.append({"row":number,"field":"currency","reason":"explicit_currency_mismatch"})
   if kind=="prices":
    irr=value if currency_unit=="IRR" else value*10
    if irr!=irr.to_integral_value():errors.append({"row":number,"field":"unitPrice","reason":"fractional_irr"})
    item["unitPriceIrr"]=format(irr,".0f")
  except (InvalidOperation,TypeError):errors.append({"row":number,"field":amount_key,"reason":"invalid_decimal"})
  if kind=="prices":
   try:item["effectiveFrom"]=item["effectiveFrom"].isoformat() if hasattr(item["effectiveFrom"],"isoformat") else date.fromisoformat(str(item["effectiveFrom"])).isoformat()
   except ValueError:errors.append({"row":number,"field":"effectiveFrom","reason":"invalid_date"})
   if item["scope"] not in ("organization","project"):errors.append({"row":number,"field":"scope","reason":"invalid_choice"})
  elif item["source"] not in ("excel_import",):errors.append({"row":number,"field":"source","reason":"must_be_excel_import"})
  normalized.append(item)
 return normalized,errors

class FinanceImportService:
 def __init__(self,repo,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.ids=id_factory;self.clock=clock
 async def preview(self,scope,kind,content,currency_unit=None):
  if scope.actor_user_id is None:raise PermissionError("authenticated actor is required")
  rows,errors=parse_excel(content,kind,currency_unit);pid=self.ids();await self.repo.save_preview(scope,pid,kind,currency_unit,hashlib.sha256(content).hexdigest(),rows,errors,self.clock())
  return {"previewId":pid,"kind":kind,"rowCount":len(rows),"errors":errors,"canCommit":not errors and bool(rows)}
 async def commit(self,scope,preview_id):
  try:result=await self.repo.commit(scope,preview_id,self.clock())
  except ValueError as exc:raise ImportConflict(str(exc)) from exc
  if result is None:raise FinanceRecordNotFound("import preview not found")
  return {"previewId":preview_id,"status":"committed","committedCount":result}
