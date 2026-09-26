"""«هزینه بروز باقیمانده» is what the invoices have not settled, priced today.

DECIDED 2026-09-26, from how a building site runs. The material for an activity is bought
before the activity starts, so an activity at 50% does not have half its steel still to
buy. Machinery is paid by the hour against the invoice, on whatever schedule the contract
used. For both, the ledger says what is settled; progress does not.

Equipment is settled by AMOUNT, read against the rate in force on the invoice date: a
truck at 2 million an hour in year one and 5 million in year two paid year-one hours at
year one's rate. `unit_price_at_invoice_date_irr` is that rate, resolved by the repository
at `invoice_date`; the estimate's own rate is the fallback for a payment dated before any
version took effect.
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.reports import WARNING_KEYS, calculate_live_report

MATERIAL_LINE = UUID("10000000-0000-4000-8000-000000000001")
LABOR_LINE = UUID("10000000-0000-4000-8000-000000000002")
GENERAL_LINE = UUID("10000000-0000-4000-8000-000000000003")
EQUIPMENT_LINE = UUID("10000000-0000-4000-8000-000000000004")
MATERIAL = UUID("20000000-0000-4000-8000-000000000001")
LABOR = UUID("20000000-0000-4000-8000-000000000002")
GENERAL = UUID("20000000-0000-4000-8000-000000000003")
EQUIPMENT = UUID("20000000-0000-4000-8000-000000000004")
SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")


def estimate(line_id, resource_id, kind, quantity, revised, original_price, current_price, assignment):
    return {"id": line_id, "resource_id": resource_id, "resource_type": kind,
            "resource_code": kind[:3], "resource_title": kind,
            "original_quantity": quantity, "revised_quantity": revised,
            "original_unit_price_irr": original_price,
            "current_unit_price_irr": current_price,
            "assignment_external_id": assignment, "activity_external_id": None,
            "progress_snapshot_id": SNAPSHOT}


class LedgerSettledRemainingTests(unittest.TestCase):

    def equipment(self, revised="10", original="100", current="500", assignment="a-e"):
        return estimate(EQUIPMENT_LINE, EQUIPMENT, "equipment", "10", revised, original, current, assignment)

    def payment(self, amount, rate_on_date, *, line=EQUIPMENT_LINE, sign=1):
        return {"estimate_line_id": line, "resource_id": EQUIPMENT, "quantity": None,
                "unit": None, "base_unit": "hour", "dimension": "time",
                "final_line_amount_irr": amount, "financial_effect_sign": sign,
                "resource_type": "equipment", "resource_code": "equ",
                "unit_price_at_invoice_date_irr": rate_on_date}

    def test_a_payment_settles_the_hours_it_bought_at_the_rate_of_its_day(self):
        # 400 paid when the hour cost 200: two hours settled. Eight remain, at TODAY's 500.
        report = calculate_live_report([self.equipment()], [self.payment("400", "200")], [], [], "10")
        self.assertEqual(Decimal("4000"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("4000"), report.metrics["moneyRequiredToContinueIrr"])
        # Forecast: what was paid plus what is still to pay. No double count of the hours.
        self.assertEqual(Decimal("4400"), report.metrics["forecastFinalCostIrr"])
        # No measurement was needed for any of it.
        self.assertEqual((0, 1, 1), (report.computed_line_count, report.required_line_count,
                                     report.total_line_count))
        self.assertEqual(Decimal("8"), report.quantity_variances[0]["remainingQuantity"])

    def test_the_same_payment_read_at_todays_rate_would_settle_fewer_hours(self):
        # The control for the test above: this is the mistake the dated rate prevents.
        # 400 / 500 would be 0.8 hours and leave 9.2 x 500 = 4600 outstanding.
        report = calculate_live_report([self.equipment()], [self.payment("400", "500")], [], [], "10")
        self.assertEqual(Decimal("4600"), report.metrics["remainingPhysicalCostIrr"])

    def test_a_payment_before_any_price_version_is_read_at_the_estimates_rate(self):
        # No version in force on that day; the estimate priced the hour at 100.
        report = calculate_live_report([self.equipment()], [self.payment("400", None)], [], [], "10")
        self.assertEqual(Decimal("3000"), report.metrics["remainingPhysicalCostIrr"], "6 x 500")
        self.assertNotIn("INVOICE_PRICE_MISSING", {w["code"] for w in report.warnings})

    def test_a_fully_paid_machine_has_nothing_remaining_whatever_its_progress(self):
        # 1000 paid at 100 an hour settles all ten hours. The activity is at 50%. Nothing
        # remains, and the forecast is exactly what was paid -- the old rule would have
        # added 5 x 500 on top of the 1000 already in the actual cost.
        report = calculate_live_report([self.equipment()], [self.payment("1000", "100")],
                                       [{"assignmentExternalId": "a-e", "actualWork": "5",
                                         "resourceType": "equipment", "task": {}}], [], "10")
        self.assertEqual(Decimal("0"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("1000"), report.metrics["forecastFinalCostIrr"])
        self.assertEqual(Decimal("2500"), report.metrics["currentExecutedValueIrr"], "5 x 500 -- still measured")

    def test_a_voided_payment_gives_its_hours_back(self):
        report = calculate_live_report([self.equipment()],
                                       [self.payment("400", "200"), self.payment("400", "200", sign=-1)],
                                       [], [], "10")
        self.assertEqual(Decimal("5000"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("0"), report.metrics["actualCostIrr"])

    def test_a_payment_naming_no_line_is_pooled_across_the_resources_lines_once(self):
        other = estimate(UUID(int=0x77), EQUIPMENT, "equipment", "10", "10", "100", "500", "a-e2")
        # 3000 at 200 an hour is 15 hours: 10 fill the first line, 5 spill to the second.
        report = calculate_live_report([self.equipment(), other], [self.payment("3000", "200", line=None)], [], [], "10")
        by_line = {row["estimateLineId"]: row["remainingQuantity"] for row in report.quantity_variances}
        self.assertEqual({str(EQUIPMENT_LINE): Decimal("0"), str(UUID(int=0x77)): Decimal("5")}, by_line)
        self.assertEqual(Decimal("2500"), report.metrics["remainingPhysicalCostIrr"])

    def test_a_payment_with_no_rate_anywhere_settles_nothing_and_says_so(self):
        line = self.equipment(original=None)
        report = calculate_live_report([line], [self.payment("400", None)], [], [], "10")
        warning = next(w for w in report.warnings if w["code"] == "INVOICE_PRICE_MISSING")
        self.assertEqual((str(EQUIPMENT_LINE), str(EQUIPMENT), "equ"),
                         (warning["estimateLineId"], warning["resourceId"], warning["resourceCode"]))
        # Not excluded: the figure exists, it is merely too high by what the 400 bought.
        self.assertFalse(warning["excludedFromCalculation"])
        self.assertEqual(["remainingPhysicalCostIrr", "moneyRequiredToContinueIrr",
                          "forecastFinalCostIrr", "forecastPerSquareMeterIrr"],
                         warning["affectedMetricKeys"])
        self.assertEqual(Decimal("5000"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(Decimal("400"), report.metrics["actualCostIrr"], "the payment is still real")
        self.assertIn("remainingPhysicalCostIrr", report.incomplete_metric_keys)
        self.assertEqual(set(WARNING_KEYS), set(warning))

    def test_the_equipment_invoice_quantity_column_is_not_what_settles_it(self):
        # The rule is the amount against the dated rate. A stated quantity on an
        # equipment invoice line is not consulted -- 400 at 200 is two hours, whatever the
        # line claims to count.
        paid = dict(self.payment("400", "200"), quantity="7", unit="hour")
        report = calculate_live_report([self.equipment()], [paid], [], [], "10")
        self.assertEqual(Decimal("4000"), report.metrics["remainingPhysicalCostIrr"])

    def test_labour_still_derives_its_remaining_from_the_measurement(self):
        # Nobody has stated a ledger rule for labour, so nothing about it changed: an
        # unmeasured labour line is excluded from the remaining and the forecast is
        # incomplete for it, exactly as before.
        labor = estimate(LABOR_LINE, LABOR, "labor", "10", "10", "100", "100", "a-l")
        unmeasured = calculate_live_report([labor], [], [{"assignmentExternalId": "a-l", "task": {}}], [], "10")
        self.assertEqual(Decimal("0"), unmeasured.metrics["remainingPhysicalCostIrr"])
        self.assertEqual((0, 0), (unmeasured.computed_line_count, unmeasured.required_line_count))
        self.assertIn("forecastFinalCostIrr", unmeasured.incomplete_metric_keys)
        measured = calculate_live_report([labor], [], [{"assignmentExternalId": "a-l", "actualWork": "4",
                                                       "resourceType": "labor", "task": {}}], [], "10")
        self.assertEqual(Decimal("600"), measured.metrics["remainingPhysicalCostIrr"], "6 x 100")

    def test_an_unmeasured_material_line_leaves_the_forecast_whole(self):
        # The material rule already read the ledger for `moneyRequiredToContinueIrr`; what
        # is new is that «هزینه بروز باقیمانده» does too, and that an absent measurement
        # is no longer reported as reaching a figure it cannot reach.
        material = estimate(MATERIAL_LINE, MATERIAL, "material", "10", "10", "100", "150", "a-m")
        report = calculate_live_report([material], [], [{"assignmentExternalId": "a-m", "task": {}}], [], "10")
        self.assertEqual(Decimal("1500"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(["currentExecutedValueIrr"], report.incomplete_metric_keys)
        missing = next(w for w in report.warnings if w["code"] == "PROGRESS_MISSING")
        self.assertEqual(["currentExecutedValueIrr"], missing["affectedMetricKeys"])

    def test_the_two_remaining_metrics_are_one_figure_under_two_names(self):
        rows = [estimate(MATERIAL_LINE, MATERIAL, "material", "10", "12", "100", "150", "a-m"),
                estimate(LABOR_LINE, LABOR, "labor", "5", "5", "100", "200", "a-l"),
                self.equipment(),
                estimate(GENERAL_LINE, GENERAL, "general_cost", None, "1200", "1000", None, None)]
        invoices = [{"estimate_line_id": MATERIAL_LINE, "resource_id": MATERIAL, "quantity": "4",
                     "unit": "each", "base_unit": "each", "dimension": "count",
                     "final_line_amount_irr": "800", "financial_effect_sign": 1, "resource_type": "material"},
                    self.payment("400", "200"),
                    {"estimate_line_id": GENERAL_LINE, "resource_id": GENERAL, "quantity": None,
                     "unit": None, "base_unit": None, "dimension": "lump_sum",
                     "final_line_amount_irr": "700", "financial_effect_sign": 1, "resource_type": "general_cost"}]
        assignments = [{"assignmentExternalId": "a-m", "actualQuantity": "4", "task": {}},
                       {"assignmentExternalId": "a-l", "actualWork": "2", "resourceType": "labor", "task": {}}]
        report = calculate_live_report(rows, invoices, assignments, [], "10")
        # material 8 x 150 + labour 3 x 200 + equipment 8 x 500 + general (1200 - 700)
        expected = Decimal("1200") + Decimal("600") + Decimal("4000") + Decimal("500")
        self.assertEqual(expected, report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(expected, report.metrics["moneyRequiredToContinueIrr"])
        self.assertEqual(Decimal("1900") + expected, report.metrics["forecastFinalCostIrr"])
        breakdown_sum = sum(row["remainingPhysicalCostIrr"] for row in report.breakdown)
        self.assertEqual(expected, breakdown_sum, "the type table adds up to the headline")


if __name__ == "__main__":
    unittest.main()
