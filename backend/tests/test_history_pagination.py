"""Paging the two append-only histories: `/price-history` and `/unit-conversions`.

Both tables only grow, so the failure being guarded against is not slowness. It is a
client that asks once, is answered with fifty rows, and has no way to learn that there
were four hundred. That is why `totalItems` is asserted against the filter rather than
against the page, and why the count and the page are required to share one predicate --
a count over a different WHERE would be a number that describes nothing the reader can see.

The database-backed case is the one that proves paging actually partitions the history.
It is skipped, loudly, when there is no disposable database to ask.
"""

import os
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

from app.main import create_app
from app.finance.domain.conversions import UnitConversion
from app.finance.domain.prices import PriceVersion
from app.finance.repositories.conversions import PsycopgUnitConversionRepository
from app.finance.repositories.prices import PsycopgFinancePriceRepository
from app.finance.security.context import AuthContext

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
RESOURCE = UUID("22222222-2222-4222-8222-222222222222")
PROJECT = "sample_site_01"


class Scope:
    organization_id = ORG
    project_id = PROJECT
    actor_user_id = ACTOR


class RecordingCursor:
    """Stands in for a psycopg cursor and remembers every statement it was given.

    It returns the same canned rows to any SELECT, because what is under test here is the
    SQL the repository builds, not what a database would answer to it.
    """

    def __init__(self, rows, total):
        self.rows = rows
        self.total = total
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def execute(self, sql, params=None):
        self.statements.append((sql, tuple(params or ())))

    async def fetchone(self):
        return {"total": self.total}

    async def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows=(), total=0):
        self.cursor_object = RecordingCursor(list(rows), total)

    def cursor(self, **_kwargs):
        return self.cursor_object

    @property
    def statements(self):
        return self.cursor_object.statements


class PriceHistorySqlTests(unittest.IsolatedAsyncioTestCase):
    """The SQL the price repository builds for one page of the history."""

    async def page(self, **kwargs):
        connection = RecordingConnection(rows=(), total=137)
        repository = PsycopgFinancePriceRepository(connection)
        rows, total = await repository.history_page(Scope(), kwargs.pop("page", 1),
                                                    kwargs.pop("page_size", 50), **kwargs)
        return connection.statements, rows, total

    async def test_the_count_and_the_page_ask_the_same_question(self):
        """`totalItems` must describe the set the rows were drawn from.

        If the count ran over a wider predicate than the page, a reader filtering by date
        would be told there are more pages than exist and would page into emptiness.
        """
        statements, _rows, total = await self.page(date_from=date(2026, 1, 1),
                                                   date_to=date(2026, 6, 30),
                                                   resource_id=RESOURCE)
        self.assertEqual(2, len(statements))
        counting, paging = statements
        self.assertTrue(counting[0].startswith("SELECT count(*) AS total"))
        # Same FROM, same WHERE, same bound values -- the page statement only adds the
        # ordering and the window.
        self.assertIn(counting[0][len("SELECT count(*) AS total"):], paging[0])
        self.assertEqual(counting[1], paging[1][:len(counting[1])])
        self.assertEqual(137, total)

    async def test_every_filter_is_bound_and_none_is_interpolated(self):
        statements, _rows, _total = await self.page(resource_id=RESOURCE,
                                                    date_from=date(2026, 1, 1),
                                                    date_to=date(2026, 6, 30))
        counting, _paging = statements
        self.assertIn("pv.resource_id=%s", counting[0])
        self.assertIn("pv.effective_from>=%s", counting[0])
        self.assertIn("pv.effective_from<=%s", counting[0])
        self.assertEqual((ORG, PROJECT, RESOURCE, date(2026, 1, 1), date(2026, 6, 30)),
                         counting[1])
        self.assertNotIn(str(RESOURCE), counting[0])

    async def test_an_unfiltered_page_binds_only_the_scope(self):
        """Every filter is optional, so a client that sends none must still be scoped."""
        statements, _rows, _total = await self.page()
        self.assertEqual((ORG, PROJECT), statements[0][1])

    async def test_the_window_is_the_page_the_caller_asked_for(self):
        statements, _rows, _total = await self.page(page=4, page_size=25)
        _counting, paging = statements
        self.assertIn("LIMIT %s OFFSET %s", paging[0])
        self.assertEqual((25, 75), paging[1][-2:])

    async def test_the_whole_history_and_a_page_of_it_are_ordered_identically(self):
        """One ordering, or a row can land on two pages and another on none.

        The id tiebreak is what makes the ordering total: two versions of the same price
        can share an effective date, a version number and a creation instant.
        """
        connection = RecordingConnection()
        repository = PsycopgFinancePriceRepository(connection)
        await repository.history(Scope())
        await repository.history_page(Scope(), 1, 50)
        whole, _count, paged = [statement for statement, _params in connection.statements]
        self.assertIn(PsycopgFinancePriceRepository.ORDER, whole)
        self.assertIn(PsycopgFinancePriceRepository.ORDER, paged)
        self.assertIn("pv.id DESC", PsycopgFinancePriceRepository.ORDER)

    async def test_the_page_still_hides_a_deleted_resource(self):
        """Paging must not become a way around the scoping the whole listing has."""
        statements, _rows, _total = await self.page()
        for statement, _params in statements:
            self.assertIn("r.deleted_at IS NULL", statement)


class ConversionPageSqlTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_count_and_the_page_share_one_predicate_and_one_ordering(self):
        connection = RecordingConnection(rows=(), total=8)
        repository = PsycopgUnitConversionRepository(connection)
        _rows, total = await repository.page(Scope(), 3, 2)
        counting, paging = connection.statements
        self.assertEqual(8, total)
        self.assertIn(PsycopgUnitConversionRepository.WHERE, counting[0])
        self.assertIn(PsycopgUnitConversionRepository.WHERE, paging[0])
        self.assertIn(PsycopgUnitConversionRepository.ORDER, paging[0])
        self.assertEqual((ORG, PROJECT), counting[1])
        self.assertEqual((ORG, PROJECT, 2, 4), paging[1])


#: A database this test file is allowed to read. It must be local and disposable: the
#: name is checked after connecting, so an environment variable cannot aim these tests
#: at anything else.
PAGING_DSN = os.environ.get(
    "FINANCE_PAGING_DSN",
    "postgresql://postgres@127.0.0.1:5432/bambo_invoice_seq_test")
PAGING_DATABASE = "bambo_invoice_seq_test"


def disposable_connection():
    """A connection to the local disposable database, or None and the reason why not."""
    try:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(PAGING_DSN, row_factory=dict_row, connect_timeout=3)
    except Exception as error:                                       # noqa: BLE001
        return None, str(error).splitlines()[0][:80]
    row = connection.execute(
        "SELECT current_database() d, host(inet_server_addr()) h").fetchone()
    if (row["d"], row["h"]) != (PAGING_DATABASE, "127.0.0.1"):
        connection.close()
        return None, "refusing %s/%s: not the local disposable database" % (row["h"], row["d"])
    return connection, None


class PagesPartitionTheHistoryTests(unittest.TestCase):
    """What a real database does when the pages are actually walked.

    The SQL tests above prove the statements are built correctly. This proves the thing a
    reader depends on: walking every page returns every row exactly once, in the same
    order the unpaged listing returns them. LIMIT/OFFSET only guarantees that when the
    ordering is total, which is why this is worth asking a database rather than a double.
    """

    @classmethod
    def setUpClass(cls):
        cls.connection, cls.reason = disposable_connection()
        if cls.connection is None:
            raise unittest.SkipTest(
                "no local disposable database to page against (%s). The SQL is still "
                "checked above; the partition property is not. Create it with "
                "python -m scripts.test_only.prepare_seq_test_db." % cls.reason)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "connection", None) is not None:
            cls.connection.close()

    def walk(self, table, order, size):
        """Every page of `table`, concatenated, and the whole table for comparison."""
        whole = [row["id"] for row in self.connection.execute(
            "SELECT id FROM %s ORDER BY %s" % (table, order)).fetchall()]
        walked = []
        for offset in range(0, max(len(whole), 1), size):
            walked += [row["id"] for row in self.connection.execute(
                "SELECT id FROM %s ORDER BY %s LIMIT %%s OFFSET %%s" % (table, order),
                (size, offset)).fetchall()]
        return whole, walked

    def test_walking_price_history_returns_every_version_exactly_once(self):
        whole, walked = self.walk(
            "price_versions",
            "effective_from DESC,version DESC,created_at DESC,id DESC", 3)
        self.assertEqual(whole, walked)
        self.assertEqual(len(set(walked)), len(walked), "a version was on two pages")

    def test_walking_unit_conversions_returns_every_conversion_exactly_once(self):
        whole, walked = self.walk("unit_conversions", "created_at,id", 2)
        self.assertEqual(whole, walked)
        self.assertEqual(len(set(walked)), len(walked), "a conversion was on two pages")


class AuthProvider:
    async def current(self, _request):
        return AuthContext(userId=ACTOR, organizationId=ORG, projectId=PROJECT,
                           permissionCodes=["finance.view"], organizationRole="finance_expert",
                           projectRole="finance_expert", timezone="Asia/Tehran", locale="fa")


class ScopeAuthorizer:
    async def require_organization(self, _context, organization_id):
        if organization_id != str(ORG):
            raise HTTPException(403, "organization denied")

    async def require_project(self, _context, organization_id, project_id):
        if project_id != PROJECT:
            raise HTTPException(403, "project denied")


class PermissionAuthorizer:
    async def require(self, context, permission_code):
        if permission_code not in context.permission_codes:
            raise HTTPException(403, "permission denied")


def a_price(index):
    return PriceVersion(UUID(int=index), ORG, PROJECT, RESOURCE, "project", index,
                        Decimal("100"), date(2026, 1, 1), "r", ACTOR,
                        datetime(2026, 1, 1, tzinfo=timezone.utc))


def a_conversion(index):
    return UnitConversion(UUID(int=index), ORG, PROJECT, "project", index, "kg", "ton",
                          "mass", Decimal("0.001"), date(2026, 1, 1), "r", ACTOR,
                          datetime(2026, 1, 1, tzinfo=timezone.utc))


class PriceService:
    def __init__(self):
        self.asked = []

    async def history_page(self, _scope, page, page_size, resource_id=None,
                           date_from=None, date_to=None):
        self.asked.append((page, page_size, resource_id, date_from, date_to))
        return [a_price(1), a_price(2)], 137


class ConversionService:
    def __init__(self):
        self.asked = []

    async def page(self, _scope, page, page_size):
        self.asked.append((page, page_size))
        return [a_conversion(1)], 3


def client():
    app = create_app()
    app.state.auth_context_provider = AuthProvider()
    app.state.scope_authorizer = ScopeAuthorizer()
    app.state.permission_authorizer = PermissionAuthorizer()
    app.state.finance_price_service = PriceService()
    app.state.unit_conversion_service = ConversionService()
    return TestClient(app), app


class PagedEnvelopeApiTests(unittest.TestCase):
    """What the two endpoints answer, in the shape the invoice listing already uses."""

    BASE = "/api/projects/%s/finance" % PROJECT

    def test_the_price_history_answers_the_invoice_listing_envelope(self):
        api, _app = client()
        with api:
            payload = api.get("%s/price-history" % self.BASE).json()
        self.assertEqual({"items", "page", "pageSize", "totalItems", "totalPages"},
                         set(payload))
        self.assertEqual((1, 50, 137, 3), (payload["page"], payload["pageSize"],
                                           payload["totalItems"], payload["totalPages"]))
        self.assertEqual(2, len(payload["items"]))

    def test_a_request_with_no_parameters_at_all_still_succeeds(self):
        """The parameters are optional so today's clients keep working.

        What does change for them is the body: it is an object now, not an array. That is
        the point of the change and it is recorded in the handover, but a client sending
        no parameters is not refused.
        """
        api, app = client()
        with api:
            response = api.get("%s/unit-conversions" % self.BASE)
        self.assertEqual(200, response.status_code)
        self.assertEqual([(1, 50)], app.state.unit_conversion_service.asked)
        self.assertEqual({"items", "page", "pageSize", "totalItems", "totalPages"},
                         set(response.json()))

    def test_the_filters_reach_the_service_under_the_names_the_host_asked_for(self):
        api, app = client()
        with api:
            api.get("%s/price-history?page=2&pageSize=10&from=2026-01-01&to=2026-06-30"
                    "&resourceId=%s" % (self.BASE, RESOURCE))
        self.assertEqual([(2, 10, RESOURCE, date(2026, 1, 1), date(2026, 6, 30))],
                         app.state.finance_price_service.asked)

    def test_a_page_larger_than_the_ceiling_is_refused(self):
        """200 is the ceiling `/invoices` already has; a client cannot ask for the table."""
        api, _app = client()
        with api:
            for endpoint in ("price-history", "unit-conversions"):
                with self.subTest(endpoint=endpoint):
                    self.assertEqual(422, api.get("%s/%s?pageSize=201"
                                                  % (self.BASE, endpoint)).status_code)
                    self.assertEqual(422, api.get("%s/%s?page=0"
                                                  % (self.BASE, endpoint)).status_code)

    def test_the_total_is_the_filter_total_and_not_the_page_length(self):
        """Two rows on the page, a hundred and thirty-seven in the history."""
        api, _app = client()
        with api:
            payload = api.get("%s/price-history?pageSize=2" % self.BASE).json()
        self.assertEqual(2, len(payload["items"]))
        self.assertEqual(137, payload["totalItems"])
        self.assertEqual(69, payload["totalPages"])


if __name__ == "__main__":
    unittest.main()
