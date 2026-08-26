from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

#: Columns a reference row is read back with. Listed once so the two callers below cannot
#: return different shapes for the same row.
REFERENCE_COLUMNS = ("id,organization_id,project_id,progress_snapshot_id,source_file_version_id,"
                     "source_file_name_safe,reporting_date,snapshot_status,imported_by,"
                     "imported_at,source_type,host_snapshot_id,host_file_version_id")


async def ensure_progress_reference(db, scope, value):
    """Return the Finance reference for a Core snapshot, creating it only if absent.

    Idempotent by lookup **and** by constraint. The lookup handles the ordinary repeat; the
    ON CONFLICT handles two requests racing, which is not exotic -- two people opening the
    report page at once is enough. `ux_progress_snapshot_refs_host_snapshot` is what makes
    the second one a no-op rather than a duplicate reference, and the row is read back
    afterwards so both callers get the reference that actually won.

    The table rejects UPDATE by trigger, so there is deliberately no upsert-and-modify path:
    an existing reference is returned untouched. That is the point of a pinned reference --
    if it could change, nothing pinned to it would be reproducible.
    """
    async with db.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            "SELECT %s FROM progress_snapshot_refs WHERE organization_id=%%s AND project_id=%%s "
            "AND host_snapshot_id=%%s" % REFERENCE_COLUMNS,
            (scope.organization_id, scope.project_id, value.host_snapshot_id))
        existing = await cursor.fetchone()
        if existing is not None:
            return existing
        await cursor.execute(
            "INSERT INTO progress_snapshot_refs(id,organization_id,project_id,progress_snapshot_id,"
            "source_file_version_id,source_file_name_safe,reporting_date,snapshot_status,"
            "imported_by,imported_at,source_type,host_snapshot_id,host_file_version_id) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (organization_id,project_id,host_snapshot_id) "
            "WHERE host_snapshot_id IS NOT NULL DO NOTHING",
            (value.id, value.organization_id, value.project_id, value.progress_snapshot_id,
             value.source_file_version_id, value.source_file_name_safe, value.reporting_date,
             value.snapshot_status, value.imported_by, value.imported_at, value.source_type,
             value.host_snapshot_id, value.host_file_version_id))
        await cursor.execute(
            "SELECT %s FROM progress_snapshot_refs WHERE organization_id=%%s AND project_id=%%s "
            "AND host_snapshot_id=%%s" % REFERENCE_COLUMNS,
            (scope.organization_id, scope.project_id, value.host_snapshot_id))
        return await cursor.fetchone()


class PsycopgProgressRepository:
 def __init__(self,db):self.db=db
 async def list_snapshots(self,s):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT organization_id,project_id,progress_snapshot_id,source_file_version_id,source_file_name_safe,imported_at,imported_by,snapshot_status status,reporting_date,source_type,host_snapshot_id,host_file_version_id FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s ORDER BY reporting_date DESC,imported_at DESC",(s.organization_id,s.project_id));return await c.fetchall()
 async def get_snapshot(self,s,sid):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT * FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s AND progress_snapshot_id=%s",(s.organization_id,s.project_id,sid));return await c.fetchone()
 async def ensure_reference(self,s,value):
  """Record the Core snapshot this operation pins to, or reuse the existing record."""
  return await ensure_progress_reference(self.db,s,value)
 async def get_line_mapping(self,s,line_id):
  async with self.db.cursor(row_factory=dict_row) as c:await c.execute("SELECT id,activity_external_id,assignment_external_id FROM estimate_lines WHERE organization_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL",(s.organization_id,s.project_id,line_id));return await c.fetchone()
 async def latest_overrides(self,s,ref_id):
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("""SELECT DISTINCT ON (o.estimate_line_id) o.estimate_line_id,o.computed_value,o.override_value,o.reason,o.created_by,o.created_at,l.activity_external_id,l.assignment_external_id FROM progress_overrides o JOIN estimate_lines l ON l.organization_id=o.organization_id AND l.project_id=o.project_id AND l.id=o.estimate_line_id WHERE o.organization_id=%s AND o.project_id=%s AND o.progress_snapshot_ref_id=%s ORDER BY o.estimate_line_id,o.created_at DESC,o.id DESC""",(s.organization_id,s.project_id,ref_id));return await c.fetchall()
 async def list_overrides(self,s,line_id):
  """Read the append-only override trail for one estimate line, newest first."""
  async with self.db.cursor(row_factory=dict_row) as c:
   await c.execute("SELECT o.id,o.estimate_line_id,o.progress_snapshot_ref_id,r.progress_snapshot_id,o.computed_value,o.override_value,o.reason,o.created_by,o.created_at FROM progress_overrides o JOIN progress_snapshot_refs r ON r.organization_id=o.organization_id AND r.project_id=o.project_id AND r.id=o.progress_snapshot_ref_id WHERE o.organization_id=%s AND o.project_id=%s AND o.estimate_line_id=%s ORDER BY o.created_at DESC,o.id DESC",(s.organization_id,s.project_id,line_id));return await c.fetchall()
 async def append_override(self,s,v,audit_id):
  async with self.db.transaction():
   async with self.db.cursor() as c:
    await c.execute("INSERT INTO progress_overrides(id,organization_id,project_id,estimate_line_id,progress_snapshot_ref_id,computed_value,override_value,reason,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(v.id,v.organization_id,v.project_id,v.estimate_line_id,v.progress_snapshot_ref_id,v.computed_value,v.override_value,v.reason,v.created_by,v.created_at))
    await c.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'progress_override.created','progress_overrides',%s,%s,%s,%s,%s)",(audit_id,s.organization_id,s.project_id,v.created_by,v.id,v.reason,Jsonb({"computedValue":str(v.computed_value)}),Jsonb({"overrideValue":str(v.override_value),"progressSnapshotId":str(v.progress_snapshot_ref_id)}),v.created_at))
  return v
