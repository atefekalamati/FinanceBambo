from datetime import datetime,timezone
from uuid import uuid4
from ..domain.progress import ProgressOverride,consumed_quantity
from ..domain.errors import FinanceDomainError
from ..domain.resources import FinanceRecordNotFound
class ProgressMappingError(FinanceDomainError):status=422;code="PROGRESS_LINE_MAPPING_MISSING"
class ProgressService:
 def __init__(self,repo,provider,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):self.repo=repo;self.provider=provider;self.ids=id_factory;self.clock=clock
 async def list_snapshots(self,s):return await self.repo.list_snapshots(s)
 async def feed(self,s,snapshot_id):
  ref=await self.repo.get_snapshot(s,snapshot_id)
  if ref is None:raise FinanceRecordNotFound("progress snapshot not found")
  feed=await self.provider.get_snapshot(str(s.organization_id),s.project_id,str(snapshot_id))
  meta=feed["snapshot"]
  if str(meta["organizationId"])!=str(s.organization_id) or meta["projectId"]!=s.project_id or str(meta["progressSnapshotId"])!=str(snapshot_id):raise FinanceRecordNotFound("progress snapshot not found")
  overrides=await self.repo.latest_overrides(s,ref["id"]);by_assignment={row["assignment_external_id"]:row for row in overrides if row["assignment_external_id"]};by_activity={row["activity_external_id"]:row for row in overrides if row["activity_external_id"]}
  assignments=[]
  for source in feed.get("assignments",[]):
   row=dict(source);override=by_assignment.get(row.get("assignmentExternalId")) or by_activity.get((row.get("task") or {}).get("activityCode"))
   if override is not None:row["manualOverride"]={"previousCalculatedValue":str(override["computed_value"]),"newValue":str(override["override_value"]),"reason":override["reason"],"userId":str(override["created_by"]),"occurredAt":override["created_at"].isoformat(),"source":"manual_override","progressSnapshotId":str(snapshot_id)}
   assignments.append(row)
  return {**feed,"assignments":assignments}
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
