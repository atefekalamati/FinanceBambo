# -*- coding: utf-8 -*-
"""A baseline nobody stated, and the total that must not pretend otherwise.

What these defend: an estimate is a quantity times a price, so a line that states neither
has no estimate -- not an estimate of zero. Counting it as zero built a project total out
of some of its lines and published it as the total. A line that states a real zero is a
different thing entirely and still counts.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from uuid import UUID

from app.finance.domain.reports import calculate_live_report

MATERIAL = UUID("20000000-0000-4000-8000-000000000001")
MATERIAL_LINE = UUID("10000000-0000-4000-8000-000000000001")
LABOR_TWO = UUID("20000000-0000-4000-8000-000000000009")


def estimate(line_id, resource_id, kind, quantity, revised, original_price, current_price):
    """One estimate row in the shape the read model returns."""
    return {"id": line_id, "resource_id": resource_id, "resource_type": kind,
            "resource_code": kind[:3], "resource_title": kind,
            "original_quantity": quantity, "revised_quantity": revised,
            "original_unit_price_irr": original_price,
            "current_unit_price_irr": current_price,
            "assignment_external_id": None, "activity_external_id": None,
            "progress_snapshot_id": None}


def build_report(estimates):
    """A report over these lines and nothing else: no invoices, no progress, no area."""
    return calculate_live_report(estimates, [], [], [], None)


def line(quantity, price, kind="material", line_id=MATERIAL_LINE, resource=MATERIAL):
    return estimate(line_id, resource, kind, quantity, None, price, None)


class EstimateBaselineTests(unittest.TestCase):
    def test_a_line_stating_neither_quantity_nor_price_leaves_the_total_unknown(self):
        report = build_report([line(None, None)])
        self.assertIsNone(report.metrics["initialEstimateIrr"],
                          "a total built from none of its lines is not zero")
        self.assertIn("initialEstimateIrr", report.incomplete_metric_keys)
        self.assertEqual("incomplete", report.calculation_status)

    def test_a_line_with_a_quantity_and_no_price_is_the_same_kind_of_gap(self):
        report = build_report([line("10", None)])
        self.assertIsNone(report.metrics["initialEstimateIrr"])
        self.assertIn("initialEstimateIrr", report.incomplete_metric_keys)

    def test_a_line_with_a_price_and_no_quantity_is_too(self):
        report = build_report([line(None, "100000")])
        self.assertIsNone(report.metrics["initialEstimateIrr"])

    def test_a_real_zero_quantity_is_an_estimate_of_zero_and_still_counts(self):
        report = build_report([line("0", "100000")])
        self.assertEqual(Decimal(0), report.metrics["initialEstimateIrr"],
                         "the line states its quantity; the answer is zero")
        self.assertNotIn("initialEstimateIrr", report.incomplete_metric_keys)

    def test_a_real_zero_price_is_an_estimate_of_zero_and_still_counts(self):
        report = build_report([line("10", "0")])
        self.assertEqual(Decimal(0), report.metrics["initialEstimateIrr"])
        self.assertNotIn("initialEstimateIrr", report.incomplete_metric_keys)

    def test_a_stated_estimate_is_quantity_times_price(self):
        report = build_report([line("10", "100000")])
        self.assertEqual(Decimal("1000000"), report.metrics["initialEstimateIrr"])
        self.assertNotIn("initialEstimateIrr", report.incomplete_metric_keys)

    def test_one_unstated_line_makes_the_whole_total_unknown(self):
        # Not "the sum of the ones we could read". A total that silently drops rows is a
        # smaller number wearing the name of the whole.
        report = build_report([line("10", "100000"), line(None, None, line_id=LABOR_TWO)])
        self.assertIsNone(report.metrics["initialEstimateIrr"])

    def test_the_gap_is_named_on_the_line_that_has_it(self):
        report = build_report([line(None, None)])
        codes = {warning["code"] for warning in report.warnings}
        self.assertIn("ESTIMATE_BASELINE_MISSING", codes)
        warning = next(w for w in report.warnings if w["code"] == "ESTIMATE_BASELINE_MISSING")
        self.assertTrue(warning["excludedFromCalculation"])
        self.assertIn("initialEstimateIrr", warning["affectedMetricKeys"])

    def test_actual_cost_is_never_made_unknown_by_a_missing_estimate(self):
        # It comes from confirmed invoices. No invoice is a real zero, not a gap, and the
        # issued-report snapshot depends on this metric always having a value.
        report = build_report([line(None, None)])
        self.assertIsNotNone(report.metrics["actualCostIrr"])

    def test_a_priced_project_is_unaffected(self):
        # The whole point of gating on "a line was read with no baseline" rather than on
        # "the total came out zero": a project that states its estimates still reports them.
        report = build_report([line("10", "100000"), line("2", "50000", kind="labor", line_id=LABOR_TWO)])
        self.assertEqual(Decimal("1100000"), report.metrics["initialEstimateIrr"])
        self.assertNotIn("initialEstimateIrr", report.incomplete_metric_keys)
        self.assertNotIn("ESTIMATE_BASELINE_MISSING",
                         {warning["code"] for warning in report.warnings})


if __name__ == "__main__":
    unittest.main()
