"""Exercise the repository queries added by the contract audit.

No PostgreSQL runs in this suite, so these drive the real repository methods through a
fake connection. That cannot prove the SQL is valid Postgres, but it does pin the parts
that silently break: parameter count and order, the shared WHERE clause between the count
and the page, tenant scoping, and the UTC day boundaries of the audit date filter.
"""

import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from psycopg import errors

from app.finance.domain.attachments import DuplicateAttachment
from app.finance.repositories.attachments import PsycopgAttachmentRepository
from app.finance.repositories.audit import PsycopgFinanceAuditRepository
from app.finance.repositories.progress import PsycopgProgressRepository
from app.finance.repositories.reports import PsycopgLiveReportRepository
from app.finance.repositories.settings import PsycopgFinanceSettingsRepository

ORG = UUID("11111111-1111-4111-8111-111111111111")
LINE = UUID("33333333-3333-4333-8333-333333333333")
SCOPE = SimpleNamespace(organization_id=ORG, project_id="sample_site_01")
NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


class Context:
    def __init__(self, owner): self.owner = owner
    async def __aenter__(self): return self.owner
    async def __aexit__(self, *_): return False


class Cursor:
    def __init__(self, results):
        self.results = list(results)
        self.executions = []

    async def execute(self, query, parameters=()):
        self.executions.append((" ".join(query.split()), tuple(parameters)))

    async def fetchone(self): return self.results.pop(0)
    async def fetchall(self): return self.results.pop(0)


class Connection:
    def __init__(self, results): self.cursor_instance = Cursor(results)
    def cursor(self, **_): return Context(self.cursor_instance)


class AuditQueryTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, **filters):
        connection = Connection([{"total": 3}, [{"id": UUID(int=1)}]])
        rows, total = await PsycopgFinanceAuditRepository(connection).list(SCOPE, **filters)
        return connection.cursor_instance.executions, rows, total

    async def test_count_and_page_share_one_where_clause_and_its_values(self):
        executions, rows, total = await self._run(limit=25, offset=50, action="invoice.confirmed")
        (count_sql, count_values), (page_sql, page_values) = executions
        self.assertEqual(3, total)
        self.assertEqual([{"id": UUID(int=1)}], rows)
        # A count that filtered differently from the page would report a total the page cannot reach.
        where = count_sql.split("WHERE", 1)[1]
        self.assertIn(where, page_sql)
        self.assertEqual(count_values, page_values[: len(count_values)])
        self.assertEqual((25, 50), page_values[-2:])

    async def test_every_filter_binds_exactly_one_placeholder_in_order(self):
        executions, _rows, _total = await self._run(
            action="invoice.confirmed", entity_type="invoices",
            occurred_from=date(2026, 4, 1), occurred_to=date(2026, 5, 1), query="اصلاح")
        count_sql, count_values = executions[0]
        self.assertEqual(count_sql.count("%s"), len(count_values))
        self.assertEqual(
            (ORG, "sample_site_01", "invoice.confirmed", "invoices",
             date(2026, 4, 1), date(2026, 5, 1), "%اصلاح%", "%اصلاح%", "%اصلاح%"),
            count_values)

    async def test_unfiltered_read_is_still_scoped_to_both_tenant_keys(self):
        executions, _rows, _total = await self._run()
        count_sql, count_values = executions[0]
        self.assertIn("WHERE organization_id=%s AND project_id=%s", count_sql)
        self.assertEqual((ORG, "sample_site_01"), count_values)

    async def test_date_filter_covers_whole_utc_days_at_both_ends(self):
        executions, _rows, _total = await self._run(
            occurred_from=date(2026, 4, 1), occurred_to=date(2026, 5, 1))
        count_sql, _values = executions[0]
        # The client filters on the UTC calendar day and includes both ends, so the upper
        # bound must reach the end of occurredTo rather than stopping at its midnight.
        self.assertIn("occurred_at>=(%s::date)::timestamp AT TIME ZONE 'UTC'", count_sql)
        self.assertIn("occurred_at<(%s::date + 1)::timestamp AT TIME ZONE 'UTC'", count_sql)

    async def test_search_term_is_bound_never_interpolated(self):
        executions, _rows, _total = await self._run(query="'; DROP TABLE finance_audit_events;--")
        count_sql, count_values = executions[0]
        self.assertNotIn("DROP TABLE", count_sql)
        self.assertIn("%'; DROP TABLE finance_audit_events;--%", count_values)


class ReportSnapshotListQueryTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, **filters):
        connection = Connection([{"total": 4}, [{"report_snapshot_id": UUID(int=1)}]])
        rows, total = await PsycopgLiveReportRepository(connection).list(SCOPE, **filters)
        return connection.cursor_instance.executions, rows, total

    async def test_count_and_page_share_one_where_clause_and_its_values(self):
        executions, rows, total = await self._run(limit=25, offset=50,
            reporting_date_from=date(2026, 4, 1), reporting_date_to=date(2026, 5, 1))
        (count_sql, count_values), (page_sql, page_values) = executions
        # A count that filtered differently from the page would report a total the page
        # cannot reach, which is exactly what filtering in Python after the fact produces.
        self.assertEqual(4, total)
        where = count_sql.split("WHERE", 1)[1]
        self.assertIn(where, page_sql)
        self.assertEqual(count_values, page_values[: len(count_values)])
        self.assertEqual((25, 50), page_values[-2:])

    async def test_both_ends_of_the_range_are_inclusive_and_bound(self):
        executions, _rows, _total = await self._run(
            reporting_date_from=date(2026, 4, 1), reporting_date_to=date(2026, 5, 1))
        count_sql, count_values = executions[0]
        self.assertIn("reporting_date>=%s", count_sql)
        self.assertIn("reporting_date<=%s", count_sql)
        self.assertEqual(count_sql.count("%s"), len(count_values))
        self.assertEqual((ORG, "sample_site_01", date(2026, 4, 1), date(2026, 5, 1)), count_values)

    async def test_an_unfiltered_read_is_still_scoped_to_both_tenant_keys(self):
        executions, _rows, _total = await self._run()
        count_sql, count_values = executions[0]
        self.assertIn("WHERE organization_id=%s AND project_id=%s", count_sql)
        self.assertEqual((ORG, "sample_site_01"), count_values)

    async def test_the_listing_counts_the_pinned_arrays_instead_of_sending_them(self):
        executions, _rows, _total = await self._run()
        page_sql = executions[1][0]
        self.assertIn("jsonb_array_length(invoice_ids) invoice_count", page_sql)
        self.assertIn("jsonb_array_length(price_version_ids) price_version_count", page_sql)
        # Those arrays grow with the project, so a listing must never carry them.
        for column in ("resource_version_ids", "estimate_revision_ids",
                       "unit_conversion_ids", "calculated_metrics", "snapshot_payload"):
            self.assertNotIn(column, page_sql)
        self.assertIn("ORDER BY reporting_date DESC,issued_at DESC,id DESC", page_sql)


class InvoiceDateFilterQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_range_filters_on_invoice_date_and_binds_both_ends(self):
        from app.finance.repositories.invoices import PsycopgInvoiceRepository

        connection = Connection([{"total_count": 2}, [], []])
        await PsycopgInvoiceRepository(connection).list(
            SCOPE, page=1, page_size=50,
            invoice_date_from=date(2026, 7, 1), invoice_date_to=date(2026, 7, 31))
        count_sql, count_values = connection.cursor_instance.executions[0]
        self.assertIn("invoice_date>=%s", count_sql)
        self.assertIn("invoice_date<=%s", count_sql)
        # The reporting engine filters on invoice_date, so the listing has to agree with
        # it; confirmed_at would give "the invoices of this period" a different meaning
        # from "the cost of this period".
        self.assertNotIn("confirmed_at", count_sql)
        self.assertEqual((ORG, "sample_site_01", date(2026, 7, 1), date(2026, 7, 31)), count_values)

    async def test_the_range_is_optional_and_leaves_the_query_untouched(self):
        from app.finance.repositories.invoices import PsycopgInvoiceRepository

        connection = Connection([{"total_count": 0}, [], []])
        await PsycopgInvoiceRepository(connection).list(SCOPE, page=1, page_size=50)
        count_sql, count_values = connection.cursor_instance.executions[0]
        self.assertNotIn("invoice_date>=", count_sql)
        self.assertEqual((ORG, "sample_site_01"), count_values)


class SettingsRevisionQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_revisions_are_read_newest_first_within_both_tenant_keys(self):
        row = {"id": UUID(int=2), "organization_id": ORG, "project_id": "sample_site_01",
               "gross_built_area": Decimal("4250.0000"), "currency": "IRR", "revision": 2,
               "effective_from": date(2026, 8, 2), "reason": "بازنگری",
               "created_by": UUID(int=3), "created_at": NOW}
        connection = Connection([[row]])
        result = await PsycopgFinanceSettingsRepository(connection).list_revisions(SCOPE)
        sql, values = connection.cursor_instance.executions[0]
        self.assertEqual((ORG, "sample_site_01"), values)
        self.assertIn("WHERE organization_id = %s AND project_id = %s", sql)
        self.assertIn("ORDER BY revision DESC", sql)
        self.assertNotIn("LIMIT", sql)
        self.assertEqual((2, Decimal("4250.0000")), (result[0].revision, result[0].gross_built_area))


class OverrideHistoryQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_joins_the_snapshot_ref_and_stays_scoped_to_the_line(self):
        connection = Connection([[{"id": UUID(int=6)}]])
        rows = await PsycopgProgressRepository(connection).list_overrides(SCOPE, LINE)
        sql, values = connection.cursor_instance.executions[0]
        self.assertEqual((ORG, "sample_site_01", LINE), values)
        self.assertEqual([{"id": UUID(int=6)}], rows)
        # The stored column is the internal ref id; the response must carry the public
        # progress_snapshot_id, which only the join can supply.
        self.assertIn("JOIN progress_snapshot_refs", sql)
        self.assertIn("r.progress_snapshot_id", sql)
        self.assertIn("o.organization_id=%s AND o.project_id=%s AND o.estimate_line_id=%s", sql)
        self.assertIn("ORDER BY o.created_at DESC,o.id DESC", sql)


class RaisingCursor(Cursor):
    async def execute(self, query, parameters=()):
        await super().execute(query, parameters)
        raise errors.UniqueViolation("duplicate key value violates unique constraint")


class RaisingConnection(Connection):
    def __init__(self): self.cursor_instance = RaisingCursor([])


class AttachmentDuplicateTests(unittest.IsolatedAsyncioTestCase):
    """The service checks the digest first, but two concurrent uploads both pass it.

    UNIQUE (organization_id, project_id, sha256) is what actually settles the race, and
    the loser must come back as the domain error rather than psycopg's UniqueViolation.
    """

    async def test_unique_violation_becomes_the_domain_duplicate_error(self):
        value = SimpleNamespace(
            file_id=UUID(int=7), invoice_id=None, logical_type="invoice_image",
            original_name_safe="bill.png", stored_name="stored.png", mime_type="image/png",
            size_bytes=12, sha256="a" * 64, storage_key="k", uploaded_by=UUID(int=9), uploaded_at=NOW)
        with self.assertRaises(DuplicateAttachment) as caught:
            await PsycopgAttachmentRepository(RaisingConnection()).create(SCOPE, value)
        # The frontend keys its message off this code; 409 keeps it out of the 500 path.
        self.assertEqual(("DUPLICATE_IMPORT_FILE", 409), (caught.exception.code, caught.exception.status))
        self.assertIsInstance(caught.exception.__cause__, errors.UniqueViolation)


if __name__ == "__main__":
    unittest.main()
