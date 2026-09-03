from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..domain.conversions import UnitConversion
class PsycopgUnitConversionRepository:
 def __init__(self,db):self.db=db
 @staticmethod
 def map(r):return UnitConversion(r["id"],r["organization_id"],r["project_id"],r["scope_kind"],r["version"],r["source_unit"],r["target_unit"],r["dimension"],r["factor"],r["effective_from"],r["reason"],r["created_by"],r["created_at"])
 async def list(self,s):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM unit_conversions WHERE organization_id=%s AND project_id=%s ORDER BY created_at,id",(s.organization_id,s.project_id));return [self.map(x) for x in await c.fetchall()]
 async def get(self,s,cid):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM unit_conversions WHERE organization_id=%s AND project_id=%s AND id=%s",(s.organization_id,s.project_id,cid));r=await c.fetchone()
  return None if r is None else self.map(r)
 async def append(self,s,v,audit_id,before=None):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("INSERT INTO unit_conversions(id,organization_id,project_id,scope_kind,version,source_unit,target_unit,dimension,factor,effective_from,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(v.id,v.organization_id,v.project_id,v.scope_kind,v.version,v.source_unit,v.target_unit,v.dimension,v.factor,v.effective_from,v.reason,v.created_by,v.created_at))
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'unit_conversion.revised','unit_conversions',%s,%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,v.created_by,v.id,v.reason,Jsonb(None if before is None else {"id":str(before.id),"factor":str(before.factor)}),Jsonb({"id":str(v.id),"factor":str(v.factor),"version":v.version}),v.created_at))
  return v
