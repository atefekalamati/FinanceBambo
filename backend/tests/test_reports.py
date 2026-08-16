import sys
import io
import unittest
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from openpyxl import load_workbook

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.reports import calculate_live_report
from app.finance.domain.resources import FinanceRecordNotFound
from app.finance.services.reports import FinanceLiveReportService
from app.finance.schemas.reports import ReportSnapshotReference
from app.finance.repositories.reports import PsycopgLiveReportRepository


MATERIAL_LINE = UUID("10000000-0000-4000-8000-000000000001")
LABOR_LINE = UUID("10000000-0000-4000-8000-000000000002")
GENERAL_LINE = UUID("10000000-0000-4000-8000-000000000003")
MATERIAL = UUID("20000000-0000-4000-8000-000000000001")
LABOR = UUID("20000000-0000-4000-8000-000000000002")
GENERAL = UUID("20000000-0000-4000-8000-000000000003")
SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")


def estimate(line_id, resource_id, kind, quantity, revised, original_price, current_price, assignment):
    return {"id": line_id, "resource_id": resource_id, "resource_type": kind,
            "resource_code": kind[:3], "resource_title": kind,
            "original_quantity": quantity, "revised_quantity": revised,
            "original_unit_price_irr": original_price,
            "current_unit_price_irr": current_price,
            "assignment_external_id": assignment, "activity_external_id": None,
            "progress_snapshot_id": SNAPSHOT}


class LiveReportDomainTests(unittest.TestCase):
    def test_calculates_eight_prd_metrics_and_charts(self):
        estimates = [
            estimate(MATERIAL_LINE, MATERIAL, "material", "10", "12", "100", "150", "a-m"),
            estimate(LABOR_LINE, LABOR, "labor", "5", "5", "100", "200", "a-l"),
            estimate(GENERAL_LINE, GENERAL, "general_cost", None, "1200", "1000", None, None),
        ]
        invoices = [
            {"estimate_line_id": MATERIAL_LINE, "resource_id": MATERIAL, "quantity": "4",
             "unit": "box", "base_unit": "each", "dimension": "count",
             "final_line_amount_irr": "800", "financial_effect_sign": 1, "resource_type": "material"},
            {"estimate_line_id": None, "resource_id": MATERIAL, "quantity": "2",
             "unit": "each", "base_unit": "each", "dimension": "count",
             "final_line_amount_irr": "200", "financial_effect_sign": 1, "resource_type": "material"},
            {"estimate_line_id": None, "resource_id": MATERIAL, "quantity": "2",
             "unit": "each", "base_unit": "each", "dimension": "count",
             "final_line_amount_irr": "200", "financial_effect_sign": -1, "resource_type": "material"},
            {"estimate_line_id": LABOR_LINE, "resource_id": LABOR, "quantity": "1",
             "unit": "hour", "base_unit": "hour", "dimension": "time",
             "final_line_amount_irr": "200", "financial_effect_sign": 1, "resource_type": "labor"},
            {"estimate_line_id": GENERAL_LINE, "resource_id": GENERAL, "quantity": None,
             "unit": None, "base_unit": None, "dimension": "lump_sum",
             "final_line_amount_irr": "1300", "financial_effect_sign": 1, "resource_type": "general_cost"},
        ]
        assignments = [
            {"assignmentExternalId": "a-m", "actualQuantity": "4", "task": {}},
            {"assignmentExternalId": "a-l", "actualWork": "2", "task": {}},
        ]
        report = calculate_live_report(estimates, invoices, assignments,
                                       [{"source_unit": "box", "target_unit": "each", "dimension": "count", "factor": "2"}], "10")
        self.assertEqual(8, len(report.metrics))
        self.assertEqual({
            "initialEstimateIrr": Decimal("2500"), "actualCostIrr": Decimal("2300"),
            "currentExecutedValueIrr": Decimal("1000"), "remainingPhysicalCostIrr": Decimal("1800"),
            "moneyRequiredToContinueIrr": Decimal("1200"), "forecastFinalCostIrr": Decimal("3500"),
            "actualCostPerSquareMeterIrr": Decimal("230"), "forecastPerSquareMeterIrr": Decimal("350")}, report.metrics)
        by_type = {row["resourceType"]: row for row in report.breakdown}
        self.assertEqual(Decimal("1200"), by_type["material"]["revisedEstimateIrr"])
        self.assertEqual(Decimal("1200"), by_type["general_cost"]["revisedEstimateIrr"])
        self.assertEqual(Decimal("1200"), by_type["material"]["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("0"), by_type["general_cost"]["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("1400"), by_type["material"]["forecastFinalIrr"])
        self.assertEqual(Decimal("800"), by_type["labor"]["forecastFinalIrr"])
        self.assertEqual(Decimal("1300"), by_type["general_cost"]["forecastFinalIrr"])
        self.assertEqual(Decimal("400"), report.price_variances[0]["varianceIrr"])
        self.assertEqual((Decimal("12"),Decimal("8"),Decimal("100"),Decimal("150")), (report.price_variances[0]["revisedQuantity"],report.price_variances[0]["remainingQuantity"],report.price_variances[0]["estimateBaseUnitPriceIrr"],report.price_variances[0]["currentUnitPriceIrr"]))
        self.assertEqual(Decimal("50.0000"), report.price_variances[0]["priceVariancePercent"])
        self.assertEqual(Decimal("2"), report.quantity_variances[0]["varianceQuantity"])
        self.assertEqual(("assignment_actual",SNAPSHOT), (report.quantity_variances[0]["sourceMethod"],report.quantity_variances[0].get("progressSnapshotId")))
        self.assertIn("GENERAL_COST_OVERRUN", {warning["code"] for warning in report.warnings})

    def test_reports_missing_sources_as_warnings(self):
        row = estimate(MATERIAL_LINE, MATERIAL, "material", "1", "1", "10", None, None)
        invoice = {"estimate_line_id": MATERIAL_LINE, "resource_id": MATERIAL, "quantity": "1",
                   "unit": "box", "base_unit": "each", "dimension": "count",
                   "final_line_amount_irr": "10", "financial_effect_sign": 1, "resource_type": "material"}
        report = calculate_live_report([row], [invoice], [], [], None)
        self.assertEqual({"PROGRESS_MISSING", "CURRENT_PRICE_MISSING", "UNIT_CONVERSION_MISSING", "GROSS_AREA_MISSING"},
                         {warning["code"] for warning in report.warnings})
        self.assertIsNone(report.metrics["actualCostPerSquareMeterIrr"])
        self.assertEqual(("incomplete",1),(report.calculation_status,report.missing_price_count))
        self.assertIsNone(report.metrics["forecastFinalCostIrr"])
        self.assertIn("forecastFinalCostIrr",report.incomplete_metric_keys)
        warning=next(item for item in report.warnings if item["code"]=="CURRENT_PRICE_MISSING")
        self.assertEqual((str(MATERIAL_LINE),str(MATERIAL),"mat",True),(warning["estimateLineId"],warning["resourceId"],warning["resourceCode"],warning["excludedFromCalculation"]))

    def test_general_cost_remaining_uses_category_formula_without_line_double_subtraction(self):
        line2=UUID("10000000-0000-4000-8000-000000000004");res2=UUID("20000000-0000-4000-8000-000000000004")
        estimates=[estimate(GENERAL_LINE,GENERAL,"general_cost",None,"1000","1000",None,None),estimate(line2,res2,"general_cost",None,"500","500",None,None)]
        invoices=[
            {"estimate_line_id":GENERAL_LINE,"resource_id":GENERAL,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"800","financial_effect_sign":1,"resource_type":"general_cost"},
            {"estimate_line_id":GENERAL_LINE,"resource_id":GENERAL,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"100","financial_effect_sign":-1,"resource_type":"general_cost"},
            {"estimate_line_id":line2,"resource_id":res2,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"700","financial_effect_sign":1,"resource_type":"general_cost"},
        ]
        row={item["resourceType"]:item for item in calculate_live_report(estimates,invoices,[],[],"10").breakdown}["general_cost"]
        self.assertEqual((Decimal("1500"),Decimal("1400"),Decimal("100"),Decimal("1500")),(row["revisedEstimateIrr"],row["actualCostIrr"],row["remainingPhysicalCostIrr"],row["forecastFinalIrr"]))

    def test_resource_level_purchase_is_allocated_once_across_multiple_estimate_lines(self):
        line2=UUID("10000000-0000-4000-8000-000000000004")
        estimates=[estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-1"),estimate(line2,MATERIAL,"material","10","10","100","100","a-2")]
        invoices=[{"estimate_line_id":None,"resource_id":MATERIAL,"quantity":"10","unit":"each","base_unit":"each","dimension":"count","final_line_amount_irr":"1000","financial_effect_sign":1,"resource_type":"material","resource_code":"mat"}]
        assignments=[{"assignmentExternalId":"a-1","actualQuantity":"0","task":{}},{"assignmentExternalId":"a-2","actualQuantity":"0","task":{}}]
        report=calculate_live_report(estimates,invoices,assignments,[],"10")
        self.assertEqual(Decimal("1000"),report.metrics["moneyRequiredToContinueIrr"])
        self.assertEqual(Decimal("2000"),report.metrics["forecastFinalCostIrr"])
        self.assertEqual(Decimal("1000"),{row["resourceType"]:row for row in report.breakdown}["material"]["actualCostIrr"])

    def test_resource_level_actual_cost_is_not_duplicated_across_lines(self):
        line2=UUID("10000000-0000-4000-8000-000000000004")
        estimates=[estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-1"),estimate(line2,MATERIAL,"material","10","10","100","100","a-2")]
        invoices=[{"estimate_line_id":None,"resource_id":MATERIAL,"quantity":"1","unit":"each","base_unit":"each","dimension":"count","final_line_amount_irr":"1000","financial_effect_sign":1,"resource_type":"material","resource_code":"mat"}]
        assignments=[{"assignmentExternalId":"a-1","actualQuantity":"0","task":{}},{"assignmentExternalId":"a-2","actualQuantity":"0","task":{}}]
        report=calculate_live_report(estimates,invoices,assignments,[],"10")
        actual_sum=sum(item["actualCostIrr"] for item in report.all_price_variances if item["resourceId"]==str(MATERIAL))
        self.assertLessEqual(actual_sum,Decimal("1000"))
        self.assertEqual(Decimal("1000"),actual_sum)

    def test_line_linked_and_resource_level_purchases_are_combined_without_duplication(self):
        line2=UUID("10000000-0000-4000-8000-000000000004")
        estimates=[estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-1"),estimate(line2,MATERIAL,"material","10","10","100","100","a-2")]
        invoices=[
            {"estimate_line_id":MATERIAL_LINE,"resource_id":MATERIAL,"quantity":"4","unit":"each","base_unit":"each","dimension":"count","final_line_amount_irr":"400","financial_effect_sign":1,"resource_type":"material","resource_code":"mat"},
            {"estimate_line_id":None,"resource_id":MATERIAL,"quantity":"10","unit":"each","base_unit":"each","dimension":"count","final_line_amount_irr":"1000","financial_effect_sign":1,"resource_type":"material","resource_code":"mat"},
        ]
        assignments=[{"assignmentExternalId":"a-1","actualQuantity":"0","task":{}},{"assignmentExternalId":"a-2","actualQuantity":"0","task":{}}]
        report=calculate_live_report(estimates,invoices,assignments,[],"10")
        self.assertEqual(Decimal("600"),report.metrics["moneyRequiredToContinueIrr"])
        self.assertEqual(Decimal("2000"),report.metrics["forecastFinalCostIrr"])

    def test_missing_conversion_marks_purchase_dependent_forecast_incomplete(self):
        row=estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-m")
        invoice={"estimate_line_id":None,"resource_id":MATERIAL,"quantity":"5","unit":"box","base_unit":"each","dimension":"count","final_line_amount_irr":"500","financial_effect_sign":1,"resource_type":"material","resource_code":"mat"}
        report=calculate_live_report([row],[invoice],[{"assignmentExternalId":"a-m","actualQuantity":"0","task":{}}],[],"10")
        self.assertEqual("incomplete",report.calculation_status)
        self.assertIsNone(report.metrics["moneyRequiredToContinueIrr"])
        self.assertIsNone(report.metrics["forecastFinalCostIrr"])
        warning=next(item for item in report.warnings if item["code"]=="UNIT_CONVERSION_MISSING")
        self.assertEqual((str(MATERIAL),"mat",True),(warning["resourceId"],warning["resourceCode"],warning["excludedFromCalculation"]))
        self.assertIn("forecastFinalCostIrr",warning["affectedMetricKeys"])

    def test_progress_quality_metadata_counts_sources(self):
        estimates=[estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-1"),estimate(LABOR_LINE,LABOR,"labor","10","10","100","100","a-2")]
        assignments=[
            {"assignmentExternalId":"a-1","actualQuantity":"3","manualOverride":{"previousCalculatedValue":"3","newValue":"4","reason":"field correction","userId":str(UUID(int=8)),"occurredAt":"2026-08-02T00:00:00+00:00","progressSnapshotId":str(SNAPSHOT),"source":"manual_override"},"task":{}},
            {"assignmentExternalId":"a-2","plannedQuantity":"10","task":{"taskProgressPercent":"50"}},
        ]
        report=calculate_live_report(estimates,[],assignments,[],"10")
        self.assertEqual({"complete":False,"manualOverrideCount":1,"taskFallbackCount":1,"missingCount":0,"assignmentActualCount":0,"assignmentPercentFallbackCount":0},report.progress_quality)

    def test_quantity_overrun_warns_with_deviation_without_clamping(self):
        row = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-m")
        report = calculate_live_report([row], [], [{"assignmentExternalId":"a-m","actualQuantity":"12","task":{}}], [], "10")
        warning = next(item for item in report.warnings if item["code"] == "QUANTITY_OVERRUN")
        self.assertEqual(("2","20.0000"), (warning["deviationQuantity"], warning["deviationPercent"]))
        self.assertEqual(Decimal("1200"), report.metrics["currentExecutedValueIrr"])
        self.assertEqual(Decimal("0"), report.metrics["remainingPhysicalCostIrr"])

    def test_rounds_money_once_per_line_with_round_half_up(self):
        estimates = [
            estimate(UUID(int=index + 1), MATERIAL, "material", "0.5", "0.5", "1", "1", f"a-{index}")
            for index in range(1000)
        ]
        assignments = [{"assignmentExternalId": f"a-{index}", "actualQuantity": "0.5", "task": {}} for index in range(1000)]
        report = calculate_live_report(estimates, [], assignments, [], "1000")
        self.assertEqual(Decimal("1000"), report.metrics["initialEstimateIrr"])
        self.assertEqual(Decimal("1000"), report.metrics["currentExecutedValueIrr"])
        self.assertEqual(Decimal("1"), report.metrics["forecastPerSquareMeterIrr"])


class Repository:
    def __init__(self):
        self.selected = {"progress_snapshot_id": SNAPSHOT, "reporting_date": date(2026, 8, 1)}

    async def load(self, scope, reporting_date):
        return {"snapshot": self.selected, "estimates": [], "invoices": [], "conversions": [], "gross_area": "100", "settings_id": UUID(int=7)}

    async def snapshot(self, scope, snapshot_id):
        return self.selected if snapshot_id == SNAPSHOT else None


class Provider:
    def __init__(self, organization_id, project_id, snapshot_id=SNAPSHOT):
        self.organization_id, self.project_id, self.snapshot_id = organization_id, project_id, snapshot_id

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        return {"snapshot": {"organizationId": str(self.organization_id), "projectId": self.project_id,
                             "progressSnapshotId": str(self.snapshot_id)}, "assignments": []}


class AssignmentProvider(Provider):
    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        feed=await super().get_snapshot(organization_id, project_id, snapshot_id)
        feed["assignments"]=[{"assignmentExternalId":"a-m","actualQuantity":"4","task":{}}]
        return feed


class LiveReportServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_only_the_exact_dual_scoped_snapshot(self):
        organization_id = UUID("40000000-0000-4000-8000-000000000001")
        scope = SimpleNamespace(organization_id=organization_id, project_id="sample_site_01")
        service = FinanceLiveReportService(Repository(), Provider(organization_id, scope.project_id))
        result = await service.live(scope, date(2026, 8, 2), SNAPSHOT)
        self.assertEqual(SNAPSHOT, result["progress_snapshot_id"])
        bad = FinanceLiveReportService(Repository(), Provider(organization_id, scope.project_id, UUID(int=9)))
        with self.assertRaises(FinanceRecordNotFound):
            await bad.live(scope, date(2026, 8, 2), SNAPSHOT)

    async def test_issued_reference_matches_kit_and_payload_is_a_frozen_copy(self):
        organization_id = UUID("40000000-0000-4000-8000-000000000001")
        scope = SimpleNamespace(organization_id=organization_id, project_id="sample_site_01", actor_user_id=UUID(int=8), locale="en")
        repository = SnapshotRepository()
        issued_at = __import__("datetime").datetime(2026,8,2,tzinfo=__import__("datetime").timezone.utc)
        service = FinanceLiveReportService(repository, Provider(organization_id, scope.project_id), lambda:UUID(int=10), lambda:issued_at)
        response = await service.issue(scope,date(2026,8,2),SNAPSHOT)
        dto = ReportSnapshotReference(**response)
        self.assertTrue(dto.immutable)
        self.assertEqual(UUID(int=10),dto.report_snapshot_id)
        self.assertEqual(8,len(dto.calculated_metrics))
        self.assertIn("estimateInputs",repository.payload)
        repository.source_estimate["resource_title"]="changed later"
        self.assertEqual("material",repository.payload["estimateInputs"][0]["resource_title"])

        csv_content=await service.export(scope,UUID(int=10),"csv")
        self.assertTrue(csv_content.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"initialEstimateIrr",csv_content)
        xlsx_content=await service.export(scope,UUID(int=10),"xlsx")
        self.assertTrue(xlsx_content.startswith(b"PK"))
        workbook=load_workbook(io.BytesIO(xlsx_content),read_only=False,data_only=True)
        self.assertEqual(["Summary","Breakdown","Price Variance","Quantity Variance"],workbook.sheetnames)
        self.assertEqual("initialEstimateIrr",workbook["Summary"]["A2"].value)
        self.assertFalse(workbook["Summary"].sheet_view.rightToLeft)
        self.assertEqual(1,len(workbook["Breakdown"]._charts))

    async def test_live_and_issued_metrics_match_then_live_changes_without_rewriting_snapshot(self):
        organization_id=UUID("40000000-0000-4000-8000-000000000001")
        scope=SimpleNamespace(organization_id=organization_id,project_id="sample_site_01",actor_user_id=UUID(int=8))
        repository=SnapshotRepository();service=FinanceLiveReportService(repository,Provider(organization_id,scope.project_id),lambda:UUID(int=10))
        live_at_issue=await service.live(scope,date(2026,8,2),SNAPSHOT)
        await service.issue(scope,date(2026,8,2),SNAPSHOT)
        self.assertEqual({key:format(value,"f") for key,value in live_at_issue["metrics"].items() if value is not None},repository.value["calculated_metrics"])
        frozen_metrics=dict(repository.payload["metrics"])
        repository.source_estimate["current_unit_price_irr"]="250"
        changed_live=await service.live(scope,date(2026,8,2),SNAPSHOT)
        self.assertNotEqual(live_at_issue["metrics"]["forecastFinalCostIrr"],changed_live["metrics"]["forecastFinalCostIrr"])
        self.assertEqual(frozen_metrics,repository.payload["metrics"])
        self.assertIn("priceVariances",repository.payload)
        self.assertIn("quantityVariances",repository.payload)

    async def test_full_variance_projection_is_paginated_without_changing_top_lists(self):
        organization_id=UUID("40000000-0000-4000-8000-000000000001")
        scope=SimpleNamespace(organization_id=organization_id,project_id="sample_site_01",actor_user_id=UUID(int=8),locale="en")
        repository=SnapshotRepository();service=FinanceLiveReportService(repository,Provider(organization_id,scope.project_id),lambda:UUID(int=10))
        live=await service.live(scope,date(2026,8,2),SNAPSHOT)
        page=await service.variances(scope,date(2026,8,2),SNAPSHOT,variance_type="all",page=1,page_size=1)
        self.assertEqual((1,2,1),(page["page"],page["total_items"],len(page["items"])))
        self.assertEqual(1,len(live["top_price_variances"]))

    async def test_progress_override_affects_live_variances_breakdown_and_snapshot_payload(self):
        organization_id=UUID("40000000-0000-4000-8000-000000000001")
        scope=SimpleNamespace(organization_id=organization_id,project_id="sample_site_01",actor_user_id=UUID(int=8),locale="en")
        repository=SnapshotRepository()
        repository.overrides=[{"estimate_line_id":MATERIAL_LINE,"computed_value":Decimal("4"),"override_value":Decimal("7"),"reason":"field correction","created_by":UUID(int=8),"created_at":__import__("datetime").datetime(2026,8,2,tzinfo=__import__("datetime").timezone.utc),"activity_external_id":None,"assignment_external_id":"a-m"}]
        service=FinanceLiveReportService(repository,AssignmentProvider(organization_id,scope.project_id),lambda:UUID(int=10))
        live=await service.live(scope,date(2026,8,2),SNAPSHOT)
        self.assertEqual((Decimal("700"),Decimal("300"),Decimal("300"),Decimal("1000")),(live["metrics"]["currentExecutedValueIrr"],live["metrics"]["remainingPhysicalCostIrr"],live["breakdown"][0]["remainingPhysicalCostIrr"],live["metrics"]["forecastFinalCostIrr"]))
        self.assertEqual((Decimal("7"),"manual_override"),(live["top_quantity_variances"][0]["executedQuantity"],live["top_quantity_variances"][0]["sourceMethod"]))
        await service.issue(scope,date(2026,8,2),SNAPSHOT)
        self.assertEqual("7",repository.payload["progressSnapshot"]["assignments"][0]["manualOverride"]["newValue"])

    def test_reporting_repository_reads_only_effective_invoices_and_never_extractions(self):
        source=inspect.getsource(PsycopgLiveReportRepository.load)
        self.assertIn("i.status IN ('confirmed','voided','corrected')",source)
        self.assertNotIn("extraction_drafts",source)

    def test_exports_neutralize_spreadsheet_formula_injection(self):
        payload={"metrics":{"safe":"1"},"breakdown":[],"topPriceVariances":[{"resourceCode":"=CMD()","resourceTitle":"+bad","resourceType":"material","varianceIrr":"-10"}],"topQuantityVariances":[]}
        csv_content=FinanceLiveReportService._csv(payload).decode("utf-8-sig")
        self.assertIn("'=CMD()",csv_content);self.assertIn("'+bad",csv_content)
        workbook=load_workbook(io.BytesIO(FinanceLiveReportService._xlsx(payload,"en")),data_only=False)
        self.assertEqual("'=CMD()",workbook["Price Variance"]["A2"].value)

    def test_report_exports_localize_backend_owned_labels_without_changing_keys(self):
        payload={"metrics":{"initialEstimateIrr":"1"},"breakdown":[{"resourceType":"material","initialEstimateIrr":"1","revisedEstimateIrr":"1","actualCostIrr":"0","remainingPhysicalCostIrr":"1","forecastFinalIrr":"1"}],"topPriceVariances":[],"topQuantityVariances":[]}
        self.assertTrue(FinanceLiveReportService._csv(payload,"fa").startswith(b"\xef\xbb\xbf"))
        self.assertIn("بخش",FinanceLiveReportService._csv(payload,"fa").decode("utf-8-sig").splitlines()[0])
        self.assertIn("القسم",FinanceLiveReportService._csv(payload,"ar").decode("utf-8-sig").splitlines()[0])
        fa=load_workbook(io.BytesIO(FinanceLiveReportService._xlsx(payload,"fa")),data_only=False)
        ar=load_workbook(io.BytesIO(FinanceLiveReportService._xlsx(payload,"ar")),data_only=False)
        en=load_workbook(io.BytesIO(FinanceLiveReportService._xlsx(payload,"en")),data_only=False)
        self.assertEqual(("خلاصه",True),(fa.sheetnames[0],fa[fa.sheetnames[0]].sheet_view.rightToLeft))
        self.assertEqual(("الملخص",True),(ar.sheetnames[0],ar[ar.sheetnames[0]].sheet_view.rightToLeft))
        self.assertEqual(("Summary",False),(en.sheetnames[0],en["Summary"].sheet_view.rightToLeft))


class SnapshotRepository(Repository):
    def __init__(self):
        super().__init__()
        self.selected["progress_snapshot_ref_id"]=UUID(int=6)
        self.source_estimate=estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-m")
        self.source_estimate.update({"estimate_version_id":MATERIAL_LINE,"price_version_id":UUID(int=5)})
        self.payload=None
        self.overrides=[]

    async def load(self,scope,reporting_date):
        return {"snapshot":self.selected,"settings_id":UUID(int=7),"gross_area":"100",
                "estimates":[self.source_estimate],"invoices":[],"conversions":[]}

    async def issue(self,scope,value,payload,audit_id):
        import copy
        self.payload=copy.deepcopy(payload)
        self.value=dict(value)
        return value

    async def export_payload(self,scope,report_id):
        if self.payload is None or report_id!=self.value["report_snapshot_id"]:return None
        return {"report_snapshot_id":report_id,"reporting_date":self.value["reporting_date"],"snapshot_payload":self.payload}

    async def latest_overrides(self,scope,progress_snapshot_ref_id):
        return self.overrides


if __name__ == "__main__":
    unittest.main()
