"""Historical absence is not a verified zero, and later evidence is not backdated."""
import unittest
from decimal import Decimal

from app.finance.domain.report_coverage import require_estimate_coverage
from app.finance.domain.reports import calculate_live_report
from app.finance.domain.estimate_basis import effective_original_price, effective_original_quantity
from app.finance.schemas.reports import TypeBreakdown


class HistoricalCoverageTests(unittest.TestCase):
    def test_unknown_empty_baseline_does_not_publish_complete_zero(self):
        original = calculate_live_report([], [], [], [], None)
        report = require_estimate_coverage(original, False)
        self.assertEqual(report.calculation_status, "incomplete")
        self.assertIsNone(report.metrics["initialEstimateIrr"])
        self.assertIsNone(report.metrics["forecastFinalCostIrr"])
        self.assertEqual(report.metrics["actualCostIrr"], Decimal(0))
        self.assertTrue(all(row["initialEstimateIrr"] is None for row in report.breakdown))
        # No mutation of the original result, including results stored in a snapshot.
        self.assertEqual(original.metrics["initialEstimateIrr"], Decimal(0))
        self.assertEqual(original.calculation_status, "complete")

    def test_known_coverage_preserves_real_zero(self):
        report = calculate_live_report([], [], [], [], None)
        self.assertIs(require_estimate_coverage(report, True), report)
        self.assertEqual(report.metrics["initialEstimateIrr"], Decimal(0))

    def test_historical_completions_are_cut_off_without_changing_current_read(self):
        for expression in (effective_original_price, effective_original_quantity):
            self.assertNotIn("completed_at", expression())
            sql = expression("l", "(SELECT as_of FROM report_cutoff)")
            self.assertIn("c.completed_at AT TIME ZONE 'Asia/Tehran'", sql)
            self.assertIn("::date <= (SELECT as_of FROM report_cutoff)", sql)
            self.assertEqual(sql.count("("), sql.count(")"))


class CoverageReachesTheResponseTests(unittest.TestCase):
    """The rule produced nulls the API then refused to publish.

    `require_estimate_coverage` nulls a breakdown row's estimate AND the two figures derived
    from it. `initialEstimateIrr` and `revisedEstimateIrr` were already nullable on the wire;
    `remainingPhysicalCostIrr` and `forecastFinalIrr` were not, so every historical report
    with unknown coverage answered 500 instead of "-". The reader saw a broken page, which is
    not the honest outcome the rule was written to produce -- it is a worse one than the
    complete zero it replaced.
    """

    def rows(self, coverage_known):
        report = require_estimate_coverage(
            calculate_live_report([], [], [], [], None), coverage_known)
        return [TypeBreakdown.model_validate(row).model_dump(by_alias=True)
                for row in report.breakdown]

    def test_an_unknown_breakdown_row_serializes_as_null_not_as_zero(self):
        for row in self.rows(False):
            for key in ("initialEstimateIrr", "revisedEstimateIrr",
                        "remainingPhysicalCostIrr", "forecastFinalIrr"):
                self.assertIsNone(row[key], "%s must be null when coverage is unknown" % key)
            self.assertEqual("incomplete", row["calculationStatus"])
            # The cost actually invoiced is a separate ledger and stays a number.
            self.assertEqual("0", row["actualCostIrr"])

    def test_a_known_zero_still_serializes_as_zero(self):
        # A verified empty project is not the same answer as an unproven one, and the
        # difference has to survive the wire or the whole rule is decorative.
        for row in self.rows(True):
            self.assertEqual("0", row["initialEstimateIrr"])
            self.assertEqual("0", row["forecastFinalIrr"])
            self.assertEqual("0", row["remainingPhysicalCostIrr"])
            self.assertEqual("complete", row["calculationStatus"])

    def test_the_row_still_refuses_a_value_that_is_not_a_number(self):
        # Nullable must not have become "anything goes": a wrong type is still an error.
        from pydantic import ValidationError
        row = dict(self.rows(True)[0], forecastFinalIrr="not a number")
        with self.assertRaises(ValidationError):
            TypeBreakdown.model_validate(row)
