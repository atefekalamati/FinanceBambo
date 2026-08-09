from uuid import uuid4
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..domain.invoices import Invoice
class PsycopgInvoiceRepository:
 def __init__(self,db):self.db=db
 async def duplicate(self,s,key,vendor,number,day,amount):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT id,idempotency_key FROM invoices WHERE organization_id=%s AND project_id=%s AND (idempotency_key=%s OR (vendor_name=%s AND invoice_number IS NOT DISTINCT FROM %s AND invoice_date=%s AND final_amount_irr=%s)) LIMIT 1",(s.organization_id,s.project_id,key,vendor,number,day,amount));r=await c.fetchone()
  return None if r is None else "exact" if r["idempotency_key"]==key else "similar"
 async def are_general_costs(self,s,resource_ids):
  unique=set(resource_ids)
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT id FROM finance_resources WHERE organization_id=%s AND project_id=%s AND type='general_cost' AND id=ANY(%s)",(s.organization_id,s.project_id,list(unique)));rows=await c.fetchall()
  return {r["id"] for r in rows}==unique
 async def valid_line_links(self,s,lines):
  async with self.db.cursor(row_factory=dict_row) as c:
   for line in lines:
    if line.estimate_line_id is None:
     await c.execute("SELECT EXISTS(SELECT 1 FROM finance_resources WHERE organization_id=%s AND project_id=%s AND id=%s AND type='general_cost') ok",(s.organization_id,s.project_id,line.resource_id))
    else:
     await c.execute("SELECT EXISTS(SELECT 1 FROM estimate_lines WHERE organization_id=%s AND project_id=%s AND id=%s AND resource_id=%s) ok",(s.organization_id,s.project_id,line.estimate_line_id,line.resource_id))
    if not (await c.fetchone())["ok"]:return False
  return True
 async def list(self,s):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM invoices WHERE organization_id=%s AND project_id=%s ORDER BY invoice_date DESC,created_at DESC",(s.organization_id,s.project_id));rows=await c.fetchall()
  return [await self._map(s,r) for r in rows]
 async def get(self,s,i):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM invoices WHERE organization_id=%s AND project_id=%s AND id=%s",(s.organization_id,s.project_id,i));r=await c.fetchone()
  return None if r is None else await self._map(s,r)
 async def _map(self,s,r):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT estimate_line_id,resource_id,quantity,unit,unit_price_snapshot_irr unit_price_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,description FROM invoice_lines WHERE organization_id=%s AND project_id=%s AND invoice_id=%s ORDER BY created_at,id",(s.organization_id,s.project_id,r["id"]));lines=await c.fetchall()
  return Invoice(r["id"],r["organization_id"],r["project_id"],r["invoice_number"],r["invoice_date"],r["vendor_name"],r["description"],r["source"],r["status"],r["discount_irr"],r["tax_irr"],r["shipping_irr"],r["other_costs_irr"],r["final_amount_irr"],r["idempotency_key"],r["version"],r["submitted_by"],r["created_at"],lines)
 async def create(self,s,v,audit_id,duplicate_reason):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("INSERT INTO invoices(id,organization_id,project_id,invoice_number,invoice_date,vendor_name,description,source,status,discount_irr,tax_irr,shipping_irr,other_costs_irr,final_amount_irr,idempotency_key,version,submitted_by,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s,%s,1,%s,%s,%s)",(v.id,v.organization_id,v.project_id,v.invoice_number,v.invoice_date,v.vendor_name,v.description,v.source,v.discount_irr,v.tax_irr,v.shipping_irr,v.other_costs_irr,v.final_amount_irr,v.idempotency_key,v.submitted_by,v.created_at,v.created_at))
    for x in v.lines:await c.execute("INSERT INTO invoice_lines(id,organization_id,project_id,invoice_id,estimate_line_id,resource_id,quantity,unit,unit_price_snapshot_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,description) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(uuid4(),s.organization_id,s.project_id,v.id,x["estimate_line_id"],x["resource_id"],x["quantity"],x["unit"],x["unit_price_irr"],x["raw_amount_irr"],x["allocated_discount_irr"],x["allocated_tax_irr"],x["allocated_shipping_irr"],x["allocated_other_costs_irr"],x["final_line_amount_irr"],x["description"]))
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,after_values,occurred_at) VALUES(%s,%s,%s,%s,'invoice.created','invoices',%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,v.submitted_by,v.id,duplicate_reason,Jsonb({"status":"draft","finalAmountIrr":str(v.final_amount_irr)}),v.created_at))
  return v
 async def update_description(self,s,v,description,audit_id,at):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("UPDATE invoices SET description=%s,version=version+1,updated_at=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND status='draft' AND version=%s",(description,at,s.organization_id,s.project_id,v.id,v.version))
    if c.rowcount!=1:raise ValueError("stale invoice version")
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'invoice.updated','invoices',%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,s.actor_user_id,v.id,Jsonb({"description":v.description,"version":v.version}),Jsonb({"description":description,"version":v.version+1}),at))
  return Invoice(v.id,v.organization_id,v.project_id,v.invoice_number,v.invoice_date,v.vendor_name,description,v.source,v.status,v.discount_irr,v.tax_irr,v.shipping_irr,v.other_costs_irr,v.final_amount_irr,v.idempotency_key,v.version+1,v.submitted_by,v.created_at,v.lines)
