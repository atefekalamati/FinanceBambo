"""The monthly cost series behind the Finance Home trend chart.

Actual cost here is the same fact the live report reports, cut into Persian months:
the signed sum of invoice lines on documents whose status is one of
('confirmed','voided','corrected'). Reading it from any other definition would let the
chart and the report disagree about the same money.

Two rules shape the output.

Months are contiguous. The chart does not fill gaps in API data, so a month with no
document is returned with an actual of zero rather than omitted — a month in which
nothing was spent is a fact, and dropping it would draw two non-adjacent months
side by side.

Estimate is absent, not zero. Estimate lines carry no planned date, only `created_at`,
which records when the row was written. There is no authoritative monthly baseline to
report, so `estimateIrr` is None and the caller is told why. Zero would claim a real
plan of nothing was budgeted.
"""

from datetime import date

from .persian_calendar import gregorian_to_persian, next_persian_month
from .reports import ZERO, money

RESOURCE_TYPES = ("material", "labor", "equipment", "general_cost")

# Twelve months is what the trend chart draws. The ceiling keeps an unbounded history
# request from turning into an unbounded scan; both ends of the window are reported so a
# caller can see what it got.
DEFAULT_MONTH_COUNT = 12
MAX_MONTH_COUNT = 60

def estimate_unavailable_warning():
    """A fresh dict each call: a module-level constant would hand every response the
    same nested list, and one caller appending to it would corrupt all later ones."""
    return {
    "code": "MONTHLY_ESTIMATE_UNAVAILABLE",
    "message": "برآورد ماهانه در دسترس نیست: خطوط برآورد تاریخ برنامه‌ریزی ندارند.",
    "estimateLineId": None,
    "resourceId": None,
    "resourceCode": None,
    "activityExternalId": None,
    "severity": "warning",
    "excludedFromCalculation": True,
    "affectedMetricKeys": ["estimateIrr"],
    }


def _breakdown_key(resource_type):
    return "generalCost" if resource_type == "general_cost" else resource_type


def build_monthly_series(amount_rows, document_rows, window):
    """Bucket day-level aggregates into the `month_count` Persian months ending on `anchor`.

    `window` is the (start_date, first_year, first_month, month_count) tuple the caller
    already used to bound the query, so the calendar walk happens once and the buckets
    cannot describe a different range than the rows were fetched for.

    `amount_rows` are (invoice_date, resource_type, amount_irr) already summed per day by
    PostgreSQL; `document_rows` are (invoice_date, financial_effect_sign, document_count).
    Neither carries a row per invoice, so the size of this loop is bounded by the number
    of days in the window rather than by how many invoices the project has.
    """
    start, first_year, first_month, month_count = window

    buckets = {}
    year, month = first_year, first_month
    for _ in range(month_count):
        buckets[(year, month)] = {
            "persianYear": year,
            "persianMonth": month,
            "actualCostIrr": ZERO,
            "estimateIrr": None,
            "invoiceCount": 0,
            "reversalCount": 0,
            "breakdown": {_breakdown_key(kind): ZERO for kind in RESOURCE_TYPES},
        }
        year, month = next_persian_month(year, month)

    for row in amount_rows:
        bucket = buckets.get(gregorian_to_persian(row["invoice_date"])[:2])
        if bucket is None:
            continue
        amount = money(ZERO if row["amount_irr"] is None else row["amount_irr"])
        bucket["actualCostIrr"] += amount
        bucket["breakdown"][_breakdown_key(row["resource_type"])] += amount

    for row in document_rows:
        bucket = buckets.get(gregorian_to_persian(row["invoice_date"])[:2])
        if bucket is None:
            continue
        key = "invoiceCount" if int(row["financial_effect_sign"]) == 1 else "reversalCount"
        bucket[key] += int(row["document_count"])

    return list(buckets.values()), start


def monthly_report(amount_rows, document_rows, window, anchor: date,
                   progress_snapshot_id=None):
    months, window_start = build_monthly_series(amount_rows, document_rows, window)
    actual_dates = [row["invoice_date"] for row in (*amount_rows, *document_rows)
                    if row.get("invoice_date") is not None]
    return {
        "months": months,
        "windowStart": window_start,
        "windowEnd": anchor,
        "reportingDate": anchor,
        "actualDataThroughDate": max(actual_dates) if actual_dates else None,
        "progressSnapshotId": progress_snapshot_id,
        "estimateSource": "unavailable",
        "actualSource": "confirmed_financial_documents",
        # "incomplete" rather than "partial": the two existing calculationStatus fields
        # in this API are Literal["complete","incomplete"], and one field name carrying
        # two vocabularies is worse than a slightly blunt word.
        "calculationStatus": "incomplete",
        "warnings": [estimate_unavailable_warning()],
    }
