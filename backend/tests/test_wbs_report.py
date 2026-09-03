"""The live report rolled up to WBS stages.

Two things these tests are built to catch, because both are silent failures:

**A stage that disappears.** The tree comes from Core's activity catalogue, not from
Finance's rows, so a stage with nothing recorded against it must still appear with zeros. A
missing heading reads as "nothing was planned here", which is a different and much worse
statement than "nothing has been spent here yet".

**Money that evaporates.** Every rial of actual cost lands in exactly one of three places:
a node, `unattributedActualIrr`, or `unmappedWbsActualIrr`. The reconciliation test asserts
the sum, so a future change that quietly drops a category fails here rather than in a report
somebody signs.
"""

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain import wbs
from app.finance.schemas.reports import WbsReportResponse
from app.finance.services.reports import FinanceLiveReportService

ORGANIZATION = UUID("40000000-0000-4000-8000-000000000001")
PROJECT = "sample_site_01"
SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")

CONCRETE = UUID("20000000-0000-4000-8000-000000000001")
CREW = UUID("20000000-0000-4000-8000-000000000002")
CRANE = UUID("20000000-0000-4000-8000-000000000003")
OVERHEAD = UUID("20000000-0000-4000-8000-000000000004")


def line(number):
    return UUID("10000000-0000-4000-8000-%012d" % number)


def activity(code, wbs_code, title):
    return {"activityExternalId": code,
            "taskExternalId": None if code is None else "t-" + code, "title": title,
            "wbsCode": wbs_code, "status": "active"}


#: A plan two levels deep, plus one stage nobody has recorded anything against.
ACTIVITIES = [
    activity("ACT-100", "1", "کارهای مقدماتی"),
    activity("ACT-110", "1.1", "تجهیز کارگاه"),
    activity("ACT-800", "1.8", "اجرای سازه بتنی"),
    activity("ACT-810", "1.8.1", "قالب‌بندی"),
    activity("ACT-820", "1.8.2", "آرماتوربندی"),
    activity("ACT-830", "1.8.10", "بتن‌ریزی"),
    activity("ACT-900", "2", "نازک‌کاری"),          # no estimate lines anywhere below it
]


def estimate(line_id, resource_id, kind, activity_code, quantity, price,
             current_price=None, revised=None):
    return {"id": line_id, "resource_id": resource_id, "resource_type": kind,
            "resource_code": kind[:3], "resource_title": kind,
            "original_quantity": quantity, "revised_quantity": revised or quantity,
            "original_unit_price_irr": price,
            "current_unit_price_irr": current_price or price,
            "assignment_external_id": None, "activity_external_id": activity_code,
            "progress_snapshot_id": SNAPSHOT}


def invoice(estimate_line_id, resource_id, kind, amount, sign=1, quantity=None):
    return {"estimate_line_id": estimate_line_id, "resource_id": resource_id,
            "resource_type": kind, "resource_code": kind[:3], "quantity": quantity,
            "unit": "each", "base_unit": "each", "dimension": "count",
            "final_line_amount_irr": amount, "financial_effect_sign": sign}


ESTIMATES = [
    estimate(line(1), CONCRETE, "material", "ACT-810", "100", "1000"),
    estimate(line(2), CREW, "labor", "ACT-820", "40", "500"),
    estimate(line(3), CRANE, "equipment", "ACT-830", "10", "2000"),
    estimate(line(4), CONCRETE, "material", "ACT-110", "20", "1000"),
    estimate(line(5), OVERHEAD, "general_cost", "ACT-100", None, "7000"),
    # An estimate line whose activity is not in the catalogue at all: it reaches no stage.
    estimate(line(6), CONCRETE, "material", "ACT-GHOST", "5", "1000"),
]

INVOICES = [
    invoice(line(1), CONCRETE, "material", "90000", quantity="90"),
    invoice(line(2), CREW, "labor", "15000", quantity="30"),
    invoice(line(3), CRANE, "equipment", "8000", quantity="4"),
    invoice(line(4), CONCRETE, "material", "12000", quantity="12"),
    invoice(line(6), CONCRETE, "material", "3000", quantity="3"),      # unmapped stage
    invoice(None, CONCRETE, "material", "5000", quantity="5"),         # no estimate line
    invoice(None, CONCRETE, "material", "1000", sign=-1, quantity="1"),  # a reversal of one
]


class Repository:
    def __init__(self, estimates=None, invoices=None):
        self.estimates = ESTIMATES if estimates is None else estimates
        self.invoices = INVOICES if invoices is None else invoices
        self.selected = {"progress_snapshot_id": SNAPSHOT, "reporting_date": date(2026, 8, 1),
                         "host_snapshot_id": 9002}

    async def load(self, scope, reporting_date):
        return {"snapshot": self.selected, "estimates": list(self.estimates),
                "invoices": list(self.invoices), "conversions": [], "gross_area": "100",
                "settings_id": UUID(int=7)}

    async def snapshot(self, scope, snapshot_id):
        return self.selected if snapshot_id == SNAPSHOT else None


class Provider:
    def __init__(self, assignments=()):
        self.assignments = list(assignments)

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        # Echo the identifier that was asked for. The service looks a feed up by the Core
        # bigint when the reference carries one, and a provider that answered with its own
        # Finance UUID instead would be rejected as a different snapshot.
        return {"snapshot": {"organizationId": str(ORGANIZATION), "projectId": PROJECT,
                             "progressSnapshotId": str(snapshot_id)},
                "assignments": self.assignments}


class Activities:
    """A catalogue that records how it was asked, so N+1 reads fail the test."""

    def __init__(self, rows=None):
        self.rows = ACTIVITIES if rows is None else rows
        self.calls = []

    async def list_activities(self, organization_id, project_id, query=None, status=None,
                              page=1, page_size=50):
        self.calls.append({"page": page, "page_size": page_size})
        start = (page - 1) * page_size
        return self.rows[start:start + page_size], len(self.rows)

    async def get_activity(self, organization_id, project_id, activity_external_id):
        self.calls.append({"single": activity_external_id})
        return next((row for row in self.rows
                     if row["activityExternalId"] == activity_external_id), None)


def build(repository=None, activities=None, assignments=()):
    return FinanceLiveReportService(repository or Repository(), Provider(assignments),
                                    activity_provider=activities or Activities())


SCOPE = SimpleNamespace(organization_id=ORGANIZATION, project_id=PROJECT,
                        actor_user_id=UUID(int=8), locale="fa")
WHEN = date(2026, 8, 2)


class WbsTreeTests(unittest.TestCase):
    def test_a_code_is_split_into_a_path_and_a_parent(self):
        self.assertEqual(("1", "8", "2"), wbs.segments("1.8.2"))
        self.assertEqual("1.8", wbs.parent_of("1.8.2"))
        self.assertIsNone(wbs.parent_of("1"))
        self.assertEqual(("1", "1.8"), wbs.ancestors("1.8.2"))

    def test_a_code_spelled_loosely_still_names_the_same_node(self):
        self.assertEqual("1.8", wbs.normalize(" 1.8. "))
        self.assertEqual("1.8", wbs.normalize("1..8"))
        self.assertIsNone(wbs.normalize(""))
        self.assertIsNone(wbs.normalize(None))

    def test_stages_sort_naturally_so_ten_follows_nine(self):
        codes = ["1.10", "1.2", "1.1", "1.9"]
        self.assertEqual(["1.1", "1.2", "1.9", "1.10"],
                         sorted(codes, key=wbs.sort_key))

    def test_an_ancestor_exists_even_when_no_activity_names_it(self):
        nodes = wbs.build_tree([activity("ACT-1", "3.4.5", "عمیق")])
        self.assertEqual({"3", "3.4", "3.4.5"}, set(nodes))
        self.assertIsNone(nodes["3"]["title"])
        self.assertEqual("عمیق", nodes["3.4.5"]["title"])

    def test_an_activity_without_a_wbs_code_is_not_filed_at_the_root(self):
        nodes = wbs.build_tree([activity("ACT-1", None, "بی‌مرحله")])
        self.assertEqual({}, nodes)

    def test_an_activity_counts_at_every_level_above_it(self):
        nodes = wbs.build_tree(ACTIVITIES)
        self.assertEqual(4, len(nodes["1.8"]["activityCodes"]))
        self.assertEqual(6, len(nodes["1"]["activityCodes"]))
        self.assertEqual(3, len(nodes["1.8"]["children"]))

    def test_selecting_children_never_returns_grandchildren(self):
        nodes = wbs.build_tree(ACTIVITIES)
        self.assertEqual(["1.1", "1.8"], wbs.select(nodes, parent_wbs_code="1"))
        self.assertEqual(["1", "2"], wbs.select(nodes, level=1))
        self.assertEqual(["1.8.1", "1.8.2", "1.8.10"],
                         wbs.select(nodes, parent_wbs_code="1.8"))

    def test_a_parent_request_wins_over_a_level_request(self):
        nodes = wbs.build_tree(ACTIVITIES)
        self.assertEqual(["1.8.1", "1.8.2", "1.8.10"],
                         wbs.select(nodes, level=1, parent_wbs_code="1.8"))

    def test_an_unknown_parent_returns_nothing_rather_than_everything(self):
        nodes = wbs.build_tree(ACTIVITIES)
        self.assertEqual([], wbs.select(nodes, parent_wbs_code="9.9"))


class WbsReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_level_one_returns_root_stages_with_rolled_up_money(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        codes = [item["wbs_code"] for item in result["items"]]
        self.assertEqual(["1", "2"], codes)
        root = result["items"][0]
        # 100x1000 + 40x500 + 10x2000 + 20x1000 + 7000 general cost
        self.assertEqual(Decimal("167000"), root["initial_estimate_irr"])
        self.assertEqual(Decimal("125000"), root["actual_cost_irr"])
        self.assertEqual(6, root["activity_count"])
        self.assertEqual(2, root["child_count"])

    async def test_level_two_returns_direct_children_only(self):
        result = await build().by_wbs(SCOPE, WHEN, parent_wbs_code="1.8")
        self.assertEqual(["1.8.1", "1.8.2", "1.8.10"],
                         [item["wbs_code"] for item in result["items"]])
        self.assertEqual([0, 0, 0], [item["child_count"] for item in result["items"]])
        formwork = result["items"][0]
        self.assertEqual("قالب‌بندی", formwork["title"])
        self.assertEqual("1.8", formwork["parent_wbs_code"])
        self.assertEqual(Decimal("100000"), formwork["initial_estimate_irr"])
        self.assertEqual(Decimal("90000"), formwork["actual_cost_irr"])

    async def test_a_stage_with_no_finance_rows_is_still_returned_at_zero(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        empty = next(item for item in result["items"] if item["wbs_code"] == "2")
        self.assertEqual("نازک‌کاری", empty["title"])
        self.assertEqual(Decimal(0), empty["initial_estimate_irr"])
        self.assertEqual(Decimal(0), empty["actual_cost_irr"])
        self.assertEqual(0, empty["estimate_line_count"])
        self.assertEqual(1, empty["activity_count"])

    async def test_titles_and_codes_come_from_the_activity_catalogue(self):
        result = await build().by_wbs(SCOPE, WHEN, parent_wbs_code="1")
        titles = {item["wbs_code"]: item["title"] for item in result["items"]}
        self.assertEqual({"1.1": "تجهیز کارگاه", "1.8": "اجرای سازه بتنی"}, titles)

    async def test_the_catalogue_is_read_once_not_once_per_line(self):
        activities = Activities()
        await build(activities=activities).by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual(1, len(activities.calls))
        self.assertGreaterEqual(activities.calls[0]["page_size"], len(ACTIVITIES))

    async def test_revised_estimate_aggregates_across_a_subtree(self):
        estimates = [
            estimate(line(1), CONCRETE, "material", "ACT-810", "100", "1000", revised="120"),
            estimate(line(2), CREW, "labor", "ACT-820", "40", "500", revised="50"),
        ]
        service = build(Repository(estimates=estimates, invoices=[]))
        result = await service.by_wbs(SCOPE, WHEN, parent_wbs_code="1")
        stage = next(item for item in result["items"] if item["wbs_code"] == "1.8")
        self.assertEqual(Decimal("120000") + Decimal("25000"), stage["revised_estimate_irr"])

    async def test_breakdown_splits_actual_cost_by_resource_type(self):
        result = await build().by_wbs(SCOPE, WHEN, parent_wbs_code="1")
        stage = next(item for item in result["items"] if item["wbs_code"] == "1.8")
        self.assertEqual(Decimal("90000"), stage["breakdown"]["material"])
        self.assertEqual(Decimal("15000"), stage["breakdown"]["labor"])
        self.assertEqual(Decimal("8000"), stage["breakdown"]["equipment"])
        self.assertEqual(Decimal("0"), stage["breakdown"]["general_cost"])

    async def test_an_invoice_with_no_estimate_line_is_counted_not_dropped(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual(Decimal("4000"), result["unattributed_actual_irr"])

    async def test_a_line_whose_activity_has_no_stage_is_reported_separately(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual(Decimal("3000"), result["unmapped_wbs_actual_irr"])
        self.assertEqual(1, result["unmapped_estimate_line_count"])

    async def test_the_three_actual_figures_reconcile_to_the_project_total(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        roots = sum((item["actual_cost_irr"] for item in result["items"]), Decimal(0))
        self.assertEqual(
            result["totals"]["actualCostIrr"],
            roots + result["unattributed_actual_irr"] + result["unmapped_wbs_actual_irr"])

    async def test_a_reversal_subtracts_from_the_unattributed_total(self):
        # 5000 purchased, 1000 reversed. A reversal that added would be invisible in a sum.
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual(Decimal("4000"), result["unattributed_actual_irr"])

    async def test_money_is_serialized_as_integer_irr_strings(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        payload = WbsReportResponse(**result).model_dump(by_alias=True)
        first = payload["items"][0]
        self.assertIsInstance(first["initialEstimateIrr"], str)
        self.assertEqual("167000", first["initialEstimateIrr"])
        self.assertIsInstance(payload["unattributedActualIrr"], str)
        self.assertIsInstance(first["breakdown"]["material"], str)
        self.assertNotIn(".", first["initialEstimateIrr"])

    async def test_every_amount_stays_decimal_never_float(self):
        result = await build().by_wbs(SCOPE, WHEN, level=1)
        for item in result["items"]:
            for key in ("initial_estimate_irr", "revised_estimate_irr", "actual_cost_irr"):
                self.assertIsInstance(item[key], Decimal, key)
            for amount in item["breakdown"].values():
                self.assertIsInstance(amount, Decimal)

    async def test_the_snapshot_identifiers_match_the_live_report(self):
        service = build()
        report = await service.live(SCOPE, WHEN)
        result = await service.by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual(report["progress_snapshot_id"], result["progress_snapshot_id"])
        self.assertEqual(report["host_snapshot_id"], result["host_snapshot_id"])

    async def test_an_explicit_snapshot_id_is_honoured(self):
        result = await build().by_wbs(SCOPE, WHEN, progress_snapshot_id=SNAPSHOT, level=1)
        self.assertEqual(SNAPSHOT, result["progress_snapshot_id"])

    async def test_no_executed_quantity_is_invented_when_the_feed_reports_none(self):
        # The feed answers for the line but carries no quantity. The engine must not read
        # that as zero progress, so the node's forecast stays derived from actual cost.
        service = build(assignments=[{"assignmentExternalId": "a-x", "task": {}}])
        result = await service.by_wbs(SCOPE, WHEN, parent_wbs_code="1")
        stage = next(item for item in result["items"] if item["wbs_code"] == "1.8")
        self.assertIsNotNone(stage["actual_cost_irr"])
        self.assertNotEqual(Decimal(0), stage["actual_cost_irr"])

    async def test_a_project_larger_than_one_page_is_still_one_tree(self):
        rows, estimates, invoices = [], [], []
        for index in range(1, 261):
            code = "ACT-%03d" % index
            rows.append(activity(code, "5.%d" % index, "مرحله %d" % index))
            estimates.append(estimate(line(1000 + index), CONCRETE, "material", code,
                                      "1", "100"))
            invoices.append(invoice(line(1000 + index), CONCRETE, "material", "50"))
        service = build(Repository(estimates=estimates, invoices=invoices),
                        activities=Activities(rows))
        result = await service.by_wbs(SCOPE, WHEN, level=1)
        root = next(item for item in result["items"] if item["wbs_code"] == "5")
        self.assertEqual(260, root["activity_count"])
        self.assertEqual(260, root["child_count"])
        self.assertEqual(Decimal("26000"), root["initial_estimate_irr"])
        self.assertEqual(Decimal("13000"), root["actual_cost_irr"])
        children = await service.by_wbs(SCOPE, WHEN, parent_wbs_code="5")
        self.assertEqual(260, len(children["items"]))

    async def test_without_an_activity_catalogue_no_stage_is_invented(self):
        service = FinanceLiveReportService(Repository(), Provider())
        result = await service.by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual([], result["items"])
        # Every rial still has to be somewhere: with no tree, it is all outside one.
        self.assertEqual(
            result["totals"]["actualCostIrr"],
            result["unattributed_actual_irr"] + result["unmapped_wbs_actual_irr"])


class ActivityCountTests(unittest.IsolatedAsyncioTestCase):
    """Why the activity count is not `COUNT(msp_tasks)`.

    The catalogue keys activities by their resolved code, so two tasks sharing a code
    collapse to one and a task whose code cannot be resolved is absent entirely. That is
    why a snapshot of 1248 tasks reports 1247 activities: the difference is these two
    rules, not an off-by-one.
    """

    async def test_two_activities_sharing_a_stage_are_counted_separately(self):
        rows = [activity("ACT-1", "7.1", "اول"), activity("ACT-2", "7.1", "دوم")]
        result = await build(Repository(estimates=[], invoices=[]),
                             activities=Activities(rows)).by_wbs(SCOPE, WHEN, level=1)
        self.assertEqual(2, result["items"][0]["activity_count"])

    async def test_the_count_follows_the_catalogue_not_the_raw_task_rows(self):
        # The catalogue is what Finance sees. A task the catalogue dropped -- no resolvable
        # code -- is not in it, so it cannot be counted here either.
        rows = [activity("ACT-1", "7.1", "اول"), activity(None, "7.1", "بدون کد")]
        nodes = wbs.build_tree(rows)
        self.assertEqual(1, len(nodes["7.1"]["activityCodes"]))


if __name__ == "__main__":
    unittest.main()
