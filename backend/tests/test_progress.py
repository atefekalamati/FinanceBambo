import sys,unittest
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.domain.progress import consumed_quantity
from app.finance.schemas.progress import ProgressOverrideCreate
from app.finance.services.progress import ProgressService

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

SNAPSHOT=UUID("11111111-1111-4111-8111-111111111111")
REF=UUID("22222222-2222-4222-8222-222222222222")
LINE=UUID("33333333-3333-4333-8333-333333333333")
ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SCOPE=SimpleNamespace(organization_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),project_id="p1",actor_user_id=ACTOR)
AT=datetime(2026,8,10,tzinfo=timezone.utc)

class Provider:
 async def get_snapshot(self,organization_id,project_id,snapshot_id):
  return {"snapshot":{"organizationId":organization_id,"projectId":project_id,"progressSnapshotId":snapshot_id},"assignments":[{"assignmentExternalId":"AS1","plannedQuantity":"20","actualQuantity":"7","manualOverride":None,"task":{"activityCode":"A1"}}]}

class Repo:
 def __init__(self,overrides=None):self.overrides=overrides or [];self.appended=None
 async def get_snapshot(self,scope,snapshot_id):return {"id":REF,"progress_snapshot_id":SNAPSHOT}
 async def get_line_mapping(self,scope,line_id):return {"id":LINE,"activity_external_id":"A1","assignment_external_id":"AS1"}
 async def latest_overrides(self,scope,ref_id):return self.overrides
 async def append_override(self,scope,value,audit_id):self.appended=value;return value

class ProgressServiceTests(unittest.IsolatedAsyncioTestCase):
 def service(self,repo):return ProgressService(repo,Provider(),id_factory=lambda:UUID("44444444-4444-4444-8444-444444444444"),clock=lambda:AT)
 async def test_override_uses_backend_computed_baseline_not_client_value(self):
  repo=Repo();command=ProgressOverrideCreate(progressSnapshotId=SNAPSHOT,computedValue="999",overrideValue="9",reason="اصلاح معتبر")
  result=await self.service(repo).override(SCOPE,LINE,command)
  self.assertEqual((Decimal("7"),Decimal("9")),(result.computed_value,result.override_value))
 async def test_feed_applies_latest_persisted_override_without_mutating_provider_truth(self):
  repo=Repo([{"estimate_line_id":LINE,"computed_value":Decimal("7"),"override_value":Decimal("9"),"reason":"اصلاح معتبر","created_by":ACTOR,"created_at":AT,"activity_external_id":"A1","assignment_external_id":"AS1"}])
  feed=await self.service(repo).feed(SCOPE,SNAPSHOT);override=feed["assignments"][0]["manualOverride"]
  self.assertEqual(("7","9","manual_override"),(override["previousCalculatedValue"],override["newValue"],override["source"]))
