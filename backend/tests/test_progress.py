import sys,unittest
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.domain.progress import MEASUREMENT_TYPES, consumed_quantity, resolve_progress_quantity
from app.finance.domain.resources import FinanceRecordNotFound
from app.finance.schemas.progress import ProgressOverrideCreate,ProgressOverrideResponse
from app.finance.services.progress import ProgressService

class ProgressTests(unittest.TestCase):
 def test_fallback_order_and_sources(self):
  base={"plannedQuantity":"20","actualQuantity":None,"assignmentWorkCompletePercent":"25","task":{"taskProgressPercent":"40"},"manualOverride":None}
  self.assertEqual((Decimal("5"),"assignment_work_percent"),consumed_quantity(base))
  self.assertEqual((Decimal("7"),"assignment_actual"),consumed_quantity({**base,"actualQuantity":"7"}))
  self.assertEqual((Decimal("6"),"assignment_actual"),consumed_quantity({**base,"actualWork":"6","resourceType":"labor"}))
  self.assertEqual((Decimal("8"),"task_progress_fallback"),consumed_quantity({**base,"assignmentWorkCompletePercent":None}))
 def test_resolution_exposes_source_quality_and_warnings_without_inventing_quantity(self):
  base={"plannedQuantity":"20","actualQuantity":None,"assignmentWorkCompletePercent":None,"task":{"taskProgressPercent":"40"},"manualOverride":None}
  resolved=resolve_progress_quantity(base)
  self.assertEqual((Decimal("8"),"task_progress_fallback",Decimal("0.6")),(resolved["effective_quantity"],resolved["source_method"],resolved["quality"]))
  self.assertEqual("TASK_PROGRESS_FALLBACK",resolved["warnings"][0]["code"])
  with self.assertRaises(ValueError):resolve_progress_quantity({"plannedQuantity":None,"actualQuantity":None,"task":{}})
 def test_override_precedes_calculation_and_keeps_previous(self):
  row={"plannedQuantity":"10","actualQuantity":"4","assignmentWorkCompletePercent":None,"task":{"taskProgressPercent":None},"manualOverride":{"previousCalculatedValue":"4","newValue":"12","reason":"اصلاح پیشرفت","userId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1","occurredAt":"2026-08-08T00:00:00Z","source":"manual_override","progressSnapshotId":"11111111-1111-4111-8111-111111111111"}}
  self.assertEqual((Decimal("12"),"manual_override"),consumed_quantity(row))
 def test_missing_source_requires_override_and_reason_is_nonblank(self):
  with self.assertRaises(ValueError):consumed_quantity({"plannedQuantity":None,"actualQuantity":None,"task":{}})
  with self.assertRaises(ValueError):ProgressOverrideCreate(progressSnapshotId=UUID(int=1),overrideValue="2",reason=" ")

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
 #: This project has imported no schedule of its own, so nothing here is its active
 #: source. test_schedule_contract.py covers the flag when one does exist.
 async def active_source_version(self,scope):return None
 async def get_snapshot(self,scope,snapshot_id):return {"id":REF,"progress_snapshot_id":SNAPSHOT}
 async def get_line_mapping(self,scope,line_id):return {"id":LINE,"activity_external_id":"A1","assignment_external_id":"AS1"}
 async def latest_overrides(self,scope,ref_id):return self.overrides
 async def list_overrides(self,scope,line_id):return [row for row in self.overrides if row["estimate_line_id"]==line_id]
 async def append_override(self,scope,value,audit_id):self.appended=value;return value

class ProgressServiceTests(unittest.IsolatedAsyncioTestCase):
 def service(self,repo):return ProgressService(repo,Provider(),id_factory=lambda:UUID("44444444-4444-4444-8444-444444444444"),clock=lambda:AT)
 async def test_override_uses_backend_computed_baseline_not_client_value(self):
  repo=Repo();command=ProgressOverrideCreate(progressSnapshotId=SNAPSHOT,overrideValue="9",reason="اصلاح معتبر")
  result=await self.service(repo).override(SCOPE,LINE,command)
  self.assertEqual((Decimal("7"),Decimal("9")),(result.computed_value,result.override_value))
 async def test_override_accepts_the_client_payload_that_omits_computed_value(self):
  # The override dialog only knows the snapshot, the new value and the reason; the
  # computed baseline lives in the progress feed, so the DTO must not demand it.
  # Validated through the JSON boundary (aliases + extra="forbid"), exactly as the browser sends it.
  repo=Repo();command=ProgressOverrideCreate.model_validate({"progressSnapshotId":str(SNAPSHOT),"overrideValue":"9","reason":"اصلاح معتبر"})
  # The baseline is the backend's to determine, so the request DTO does not carry it at all.
  self.assertNotIn("computed_value",ProgressOverrideCreate.model_fields)
  result=await self.service(repo).override(SCOPE,LINE,command)
  self.assertEqual((Decimal("7"),Decimal("9")),(result.computed_value,result.override_value))
 def test_override_response_always_carries_the_backend_computed_value(self):
  payload=ProgressOverrideResponse.from_domain(SimpleNamespace(id=UUID(int=4),estimate_line_id=LINE,progress_snapshot_id=SNAPSHOT,computed_value=Decimal("7"),override_value=Decimal("9"),reason="اصلاح معتبر",created_by=ACTOR,created_at=AT)).model_dump(by_alias=True)
  self.assertEqual(("7","9","manual_override"),(payload["computedValue"],payload["overrideValue"],payload["source"]))
  with self.assertRaises(ValueError):ProgressOverrideResponse(id=UUID(int=4),estimateLineId=LINE,progressSnapshotId=SNAPSHOT,computedValue=None,overrideValue="9",reason="اصلاح معتبر",createdBy=ACTOR,createdAt=AT)
 async def test_feed_applies_latest_persisted_override_without_mutating_provider_truth(self):
  repo=Repo([{"estimate_line_id":LINE,"computed_value":Decimal("7"),"override_value":Decimal("9"),"reason":"اصلاح معتبر","created_by":ACTOR,"created_at":AT,"activity_external_id":"A1","assignment_external_id":"AS1"}])
  feed=await self.service(repo).feed(SCOPE,SNAPSHOT);override=feed["assignments"][0]["manualOverride"]
  self.assertEqual(("7","9","manual_override"),(override["previousCalculatedValue"],override["newValue"],override["source"]))
  self.assertEqual(("7","9","manual_override","1"),(feed["assignments"][0]["computedExecutedQuantity"],feed["assignments"][0]["effectiveExecutedQuantity"],feed["assignments"][0]["sourceMethod"],feed["assignments"][0]["quality"]))
 async def test_override_history_returns_the_full_trail_for_the_line(self):
  trail=[{"id":UUID(int=6),"estimate_line_id":LINE,"progress_snapshot_id":SNAPSHOT,"computed_value":Decimal("7"),"override_value":Decimal("9"),"reason":"دوم","created_by":ACTOR,"created_at":AT},
         {"id":UUID(int=5),"estimate_line_id":LINE,"progress_snapshot_id":SNAPSHOT,"computed_value":Decimal("7"),"override_value":Decimal("8"),"reason":"اول","created_by":ACTOR,"created_at":AT}]
  rows=await self.service(Repo(trail)).override_history(SCOPE,LINE)
  self.assertEqual([Decimal("9"),Decimal("8")],[row["override_value"] for row in rows])
  payload=ProgressOverrideResponse.from_row(rows[0]).model_dump(by_alias=True)
  self.assertEqual(("9","7","manual_override"),(payload["overrideValue"],payload["computedValue"],payload["source"]))

 async def test_override_history_conceals_a_line_outside_this_scope(self):
  class Foreign(Repo):
   async def get_line_mapping(self,scope,line_id):return None
  with self.assertRaises(FinanceRecordNotFound):
   await self.service(Foreign()).override_history(SCOPE,LINE)

 async def test_unpinned_finance_version_is_listed_and_read_without_a_get_write(self):
  class FinanceProvider(Provider):
   def envelope(self,organization_id,project_id,snapshot_id):
    return {"snapshot":{"organizationId":organization_id,"projectId":project_id,
      "progressSnapshotId":snapshot_id,"sourceFileVersionId":snapshot_id,
      "sourceFileNameSafe":"period-12.mpp","reportingDate":"2026-08-02",
      "status":"ready","sourceType":"microsoft_project",
      "importedBy":str(ACTOR),"importedAt":"2026-08-03T08:00:00+00:00"},
      "assignments":[]}
   async def current_snapshot(self,organization_id,project_id,as_of=None):
    return self.envelope(organization_id,project_id,str(SNAPSHOT))
   async def get_snapshot(self,organization_id,project_id,snapshot_id):
    return self.envelope(organization_id,project_id,snapshot_id)
  class UnpinnedRepo(Repo):
   async def list_snapshots(self,scope):return []
   async def get_snapshot(self,scope,snapshot_id):return None
  service=ProgressService(UnpinnedRepo(),FinanceProvider(),id_factory=lambda:REF,
                          clock=lambda:AT)
  listed=await service.list_snapshots(SCOPE)
  self.assertEqual((SNAPSHOT,date(2026,8,2),True),
                   (listed[0]["progress_snapshot_id"],listed[0]["reporting_date"],
                    listed[0]["is_latest"]))
  feed=await service.feed(SCOPE,SNAPSHOT)
  self.assertEqual(SNAPSHOT,feed["snapshot"]["progressSnapshotId"])


class MeasurementTypeTests(unittest.TestCase):
 """What kind of number each branch produced, beside which field produced it.

 `source_method` answers "where did this come from". It cannot answer "is this a
 measurement of physical work in the resource's unit", and only the second question tells
 a reader whether multiplying the number by a unit price means anything.
 """
 BASE={"plannedQuantity":"20","actualQuantity":None,"assignmentWorkCompletePercent":None,"task":{"taskProgressPercent":None},"manualOverride":None}
 OVERRIDE={"previousCalculatedValue":"3","newValue":"9","reason":"صورت‌جلسه","userId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1","occurredAt":"2026-08-08T00:00:00Z","source":"manual_override","progressSnapshotId":"11111111-1111-4111-8111-111111111111"}
 def test_each_branch_declares_a_known_measurement_type(self):
  cases={"manual_override":({"manualOverride":self.OVERRIDE},"stated_quantity"),
   "assignment_actual":({"actualQuantity":"7"},"measured_quantity"),
   "assignment_work":({"actualWork":"6","resourceType":"labor"},"work_effort"),
   "assignment_work_percent":({"assignmentWorkCompletePercent":"25"},"derived_from_percent"),
   "task_progress_fallback":({"task":{"taskProgressPercent":"40"}},"derived_from_percent")}
  for label,(patch,expected) in cases.items():
   with self.subTest(label):
    resolved=resolve_progress_quantity({**self.BASE,**patch})
    self.assertEqual(expected,resolved["measurement_type"])
    self.assertIn(resolved["measurement_type"],MEASUREMENT_TYPES)
 def test_work_effort_keeps_its_value_and_loses_its_claim_to_confidence(self):
  resolved=resolve_progress_quantity({**self.BASE,"actualWork":"6","resourceType":"labor"})
  # The number is untouched -- deciding what hours mean in kilograms is a product
  # decision, and this module does not make it.
  self.assertEqual((Decimal("6"),Decimal("6")),(resolved["computed_quantity"],resolved["effective_quantity"]))
  # Below task_progress_fallback's 0.6: that fallback at least yields the right unit.
  self.assertEqual(Decimal("0.5"),resolved["quality"])
  self.assertLess(resolved["quality"],resolve_progress_quantity({**self.BASE,"task":{"taskProgressPercent":"40"}})["quality"])
  self.assertEqual(["PROGRESS_WORK_NOT_QUANTITY"],[w["code"] for w in resolved["warnings"]])
 def test_a_measured_quantity_is_full_confidence_and_silent(self):
  resolved=resolve_progress_quantity({**self.BASE,"actualQuantity":"7"})
  self.assertEqual((Decimal("1"),[]),(resolved["quality"],resolved["warnings"]))
 def test_reported_work_beside_a_measured_quantity_raises_nothing(self):
  # An equipment assignment priced by the hour reports both. Precedence takes the measured
  # value, so the warning must stay silent; firing here would put one on every such row.
  resolved=resolve_progress_quantity({**self.BASE,"actualQuantity":"7","actualWork":"6","resourceType":"labor"})
  self.assertEqual(("measured_quantity",[]),(resolved["measurement_type"],resolved["warnings"]))
 def test_the_new_warning_does_not_displace_the_task_fallback_warning(self):
  resolved=resolve_progress_quantity({**self.BASE,"task":{"taskProgressPercent":"40"}})
  self.assertEqual(["TASK_PROGRESS_FALLBACK"],[w["code"] for w in resolved["warnings"]])
 def test_a_feed_warning_carries_only_a_code_and_a_message(self):
  # The progress feed's per-assignment warnings are bare dicts read by code, and the
  # frontend keys off `code` alone. A third key here would be a shape the UI never reads.
  resolved=resolve_progress_quantity({**self.BASE,"actualWork":"6","resourceType":"labor"})
  self.assertEqual([{"code","message"}],[set(w) for w in resolved["warnings"]])
 def test_consumed_quantity_still_answers_in_two_parts(self):
  # services/progress.py records an override baseline from this tuple; widening it would
  # break that caller for no gain, since it never needed the measurement kind.
  self.assertEqual((Decimal("6"),"assignment_actual"),consumed_quantity({**self.BASE,"actualWork":"6","resourceType":"labor"}))

class FeedMeasurementTests(unittest.IsolatedAsyncioTestCase):
 """The per-assignment feed carries the same distinction the report does.

 The progress page reads this feed row by row, so a reader looking at one assignment must
 be able to tell a measured quantity from reported effort without opening the report.
 """
 class Source(Provider):
  async def get_snapshot(self,organization_id,project_id,snapshot_id):
   return {"snapshot":{"organizationId":organization_id,"projectId":project_id,"progressSnapshotId":snapshot_id},
    "assignments":[{"assignmentExternalId":"AS1","actualQuantity":"7","manualOverride":None,"task":{"activityCode":"A1"}},
     {"assignmentExternalId":"AS2","actualWork":"6","resourceType":"labor","manualOverride":None,"task":{"activityCode":"A2"}},
     {"assignmentExternalId":"AS3","manualOverride":None,"task":{"activityCode":"A3"}}]}
 def service(self):return ProgressService(Repo(),self.Source(),id_factory=lambda:UUID(int=4),clock=lambda:AT)
 async def test_each_row_says_what_kind_of_number_it_reports(self):
  rows={row["assignmentExternalId"]:row for row in (await self.service().feed(SCOPE,SNAPSHOT))["assignments"]}
  self.assertEqual(["measured_quantity","work_effort",None],
   [rows["AS1"]["measurementType"],rows["AS2"]["measurementType"],rows["AS3"]["measurementType"]])
 async def test_the_effort_row_keeps_its_quantity_and_carries_the_warning(self):
  rows={row["assignmentExternalId"]:row for row in (await self.service().feed(SCOPE,SNAPSHOT))["assignments"]}
  self.assertEqual(("6","6","0.5"),(rows["AS2"]["computedExecutedQuantity"],rows["AS2"]["effectiveExecutedQuantity"],rows["AS2"]["quality"]))
  # Under the frontend's LOW_QUALITY_THRESHOLD of 0.8, so the existing low-quality note
  # appears on this row with no frontend change at all.
  self.assertLess(float(rows["AS2"]["quality"]),0.8)
  self.assertEqual(["PROGRESS_WORK_NOT_QUANTITY"],[w["code"] for w in rows["AS2"]["warnings"]])
 async def test_a_row_with_nothing_to_report_is_unchanged(self):
  rows={row["assignmentExternalId"]:row for row in (await self.service().feed(SCOPE,SNAPSHOT))["assignments"]}
  self.assertEqual(("missing",None,"0"),(rows["AS3"]["sourceMethod"],rows["AS3"]["measurementType"],rows["AS3"]["quality"]))
  self.assertEqual(["PROGRESS_MISSING"],[w["code"] for w in rows["AS3"]["warnings"]])
 async def test_each_row_says_how_far_to_trust_its_quantity(self):
  rows={row["assignmentExternalId"]:row for row in (await self.service().feed(SCOPE,SNAPSHOT))["assignments"]}
  self.assertEqual(["measured","fallback","unavailable"],
   [rows["AS1"]["progressStatus"],rows["AS2"]["progressStatus"],rows["AS3"]["progressStatus"]])
 async def test_the_feed_never_reports_a_line_level_status(self):
  # unmapped_assignment and unmapped_activity describe an estimate line that reached no
  # assignment. A feed row IS an assignment, so neither can be true of it.
  for row in (await self.service().feed(SCOPE,SNAPSHOT))["assignments"]:
   self.assertNotIn("unmapped",row["progressStatus"])
class HostIdentifierLookupTests(unittest.IsolatedAsyncioTestCase):
 """`feed()` must ask the host with the host's own identifier.

 The fourth place this mistake lived. `_calculate` and `override` were fixed earlier;
 `feed()` still loaded the reference row -- which carries `host_snapshot_id` -- and then
 asked the provider with Finance's UUID, which a real host has never issued and cannot
 recognise. It passed every test because the development fixture answers to both.
 """

 class HostOnlyProvider:
  """A provider that behaves like a real one: it knows its own ids and nothing else."""
  def __init__(self):self.asked=[]
  async def get_snapshot(self,organization_id,project_id,snapshot_id):
   self.asked.append(snapshot_id)
   if snapshot_id!="9003":return None
   return {"snapshot":{"organizationId":organization_id,"projectId":project_id,"progressSnapshotId":"9003"},
           "assignments":[{"assignmentExternalId":None,"plannedQuantity":"20","actualQuantity":"7","manualOverride":None,"task":{"activityCode":"A1"}}]}

 class HostRefRepo(Repo):
  async def get_snapshot(self,scope,snapshot_id):
   return {"id":REF,"progress_snapshot_id":SNAPSHOT,"host_snapshot_id":9003}

 async def test_the_feed_is_requested_by_the_host_snapshot_id(self):
  provider=self.HostOnlyProvider()
  service=ProgressService(self.HostRefRepo(),provider,id_factory=lambda:UUID(int=4),clock=lambda:AT)
  result=await service.feed(SCOPE,SNAPSHOT)
  self.assertEqual(["9003"],provider.asked,"asked with the Core id, not Finance's UUID")
  self.assertEqual(1,len(result["assignments"]))
  self.assertEqual("7",result["assignments"][0]["effectiveExecutedQuantity"])

 async def test_finance_uuid_is_still_used_when_no_host_id_was_recorded(self):
  """References created before 0006 have no host id, and must keep working."""
  provider=self.HostOnlyProvider()
  service=ProgressService(Repo(),provider,id_factory=lambda:UUID(int=4),clock=lambda:AT)
  with self.assertRaises(FinanceRecordNotFound):await service.feed(SCOPE,SNAPSHOT)
  self.assertEqual([str(SNAPSHOT)],provider.asked)
