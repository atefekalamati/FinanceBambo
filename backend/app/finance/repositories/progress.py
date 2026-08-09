from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
class PsycopgProgressRepository:
 def __init__(self,db):self.db=db
 async def list_snapshots(self,s):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT organization_id,project_id,progress_snapshot_id,source_file_version_id,source_file_name_safe,imported_at,imported_by,snapshot_status status,reporting_date FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s ORDER BY reporting_date DESC,imported_at DESC",(s.organization_id,s.project_id));return await c.fetchall()
 async def get_snapshot(self,s,sid):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s AND progress_snapshot_id=%s",(s.organization_id,s.project_id,sid));return await c.fetchone()
 async def append_override(self,s,v,audit_id):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("INSERT INTO progress_overrides(id,organization_id,project_id,estimate_line_id,progress_snapshot_ref_id,computed_value,override_value,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(v.id,v.organization_id,v.project_id,v.estimate_line_id,v.progress_snapshot_ref_id,v.computed_value,v.override_value,v.reason,v.created_by,v.created_at))
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'progress_override.created','progress_overrides',%s,%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,v.created_by,v.id,v.reason,Jsonb({"computedValue":str(v.computed_value)}),Jsonb({"overrideValue":str(v.override_value),"progressSnapshotId":str(v.progress_snapshot_ref_id)}),v.created_at))
  return v
