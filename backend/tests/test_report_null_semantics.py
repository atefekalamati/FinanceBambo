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
    """A total built from some of its lines: published, and never published bare.

    The rule used to be that one unstated line withheld the figure entirely. It was honest
    and it was unusable: this project's equipment states no price anywhere in its schedule
    -- the file simply does not contain one -- so every stage that carries equipment
    withheld the material estimate sitting beside it, and 342 billion toman of stated
    estimate reached the reader as an em dash. The figure is now the subtotal of the lines
    that state a baseline, and three separate things say so: `incompleteMetricKeys` names
    the metric, `missingEstimateLineCount` says how many lines are not in it, and
    `calculationStatus` is `incomplete`. What must never happen is the subtotal travelling
    without them, which is what these tests hold.
    """

    def test_a_line_stating_neither_quantity_nor_price_is_counted_and_named(self):
        report = build_report([line(None, None)])
        self.assertEqual(Decimal(0), report.metrics["initialEstimateIrr"],
                         "no line states a baseline, so the subtotal of those that do is zero")
        self.assertEqual(1, report.missing_estimate_line_count,
                         "and the zero arrives beside the count that explains it")
        self.assertIn("initialEstimateIrr", report.incomplete_metric_keys)
        self.assertEqual("incomplete", report.calculation_status)

    def test_a_line_with_a_quantity_and_no_price_is_the_same_kind_of_gap(self):
        report = build_report([line("10", None)])
        self.assertEqual(1, report.missing_estimate_line_count)
        self.assertIn("initialEstimateIrr", report.incomplete_metric_keys)

    def test_a_line_with_a_price_and_no_quantity_is_too(self):
        report = build_report([line(None, "100000")])
        self.assertEqual(1, report.missing_estimate_line_count)
        self.assertIn("initialEstimateIrr", report.incomplete_metric_keys)

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

    def test_one_unstated_line_makes_the_total_a_flagged_subtotal(self):
        # The sum of the ones that state a baseline -- which is a smaller number than the
        # whole, and must never wear the name of the whole. Everything that says so is
        # asserted here, because the figure alone would be exactly the old defect.
        report = build_report([line("10", "100000"), line(None, None, line_id=LABOR_TWO)])
        self.assertEqual(Decimal("1000000"), report.metrics["initialEstimateIrr"])
        self.assertEqual(1, report.missing_estimate_line_count)
        self.assertIn("initialEstimateIrr", report.incomplete_metric_keys)
        self.assertIn("revisedEstimateIrr", report.incomplete_metric_keys)
        self.assertEqual("incomplete", report.calculation_status)

    def test_a_type_whose_lines_are_all_unstated_says_so_on_its_own_row(self):
        # The per-type row has the same problem in miniature: a type made entirely of
        # unestimated lines must not publish a confident zero beside a type that really
        # was estimated at nothing.
        # The line still says `equipment`, as rows written before 0038 do; it is `work`.
        report = build_report([line("10", "100000"),
                               line(None, None, kind="equipment", line_id=LABOR_TWO)])
        rows = {row["resourceType"]: row for row in report.breakdown}
        self.assertEqual(0, rows["material"]["missingEstimateLineCount"],
                         "this type stated its baseline; its estimate is its total")
        self.assertEqual(1, rows["work"]["missingEstimateLineCount"])
        self.assertEqual("incomplete", rows["work"]["calculationStatus"])
        # `general_cost` has no lines here at all, which is a third state again: nothing
        # to estimate, nothing missing, and a status that stays complete.
        self.assertEqual(0, rows["general_cost"]["missingEstimateLineCount"])
        self.assertEqual("complete", rows["general_cost"]["calculationStatus"])

    def test_a_fully_stated_project_carries_a_zero_count(self):
        # The counter is published even when there is nothing to report: "none of them"
        # is the answer that lets a reader trust the figure, and its absence would read
        # the same as a reader who forgot to look.
        report = build_report([line("10", "100000")])
        self.assertEqual(0, report.missing_estimate_line_count)
        self.assertNotIn("initialEstimateIrr", report.incomplete_metric_keys)

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
