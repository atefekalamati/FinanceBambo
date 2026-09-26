# -*- coding: utf-8 -*-
"""Equipment rates on the daily-prices page: read-only, and not a sheet row.

WHAT THIS IS

A project prices its equipment with `price_versions` rows -- somebody decides a crane
costs so much per hour and records it against the Finance resource. The daily-prices page
shows material prices from a Google Sheet, and a person looking for "what does this cost
today" had to know which of two pages to open, because equipment was on neither.

So equipment appears there as a category, built by READING `price_versions` through the
same rung the report and Items-and-Estimates already resolve a manual price from.

WHAT IT MUST NEVER BECOME

A `provider_items` row, or a `price_observations` row. A provider item is a listing a
supplier published; an equipment rate is a decision somebody made. Copying one into the
other would put a fabricated listing in the table the importer owns, and the next import
would have to decide what to do with a row no sheet produced. Several tests here exist
only to pin that, because it is the tempting shortcut and it is not reversible.
"""

import ast
import inspect
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.material_categories import (CATEGORY_LABELS, VIRTUAL_CATEGORIES,
                                                    category_columns, specs_of)
from app.finance.domain.price_resolution import manual_price_join
from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
from app.finance.security.context import AuthContext
from app.finance.services.material_prices import EQUIPMENT_CATEGORY, MaterialPriceService
from app.main import create_app

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"
BASE = "/api/projects/%s/finance" % PROJECT

CRANE = UUID("44444444-4444-4444-8444-000000000001")
PUMP = UUID("44444444-4444-4444-8444-000000000002")
MIXER = UUID("44444444-4444-4444-8444-000000000003")
UNPRICED = UUID("44444444-4444-4444-8444-000000000004")

TODAY = date(2026, 9, 24)


def resource(resource_id, title, unit="hour"):
    return {"id": resource_id, "title": title, "base_unit": unit}


def version(resource_id, amount, effective, *, scope="project", created_by=ACTOR,
            recorded=None):
    """One `price_versions` row, as the table stores it."""
    return {"resource_id": resource_id, "unit_price_irr": Decimal(amount),
            "effective_from": effective, "scope_kind": scope, "created_by": created_by,
            "price_recorded_at": recorded or datetime(2026, 9, 1, tzinfo=timezone.utc)}


class FakeRepository:
    """Resources and price versions this test wrote, resolved by the documented ladder.

    The precedence is implemented here rather than mocked away, because the point of most
    of these tests is WHICH version wins. That the production repository resolves it with
    the shared SQL rung instead of a second copy is pinned separately, in
    `TheLadderIsSharedNotCopiedTests`.
    """

    def __init__(self, resources=(), versions=()):
        self.resources = list(resources)
        self.versions = list(versions)
        #: Every statement this fake was asked to run, so a test can assert what was not.
        self.statements = []

    def _selected(self, resource_id, as_of):
        applicable = [v for v in self.versions
                      if v["resource_id"] == resource_id and v["effective_from"] <= as_of]
        if not applicable:
            return None
        # Project before organization, then the newest effective date. The same order the
        # shared rung states in SQL.
        applicable.sort(key=lambda v: (v["scope_kind"] == "project", v["effective_from"]),
                        reverse=True)
        return applicable[0]

    async def equipment_rates(self, _scope, *, as_of):
        self.statements.append(("SELECT", "equipment_rates"))
        rows = []
        for item in sorted(self.resources, key=lambda r: r["title"]):
            chosen = self._selected(item["id"], as_of)
            if chosen is None:
                continue
            rows.append({"provider_item_id": item["id"], "external_name": item["title"],
                         "base_unit": item["base_unit"],
                         "unit_price_irr": chosen["unit_price_irr"],
                         "effective_from": chosen["effective_from"],
                         "created_by": chosen["created_by"],
                         "price_recorded_at": chosen["price_recorded_at"],
                         "scope_kind": chosen["scope_kind"]})
        return rows

    async def equipment_rate_count(self, scope, *, as_of):
        self.statements.append(("SELECT", "equipment_rate_count"))
        return len(await self.equipment_rates(scope, as_of=as_of))

    # ---- the sheet side, empty unless a test says otherwise
    async def categories(self, _scope):
        return []

    async def declared_categories(self, _scope):
        return []

    async def latest_observations(self, _scope, **_kwargs):
        return []

    async def unit_settings(self, _scope, category=None):
        return []

    async def labels(self, _scope, provider_item_id=None, active_only=True):
        return []

    async def mapped_resource_units(self, _scope):
        return {}


class Scope:
    organization_id = ORG
    project_id = PROJECT
    actor_user_id = ACTOR


def three_priced():
    return FakeRepository(
        resources=[resource(CRANE, "جرثقیل"), resource(PUMP, "پمپ بتن"),
                   resource(MIXER, "میکسر")],
        versions=[version(CRANE, "12000000", date(2026, 9, 1)),
                  version(PUMP, "8000000", date(2026, 9, 1)),
                  version(MIXER, "5000000", date(2026, 9, 1))])


class CategoryTests(unittest.IsolatedAsyncioTestCase):
    async def categories(self, repository, today=TODAY):
        return await MaterialPriceService(repository).categories(Scope, today=today)

    async def test_the_chip_appears_when_the_project_has_priced_equipment(self):
        items = await self.categories(three_priced())
        equipment, = [x for x in items if x["category"] == EQUIPMENT_CATEGORY]
        self.assertEqual(3, equipment["item_count"])
        self.assertEqual(3, equipment["active_count"])
        self.assertEqual(0, equipment["inactive_count"])

    async def test_it_does_not_appear_when_nothing_is_priced(self):
        empty = FakeRepository(resources=[resource(UNPRICED, "بیل مکانیکی")], versions=[])
        items = await self.categories(empty)
        self.assertEqual([], [x for x in items if x["category"] == EQUIPMENT_CATEGORY],
                         "a category with nothing in it is not a category this project has")

    async def test_unpriced_equipment_is_not_counted(self):
        repository = three_priced()
        repository.resources.append(resource(UNPRICED, "بیل مکانیکی"))
        items = await self.categories(repository)
        equipment, = [x for x in items if x["category"] == EQUIPMENT_CATEGORY]
        self.assertEqual(3, equipment["item_count"], "the fourth has no rate to publish")

    async def test_a_caller_naming_no_day_gets_no_equipment_chip(self):
        # This service reads no clock, deliberately. "Which rates are in force" is a
        # question about a day, and a caller that named none did not ask it.
        items = await self.categories(three_priced(), today=None)
        self.assertEqual([], [x for x in items if x["category"] == EQUIPMENT_CATEGORY])

    def test_the_label_comes_from_the_shared_vocabulary(self):
        self.assertEqual("نیرو و تجهیزات", CATEGORY_LABELS[EQUIPMENT_CATEGORY])

    def test_it_publishes_no_worksheet_columns(self):
        self.assertIn(EQUIPMENT_CATEGORY, VIRTUAL_CATEGORIES)
        self.assertEqual([], category_columns(EQUIPMENT_CATEGORY))
        self.assertNotEqual([], category_columns("rebar"), "a real worksheet still has its own")

    def test_it_publishes_no_specs(self):
        self.assertEqual({}, specs_of(EQUIPMENT_CATEGORY, {"وزن": "27"}))


class CurrentRateTests(unittest.IsolatedAsyncioTestCase):
    async def current(self, repository, **kwargs):
        options = {"category": EQUIPMENT_CATEGORY, "today": TODAY}
        options.update(kwargs)
        return await MaterialPriceService(repository).current(Scope, **options)

    async def test_it_returns_one_row_per_priced_resource(self):
        items, total = await self.current(three_priced())
        self.assertEqual(3, total)
        self.assertEqual({CRANE, PUMP, MIXER}, {x["provider_item_id"] for x in items})

    async def test_unpriced_equipment_is_absent_even_with_include_inactive(self):
        repository = three_priced()
        repository.resources.append(resource(UNPRICED, "بیل مکانیکی"))
        items, total = await self.current(repository, only_active=False)
        self.assertEqual(3, total)
        self.assertNotIn(UNPRICED, {x["provider_item_id"] for x in items},
                         "a row with no price does not belong in a price list")

    async def test_no_category_means_no_equipment(self):
        items, total = await self.current(three_priced(), category=None)
        self.assertEqual(([], 0), (items, total), "the all view stays sheet rows only")

    async def test_another_category_means_no_equipment(self):
        for other in ("rebar", "brick", "pipe"):
            with self.subTest(category=other):
                items, total = await self.current(three_priced(), category=other)
                self.assertEqual(([], 0), (items, total))

    async def test_a_project_price_beats_an_organization_price(self):
        repository = FakeRepository(
            resources=[resource(CRANE, "جرثقیل")],
            versions=[version(CRANE, "9000000", date(2026, 9, 1), scope="organization"),
                      version(CRANE, "12000000", date(2026, 9, 1), scope="project")])
        items, _ = await self.current(repository)
        self.assertEqual(Decimal("12000000"), items[0]["current_price_irr"],
                         "the more specific statement wins, as everywhere else")

    async def test_an_organization_price_is_used_when_the_project_set_none(self):
        repository = FakeRepository(
            resources=[resource(CRANE, "جرثقیل")],
            versions=[version(CRANE, "9000000", date(2026, 9, 1), scope="organization")])
        items, _ = await self.current(repository)
        self.assertEqual(Decimal("9000000"), items[0]["current_price_irr"])

    async def test_as_of_reads_the_rate_in_force_on_that_day_not_today(self):
        repository = FakeRepository(
            resources=[resource(CRANE, "جرثقیل")],
            versions=[version(CRANE, "10000000", date(2026, 9, 1)),
                      version(CRANE, "15000000", date(2026, 9, 20))])
        current, _ = await self.current(repository)
        self.assertEqual(Decimal("15000000"), current[0]["current_price_irr"])
        earlier, _ = await self.current(repository, as_of=date(2026, 9, 10))
        self.assertEqual(Decimal("10000000"), earlier[0]["current_price_irr"])
        self.assertEqual(date(2026, 9, 1), earlier[0]["workflow_date_gregorian"],
                         "and the date shown is the one that rate takes effect from")

    async def test_a_version_that_has_not_taken_effect_is_not_used(self):
        repository = FakeRepository(
            resources=[resource(CRANE, "جرثقیل")],
            versions=[version(CRANE, "10000000", date(2026, 9, 1)),
                      version(CRANE, "99000000", date(2026, 12, 1))])
        items, _ = await self.current(repository)
        self.assertEqual(Decimal("10000000"), items[0]["current_price_irr"])

    async def test_pagination_slices_and_totals_like_every_other_price_page(self):
        repository = three_priced()
        first, total = await self.current(repository, page=1, page_size=2)
        second, total_again = await self.current(repository, page=2, page_size=2)
        self.assertEqual((3, 3), (total, total_again), "total counts all of them")
        self.assertEqual(2, len(first))
        self.assertEqual(1, len(second))
        self.assertEqual(set(), {x["provider_item_id"] for x in first}
                         & {x["provider_item_id"] for x in second})

    async def test_a_page_past_the_end_is_empty_and_still_reports_the_total(self):
        items, total = await self.current(three_priced(), page=9, page_size=50)
        self.assertEqual(([], 3), (items, total))

    async def test_the_fields_a_sheet_would_have_filled_are_null(self):
        items, _ = await self.current(three_priced())
        row = items[0]
        for field in ("external_id", "provider_name", "worksheet", "source_row_number",
                      "source_url", "workflow_date_raw", "workflow_date_jalali",
                      "raw_price", "conversion_factor", "conversion_note"):
            with self.subTest(field=field):
                self.assertIsNone(row[field], "%s must be null, not empty or zero" % field)

    async def test_it_says_a_person_entered_it(self):
        items, _ = await self.current(three_priced())
        self.assertEqual("manual", items[0]["origin"])
        self.assertEqual(ACTOR, items[0]["entered_by"])

    async def test_the_date_is_the_versions_effective_date(self):
        repository = FakeRepository(
            resources=[resource(CRANE, "جرثقیل")],
            versions=[version(CRANE, "10000000", date(2026, 5, 6))])
        items, _ = await self.current(repository)
        self.assertEqual(date(2026, 5, 6), items[0]["workflow_date_gregorian"])
        self.assertEqual("workflow_date", items[0]["observed_at_source"],
                         "the timestamp is a widened date and says so")

    async def test_every_unit_is_the_resources_own(self):
        repository = FakeRepository(
            resources=[resource(CRANE, "جرثقیل", unit="hour")],
            versions=[version(CRANE, "10000000", date(2026, 9, 1))])
        items, _ = await self.current(repository)
        row = items[0]
        self.assertEqual(["hour"] * 4, [row["source_unit"], row["source_unit_code"],
                                        row["display_unit"], row["target_unit"]])

    async def test_it_is_resolved_and_valid_by_construction(self):
        items, _ = await self.current(three_priced())
        self.assertEqual("valid", items[0]["validation_status"])
        self.assertEqual("resolved", items[0]["resolution_status"])
        self.assertEqual("IRR", items[0]["source_currency"],
                         "price_versions is rials; the sheet is toman")


class TheLadderIsSharedNotCopiedTests(unittest.TestCase):
    """The precedence is stated once. Two readers of it would drift, and silently."""

    def test_the_repository_builds_its_join_from_the_shared_rung(self):
        statement = " ".join(PsycopgMaterialPriceRepository._EQUIPMENT_RATES.split())
        shared = " ".join(manual_price_join(organization="r.organization_id",
                                            project="r.project_id", resource="r.id",
                                            as_of="%(as_of)s").split())
        self.assertIn(shared, statement)

    def test_it_states_no_precedence_of_its_own(self):
        # It may READ `manual_price.scope_kind` -- that is a column of the derived table.
        # What it must not do is order `price_versions` a second time: exactly one ORDER BY
        # in this statement may mention the versions table, and it is the shared rung's.
        statement = " ".join(PsycopgMaterialPriceRepository._EQUIPMENT_RATES.split())
        orderings = [part for part in statement.split("ORDER BY ")[1:]]
        self.assertEqual(2, len(orderings), "the shared rung's, and the display order")
        self.assertIn("pv.scope_kind", orderings[0], "the rung's, verbatim")
        self.assertNotIn("pv.", orderings[1], "the display order says nothing about price")
        self.assertIn("r.title", orderings[1])

    def test_only_priced_equipment_is_selected(self):
        statement = " ".join(PsycopgMaterialPriceRepository._EQUIPMENT_RATES.split())
        # `work` since 0038, and the two names rows written before it still carry.
        self.assertIn("r.resource_type IN ('work', 'labor', 'equipment')", statement)
        self.assertIn("r.deleted_at IS NULL", statement)
        self.assertIn("manual_price.unit_price_irr IS NOT NULL", statement)


class NothingIsWrittenTests(unittest.TestCase):
    """The reason this feature is safe: it only reads."""

    def statements(self):
        source = inspect.getsource(PsycopgMaterialPriceRepository)
        tree = ast.parse("class X:\n" + "\n".join(
            "    " + line for line in source.splitlines()[1:]))
        equipment = [node for node in ast.walk(tree)
                     if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                     and node.name.startswith("equipment")]
        self.assertTrue(equipment, "the equipment readers must exist to be checked")
        return equipment

    def test_the_equipment_readers_contain_no_write(self):
        for node in self.statements():
            text = ast.unparse(node).upper()
            for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
                with self.subTest(function=node.name, sql=forbidden):
                    self.assertNotIn(forbidden, text)

    def test_the_equipment_statement_names_neither_table_it_must_not_write(self):
        statement = PsycopgMaterialPriceRepository._EQUIPMENT_RATES
        self.assertNotIn("provider_items", statement,
                         "an equipment rate is not a supplier listing")
        self.assertNotIn("price_observations", statement,
                         "an equipment rate is not a sheet reading")

    def test_the_service_path_writes_nothing(self):
        source = inspect.getsource(MaterialPriceService._equipment_row)
        source += inspect.getsource(MaterialPriceService._equipment_current)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "provider_items",
                          "price_observations"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)

    def test_no_migration_was_added_for_this(self):
        versions = sorted(p.name for p in
                          (BACKEND_ROOT / "alembic" / "versions").glob("00*.py"))
        # 0038 came later and is about the type vocabulary, not about rates: it widens a
        # CHECK and creates nothing. The claim this test makes still holds.
        self.assertEqual("0038", versions[-1][:4],
                         "equipment rates read existing tables; nothing was migrated")


class AuthProvider:
    def __init__(self, permissions):
        self.permissions = tuple(permissions)

    async def current(self, _request):
        return AuthContext(userId=ACTOR, organizationId=ORG, projectId=PROJECT,
                           permissionCodes=list(self.permissions),
                           organizationRole="finance_expert",
                           projectRole="finance_expert",
                           timezone="Asia/Tehran", locale="fa")


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


def client(repository):
    app = create_app()
    app.state.auth_context_provider = AuthProvider(("finance.view", "finance.edit"))
    app.state.scope_authorizer = ScopeAuthorizer()
    app.state.permission_authorizer = PermissionAuthorizer()
    app.state.material_price_service = MaterialPriceService(repository)
    return TestClient(app, raise_server_exceptions=False)


class EndpointTests(unittest.TestCase):
    """The same answers, through the router the page actually calls."""

    def test_the_category_is_published_with_an_empty_column_list(self):
        with client(three_priced()) as api:
            response = api.get(BASE + "/material-prices/categories")
        self.assertEqual(200, response.status_code, response.text)
        equipment, = [x for x in response.json()["items"]
                      if x["category"] == EQUIPMENT_CATEGORY]
        self.assertEqual("نیرو و تجهیزات", equipment["label"])
        self.assertEqual([], equipment["columns"])
        self.assertEqual([3, 3, 0], [equipment["itemCount"], equipment["activeCount"],
                                     equipment["inactiveCount"]])

    def test_current_returns_the_rates_in_the_ordinary_shape(self):
        with client(three_priced()) as api:
            response = api.get(BASE + "/material-prices/current",
                               params={"category": "work"})
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(3, body["totalItems"])
        row = body["items"][0]
        self.assertEqual("work", row["category"])
        self.assertIsNone(row["externalId"])
        self.assertIsNone(row["providerName"])
        self.assertEqual("manual", row["origin"])
        self.assertEqual({}, row["specs"])
        self.assertEqual("hour", row["sourceUnit"])

    def test_the_all_view_does_not_show_equipment(self):
        with client(three_priced()) as api:
            response = api.get(BASE + "/material-prices/current")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, response.json()["totalItems"])

    def test_reading_the_rates_still_requires_finance_view(self):
        app = create_app()
        app.state.auth_context_provider = AuthProvider(("finance.edit",))
        app.state.scope_authorizer = ScopeAuthorizer()
        app.state.permission_authorizer = PermissionAuthorizer()
        app.state.material_price_service = MaterialPriceService(three_priced())
        with TestClient(app, raise_server_exceptions=False) as api:
            response = api.get(BASE + "/material-prices/current",
                               params={"category": "equipment"})
        self.assertEqual(403, response.status_code)


if __name__ == "__main__":
    unittest.main()
