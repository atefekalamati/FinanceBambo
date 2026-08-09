import sys,unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.domain.progress import consumed_quantity
from app.finance.schemas.progress import ProgressOverrideCreate

class ProgressTests(unittest.TestCase):
 def test_fallback_order_and_sources(self):
  base={"plannedQuantity":"20","actualQuantity":None,"assignmentWorkCompletePercent":"25","task":{"taskProgressPercent":"40"},"manualOverride":None}
  self.assertEqual((Decimal("5"),"assignment_work_percent"),consumed_quantity(base))
  self.assertEqual((Decimal("7"),"assignment_actual"),consumed_quantity({**base,"actualQuantity":"7"}))
  self.assertEqual((Decimal("6"),"assignment_actual"),consumed_quantity({**base,"actualWork":"6"}))
  self.assertEqual((Decimal("8"),"task_progress_fallback"),consumed_quantity({**base,"assignmentWorkCompletePercent":None}))
 def test_override_precedes_calculation_and_keeps_previous(self):
  row={"plannedQuantity":"10","actualQuantity":"4","assignmentWorkCompletePercent":None,"task":{"taskProgressPercent":None},"manualOverride":{"previousCalculatedValue":"4","newValue":"12","reason":"اصلاح پیشرفت","userId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1","occurredAt":"2026-08-08T00:00:00Z","source":"manual_override","progressSnapshotId":"11111111-1111-4111-8111-111111111111"}}
  self.assertEqual((Decimal("12"),"manual_override"),consumed_quantity(row))
 def test_missing_source_requires_override_and_reason_is_nonblank(self):
  with self.assertRaises(ValueError):consumed_quantity({"plannedQuantity":None,"actualQuantity":None,"task":{}})
  with self.assertRaises(ValueError):ProgressOverrideCreate(progressSnapshotId=UUID(int=1),computedValue="1",overrideValue="2",reason=" ")
