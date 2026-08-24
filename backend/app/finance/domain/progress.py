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

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

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

def _override_payload(row,snapshot_id):
 return {"previousCalculatedValue":str(row["computed_value"]),"newValue":str(row["override_value"]),"reason":row["reason"],"userId":str(row["created_by"]),"occurredAt":row["created_at"].isoformat(),"source":"manual_override","progressSnapshotId":str(snapshot_id)}

def apply_progress_overrides(assignments,overrides,snapshot_id):
 by_assignment={row["assignment_external_id"]:row for row in overrides if row.get("assignment_external_id")}
 by_activity={row["activity_external_id"]:row for row in overrides if row.get("activity_external_id")}
 result=[]
 for source in assignments:
  row=dict(source)
  override=by_assignment.get(row.get("assignmentExternalId")) or by_activity.get((row.get("task") or {}).get("activityCode"))
  if override is not None:row["manualOverride"]=_override_payload(override,snapshot_id)
  result.append(row)
 return result

@dataclass(frozen=True)
class ProgressOverride:
 id:UUID;organization_id:UUID;project_id:str;estimate_line_id:UUID;progress_snapshot_ref_id:UUID;progress_snapshot_id:UUID;computed_value:Decimal;override_value:Decimal;reason:str;created_by:UUID;created_at:datetime
