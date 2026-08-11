from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

def resolve_progress_quantity(a):
 warnings=[]
 o=a.get("manualOverride")
 if o is not None:
  required=("previousCalculatedValue","newValue","reason","userId","occurredAt","progressSnapshotId")
  if o.get("source")!="manual_override" or any(not o.get(k) for k in required):raise ValueError("manual override requires complete audit metadata")
  computed=Decimal(o["previousCalculatedValue"]);effective=Decimal(o["newValue"])
  return {"computed_quantity":computed,"effective_quantity":effective,"source_method":"manual_override","quality":Decimal("1"),"warnings":warnings}
 if a.get("actualQuantity") is not None:
  value=Decimal(a["actualQuantity"])
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_actual","quality":Decimal("1"),"warnings":warnings}
 if a.get("actualWork") is not None:
  value=Decimal(a["actualWork"])
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_actual","quality":Decimal("1"),"warnings":warnings}
 planned=a.get("plannedQuantity")
 if planned is not None and a.get("assignmentWorkCompletePercent") is not None:
  value=Decimal(planned)*Decimal(a["assignmentWorkCompletePercent"])/100
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_work_percent","quality":Decimal("0.8"),"warnings":warnings}
 percent=(a.get("task") or {}).get("taskProgressPercent")
 if planned is not None and percent is not None:
  value=Decimal(planned)*Decimal(percent)/100
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"task_progress_fallback","quality":Decimal("0.6"),"warnings":[{"code":"TASK_PROGRESS_FALLBACK","message":"Executed quantity was resolved from task progress because assignment-level progress was unavailable."}]}
 raise ValueError("manual override is required when no calculation source exists")

def consumed_quantity(a):
 resolved=resolve_progress_quantity(a)
 return resolved["effective_quantity"],resolved["source_method"]

@dataclass(frozen=True)
class ProgressOverride:
 id:UUID;organization_id:UUID;project_id:str;estimate_line_id:UUID;progress_snapshot_ref_id:UUID;progress_snapshot_id:UUID;computed_value:Decimal;override_value:Decimal;reason:str;created_by:UUID;created_at:datetime
