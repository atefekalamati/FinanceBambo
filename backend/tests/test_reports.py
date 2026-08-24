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
        self.assertEqual({"PROGRESS_UNMAPPED", "CURRENT_PRICE_MISSING", "UNIT_CONVERSION_MISSING", "GROSS_AREA_MISSING"},
                         {warning["code"] for warning in report.warnings})
        self.assertIsNone(report.metrics["actualCostPerSquareMeterIrr"])
        self.assertEqual(("incomplete",1),(report.calculation_status,report.missing_price_count))
        self.assertIsNone(report.metrics["forecastFinalCostIrr"])
        self.assertIn("forecastFinalCostIrr",report.incomplete_metric_keys)
        warning=next(item for item in report.warnings if item["code"]=="CURRENT_PRICE_MISSING")
        self.assertEqual((str(MATERIAL_LINE),str(MATERIAL),"mat",True),(warning["estimateLineId"],warning["resourceId"],warning["resourceCode"],warning["excludedFromCalculation"]))

    def test_an_unlinked_line_and_an_empty_assignment_report_different_codes(self):
        """The two used to share PROGRESS_MISSING, which told the reader nothing.

        An unlinked line is fixed here, by correcting its activity link. A linked line with
        nothing on it needs a report from project controls. Neither changes what the line
        contributes, so the codes are the only thing that differs.
        """
        unlinked = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-none")
        linked = estimate(LABOR_LINE, LABOR, "labor", "10", "10", "100", "100", "a-empty")
        # Matches by id, but carries no quantity, no work and no task percent.
        empty = {"assignmentExternalId": "a-empty", "task": {}}
        report = calculate_live_report([unlinked, linked], [], [empty], [], "10")
        by_line = {(w["code"], w["estimateLineId"]) for w in report.warnings
                   if w["code"] in ("PROGRESS_UNMAPPED", "PROGRESS_MISSING")}
        self.assertEqual({("PROGRESS_UNMAPPED", str(MATERIAL_LINE)),
                          ("PROGRESS_MISSING", str(LABOR_LINE))}, by_line)

    def test_one_line_never_carries_both_progress_codes(self):
        row = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-none")
        report = calculate_live_report([row], [], [], [], "10")
        codes = [w["code"] for w in report.warnings if w["code"].startswith("PROGRESS_")]
        self.assertEqual(["PROGRESS_UNMAPPED"], codes)

    def test_the_new_code_keeps_the_shape_the_other_warnings_use(self):
        row = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-none")
        report = calculate_live_report([row], [], [], [], "10")
        unmapped = next(w for w in report.warnings if w["code"] == "PROGRESS_UNMAPPED")
        self.assertEqual({"code", "message", "estimateLineId", "resourceId", "resourceCode",
                          "activityExternalId", "severity", "excludedFromCalculation",
                          "affectedMetricKeys"}, set(unmapped))
        # Same affected metrics as PROGRESS_MISSING: the consequence is identical, only the
        # cause differs.
        self.assertEqual(["currentExecutedValueIrr", "remainingPhysicalCostIrr",
                          "forecastFinalCostIrr"], unmapped["affectedMetricKeys"])

    def test_splitting_the_codes_moved_no_financial_figure(self):
        """An unlinked line and a linked-but-empty one must still produce identical money.

        Both score executed = 0, so every metric, breakdown row and variance has to match
        exactly. If the split had changed how either case is calculated, this fails -- which
        is the whole guarantee, since the codes were meant to be diagnostic only.
        """
        unlinked = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-none")
        linked = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-empty")
        empty_assignment = [{"assignmentExternalId": "a-empty", "task": {}}]
        unmapped_report = calculate_live_report([unlinked], [], [], [], "10")
        missing_report = calculate_live_report([linked], [], empty_assignment, [], "10")
        self.assertEqual(unmapped_report.metrics, missing_report.metrics)
        self.assertEqual(unmapped_report.breakdown, missing_report.breakdown)
        self.assertEqual(unmapped_report.calculation_status, missing_report.calculation_status)
        self.assertEqual(unmapped_report.incomplete_metric_keys, missing_report.incomplete_metric_keys)
        # Only the diagnosis differs.
        self.assertNotEqual(
            {w["code"] for w in unmapped_report.warnings},
            {w["code"] for w in missing_report.warnings})

    def test_a_fully_mapped_report_is_untouched_by_the_new_counters(self):
        row = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-1")
        report = calculate_live_report(
            row and [row], [], [{"assignmentExternalId": "a-1", "actualQuantity": "4", "task": {}}], [], "10")
        # Exact pre-split figures for this fixture: executed 4 of 10 at 100 IRR. The domain
        # returns Decimal; the string form appears only after DTO serialisation.
        self.assertEqual(Decimal("400"), report.metrics["currentExecutedValueIrr"])
        self.assertEqual(Decimal("600"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("1000"), report.metrics["forecastFinalCostIrr"])
        self.assertEqual([], [w["code"] for w in report.warnings if w["code"].startswith("PROGRESS_")])
        self.assertTrue(report.progress_quality["complete"])
        self.assertEqual((1, 0, 0), (report.progress_quality["mappedLineCount"],
                                     report.progress_quality["unmappedLineCount"],
                                     report.progress_quality["generalCostLineCount"]))

    def test_the_three_line_counters_account_for_every_estimate_line(self):
        rows = [
            estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-1"),
            estimate(LABOR_LINE, LABOR, "labor", "10", "10", "100", "100", "a-none"),
            estimate(GENERAL_LINE, GENERAL, "general_cost", "500", "500", "500", "500", None),
        ]
        report = calculate_live_report(
            rows, [], [{"assignmentExternalId": "a-1", "actualQuantity": "3", "task": {}}], [], "10")
        quality = report.progress_quality
        self.assertEqual((1, 1, 1), (quality["mappedLineCount"], quality["unmappedLineCount"],
                                     quality["generalCostLineCount"]))
        # The invariant the counters exist for: general cost used to fall in no bucket.
        self.assertEqual(len(rows), quality["mappedLineCount"] + quality["unmappedLineCount"]
                         + quality["generalCostLineCount"])

    def test_missing_count_now_excludes_unlinked_lines(self):
        rows = [estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "100", "a-none"),
                estimate(LABOR_LINE, LABOR, "labor", "10", "10", "100", "100", "a-empty")]
        report = calculate_live_report(
            rows, [], [{"assignmentExternalId": "a-empty", "task": {}}], [], "10")
        # Two problem lines, but only the linked one is "missing".
        self.assertEqual((1, 1), (report.progress_quality["missingCount"],
                                  report.progress_quality["unmappedLineCount"]))
        self.assertFalse(report.progress_quality["complete"])

    def test_general_cost_remaining_is_allocated_per_line_without_cross_line_subsidy(self):
        line2=UUID("10000000-0000-4000-8000-000000000004");res2=UUID("20000000-0000-4000-8000-000000000004")
        estimates=[estimate(GENERAL_LINE,GENERAL,"general_cost",None,"1000","1000",None,None),estimate(line2,res2,"general_cost",None,"500","500",None,None)]
        invoices=[
            {"estimate_line_id":GENERAL_LINE,"resource_id":GENERAL,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"800","financial_effect_sign":1,"resource_type":"general_cost"},
            {"estimate_line_id":GENERAL_LINE,"resource_id":GENERAL,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"100","financial_effect_sign":-1,"resource_type":"general_cost"},
            {"estimate_line_id":line2,"resource_id":res2,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"700","financial_effect_sign":1,"resource_type":"general_cost"},
        ]
        report=calculate_live_report(estimates,invoices,[],[],"10")
        row={item["resourceType"]:item for item in report.breakdown}["general_cost"]
        # line 1 owes max(1000-700,0)=300; line 2 already overran at max(500-700,0)=0.
        # The category formula would net these to max(1500-1400,0)=100 and under-report the call on cash.
        self.assertEqual((Decimal("1500"),Decimal("1400"),Decimal("300"),Decimal("1700")),(row["revisedEstimateIrr"],row["actualCostIrr"],row["remainingPhysicalCostIrr"],row["forecastFinalIrr"]))
        self.assertEqual(Decimal("1700"),report.metrics["forecastFinalCostIrr"])
        overrun=[item for item in report.warnings if item["code"]=="GENERAL_COST_OVERRUN"]
        self.assertEqual([str(line2)],[item["estimateLineId"] for item in overrun])

    def test_general_cost_actual_is_never_subtracted_from_more_than_one_line(self):
        line2=UUID("10000000-0000-4000-8000-000000000004")
        estimates=[estimate(GENERAL_LINE,GENERAL,"general_cost",None,"1000","1000",None,None),estimate(line2,GENERAL,"general_cost",None,"1000","1000",None,None)]
        invoices=[{"estimate_line_id":None,"resource_id":GENERAL,"quantity":None,"unit":None,"base_unit":None,"dimension":"lump_sum","final_line_amount_irr":"600","financial_effect_sign":1,"resource_type":"general_cost"}]
        row={item["resourceType"]:item for item in calculate_live_report(estimates,invoices,[],[],"10").breakdown}["general_cost"]
        # 600 of unlinked actual is consumed once: 400 remains on the line it was allocated to, 1000 on the other.
        self.assertEqual((Decimal("600"),Decimal("1400"),Decimal("2000")),(row["actualCostIrr"],row["remainingPhysicalCostIrr"],row["forecastFinalIrr"]))

    def test_missing_price_does_not_report_a_zero_cost_breakdown_or_variance_row(self):
        priced=estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-1")
        unpriced=estimate(LABOR_LINE,LABOR,"labor","10","10","100",None,"a-2")
        assignments=[{"assignmentExternalId":"a-1","actualQuantity":"0","task":{}},{"assignmentExternalId":"a-2","actualQuantity":"0","task":{}}]
        report=calculate_live_report([priced,unpriced],[],assignments,[],"10")
        by_type={item["resourceType"]:item for item in report.breakdown}
        self.assertEqual(("complete",0),(by_type["material"]["calculationStatus"],by_type["material"]["excludedEstimateLineCount"]))
        self.assertEqual(("incomplete",1),(by_type["labor"]["calculationStatus"],by_type["labor"]["excludedEstimateLineCount"]))
        # The unpriced line must not present itself as a fully-costed line worth zero.
        unpriced_row=next(item for item in report.all_price_variances if item["estimateLineId"]==str(LABOR_LINE))
        self.assertEqual((False,None,None,None),(unpriced_row["priceAvailable"],unpriced_row["currentUnitPriceIrr"],unpriced_row["remainingPhysicalCostIrr"],unpriced_row["forecastFinalIrr"]))
        self.assertEqual(Decimal("0"),unpriced_row["varianceIrr"])
        self.assertIsNone(unpriced_row["impactSharePercent"])
        unpriced_quantity=next(item for item in report.all_quantity_variances if item["estimateLineId"]==str(LABOR_LINE))
        self.assertEqual((False,None,None),(unpriced_quantity["priceAvailable"],unpriced_quantity["remainingPhysicalCostIrr"],unpriced_quantity["forecastFinalIrr"]))
        priced_row=next(item for item in report.all_price_variances if item["estimateLineId"]==str(MATERIAL_LINE))
        self.assertEqual((True,Decimal("1000")),(priced_row["priceAvailable"],priced_row["remainingPhysicalCostIrr"]))
        # The priced category keeps a real number; only the unpriced one is withheld.
        self.assertEqual(Decimal("1000"),by_type["material"]["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("0"),by_type["labor"]["remainingPhysicalCostIrr"])

    def test_missing_conversion_marks_only_the_affected_breakdown_category_incomplete(self):
        row=estimate(MATERIAL_LINE,MATERIAL,"material","10","10","100","100","a-m")
        invoice={"estimate_line_id":None,"resource_id":MATERIAL,"quantity":"5","unit":"box","base_unit":"each","dimension":"count","final_line_amount_irr":"500","financial_effect_sign":1,"resource_type":"material","resource_code":"mat"}
        report=calculate_live_report([row],[invoice],[{"assignmentExternalId":"a-m","actualQuantity":"0","task":{}}],[],"10")
        by_type={item["resourceType"]:item for item in report.breakdown}
        self.assertEqual("incomplete",by_type["material"]["calculationStatus"])
        self.assertEqual("complete",by_type["labor"]["calculationStatus"])

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
        self.assertEqual({"complete":False,"manualOverrideCount":1,"taskFallbackCount":1,"missingCount":0,"assignmentActualCount":0,"assignmentPercentFallbackCount":0,"mappedLineCount":2,"unmappedLineCount":0,"generalCostLineCount":0},report.progress_quality)

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


class SnapshotRepo:
    """Stands in for the paged repository read; records what the service asked for."""

    def __init__(self, rows, total):
        self.rows, self.total, self.call = rows, total, None

    async def list(self, scope, limit=50, offset=0, **filters):
        self.call = {"scope": scope, "limit": limit, "offset": offset, **filters}
        return self.rows, self.total


class ReportSnapshotListTests(unittest.IsolatedAsyncioTestCase):
    def service(self, repo):
        return FinanceLiveReportService(repo, Provider(UUID(int=2), "p1"))

    async def test_the_envelope_reports_the_whole_match_not_the_page(self):
        repo = SnapshotRepo([{"report_snapshot_id": UUID(int=1)}], 7)
        result = await self.service(repo).list_snapshots(
            SimpleNamespace(organization_id=UUID(int=2), project_id="p1"), page=3, page_size=2)
        # total_items is the count of everything that matched, so the client can page
        # through it; using the page size would say there is nothing more to fetch.
        self.assertEqual((3, 2, 7, 4), (result["page"], result["page_size"],
                                        result["total_items"], result["total_pages"]))
        self.assertEqual(1, len(result["items"]))

    async def test_the_date_range_is_handed_to_the_repository_not_applied_afterwards(self):
        repo = SnapshotRepo([], 0)
        await self.service(repo).list_snapshots(
            SimpleNamespace(organization_id=UUID(int=2), project_id="p1"),
            page=1, page_size=50,
            reporting_date_from=date(2026, 4, 1), reporting_date_to=date(2026, 5, 1))
        self.assertEqual(date(2026, 4, 1), repo.call["reporting_date_from"])
        self.assertEqual(date(2026, 5, 1), repo.call["reporting_date_to"])
        self.assertEqual((50, 0), (repo.call["limit"], repo.call["offset"]))

    async def test_total_pages_is_zero_when_nothing_matches(self):
        repo = SnapshotRepo([], 0)
        result = await self.service(repo).list_snapshots(
            SimpleNamespace(organization_id=UUID(int=2), project_id="p1"))
        self.assertEqual(([], 0, 0), (result["items"], result["total_items"], result["total_pages"]))

    async def test_the_offset_follows_the_requested_page(self):
        repo = SnapshotRepo([], 0)
        await self.service(repo).list_snapshots(
            SimpleNamespace(organization_id=UUID(int=2), project_id="p1"), page=4, page_size=25)
        self.assertEqual(75, repo.call["offset"])

