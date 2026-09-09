"""Conservative historical coverage, separate from the eligible invoice ledger.

Created/completed timestamps prove when a fact was recorded, not when an estimate
became effective. Until an earlier effective date is supported, later facts cannot
establish a complete historical baseline. This never edits issued report payloads.
"""
from dataclasses import replace

from .reports import _warning

ESTIMATE_METRICS = (
    "initialEstimateIrr", "currentExecutedValueIrr", "remainingPhysicalCostIrr",
    "moneyRequiredToContinueIrr", "forecastFinalCostIrr", "forecastPerSquareMeterIrr",
)


def require_estimate_coverage(report, coverage_known):
    if coverage_known:
        return report
    metrics = {**report.metrics, **dict.fromkeys(ESTIMATE_METRICS)}
    breakdown = [dict(row, initialEstimateIrr=None, revisedEstimateIrr=None,
                      remainingPhysicalCostIrr=None, forecastFinalIrr=None,
                      calculationStatus="incomplete") for row in report.breakdown]
    warning = _warning(
        "ESTIMATE_HISTORICAL_COVERAGE_UNKNOWN",
        "پوشش برآورد در تاریخ گزارش قابل اثبات نیست؛ تاریخ ثبت جای تاریخ اثر تجاری نیست.",
        excluded=True, affected=ESTIMATE_METRICS + ("revisedEstimateIrr",))
    return replace(report, metrics=metrics, breakdown=breakdown,
                   calculation_status="incomplete",
                   incomplete_metric_keys=list(dict.fromkeys(
                       [*report.incomplete_metric_keys, *ESTIMATE_METRICS, "revisedEstimateIrr"])),
                   warnings=[*report.warnings, warning],
                   price_variances=[], quantity_variances=[],
                   all_price_variances=[], all_quantity_variances=[])
