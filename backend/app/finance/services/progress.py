from datetime import datetime,timezone
from uuid import uuid4
from ..domain.progress import (ProgressOverride,ProgressPairing,ProgressReference,
 apply_progress_overrides,assignment_keys,consumed_quantity,line_keys,
 reference_from_header,resolve_progress_quantity,snapshot_assignments,snapshot_metadata)
from ..adapters.ports import supports_current_snapshot
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
  # Ask the host with the identifier the host issued. `snapshot_id` is Finance's own UUID,
  # which a real provider has never seen: it mints nothing and only recognises its own
  # bigint. The reference row was just loaded and already carries that id, so use it. The
  # fourth site of the same mistake -- `_calculate` and `override` had it too -- and the
  # last one, because every provider call now goes through a reference that knows both.
  lookup=ref.get("host_snapshot_id") or snapshot_id
  feed=await self.provider.get_snapshot(str(s.organization_id),s.project_id,str(lookup))
  header=snapshot_metadata(feed,s.organization_id,s.project_id,lookup)
  # Overrides stay keyed by the Finance UUID: they are Finance's records about the host's
  # snapshot, not the host's records, so they are named the way Finance names things.
  overrides=await self.repo.latest_overrides(s,ref["id"])
  assignments=[]
  for row in apply_progress_overrides(snapshot_assignments(feed),overrides,snapshot_id):
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
  # The header still comes from the host's envelope -- that is the design, and the schema
  # says so where it makes `version` optional "because the feed's header comes from the host
  # provider, which cannot know it". Two things in that envelope are not Finance's contract,
  # and returning `{**feed}` sent both straight through:
  #
  #   * `progressSnapshotId` is the identifier the provider was ASKED with, so a Core
  #     adapter echoes back Core's bigint -- `"38"`. The response model means Finance's UUID.
  #     The two identities are deliberately separate, and `hostSnapshotId` below is where
  #     the Core one belongs.
  #   * `snapshotType` is Core's vocabulary (TARGET/ACTUAL/RESCHEDULED). Finance's contract
  #     excludes it on purpose: a *type* is not the *freshness* question `status` answers,
  #     and `ApiModel` forbids extras, so it was a 500.
  #
  # Both surfaced the moment a reference existed for this project to open a feed with.
  # Named field by field rather than filtered, so a key the provider adds later cannot
  # silently become part of Finance's response.
  return {"snapshot":{"organizationId":header.get("organizationId"),
                      "projectId":header.get("projectId"),
                      # Finance's own identifier -- the one the caller asked with.
                      "progressSnapshotId":snapshot_id,
                      "sourceFileVersionId":header.get("sourceFileVersionId"),
                      "sourceFileNameSafe":header.get("sourceFileNameSafe"),
                      "importedAt":header.get("importedAt"),
                      "importedBy":header.get("importedBy"),
                      "status":header.get("status"),
                      "reportingDate":header.get("reportingDate"),
                      "hostSnapshotId":header.get("hostSnapshotId"),
                      "hostFileVersionId":header.get("hostFileVersionId"),
                      "sourceType":header.get("sourceType")},
          "assignments":assignments}
 async def current_reference(self,s,as_of):
  """The Finance reference for the host's current snapshot, created only if absent.

  This is the answer to a gap that made Finance unusable in production: nothing except the
  development seed ever wrote a `progress_snapshot_refs` row, so a real database had none
  and every live report answered 404. A financial operation that must stay reproducible --
  issuing a report, recording an override -- needs a stable reference to the exact Core
  snapshot it used, and asking a person to create one by hand would be asking them to
  transcribe a Core identifier.

  Returns None rather than raising when the host cannot answer. A host without
  `current_snapshot`, or one with no snapshot for this project yet, is not an error: it
  means there is no progress to pin to, and the report says so through its existing
  warnings instead of inventing a reference.
  """
  if not supports_current_snapshot(self.provider):return None
  feed=await self.provider.current_snapshot(str(s.organization_id),s.project_id,as_of)
  return await self.record_reference(s,feed,as_of)

 async def record_reference(self,s,feed,fallback_reporting_date=None):
  """Turn a host feed header into a stored Finance reference, idempotently."""
  metadata=feed.get("snapshot") if isinstance(feed,dict) else None
  value=reference_from_header(metadata,s,self.ids,self.clock,fallback_reporting_date)
  if value is None:return None
  return await self.repo.ensure_reference(s,value)

 async def override_history(self,s,line_id):
  """List one line's overrides; the line is resolved in-scope first so another tenant's id reveals nothing."""
  if await self.repo.get_line_mapping(s,line_id) is None:raise FinanceRecordNotFound("estimate line not found")
  return await self.repo.list_overrides(s,line_id)
 async def override(self,s,line_id,c):
  if s.actor_user_id is None:raise PermissionError("authenticated actor is required")
  ref=await self.repo.get_snapshot(s,c.progress_snapshot_id)
  if ref is None:
   # Nothing recorded for this project yet. An override is a financial correction that has
   # to name the snapshot it corrects, so pin the host's current snapshot and look again --
   # rather than requiring someone to have opened the live report first, which is an
   # ordering dependency nobody would guess.
   await self.current_reference(s,None)
   ref=await self.repo.get_snapshot(s,c.progress_snapshot_id)
  if ref is None:raise FinanceRecordNotFound("progress snapshot not found")
  line=await self.repo.get_line_mapping(s,line_id)
  if line is None:raise FinanceRecordNotFound("estimate line not found")
  # Ask the host by the host's own identifier, exactly as the live report does. Finance
  # mints progress_snapshot_id itself for an ingested reference and the host cannot resolve
  # it; references predating the Core integration have no host id and are looked up as before.
  lookup=ref.get("host_snapshot_id") or c.progress_snapshot_id
  feed=await self.provider.get_snapshot(str(s.organization_id),s.project_id,str(lookup))
  snapshot_metadata(feed,s.organization_id,s.project_id,lookup)
  assignment=ProgressPairing(snapshot_assignments(feed),assignment_keys).match(*line_keys(line))
  if assignment is None:raise ProgressMappingError("estimate line is not mapped to the selected progress snapshot")
  try:computed,_source=consumed_quantity({**assignment,"manualOverride":None})
  except ValueError as error:raise ProgressMappingError("progress snapshot has no computable baseline for this estimate line") from error
  value=ProgressOverride(self.ids(),s.organization_id,s.project_id,line_id,ref["id"],c.progress_snapshot_id,computed,c.override_value,c.reason,s.actor_user_id,self.clock())
  return await self.repo.append_override(s,value,self.ids())
