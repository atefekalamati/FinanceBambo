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


#: The metrics an empty basis cannot support. `actualCostIrr` is deliberately absent: an
#: invoice line names an estimate line, so a stage with no estimate lines has no invoice
#: lines either, and nothing spent through it is a measured nothing rather than an unknown.
EMPTY_BASIS_METRICS = ESTIMATE_METRICS + ("revisedEstimateIrr",)


def report_of_an_empty_basis(report, estimate_line_count):
    """The estimate of a stage nobody has estimated is unknown, not zero.

    A sum over no rows is arithmetically zero and that is what the engine returns, which is
    correct arithmetic and the wrong statement: the reader sees «۰» and understands "this
    costs nothing", while the data says only "nothing here has been costed".

    Only the empty case is touched. One line stating zero is a costing that came out at
    zero, and it keeps saying zero -- which is why this is keyed on the count of lines and
    not on the total being zero.
    """
    if estimate_line_count:
        return report
    metrics = {**report.metrics, **dict.fromkeys(ESTIMATE_METRICS)}
    breakdown = [dict(row, initialEstimateIrr=None, revisedEstimateIrr=None,
                      remainingPhysicalCostIrr=None, forecastFinalIrr=None,
                      calculationStatus="incomplete") for row in report.breakdown]
    warning = _warning(
        "ESTIMATE_BASIS_ABSENT",
        "برای این مرحله هیچ ردیف برآوردی ثبت نشده است؛ برآورد آن نامعلوم است، نه صفر.",
        excluded=True, affected=EMPTY_BASIS_METRICS)
    return replace(report, metrics=metrics, breakdown=breakdown,
                   calculation_status="incomplete",
                   incomplete_metric_keys=list(dict.fromkeys(
                       [*report.incomplete_metric_keys, *EMPTY_BASIS_METRICS])),
                   warnings=[*report.warnings, warning])


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
