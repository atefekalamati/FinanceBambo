from uuid import uuid4
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
class PsycopgFinanceImportRepository:
 def __init__(self,db):self.db=db
 async def save_preview(self,s,pid,kind,currency,file_hash,rows,errors,at):
  async with self.db.transaction():
   async with self.db.cursor() as c:await c.execute("INSERT INTO finance_import_batches(id,organization_id,project_id,import_kind,currency_unit,file_sha256,normalized_rows,validation_errors,status,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'previewed',%s,%s)",(pid,s.organization_id,s.project_id,kind,currency,file_hash,Jsonb(rows),Jsonb(errors),s.actor_user_id,at))
 async def commit(self,s,pid,at):
  async with self.db.transaction():
   async with self.db.cursor(row_factory=dict_row) as c:
    await c.execute("SELECT * FROM finance_import_batches WHERE organization_id=%s AND project_id=%s AND id=%s FOR UPDATE",(s.organization_id,s.project_id,pid));batch=await c.fetchone()
    if batch is None:return None
    if batch["status"]!="previewed" or batch["validation_errors"]:raise ValueError("preview is not committable")
    count=0
    for row in batch["normalized_rows"]:
     await c.execute("SELECT id FROM finance_resources WHERE organization_id=%s AND project_id=%s AND code=%s AND deleted_at IS NULL",(s.organization_id,s.project_id,row["resourceCode"]));resource=await c.fetchone()
     if resource is None:raise ValueError("resource code not found")
     if batch["import_kind"]=="prices":
      await c.execute("SELECT COALESCE(max(version),0)+1 next_version FROM price_versions WHERE organization_id=%s AND project_id=%s AND resource_id=%s AND scope_kind=%s",(s.organization_id,s.project_id,resource["id"],row["scope"]));version=(await c.fetchone())["next_version"]
      await c.execute("INSERT INTO price_versions(id,organization_id,project_id,resource_id,scope_kind,version,unit_price_irr,effective_from,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'Excel import',%s,%s)",(uuid4(),s.organization_id,s.project_id,resource["id"],row["scope"],version,row["unitPriceIrr"],row["effectiveFrom"],s.actor_user_id,at))
     else:await c.execute("INSERT INTO estimate_lines(id,organization_id,project_id,resource_id,activity_external_id,assignment_external_id,original_quantity,source,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'excel_import',%s,%s)",(uuid4(),s.organization_id,s.project_id,resource["id"],row["activityExternalId"],row["assignmentExternalId"],row["originalQuantity"],s.actor_user_id,at))
     count+=1
    await c.execute("UPDATE finance_import_batches SET status='committed',committed_at=%s WHERE organization_id=%s AND project_id=%s AND id=%s",(at,s.organization_id,s.project_id,pid))
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,after_values,occurred_at) VALUES(%s,%s,%s,%s,'finance_import.committed','finance_import_batches',%s,%s,%s)",(uuid4(),s.organization_id,s.project_id,s.actor_user_id,pid,Jsonb({"kind":batch["import_kind"],"rowCount":count}),at))
  return count
