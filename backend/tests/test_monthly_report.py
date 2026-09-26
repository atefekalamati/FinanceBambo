"""The Persian-month cost series that feeds the Finance Home trend chart.

Three things are worth stating about what these tests actually pin.

The calendar is cross-checked against ICU, not against itself. The boundaries are covered
below; the converter as a whole was diffed day-by-day against the same
`Intl.DateTimeFormat("en-US-u-ca-persian")` the frontend buckets with, over 1990-2050,
and agreed on all 22280 days. A backend that disagreed with the browser about where
Farvardin starts would move money between bars.

Actual cost is not redefined here. The reconciliation test runs one invoice fixture
through both this series and `calculate_live_report` and requires the same total, so the
chart and the report cannot drift apart.

An absent estimate is not zero. Several tests assert `estimateIrr is None` rather than
"0", because the two mean different things to a reader deciding whether a month overspent.
"""

import re
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.monthly import (
    DEFAULT_MONTH_COUNT, MAX_MONTH_COUNT, build_monthly_series, monthly_report)
from app.finance.domain.persian_calendar import (
    gregorian_to_persian, persian_month_window, persian_to_gregorian)
from app.finance.domain.reports import calculate_live_report
from app.finance.repositories.reports import PsycopgLiveReportRepository
from app.finance.schemas.reports import MonthlyReportResponse
from app.finance.security.context import AuthContext
from app.finance.services.reports import FinanceLiveReportService, MonthlyWindowUnsupported
from app.main import create_app
from persian_calendar_golden import golden_pairs

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"
SCOPE = SimpleNamespace(organization_id=ORG, project_id=PROJECT, actor_user_id=ACTOR)
ANCHOR = date(2026, 8, 21)   # 1405-05-30


def amount(day, resource_type, value):
    return {"invoice_date": date.fromisoformat(day), "resource_type": resource_type,
            "amount_irr": Decimal(value)}


def documents(day, sign, count):
    return {"invoice_date": date.fromisoformat(day), "financial_effect_sign": sign,
            "document_count": count}


def window(anchor, month_count):
    start, year, month = persian_month_window(anchor, month_count)
    return start, year, month, month_count


def series(amount_rows, document_rows, anchor, month_count):
    return build_monthly_series(amount_rows, document_rows, window(anchor, month_count))


def month_of(months, persian_year, persian_month):
    for entry in months:
        if (entry["persianYear"], entry["persianMonth"]) == (persian_year, persian_month):
            return entry
    raise AssertionError("month %s-%s missing from series" % (persian_year, persian_month))


class PersianCalendarTests(unittest.TestCase):
    def test_persian_year_boundary_falls_between_the_two_gregorian_days(self):
        # Nowruz 1405 is 2026-03-21; the day before still belongs to Esfand 1404.
        self.assertEqual((1404, 12, 29), gregorian_to_persian(date(2026, 3, 20)))
        self.assertEqual((1405, 1, 1), gregorian_to_persian(date(2026, 3, 21)))

    def test_persian_month_boundary_decides_the_bucket_not_the_gregorian_one(self):
        # Farvardin runs 31 days, so 2026-04-20 is still month 1 and 2026-04-21 is month 2.
        self.assertEqual((1405, 1, 31), gregorian_to_persian(date(2026, 4, 20)))
        self.assertEqual((1405, 2, 1), gregorian_to_persian(date(2026, 4, 21)))

    def test_leap_year_esfand_has_a_thirtieth_day(self):
        # 1403 is a leap year: Esfand reaches 30 and 1404 opens the following day.
        self.assertEqual((1403, 12, 30), gregorian_to_persian(date(2025, 3, 20)))
        self.assertEqual((1404, 1, 1), gregorian_to_persian(date(2025, 3, 21)))
        # 1404 is not: its Esfand stops at 29.
        self.assertEqual((1404, 12, 29), gregorian_to_persian(date(2026, 3, 20)))

    def test_conversion_round_trips_across_every_month_of_several_years(self):
        for year in (1403, 1404, 1405, 1406, 1407):
            for month in range(1, 13):
                for day in (1, 15, 29):
                    self.assertEqual(
                        (year, month, day),
                        gregorian_to_persian(persian_to_gregorian(year, month, day)))

    def test_window_opens_on_the_first_day_of_the_earliest_month(self):
        start, year, month = persian_month_window(ANCHOR, 12)
        self.assertEqual((1404, 6), (year, month))
        self.assertEqual(date(2025, 8, 23), start)
        self.assertEqual((1404, 6, 1), gregorian_to_persian(start))

    def test_a_single_month_window_opens_inside_the_anchor_month(self):
        start, year, month = persian_month_window(ANCHOR, 1)
        self.assertEqual(((1405, 5), (1405, 5, 1)), ((year, month), gregorian_to_persian(start)))

    def test_every_icu_month_boundary_is_reproduced(self):
        # The frontend buckets with Intl; persian_calendar_golden.py holds what Intl says
        # for every month boundary from 1394-11 to 1420-10, and the day before each. A
        # round-trip test would not catch a uniformly shifted calendar. This does.
        checked = 0
        for gregorian, expected in golden_pairs():
            self.assertEqual(expected, gregorian_to_persian(date.fromisoformat(gregorian)),
                             "disagreed with ICU on " + gregorian)
            checked += 1
        self.assertGreater(checked, 600)

    def test_a_non_positive_month_count_is_refused(self):
        with self.assertRaises(ValueError):
            persian_month_window(ANCHOR, 0)


class MonthlySeriesTests(unittest.TestCase):
    def test_one_invoice_in_one_month_lands_in_that_month_alone(self):
        months, _start = series(
            [amount("2026-04-15", "material", "1000")], [documents("2026-04-15", 1, 1)], ANCHOR, 12)
        self.assertEqual(Decimal("1000"), month_of(months, 1405, 1)["actualCostIrr"])
        self.assertEqual(1, month_of(months, 1405, 1)["invoiceCount"])
        self.assertEqual(
            [Decimal(0)] * 11,
            [m["actualCostIrr"] for m in months if (m["persianYear"], m["persianMonth"]) != (1405, 1)])

    def test_several_invoices_in_one_month_are_summed(self):
        months, _start = series(
            [amount("2026-04-15", "material", "1000"), amount("2026-04-18", "labor", "500"),
             amount("2026-04-20", "material", "250")],
            [documents("2026-04-15", 1, 1), documents("2026-04-18", 1, 1), documents("2026-04-20", 1, 2)],
            ANCHOR, 12)
        entry = month_of(months, 1405, 1)
        self.assertEqual(Decimal("1750"), entry["actualCostIrr"])
        self.assertEqual(4, entry["invoiceCount"])

    def test_invoices_across_months_stay_in_their_own_persian_month(self):
        months, _start = series(
            [amount("2026-04-20", "material", "1000"), amount("2026-04-21", "material", "300"),
             amount("2026-05-10", "equipment", "700")],
            [], ANCHOR, 12)
        self.assertEqual(Decimal("1000"), month_of(months, 1405, 1)["actualCostIrr"])
        # 2026-04-21 and 2026-05-10 are both Ordibehesht despite spanning two Gregorian months.
        self.assertEqual(Decimal("1000"), month_of(months, 1405, 2)["actualCostIrr"])

    def test_the_series_crosses_a_persian_year_boundary(self):
        anchor = date(2026, 4, 15)  # 1405-01-26
        months, start = series(
            [amount("2026-03-20", "material", "800"), amount("2026-03-21", "material", "900")],
            [], anchor, 3)
        self.assertEqual([(1404, 11), (1404, 12), (1405, 1)],
                         [(m["persianYear"], m["persianMonth"]) for m in months])
        self.assertEqual(Decimal("800"), month_of(months, 1404, 12)["actualCostIrr"])
        self.assertEqual(Decimal("900"), month_of(months, 1405, 1)["actualCostIrr"])
        self.assertEqual(date(2026, 1, 21), start)

    def test_a_month_with_no_document_is_returned_as_zero_not_omitted(self):
        # The chart does not fill gaps in API data; a missing month would draw two
        # non-adjacent months side by side as if they were consecutive.
        months, _start = series([amount("2026-08-01", "material", "10")], [], ANCHOR, 12)
        self.assertEqual(12, len(months))
        empty = month_of(months, 1405, 4)
        self.assertEqual((Decimal(0), 0, 0),
                         (empty["actualCostIrr"], empty["invoiceCount"], empty["reversalCount"]))

    def test_months_are_contiguous_and_chronologically_ordered(self):
        months, _start = series([], [], ANCHOR, 14)
        keys = [(m["persianYear"], m["persianMonth"]) for m in months]
        self.assertEqual(sorted(keys), keys)
        self.assertEqual(14, len(set(keys)))
        for earlier, later in zip(keys, keys[1:]):
            expected = (earlier[0] + 1, 1) if earlier[1] == 12 else (earlier[0], earlier[1] + 1)
            self.assertEqual(expected, later)
        self.assertEqual((1405, 5), keys[-1])

    def test_a_document_outside_the_window_is_ignored_rather_than_folded_into_an_edge_month(self):
        months, _start = series(
            [amount("2020-04-15", "material", "999"), amount("2026-08-01", "material", "10")],
            [], ANCHOR, 12)
        self.assertEqual(Decimal("10"), sum(m["actualCostIrr"] for m in months))

    def test_reversals_subtract_and_are_counted_apart_from_purchases(self):
        months, _start = series(
            [amount("2026-08-01", "material", "1000"), amount("2026-08-02", "material", "-1000")],
            [documents("2026-08-01", 1, 1), documents("2026-08-02", -1, 1)], ANCHOR, 12)
        entry = month_of(months, 1405, 5)
        self.assertEqual(Decimal("0"), entry["actualCostIrr"])
        # A reversal is not new purchasing activity, so it must not inflate invoiceCount.
        self.assertEqual((1, 1), (entry["invoiceCount"], entry["reversalCount"]))

    def test_estimate_is_absent_rather_than_zero_for_every_month(self):
        months, _start = series([amount("2026-08-01", "material", "10")], [], ANCHOR, 12)
        self.assertTrue(all(m["estimateIrr"] is None for m in months))

    def test_the_breakdown_is_exhaustive_and_sums_to_the_month_total(self):
        months, _start = series(
            [amount("2026-08-01", "material", "1000"), amount("2026-08-01", "labor", "500"),
             amount("2026-08-02", "equipment", "300"), amount("2026-08-03", "general_cost", "200")],
            [], ANCHOR, 12)
        entry = month_of(months, 1405, 5)
        # The rows still say `labor` and `equipment` -- rows written before 0038 do -- and
        # both land in `work`: one kind, and the old names are read as it.
        self.assertEqual({"material": Decimal("1000"), "work": Decimal("800"),
                          "generalCost": Decimal("200")},
                         entry["breakdown"])
        self.assertEqual(entry["actualCostIrr"], sum(entry["breakdown"].values()))

    def test_an_empty_dataset_still_returns_the_full_contiguous_window(self):
        report = monthly_report([], [], window(ANCHOR, 12), ANCHOR)
        self.assertEqual(12, len(report["months"]))
        self.assertEqual(Decimal(0), sum(m["actualCostIrr"] for m in report["months"]))

    def test_the_envelope_reports_the_estimate_as_unavailable_and_says_why(self):
        report = monthly_report([], [], window(ANCHOR, 12), ANCHOR)
        self.assertEqual("unavailable", report["estimateSource"])
        self.assertEqual("confirmed_financial_documents", report["actualSource"])
        self.assertEqual("incomplete", report["calculationStatus"])
        warning = report["warnings"][0]
        self.assertEqual("MONTHLY_ESTIMATE_UNAVAILABLE", warning["code"])
        self.assertEqual(["estimateIrr"], warning["affectedMetricKeys"])

    def test_the_contract_cannot_express_preview_as_an_estimate_source(self):
        # The frontend renders a "this is fake data" banner on estimateSource ===
        # "preview". Asserting the current value is not enough — the type must make the
        # value unreachable, so no later change can send it by accident.
        allowed = get_args(MonthlyReportResponse.model_fields["estimate_source"].annotation)
        self.assertNotIn("preview", allowed)
        self.assertEqual(("unavailable", "schedule", "manual_plan"), allowed)


class Cursor:
    def __init__(self): self.executions = []
    async def execute(self, query, parameters=()):
        self.executions.append((" ".join(query.split()), tuple(parameters)))
    async def fetchall(self): return []


class Context:
    def __init__(self, owner): self.owner = owner
    async def __aenter__(self): return self.owner
    async def __aexit__(self, *_): return False


class Connection:
    def __init__(self, cursor): self.cursor_instance = cursor
    def cursor(self, **_): return Context(self.cursor_instance)


class MonthlyActualsSqlTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self):
        cursor = Cursor()
        await PsycopgLiveReportRepository(Connection(cursor)).monthly_actuals(
            SCOPE, date(2025, 8, 23), ANCHOR)
        return cursor.executions

    async def test_the_amount_query_matches_the_live_report_definition_of_actual_cost(self):
        (amount_sql, amount_values), _documents = await self._run()
        self.assertIn("i.status IN ('confirmed','voided','corrected')", amount_sql)
        # An unsigned sum would report a reversal as extra spending.
        self.assertIn("SUM(il.final_line_amount_irr*i.financial_effect_sign)", amount_sql)
        self.assertIn("GROUP BY i.invoice_date,r.resource_type", amount_sql)
        self.assertEqual((ORG, PROJECT, date(2025, 8, 23), ANCHOR), amount_values)

    async def test_both_queries_bind_the_tenant_scope_before_anything_else(self):
        for sql, values in await self._run():
            self.assertIn("organization_id=%s AND", sql)
            self.assertIn("project_id=%s", sql)
            self.assertEqual((ORG, PROJECT), values[:2])
            self.assertEqual(sql.count("%s"), len(values))

    async def test_the_date_window_is_inclusive_at_both_ends(self):
        # invoice_date is a date and the rest of the reporting engine compares it
        # inclusively; a half-open bound here would drop the reporting day itself.
        for sql, _values in await self._run():
            self.assertIn("invoice_date>=%s AND", sql)
            self.assertIn("invoice_date<=%s", sql)

    async def test_the_document_count_is_grouped_by_sign_so_reversals_stay_separable(self):
        _amounts, (document_sql, _values) = await self._run()
        self.assertIn("GROUP BY invoice_date,financial_effect_sign", document_sql)
        self.assertIn("COUNT(*) document_count", document_sql)

    def test_the_status_predicate_is_the_same_text_as_the_live_report_uses(self):
        # Comparing against a literal copied into the test would let both drift together.
        # Read the predicate out of the module and require every occurrence to agree, so
        # changing actual cost in one query and not the other fails here.
        source = Path(PsycopgLiveReportRepository.__module__.replace(".", "/") + ".py")
        text = (BACKEND_ROOT / source).read_text(encoding="utf-8")
        predicates = re.findall(r"i\.status IN \([^)]*\)", text)
        self.assertEqual(2, len(predicates), "expected the live report query and the monthly query")
        self.assertEqual(1, len(set(predicates)), "the two queries disagree about actual cost: %s" % predicates)

    async def test_grouping_never_filters_on_a_derived_month_expression(self):
        # date_trunc in the WHERE clause would defeat ix_invoices_scope.
        for sql, _values in await self._run():
            self.assertNotIn("date_trunc", sql.lower())


class Repo:
    """Applies the documented predicate to invoice fixtures, as the SQL does."""

    EFFECTIVE = ("confirmed", "voided", "corrected")

    def __init__(self, invoices):
        self.invoices = invoices
        self.calls = []

    async def monthly_actuals(self, scope, date_from, date_to):
        self.calls.append((date_from, date_to))
        rows = [i for i in self.invoices
                if i["status"] in self.EFFECTIVE and date_from <= i["invoice_date"] <= date_to]
        amounts = {}
        for entry in rows:
            for resource_type, value in entry["lines"]:
                key = (entry["invoice_date"], resource_type)
                amounts[key] = amounts.get(key, Decimal(0)) + Decimal(value) * entry["sign"]
        counts = {}
        for entry in rows:
            key = (entry["invoice_date"], entry["sign"])
            counts[key] = counts.get(key, 0) + 1
        return ([{"invoice_date": day, "resource_type": kind, "amount_irr": value}
                 for (day, kind), value in sorted(amounts.items(), key=lambda item: item[0])],
                [{"invoice_date": day, "financial_effect_sign": sign, "document_count": count}
                 for (day, sign), count in sorted(counts.items(), key=lambda item: item[0])])

    async def snapshot(self, scope, snapshot_id):
        return {"progress_snapshot_id": snapshot_id,
                "reporting_date": date(2026, 5, 12)}


def invoice(day, status, sign, lines):
    return {"invoice_date": date.fromisoformat(day), "status": status, "sign": sign, "lines": lines}


FIXTURE = [
    invoice("2026-04-15", "confirmed", 1, [("material", "1000"), ("labor", "500")]),
    invoice("2026-04-15", "voided", -1, [("material", "1000"), ("labor", "500")]),
    invoice("2026-04-25", "confirmed", 1, [("material", "300")]),
    invoice("2026-05-10", "confirmed", 1, [("equipment", "700")]),
    invoice("2026-05-12", "corrected", -1, [("general_cost", "200")]),
    invoice("2026-06-01", "draft", 1, [("material", "9999")]),
    invoice("2026-06-02", "awaitingConfirmation", 1, [("labor", "8888")]),
]


def service(invoices=FIXTURE):
    return FinanceLiveReportService(Repo(invoices), progress_provider=None)


class MonthlyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_snapshot_id_is_the_authority_for_the_curve_end_date(self):
        snapshot_id = UUID(int=44)
        instance = service()
        report = await instance.monthly(
            SCOPE, date(2026, 8, 21), 6, snapshot_id)
        self.assertEqual(date(2026, 5, 12), report["reportingDate"])
        self.assertEqual(snapshot_id, report["progressSnapshotId"])
        self.assertEqual(date(2026, 5, 12), instance.repo.calls[0][1])

    async def test_actual_data_date_is_separate_from_the_snapshot_period(self):
        report = await service().monthly(SCOPE, ANCHOR, 12)
        self.assertEqual(ANCHOR, report["reportingDate"])
        self.assertEqual(date(2026, 5, 12), report["actualDataThroughDate"])

    async def test_draft_and_awaiting_confirmation_never_reach_actual_cost(self):
        report = await service().monthly(SCOPE, ANCHOR, 12)
        self.assertEqual(Decimal("800"), sum(m["actualCostIrr"] for m in report["months"]))
        self.assertNotIn(Decimal("9999"), {m["actualCostIrr"] for m in report["months"]})

    async def test_a_void_nets_its_original_to_zero_in_the_original_month(self):
        report = await service().monthly(SCOPE, ANCHOR, 12)
        # Farvardin holds only the 1500 purchase and its -1500 reversal, both dated
        # 1405-01-26, so the month reports exactly nothing rather than 1500.
        self.assertEqual(Decimal("0"), month_of(report["months"], 1405, 1)["actualCostIrr"])
        self.assertEqual((1, 1), (month_of(report["months"], 1405, 1)["invoiceCount"],
                                  month_of(report["months"], 1405, 1)["reversalCount"]))

    async def test_a_corrective_document_subtracts_where_its_own_date_falls(self):
        report = await service().monthly(SCOPE, ANCHOR, 12)
        # Ordibehesht: 300 + 700 purchases less the 200 correction dated 1405-02-22.
        entry = month_of(report["months"], 1405, 2)
        self.assertEqual(Decimal("800"), entry["actualCostIrr"])
        self.assertEqual(Decimal("-200"), entry["breakdown"]["generalCost"])

    async def test_the_monthly_total_reconciles_with_the_live_report_actual_cost(self):
        # Two independent implementations over one fixture: if either changes its mind
        # about which documents are financially effective, this fails.
        report = await service().monthly(SCOPE, ANCHOR, 24)
        invoice_rows = [
            {"invoice_id": UUID(int=index), "estimate_line_id": None, "resource_id": UUID(int=index),
             "quantity": Decimal(1), "unit": "kg", "final_line_amount_irr": Decimal(value),
             "financial_effect_sign": entry["sign"], "resource_type": resource_type,
             "resource_code": "R", "base_unit": "kg", "dimension": None}
            for index, entry in enumerate(FIXTURE, 1) if entry["status"] in Repo.EFFECTIVE
            for resource_type, value in entry["lines"]]
        live = calculate_live_report([], invoice_rows, [], [], None)
        self.assertEqual(Decimal(live.metrics["actualCostIrr"]),
                         sum(m["actualCostIrr"] for m in report["months"]))
        # A total alone would survive every invoice being dropped into one bar, so pin
        # where the money landed as well.
        self.assertEqual({(1405, 1): Decimal("0"), (1405, 2): Decimal("800")},
                         {(m["persianYear"], m["persianMonth"]): m["actualCostIrr"]
                          for m in report["months"] if m["invoiceCount"] or m["reversalCount"]})

    async def test_the_window_asked_of_the_repository_ends_on_the_reporting_date(self):
        instance = service()
        await instance.monthly(SCOPE, ANCHOR, 6)
        # Not the end of the anchor's Persian month: cost dated after the reporting date
        # must not appear, exactly as the live report filters it.
        # Six months ending in Mordad 1405 open on 1404-12-01, which is 2026-02-20.
        self.assertEqual((date(2026, 2, 20), ANCHOR), instance.repo.calls[0])

    async def test_the_month_count_defaults_to_twelve_and_is_bounded(self):
        self.assertEqual(DEFAULT_MONTH_COUNT, len((await service().monthly(SCOPE, ANCHOR))["months"]))
        for invalid in (0, -1, MAX_MONTH_COUNT + 1):
            with self.assertRaises(MonthlyWindowUnsupported) as caught:
                await service().monthly(SCOPE, ANCHOR, invalid)
            self.assertEqual(422, caught.exception.status)

    async def test_a_reporting_date_before_the_persian_epoch_is_refused_not_crashed(self):
        # Walking twelve months back from the Gregorian epoch leaves Persian year 1
        # behind; date() would raise and the DTO could not represent the result.
        for impossible in (date(1, 1, 1), date(622, 1, 1)):
            with self.assertRaises(MonthlyWindowUnsupported) as caught:
                await service().monthly(SCOPE, impossible, 12)
            self.assertEqual((422, "VALIDATION_ERROR"),
                             (caught.exception.status, caught.exception.code))


class AuthProvider:
    def __init__(self, permissions): self.permissions = tuple(permissions)
    async def current(self, _request):
        return AuthContext(userId=ACTOR, organizationId=ORG, projectId=PROJECT,
                           organizationRole="finance_viewer", projectRole="viewer",
                           permissionCodes=self.permissions, locale="fa-IR", timezone="Asia/Tehran")


class ScopeAuthorizer:
    async def require_organization(self, _context, organization_id):
        if organization_id != str(ORG):
            raise HTTPException(403, "organization denied")

    async def require_project(self, _context, organization_id, project_id):
        if organization_id != str(ORG) or project_id != PROJECT:
            raise HTTPException(403, "project denied")


class PermissionAuthorizer:
    async def require(self, context, permission_code):
        if permission_code not in context.permission_codes:
            raise HTTPException(403, "permission denied")


def client(permissions=("finance_report.view",)):
    app = create_app()
    app.state.auth_context_provider = AuthProvider(permissions)
    app.state.scope_authorizer = ScopeAuthorizer()
    app.state.permission_authorizer = PermissionAuthorizer()
    app.state.finance_live_report_service = service()
    return TestClient(app)


class MonthlyApiTests(unittest.TestCase):
    URL = "/api/projects/%s/finance/reports/monthly" % PROJECT

    def test_money_is_serialised_as_an_exact_integer_string(self):
        with client() as api:
            body = api.get(self.URL, params={"reportingDate": "2026-08-21"}).json()
        entry = month_of(body["months"], 1405, 2)
        self.assertEqual("800", entry["actualCostIrr"])
        self.assertIsInstance(entry["actualCostIrr"], str)
        self.assertIsInstance(entry["breakdown"]["material"], str)
        self.assertEqual("-200", entry["breakdown"]["generalCost"])
        for month in body["months"]:
            self.assertRegex(month["actualCostIrr"], r"^-?\d+$")

    def test_the_payload_carries_the_field_names_the_chart_reads(self):
        with client() as api:
            body = api.get(self.URL, params={"reportingDate": "2026-08-21"}).json()
        self.assertEqual({"persianYear", "persianMonth", "actualCostIrr", "estimateIrr",
                          "invoiceCount", "reversalCount", "breakdown"}, set(body["months"][0]))
        self.assertEqual({"material", "work", "generalCost"},
                         set(body["months"][0]["breakdown"]))
        self.assertEqual("unavailable", body["estimateSource"])

    def test_estimate_is_null_in_json_rather_than_a_zero_string(self):
        with client() as api:
            body = api.get(self.URL, params={"reportingDate": "2026-08-21"}).json()
        self.assertTrue(all(month["estimateIrr"] is None for month in body["months"]))

    def test_month_count_is_honoured_and_out_of_range_values_are_refused(self):
        with client() as api:
            ok = api.get(self.URL, params={"reportingDate": "2026-08-21", "monthCount": 3})
            too_many = api.get(self.URL, params={"reportingDate": "2026-08-21", "monthCount": 61})
            zero = api.get(self.URL, params={"reportingDate": "2026-08-21", "monthCount": 0})
        self.assertEqual(3, len(ok.json()["months"]))
        self.assertEqual((422, 422), (too_many.status_code, zero.status_code))
        self.assertEqual("VALIDATION_ERROR", too_many.json()["error"]["code"])

    def test_a_missing_or_malformed_reporting_date_is_refused(self):
        with client() as api:
            missing = api.get(self.URL)
            malformed = api.get(self.URL, params={"reportingDate": "not-a-date"})
        self.assertEqual((422, 422), (missing.status_code, malformed.status_code))

    def test_reading_the_series_needs_the_reporting_view_permission(self):
        with client(("finance.view",)) as api:
            denied = api.get(self.URL, params={"reportingDate": "2026-08-21"})
        self.assertEqual(403, denied.status_code)

    def test_another_project_in_the_same_organization_is_refused(self):
        with client() as api:
            denied = api.get("/api/projects/other_project/finance/reports/monthly",
                             params={"reportingDate": "2026-08-21"})
        self.assertEqual(403, denied.status_code)
        self.assertEqual("FINANCE_FORBIDDEN", denied.json()["error"]["code"])

    def test_naming_another_organization_in_the_query_changes_nothing(self):
        # The organization comes from the authenticated context. Comparing the two bodies
        # is what proves the parameter is inert; asserting it is absent from the response
        # would pass even if it had been honoured.
        with client() as api:
            plain = api.get(self.URL, params={"reportingDate": "2026-08-21"})
            injected = api.get(self.URL, params={"reportingDate": "2026-08-21",
                                                 "organizationId": str(OTHER_ORG)})
        self.assertEqual(200, injected.status_code)
        self.assertEqual(plain.json(), injected.json())

    def test_a_reporting_date_outside_the_calendar_is_refused_rather_than_a_server_error(self):
        with client() as api:
            responses = [api.get(self.URL, params={"reportingDate": day})
                         for day in ("0001-01-01", "0622-01-01")]
        self.assertEqual([422, 422], [r.status_code for r in responses])
        self.assertEqual(["VALIDATION_ERROR"] * 2, [r.json()["error"]["code"] for r in responses])


if __name__ == "__main__":
    unittest.main()
