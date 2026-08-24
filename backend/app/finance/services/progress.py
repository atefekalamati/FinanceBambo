from datetime import datetime,timezone
from uuid import uuid4
from ..domain.progress import ProgressOverride,apply_progress_overrides,consumed_quantity,resolve_progress_quantity
from ..domain.schedule import derive_snapshot_versions
from ..domain.errors import FinanceDomainError
from ..domain.resources import FinanceRecordNotFound
class ProgressMappingError(FinanceDomainError):status=422;code="PROGRESS_LINE_MAPPING_MISSING"
class ProgressService:
 def __init__(self,repo,provider,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.provider=provider;self.ids=id_factory;self.clock=clock
 async def list_snapshots(self,s):
  """Newest first, each numbered by its place in this project's history."""
  return derive_snapshot_versions(await self.repo.list_snapshots(s))

 async def snapshot(self,s,snapshot_id):
  """One snapshot, with the version the list would have given it.

  Read from the same numbered list rather than from a second query, so a snapshot cannot
  report one version here and another there. The list is per project and one row per
  reporting period, so it stays small.
  """
  for row in await self.list_snapshots(s):
   if str(row["progress_snapshot_id"])==str(snapshot_id):return row
  raise FinanceRecordNotFound("progress snapshot not found")
 async def feed(self,s,snapshot_id):
  ref=await self.repo.get_snapshot(s,snapshot_id)
  if ref is None:raise FinanceRecordNotFound("progress snapshot not found")
  feed=await self.provider.get_snapshot(str(s.organization_id),s.project_id,str(snapshot_id))
  meta=feed["snapshot"]
  if str(meta["organizationId"])!=str(s.organization_id) or meta["projectId"]!=s.project_id or str(meta["progressSnapshotId"])!=str(snapshot_id):raise FinanceRecordNotFound("progress snapshot not found")
  overrides=await self.repo.latest_overrides(s,ref["id"])
  assignments=[]
  for row in apply_progress_overrides(feed.get("assignments",[]),overrides,snapshot_id):
   try:
    resolved=resolve_progress_quantity(row)
    row["computedExecutedQuantity"]=format(resolved["computed_quantity"],"f")
    row["effectiveExecutedQuantity"]=format(resolved["effective_quantity"],"f")
    row["sourceMethod"]=resolved["source_method"]
    row["measurementType"]=resolved["measurement_type"]
    row["progressStatus"]=resolved["progress_status"]
    row["quality"]=format(resolved["quality"],"f")
    row["warnings"]=resolved["warnings"]
   except ValueError:
    row["computedExecutedQuantity"]=None
    row["effectiveExecutedQuantity"]=None
    row["sourceMethod"]="missing"
    # Nothing was measured, so no kind of measurement can be named. None, not a label.
    row["measurementType"]=None
    # The report's two unmapped statuses cannot occur here: they describe an estimate line
    # that reached no assignment, and this row IS an assignment.
    row["progressStatus"]="unavailable"
    row["quality"]="0"
    row["warnings"]=[{"code":"PROGRESS_MISSING","message":"No valid progress quantity is available for this assignment."}]
   assignments.append(row)
  return {**feed,"assignments":assignments}
 async def override_history(self,s,line_id):
  """List one line's overrides; the line is resolved in-scope first so another tenant's id reveals nothing."""
  if await self.repo.get_line_mapping(s,line_id) is None:raise FinanceRecordNotFound("estimate line not found")
  return await self.repo.list_overrides(s,line_id)
 async def override(self,s,line_id,c):
  if s.actor_user_id is None:raise PermissionError("authenticated actor is required")
  ref=await self.repo.get_snapshot(s,c.progress_snapshot_id)
  if ref is None:raise FinanceRecordNotFound("progress snapshot not found")
  line=await self.repo.get_line_mapping(s,line_id)
  if line is None:raise FinanceRecordNotFound("estimate line not found")
  feed=await self.provider.get_snapshot(str(s.organization_id),s.project_id,str(c.progress_snapshot_id));meta=feed.get("snapshot") or {}
  if str(meta.get("organizationId"))!=str(s.organization_id) or meta.get("projectId")!=s.project_id or str(meta.get("progressSnapshotId"))!=str(c.progress_snapshot_id):raise FinanceRecordNotFound("progress snapshot not found")
  assignment=next((row for row in feed.get("assignments",[]) if (line["assignment_external_id"] and row.get("assignmentExternalId")==line["assignment_external_id"]) or (line["activity_external_id"] and (row.get("task") or {}).get("activityCode")==line["activity_external_id"])),None)
  if assignment is None:raise ProgressMappingError("estimate line is not mapped to the selected progress snapshot")
  try:computed,_source=consumed_quantity({**assignment,"manualOverride":None})
  except ValueError as error:raise ProgressMappingError("progress snapshot has no computable baseline for this estimate line") from error
  value=ProgressOverride(self.ids(),s.organization_id,s.project_id,line_id,ref["id"],c.progress_snapshot_id,computed,c.override_value,c.reason,s.actor_user_id,self.clock())
  return await self.repo.append_override(s,value,self.ids())
