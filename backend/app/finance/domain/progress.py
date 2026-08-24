"""How an assignment's reported progress becomes an executed quantity.

The branches below are a precedence, not a menu: the first source that can answer wins,
and each later one is a fallback carrying a lower `quality`.

WHY `measurement_type` EXISTS
`source_method` names the field a number came from. It does not say whether that number is
a measurement of physical work in the resource's own unit, and the difference matters
because `domain/reports.py` turns the result straight into money:

    executed_value = money(executed * current)   # current is IRR per kg, per m3, per hour

`actualQuantity` is stated in the resource's unit, so that product is money.

`actualWork` is effort. The schedule contract (`domain/schedule.py`) keeps work and
quantity in separate fields precisely because they are different things, and it states no
unit for work at all -- so `actualWork * IRR-per-kg` is money only if the resource happens
to be priced in whatever unit the effort was counted in. Nothing available here can
establish that: the assignment's `unit` is the resource's unit, not the work's, and
`PRODUCTION_MSP_AUDIT_FA.md` section 6 is still an open question against real data.

So the value is passed through unchanged and labelled: `measurement_type` says what kind
of number it is, `quality` drops below every fallback that at least produces a value in
the right unit, and PROGRESS_WORK_NOT_QUANTITY says so out loud.

WHY IT IS PASSED THROUGH AT ALL
Refusing it would push the line into "no progress" and report 0% executed, which is a
different wrong answer rather than an absent one. Which of the two is correct is a product
decision this module does not own, so it keeps the existing number and stops claiming the
number is something it is not.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .resources import FinanceRecordNotFound

#: What kind of number `effective_quantity` is, independent of which field supplied it.
#:   measured_quantity   -- reported in the resource's own unit
#:   work_effort         -- reported as effort; its unit is not stated by the source
#:   derived_from_percent-- planned quantity scaled by a percentage, so in the right unit
#:   stated_quantity     -- a person put the number there, with an audit record
MEASUREMENT_TYPES=("measured_quantity","work_effort","derived_from_percent","stated_quantity")

#: Effort used as a quantity sits below `task_progress_fallback` (0.6) on purpose: a
#: fallback derived from a percentage is at least denominated in the resource's unit, and
#: this is not. The number is only ever reported, never multiplied into a metric.
WORK_AS_QUANTITY_QUALITY=Decimal("0.5")

#: How much a reader should trust the quantity, coarser than `measurement_type` and meant
#: for a reader who only wants to know whether to trust it:
#:   measured -- the assignment stated this quantity, or a person did with an audit record
#:   fallback -- it stands in for a quantity nobody stated: derived from a percentage, or
#:               taken from effort in a unit the source never declared
#: The finer reason stays in `measurement_type`, and the two are derived from one table so
#: they cannot drift apart. Report-level statuses -- unavailable, and the two unmapped ones
#: -- are about an estimate line rather than an assignment, so they live in
#: `domain/reports.py` and never appear here.
PROGRESS_MEASURED="measured"
PROGRESS_FALLBACK="fallback"
MEASUREMENT_STATUS={"measured_quantity":PROGRESS_MEASURED,"stated_quantity":PROGRESS_MEASURED,
 "derived_from_percent":PROGRESS_FALLBACK,"work_effort":PROGRESS_FALLBACK}

def resolve_progress_quantity(a):
 warnings=[]
 o=a.get("manualOverride")
 if o is not None:
  required=("previousCalculatedValue","newValue","reason","userId","occurredAt","progressSnapshotId")
  if o.get("source")!="manual_override" or any(not o.get(k) for k in required):raise ValueError("manual override requires complete audit metadata")
  computed=Decimal(o["previousCalculatedValue"]);effective=Decimal(o["newValue"])
  return {"computed_quantity":computed,"effective_quantity":effective,"source_method":"manual_override","measurement_type":"stated_quantity","progress_status":MEASUREMENT_STATUS["stated_quantity"],"quality":Decimal("1"),"warnings":warnings}
 if a.get("actualQuantity") is not None:
  value=Decimal(a["actualQuantity"])
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_actual","measurement_type":"measured_quantity","progress_status":MEASUREMENT_STATUS["measured_quantity"],"quality":Decimal("1"),"warnings":warnings}
 if a.get("actualWork") is not None:
  # Effort, taken as a quantity without any unit reconciliation. See the module docstring:
  # the value is unchanged, the metadata around it is not.
  value=Decimal(a["actualWork"])
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_actual","measurement_type":"work_effort","progress_status":MEASUREMENT_STATUS["work_effort"],"quality":WORK_AS_QUANTITY_QUALITY,
   "warnings":[{"code":"PROGRESS_WORK_NOT_QUANTITY","message":"Executed quantity was taken from reported work effort; the source stated no measured quantity in the resource's unit."}]}
 planned=a.get("plannedQuantity")
 if planned is not None and a.get("assignmentWorkCompletePercent") is not None:
  value=Decimal(planned)*Decimal(a["assignmentWorkCompletePercent"])/100
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_work_percent","measurement_type":"derived_from_percent","progress_status":MEASUREMENT_STATUS["derived_from_percent"],"quality":Decimal("0.8"),"warnings":warnings}
 percent=(a.get("task") or {}).get("taskProgressPercent")
 if planned is not None and percent is not None:
  value=Decimal(planned)*Decimal(percent)/100
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"task_progress_fallback","measurement_type":"derived_from_percent","progress_status":MEASUREMENT_STATUS["derived_from_percent"],"quality":Decimal("0.6"),"warnings":[{"code":"TASK_PROGRESS_FALLBACK","message":"Executed quantity was resolved from task progress because assignment-level progress was unavailable."}]}
 raise ValueError("manual override is required when no calculation source exists")

def consumed_quantity(a):
 """Effective quantity and the field it came from.

 Kept as a two-tuple: `services/progress.py` needs exactly this to record an override's
 baseline. A caller that needs to know what kind of number it received reads
 `resolve_progress_quantity` directly, as `domain/reports.py` does.
 """
 resolved=resolve_progress_quantity(a)
 return resolved["effective_quantity"],resolved["source_method"]

def snapshot_metadata(feed,organization_id,project_id,snapshot_id):
 """The feed's header, proven to describe the snapshot that was actually asked for.

 `ProgressSnapshotProvider` is implemented by the host and its port constrains nothing
 about the reply, so Finance has to treat every shape as possible: no reply at all, a
 reply with no header, a header that is empty, or a header describing another tenant's
 snapshot. Reading straight through any of those raised KeyError or TypeError and left
 the caller with a 500, which says "this service is broken" about a request that was
 simply for something the provider does not have.

 All of them end as FinanceRecordNotFound -- a 404 in the existing envelope. Not found
 rather than a validation error on purpose: the requester named a snapshot id, and
 answering "malformed" for a header belonging to another tenant would confirm that the
 id exists somewhere. A caller who may not see it and a caller asking for something
 absent get the same answer.
 """
 metadata=feed.get("snapshot") if isinstance(feed,Mapping) else None
 if not isinstance(metadata,Mapping):raise FinanceRecordNotFound("progress snapshot not found")
 if (str(metadata.get("organizationId"))!=str(organization_id)
   or metadata.get("projectId")!=project_id
   or str(metadata.get("progressSnapshotId"))!=str(snapshot_id)):
  raise FinanceRecordNotFound("progress snapshot not found")
 return metadata

def snapshot_assignments(feed):
 """The feed's assignment rows, whatever the provider put in their place.

 A snapshot with no assignments is a legitimate answer -- a schedule can be imported
 before anyone reports against it -- so an absent or null list is an empty one here, not
 an error. Only the header decides whether the snapshot exists; see `snapshot_metadata`.
 A string is rejected along with everything else that is not a sequence of rows, because
 iterating one would silently produce a feed of characters.
 """
 rows=feed.get("assignments") if isinstance(feed,Mapping) else None
 if isinstance(rows,Sequence) and not isinstance(rows,(str,bytes)):return list(rows)
 return []


def assignment_keys(row):
 """The identifier pair a progress-feed row is found by."""
 return row.get("assignmentExternalId"),(row.get("task") or {}).get("activityCode")

def line_keys(row):
 """The same pair as an estimate line -- or an override of one -- states it."""
 return row.get("assignment_external_id"),row.get("activity_external_id")

class ProgressPairing:
 """Which progress-feed row belongs to which estimate line.

 The rule: they are paired when their assignment external ids match, and failing that
 when their activity external ids match. The assignment id wins because it is the more
 specific claim -- an activity can carry many assignments, so an activity match says only
 that the two are about the same piece of schedule, not about the same resource.

 WHY THIS IS ONE OBJECT USED TWICE
 The rule was written three times: once in `domain/reports.py` to find a line's
 assignment, once in `services/progress.py` for the same thing, and once in
 `apply_progress_overrides` below to go the other way -- from a feed row to the override
 stored against a line. The last is the same pairing with the roles swapped, which is why
 `keys` is a parameter: it says which of the two vocabularies the indexed rows speak, and
 the direction follows from what the caller then matches against.

 THE TWO THAT DISAGREED
 They were not merely duplicated, they gave different answers. `domain/reports.py` built
 two indexes and consulted the assignment one first, so the assignment id always won.
 `services/progress.py` scanned the feed and took the first row satisfying either test, so
 row order won: a line naming ASG-2 on activity ACT-1 paired with ASG-9 whenever ASG-9
 merely shared ACT-1 and came first. An override's baseline could therefore be computed
 from a different assignment than the one the report had used for that same line. This
 class keeps the report's precedence, which is the one the code was reaching for.

 Ties within one index are resolved as they always were: the last row wins, because both
 previous versions built plain dicts.
 """

 __slots__=("_by_assignment","_by_activity")

 def __init__(self,rows,keys):
  self._by_assignment={};self._by_activity={}
  for row in rows:
   assignment_external_id,activity_external_id=keys(row)
   if assignment_external_id:self._by_assignment[assignment_external_id]=row
   if activity_external_id:self._by_activity[activity_external_id]=row

 def match(self,assignment_external_id,activity_external_id):
  """The paired row, or None.

  No guard against a blank or absent identifier here: `__init__` refuses to index one, so
  looking one up finds nothing. Guarding in both places would leave neither able to fail
  on its own, and this is also exactly what `domain/reports.py` did before -- a plain
  lookup of whatever the line claimed.
  """
  paired=self._by_assignment.get(assignment_external_id)
  if paired is not None:return paired
  return self._by_activity.get(activity_external_id)

def _override_payload(row,snapshot_id):
 return {"previousCalculatedValue":str(row["computed_value"]),"newValue":str(row["override_value"]),"reason":row["reason"],"userId":str(row["created_by"]),"occurredAt":row["created_at"].isoformat(),"source":"manual_override","progressSnapshotId":str(snapshot_id)}

def apply_progress_overrides(assignments,overrides,snapshot_id):
 # The reverse direction: the overrides are indexed by the line identifiers they carry,
 # and each feed row is matched against them. Same rule, same precedence, read backwards.
 pairing=ProgressPairing(overrides,line_keys)
 result=[]
 for source in assignments:
  row=dict(source)
  override=pairing.match(*assignment_keys(row))
  if override is not None:row["manualOverride"]=_override_payload(override,snapshot_id)
  result.append(row)
 return result

@dataclass(frozen=True)
class ProgressOverride:
 id:UUID;organization_id:UUID;project_id:str;estimate_line_id:UUID;progress_snapshot_ref_id:UUID;progress_snapshot_id:UUID;computed_value:Decimal;override_value:Decimal;reason:str;created_by:UUID;created_at:datetime
