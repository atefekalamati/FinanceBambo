from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

def consumed_quantity(a):
 o=a.get("manualOverride")
 if o is not None:
  required=("previousCalculatedValue","newValue","reason","userId","occurredAt","progressSnapshotId")
  if o.get("source")!="manual_override" or any(not o.get(k) for k in required):raise ValueError("manual override requires complete audit metadata")
  return Decimal(o["newValue"]),"manual_override"
 if a.get("actualQuantity") is not None:return Decimal(a["actualQuantity"]),"assignment_actual"
 if a.get("actualWork") is not None:return Decimal(a["actualWork"]),"assignment_actual"
 planned=a.get("plannedQuantity")
 if planned is not None and a.get("assignmentWorkCompletePercent") is not None:return Decimal(planned)*Decimal(a["assignmentWorkCompletePercent"])/100,"assignment_work_percent"
 percent=(a.get("task") or {}).get("taskProgressPercent")
 if planned is not None and percent is not None:return Decimal(planned)*Decimal(percent)/100,"task_progress_fallback"
 raise ValueError("manual override is required when no calculation source exists")

@dataclass(frozen=True)
class ProgressOverride:
 id:UUID;organization_id:UUID;project_id:str;estimate_line_id:UUID;progress_snapshot_ref_id:UUID;progress_snapshot_id:UUID;computed_value:Decimal;override_value:Decimal;reason:str;created_by:UUID;created_at:datetime
