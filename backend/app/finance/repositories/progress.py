from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
class PsycopgProgressRepository:
 def __init__(self,db):self.db=db
 async def list_snapshots(self,s):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT organization_id,project_id,progress_snapshot_id,source_file_version_id,source_file_name_safe,imported_at,imported_by,snapshot_status status,reporting_date FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s ORDER BY reporting_date DESC,imported_at DESC",(s.organization_id,s.project_id));return await c.fetchall()
 async def get_snapshot(self,s,sid):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s AND progress_snapshot_id=%s",(s.organization_id,s.project_id,sid));return await c.fetchone()
 async def get_line_mapping(self,s,line_id):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT id,activity_external_id,assignment_external_id FROM estimate_lines WHERE organization_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL",(s.organization_id,s.project_id,line_id));return await c.fetchone()
 async def latest_overrides(self,s,ref_id):
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("""SELECT DISTINCT ON (o.estimate_line_id) o.estimate_line_id,o.computed_value,o.override_value,o.reason,o.created_by,o.created_at,l.activity_external_id,l.assignment_external_id FROM progress_overrides o JOIN estimate_lines l ON l.organization_id=o.organization_id AND l.project_id=o.project_id AND l.id=o.estimate_line_id WHERE o.organization_id=%s AND o.project_id=%s AND o.progress_snapshot_ref_id=%s ORDER BY o.estimate_line_id,o.created_at DESC,o.id DESC""",(s.organization_id,s.project_id,ref_id));return await c.fetchall()
 async def append_override(self,s,v,audit_id):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("INSERT INTO progress_overrides(id,organization_id,project_id,estimate_line_id,progress_snapshot_ref_id,computed_value,override_value,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(v.id,v.organization_id,v.project_id,v.estimate_line_id,v.progress_snapshot_ref_id,v.computed_value,v.override_value,v.reason,v.created_by,v.created_at))
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'progress_override.created','progress_overrides',%s,%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,v.created_by,v.id,v.reason,Jsonb({"computedValue":str(v.computed_value)}),Jsonb({"overrideValue":str(v.override_value),"progressSnapshotId":str(v.progress_snapshot_ref_id)}),v.created_at))
  return v
