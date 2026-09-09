from uuid import uuid4
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..domain.invoices import Invoice
class PsycopgInvoiceRepository:
 def __init__(self,db):self.db=db
 async def duplicate(self,s,key,vendor,number,day,amount):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT id,idempotency_key FROM invoices WHERE organization_id=%s AND project_id=%s AND (idempotency_key=%s OR (vendor_name=%s AND invoice_number IS NOT DISTINCT FROM %s AND invoice_date=%s AND final_amount_irr=%s)) LIMIT 1",(s.organization_id,s.project_id,key,vendor,number,day,amount));r=await c.fetchone()
  if r is None:return None
  if r["idempotency_key"]==key:return await self.get(s,r["id"])
  return "similar"
 async def are_general_costs(self,s,resource_ids):
  unique=set(resource_ids)
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT id FROM finance_resources WHERE organization_id=%s AND project_id=%s AND resource_type='general_cost' AND id=ANY(%s)",(s.organization_id,s.project_id,list(unique)));rows=await c.fetchall()
  return {r["id"] for r in rows}==unique
 async def valid_line_links(self,s,lines):
  async with self.db.cursor(row_factory=dict_row) as c:
   for line in lines:
    if line.estimate_line_id is None:
     await c.execute("SELECT EXISTS(SELECT 1 FROM finance_resources WHERE organization_id=%s AND project_id=%s AND id=%s AND resource_type='general_cost') ok",(s.organization_id,s.project_id,line.resource_id))
    else:
     await c.execute("SELECT EXISTS(SELECT 1 FROM estimate_lines WHERE organization_id=%s AND project_id=%s AND id=%s AND resource_id=%s) ok",(s.organization_id,s.project_id,line.estimate_line_id,line.resource_id))
    if not (await c.fetchone())["ok"]:return False
  return True
 async def list(self,s,page,page_size,query=None,status=None,source=None,invoice_date_from=None,invoice_date_to=None):
  clauses=["organization_id=%s","project_id=%s"];args=[s.organization_id,s.project_id]
  if query:
   clauses.append("(invoice_number ILIKE %s OR vendor_name ILIKE %s OR COALESCE(description,'') ILIKE %s)");term=f"%{query}%";args.extend([term,term,term])
  if status:clauses.append("status=%s");args.append(status)
  if source:clauses.append("source=%s");args.append(source)
  # invoice_date is a date, not a timestamptz, so both ends compare directly and both
  # are inclusive. The reporting engine filters on this same column, so "the invoices of
  # this period" and "the cost of this period" cannot drift apart.
  if invoice_date_from:clauses.append("invoice_date>=%s");args.append(invoice_date_from)
  if invoice_date_to:clauses.append("invoice_date<=%s");args.append(invoice_date_to)
  where=" AND ".join(clauses)
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("SELECT COUNT(*) total_count FROM invoices WHERE "+where,tuple(args));total=(await c.fetchone())["total_count"]
   await c.execute("SELECT * FROM invoices WHERE "+where+" ORDER BY invoice_date DESC,created_at DESC,id DESC LIMIT %s OFFSET %s",(*args,page_size,(page-1)*page_size));rows=await c.fetchall()
   ids=[row["id"] for row in rows];lines=[]
   if ids:
    await c.execute("SELECT invoice_id,estimate_line_id,resource_id,quantity,unit,unit_price_snapshot_irr unit_price_irr,CASE WHEN quantity IS NULL AND unit IS NULL AND unit_price_snapshot_irr IS NULL THEN raw_amount_irr ELSE NULL END line_amount_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,description FROM invoice_lines WHERE organization_id=%s AND project_id=%s AND invoice_id=ANY(%s) ORDER BY invoice_id,created_at,id",(s.organization_id,s.project_id,ids));lines=await c.fetchall()
  grouped={invoice_id:[] for invoice_id in ids}
  for line in lines:grouped[line["invoice_id"]].append({key:value for key,value in line.items() if key!="invoice_id"})
  return [self._invoice(row,grouped[row["id"]]) for row in rows],total
 async def get(self,s,i):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM invoices WHERE organization_id=%s AND project_id=%s AND id=%s",(s.organization_id,s.project_id,i));r=await c.fetchone()
  return None if r is None else await self._map(s,r)
 async def get_by_idempotency(self,s,key):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM invoices WHERE organization_id=%s AND project_id=%s AND idempotency_key=%s",(s.organization_id,s.project_id,key));r=await c.fetchone()
  return None if r is None else await self._map(s,r)
 async def has_reversal(self,s,invoice_id):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT EXISTS(SELECT 1 FROM invoices WHERE organization_id=%s AND project_id=%s AND original_invoice_id=%s AND source='reversal') ok",(s.organization_id,s.project_id,invoice_id));r=await c.fetchone()
  return r["ok"]
 async def _map(self,s,r):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT estimate_line_id,resource_id,quantity,unit,unit_price_snapshot_irr unit_price_irr,CASE WHEN quantity IS NULL AND unit IS NULL AND unit_price_snapshot_irr IS NULL THEN raw_amount_irr ELSE NULL END line_amount_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,description FROM invoice_lines WHERE organization_id=%s AND project_id=%s AND invoice_id=%s ORDER BY created_at,id",(s.organization_id,s.project_id,r["id"]));lines=await c.fetchall()
  return self._invoice(r,lines)
 @staticmethod
 def _invoice(r,lines):return Invoice(r["id"],r["organization_id"],r["project_id"],r["invoice_number"],r["invoice_date"],r["vendor_name"],r["description"],r["source"],r["status"],r["discount_irr"],r["tax_irr"],r["shipping_irr"],r["other_costs_irr"],r["final_amount_irr"],r["idempotency_key"],r["version"],r["submitted_by"],r["confirmed_by"],r["confirmed_at"],r["created_at"],lines,r["financial_effect_sign"],r["original_invoice_id"])
 async def create(self,s,v,audit_id,duplicate_reason,action="invoice.created"):
  try:
   async with self.db.transaction():
    async with self.db.cursor() as c:
     await c.execute("INSERT INTO invoices(id,organization_id,project_id,invoice_number,invoice_date,vendor_name,description,source,status,discount_irr,tax_irr,shipping_irr,other_costs_irr,final_amount_irr,financial_effect_sign,idempotency_key,original_invoice_id,version,submitted_by,confirmed_by,confirmed_at,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(v.id,v.organization_id,v.project_id,v.invoice_number,v.invoice_date,v.vendor_name,v.description,v.source,v.status,v.discount_irr,v.tax_irr,v.shipping_irr,v.other_costs_irr,v.final_amount_irr,v.financial_effect_sign,v.idempotency_key,v.original_invoice_id,v.version,v.submitted_by,v.confirmed_by,v.confirmed_at,v.created_at,v.created_at))
     for x in v.lines:await c.execute("INSERT INTO invoice_lines(id,organization_id,project_id,invoice_id,estimate_line_id,resource_id,quantity,unit,unit_price_snapshot_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,description) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(uuid4(),s.organization_id,s.project_id,v.id,x["estimate_line_id"],x["resource_id"],x["quantity"],x["unit"],x["unit_price_irr"],x["raw_amount_irr"],x["allocated_discount_irr"],x["allocated_tax_irr"],x["allocated_shipping_irr"],x["allocated_other_costs_irr"],x["final_line_amount_irr"],x["description"]))
     await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,after_values,occurred_at) VALUES(%s,%s,%s,%s,%s,'invoices',%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,v.submitted_by,action,v.id,duplicate_reason,Jsonb({"status":v.status,"finalAmountIrr":str(v.final_amount_irr),"financialEffectSign":v.financial_effect_sign,"originalInvoiceId":None if v.original_invoice_id is None else str(v.original_invoice_id)}),v.created_at))
  except errors.UniqueViolation as error:raise ValueError("invoice idempotency or linked document conflict") from error
  return v
 async def update_draft(self,s,v,description,status,audit_id,at):
  next_status=status or "draft"
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("UPDATE invoices SET description=%s,status=%s,version=version+1,updated_at=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND status='draft' AND version=%s",(description,next_status,at,s.organization_id,s.project_id,v.id,v.version))
    if c.rowcount!=1:raise ValueError("stale invoice version")
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'invoice.updated','invoices',%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,s.actor_user_id,v.id,Jsonb({"description":v.description,"status":v.status,"version":v.version}),Jsonb({"description":description,"status":next_status,"version":v.version+1}),at))
  return Invoice(v.id,v.organization_id,v.project_id,v.invoice_number,v.invoice_date,v.vendor_name,description,v.source,next_status,v.discount_irr,v.tax_irr,v.shipping_irr,v.other_costs_irr,v.final_amount_irr,v.idempotency_key,v.version+1,v.submitted_by,v.confirmed_by,v.confirmed_at,v.created_at,v.lines)
 async def confirmation_matches(self,s,invoice_id,key):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT confirmation_idempotency_key FROM invoices WHERE organization_id=%s AND project_id=%s AND id=%s AND status='confirmed'",(s.organization_id,s.project_id,invoice_id));row=await c.fetchone()
  return row is not None and row["confirmation_idempotency_key"]==key
 async def confirm(self,s,v,key,audit_id,at):
  repeated=False
  try:
   async with self.db.transaction():
    async with self.db.cursor(row_factory=dict_row) as c:
     # No `AND submitted_by=%s` here. The rule that only the submitter could confirm was
     # written twice -- once in the service and once into this WHERE clause -- so removing
     # the readable one would have left this one deciding, and it fails by matching zero
     # rows: the caller would have been told the version was stale, which is not what
     # happened and not a thing they could fix. Who may confirm is a permission
     # (`finance.manage_invoice`) settled at the route; what this clause still guarantees is
     # the concurrency contract -- right tenant, right invoice, still awaiting, unchanged
     # version -- and `confirmed_by` records who actually did it.
     await c.execute("UPDATE invoices SET status='confirmed',confirmation_idempotency_key=%s,confirmed_by=%s,confirmed_at=%s,version=version+1,updated_at=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND status='awaitingConfirmation' AND version=%s",(key,s.actor_user_id,at,at,s.organization_id,s.project_id,v.id,v.version))
     if c.rowcount!=1:
      await c.execute("SELECT confirmation_idempotency_key FROM invoices WHERE organization_id=%s AND project_id=%s AND id=%s AND status='confirmed'",(s.organization_id,s.project_id,v.id));row=await c.fetchone()
      if row is None or row["confirmation_idempotency_key"]!=key:raise ValueError("competing confirmation")
      repeated=True
     if not repeated:await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'invoice.confirmed','invoices',%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,s.actor_user_id,v.id,Jsonb({"status":"awaitingConfirmation","version":v.version}),Jsonb({"status":"confirmed","version":v.version+1,"finalAmountIrr":str(v.final_amount_irr)}),at))
  except errors.UniqueViolation as error:raise ValueError("confirmation idempotency key conflict") from error
  if repeated:return await self.get(s,v.id)
  return Invoice(v.id,v.organization_id,v.project_id,v.invoice_number,v.invoice_date,v.vendor_name,v.description,v.source,"confirmed",v.discount_irr,v.tax_irr,v.shipping_irr,v.other_costs_irr,v.final_amount_irr,v.idempotency_key,v.version+1,v.submitted_by,s.actor_user_id,at,v.created_at,v.lines)
