from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..domain.prices import PriceVersion

class PsycopgFinancePriceRepository:
 def __init__(self,connection): self.db=connection
 @staticmethod
 def map(r): return PriceVersion(r["id"],r["organization_id"],r["project_id"],r["resource_id"],r["scope_kind"],r["version"],r["unit_price_irr"],r["effective_from"],r["reason"],r["created_by"],r["created_at"])
 async def history(self,scope,resource_id=None):
  sql="SELECT * FROM price_versions WHERE organization_id=%s AND project_id=%s"; args=[scope.organization_id,scope.project_id]
  if resource_id is not None: sql+=" AND resource_id=%s";args.append(resource_id)
  sql+=" ORDER BY effective_from DESC,version DESC,created_at DESC,id DESC"
  async with self.db.cursor(row_factory=dict_row) as c: await c.execute(sql,tuple(args)); return [self.map(x) for x in await c.fetchall()]
 async def current(self,scope,resource_id,as_of):
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("""SELECT * FROM price_versions WHERE organization_id=%s AND project_id=%s AND resource_id=%s AND effective_from<=%s ORDER BY (scope_kind='project') DESC,effective_from DESC,version DESC,created_at DESC,id DESC LIMIT 1""",(scope.organization_id,scope.project_id,resource_id,as_of)); row=await c.fetchone()
  return None if row is None else self.map(row)
 async def trend_history(self,scope,as_of):
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("""SELECT r.id resource_id,pv.id,pv.organization_id,pv.project_id,pv.scope_kind,pv.version,pv.unit_price_irr,pv.effective_from,pv.reason,pv.created_by,pv.created_at FROM finance_resources r LEFT JOIN price_versions pv ON pv.organization_id=r.organization_id AND pv.project_id=r.project_id AND pv.resource_id=r.id AND pv.effective_from<=%s WHERE r.organization_id=%s AND r.project_id=%s AND r.deleted_at IS NULL ORDER BY r.id,pv.effective_from,pv.version,pv.created_at,pv.id""",(as_of,scope.organization_id,scope.project_id));rows=await c.fetchall()
  grouped={}
  for row in rows:
   grouped.setdefault(row["resource_id"],[])
   if row["id"] is not None:grouped[row["resource_id"]].append(self.map(row))
  return grouped
 async def append(self,scope,v,audit_id):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("""INSERT INTO price_versions(id,organization_id,project_id,resource_id,scope_kind,version,unit_price_irr,effective_from,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(v.id,v.organization_id,v.project_id,v.resource_id,v.scope_kind,v.version,v.unit_price_irr,v.effective_from,v.reason,v.created_by,v.created_at))
    await c.execute("""INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'price_version.created','price_versions',%s,%s,NULL,%s,%s)""",(audit_id,scope.organization_id,scope.project_id,v.created_by,v.id,v.reason,Jsonb({"version":v.version,"unitPriceIrr":str(v.unit_price_irr)}),v.created_at))
  return v
