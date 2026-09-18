"""Correcting an invoice before anybody confirms it, against a real PostgreSQL.

Most of this is a claim about the DATABASE -- that replacing an invoice's lines and its
totals happens in one transaction or not at all, that a confirmed document cannot be
reached by this path, that a competing edit is refused rather than silently applied. A test
double would only prove the double was written to agree, so those cases skip, naming the
script that creates the database, when there is nothing to ask.

The disposable database is created and owned by `scripts/test_only/prepare_seq_test_db.py`
and is the same one `test_invoice_numbering` uses. Its name and host are checked after
connecting, so an environment variable cannot aim these at a database that matters.
"""

import asyncio
import os
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.repositories.invoices import PsycopgInvoiceRepository
from app.finance.schemas.invoices import InvoiceConfirm, InvoiceCreate, InvoicePatch
from app.finance.security.guards import FinanceScope
from app.finance.services.invoices import (FinanceInvoiceService, InvoiceAlreadyConfirmed,
                                           StaleInvoice)

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")

DATABASE = "bambo_invoice_seq_test"
DSN = os.environ.get("FINANCE_SEQ_DSN",
                     "postgresql://postgres@127.0.0.1:5432/" + DATABASE)
PREPARE = "python -m scripts.test_only.prepare_seq_test_db"


def disposable():
    """A synchronous connection to the disposable database, or None and why not."""
    try:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(DSN, row_factory=dict_row, connect_timeout=3,
                                     autocommit=True)
    except Exception as error:                                      # noqa: BLE001
        return None, str(error).splitlines()[0][:80]
    row = connection.execute(
        "SELECT current_database() d, host(inet_server_addr()) h").fetchone()
    if (row["d"], row["h"]) != (DATABASE, "127.0.0.1"):
        connection.close()
        return None, "refusing %s/%s: not the local disposable database" % (row["h"], row["d"])
    return connection, None


def _selector_loop():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def run(coroutine):
    return asyncio.run(coroutine, loop_factory=_selector_loop)


async def connect():
    import psycopg
    from psycopg.rows import dict_row
    # Autocommit, exactly as the development host opens its connection. Without it the
    # repositories' transaction blocks become savepoints inside one implicit transaction
    # and nothing is ever committed -- which is most of what is asked here.
    return await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row,
                                                 connect_timeout=5, autocommit=True)


class EditingTestCase(unittest.TestCase):
    """Shared gate: skip with a reason rather than fail when there is nothing to ask."""

    @classmethod
    def setUpClass(cls):
        cls.connection, cls.reason = disposable()
        if cls.connection is None:
            raise unittest.SkipTest(
                "no disposable database for invoice editing (%s). Create it with `%s`."
                % (cls.reason, PREPARE))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "connection", None) is not None:
            cls.connection.close()

    def setUp(self):
        self.project = self.fresh_project(self.id().rsplit(".", 1)[-1][:40])
        self.scope = FinanceScope(ORG, self.project, ACTOR)
        self.resource = self.general_cost()
        self.other_resource = self.general_cost()

    def fresh_project(self, name):
        """A project of this test's own, emptied first so a re-run starts from nothing."""
        project = "edit_%s" % name
        with self.connection.cursor() as cursor:
            cursor.execute("SET session_replication_role = replica")
            for table in ("invoice_lines", "invoices", "finance_audit_events",
                          "finance_resources", "finance_invoice_counters"):
                cursor.execute("DELETE FROM %s WHERE organization_id=%%s AND project_id=%%s"
                               % table, (ORG, project))
            cursor.execute("SET session_replication_role = DEFAULT")
        return project

    def general_cost(self):
        """One financial item for the invoice lines to point at."""
        resource_id = uuid4()
        self.connection.execute(
            "INSERT INTO finance_resources(id,organization_id,project_id,resource_type,"
            "code,title,base_unit,created_by) VALUES(%s,%s,%s,'general_cost',%s,%s,'unit',%s)",
            (resource_id, ORG, self.project, "GC-" + str(resource_id)[:8], "general cost",
             ACTOR))
        return resource_id

    # ------------------------------------------------------------------ small helpers

    async def _service(self, database):
        return FinanceInvoiceService(PsycopgInvoiceRepository(database))

    def with_service(self, body):
        """Run one coroutine that is handed a live service, and close the connection."""
        async def main():
            database = await connect()
            try:
                return await body(await self._service(database))
            finally:
                await database.close()
        return run(main())

    def a_draft(self, service, *, key="edit-1", amount="1000000"):
        return service.create(self.scope, InvoiceCreate(
            invoiceDate="2026-05-01", vendorName="فروشنده", idempotencyKey=key,
            lines=[{"resourceId": str(self.resource), "lineAmountIrr": amount}]))

    def stored(self, invoice_id):
        return self.connection.execute(
            "SELECT * FROM invoices WHERE id=%s", (invoice_id,)).fetchone()

    def stored_lines(self, invoice_id):
        return self.connection.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id=%s ORDER BY created_at, id",
            (invoice_id,)).fetchall()

    def audit(self, invoice_id):
        return self.connection.execute(
            "SELECT * FROM finance_audit_events WHERE entity_id=%s AND action='invoice.updated'"
            " ORDER BY occurred_at, id", (invoice_id,)).fetchall()


class DraftEditingTests(EditingTestCase):
    def test_a_field_that_is_not_sent_is_left_alone(self):
        """Absent is not null. The old patch could only set a description; this one must
        not clear a vendor because the caller did not mention it."""
        async def body(service):
            draft = await self.a_draft(service)
            return await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version, description="اصلاح‌شده"))

        after = self.with_service(body)
        self.assertEqual("اصلاح‌شده", after.description)
        self.assertEqual("فروشنده", after.vendor_name, "the vendor was never mentioned")
        self.assertEqual(date(2026, 5, 1), after.invoice_date)
        self.assertEqual(Decimal("1000000"), after.final_amount_irr)
        self.assertEqual(1, len(self.stored_lines(after.id)), "and its line is still there")

    def test_every_field_a_reader_can_see_is_wrong_is_a_field_they_can_correct(self):
        """The whole point. An extracted invoice arrives with a vendor, a date and lines
        that are usually right; correcting only the description is not correcting it."""
        async def body(service):
            draft = await self.a_draft(service)
            return await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version,
                invoiceDate="2026-05-09", vendorName="فروشندهٔ درست",
                description="از روی تصویر اصلاح شد",
                taxIrr="90000", shippingIrr="10000",
                lines=[{"resourceId": str(self.resource), "lineAmountIrr": "700000"},
                       {"resourceId": str(self.other_resource), "lineAmountIrr": "300000"}]))

        after = self.with_service(body)
        self.assertEqual(date(2026, 5, 9), after.invoice_date)
        self.assertEqual("فروشندهٔ درست", after.vendor_name)
        self.assertEqual("از روی تصویر اصلاح شد", after.description)
        self.assertEqual(Decimal("90000"), after.tax_irr)
        self.assertEqual(Decimal("10000"), after.shipping_irr)
        # 700000 + 300000 + 90000 tax + 10000 shipping
        self.assertEqual(Decimal("1100000"), after.final_amount_irr)

        row = self.stored(after.id)
        self.assertEqual(Decimal("1100000"), row["final_amount_irr"],
                         "the stored total agrees with the lines it was computed from")
        self.assertEqual(2, row["version"])

    def test_the_lines_are_replaced_entirely_rather_than_merged(self):
        """A partial list has no way to say whether a missing line was deleted or simply
        not mentioned, and the difference is money. So the list sent IS the list."""
        async def body(service):
            draft = await self.a_draft(service)
            before = self.stored_lines(draft.id)
            after = await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version,
                lines=[{"resourceId": str(self.other_resource), "lineAmountIrr": "250000"}]))
            return before, after

        before, after = self.with_service(body)
        lines = self.stored_lines(after.id)
        self.assertEqual(1, len(lines))
        self.assertEqual(self.other_resource, lines[0]["resource_id"])
        self.assertEqual(Decimal("250000"), lines[0]["final_line_amount_irr"])
        self.assertNotEqual(before[0]["id"], lines[0]["id"],
                            "the old row is gone, not edited in place")
        self.assertEqual(Decimal("250000"), self.stored(after.id)["final_amount_irr"])

    def test_an_adjustment_lands_where_the_patch_says_it_lands(self):
        """The same distribution `create` uses, reached through the same function.

        A second implementation that agreed today would eventually not, and an invoice
        whose tax was spread one way when it was created and another way when it was
        corrected is two documents wearing one number.
        """
        async def body(service):
            draft = await self.a_draft(service)
            return await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version, taxIrr="15000",
                lines=[{"resourceId": str(self.resource), "lineAmountIrr": "100000"},
                       {"resourceId": str(self.other_resource), "lineAmountIrr": "50000"}],
                directAdjustmentAllocations=[{"kind": "tax", "generalCostLineIndex": 1}]))

        after = self.with_service(body)
        # Matched by resource rather than by position. `invoice_lines` has no ordinal
        # column and `created_at` is the transaction's clock, identical for every line
        # written together -- so the read-back order is the tiebreak, a random uuid. That
        # is true of `create` as well and predates this path; it is not what is being
        # tested here, so this test does not depend on it.
        tax = {x["resource_id"]: x["allocated_tax_irr"] for x in self.stored_lines(after.id)}
        self.assertEqual(Decimal("15000"), tax[self.other_resource],
                         "all of it on the line the patch chose")
        self.assertEqual(Decimal("0"), tax[self.resource], "and none spread onto the other")
        self.assertEqual(Decimal("165000"), after.final_amount_irr)


class AwaitingConfirmationTests(EditingTestCase):
    def test_an_invoice_awaiting_confirmation_is_still_correctable(self):
        """The state in which mistakes are FOUND used to be the state in which they could
        not be fixed: the reviewer's only way forward was to discard the document."""
        async def body(service):
            draft = await self.a_draft(service)
            awaiting = await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version, status="awaitingConfirmation"))
            self.assertEqual("awaitingConfirmation", awaiting.status)
            return await service.update(self.scope, awaiting.id, InvoicePatch(
                expectedVersion=awaiting.version, vendorName="نام درست",
                lines=[{"resourceId": str(self.resource), "lineAmountIrr": "880000"}]))

        after = self.with_service(body)
        self.assertEqual("نام درست", after.vendor_name)
        self.assertEqual(Decimal("880000"), after.final_amount_irr)
        self.assertEqual("awaitingConfirmation", after.status,
                         "correcting it did not send it back to draft")
        self.assertEqual(Decimal("880000"), self.stored(after.id)["final_amount_irr"])

    def test_a_confirmed_invoice_is_not_reachable_from_here(self):
        """It has a number, it was approved, and the reports count it. Correcting it is
        void-and-reissue, which leaves both versions readable -- a different act."""
        async def body(service):
            draft = await self.a_draft(service)
            awaiting = await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version, status="awaitingConfirmation"))
            confirmed = await service.confirm(self.scope, awaiting.id, InvoiceConfirm(
                expectedVersion=awaiting.version, idempotencyKey="confirm-1"))
            with self.assertRaises(InvoiceAlreadyConfirmed) as refusal:
                await service.update(self.scope, confirmed.id, InvoicePatch(
                    expectedVersion=confirmed.version, vendorName="نباید عوض شود"))
            return confirmed, refusal.exception

        confirmed, error = self.with_service(body)
        self.assertEqual(409, error.status)
        self.assertEqual("INVOICE_ALREADY_CONFIRMED", error.code)
        self.assertEqual("فروشنده", self.stored(confirmed.id)["vendor_name"],
                         "and nothing about the confirmed document moved")


class RefusalTests(EditingTestCase):
    def test_a_stale_version_is_refused_and_writes_nothing(self):
        """Two people correcting the same extraction is the ordinary case, not the
        exotic one. The second is told to refresh, which is true and is actionable."""
        async def body(service):
            draft = await self.a_draft(service)
            await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version, description="اولی"))
            with self.assertRaises(StaleInvoice) as refusal:
                await service.update(self.scope, draft.id, InvoicePatch(
                    expectedVersion=draft.version, description="دومی",
                    lines=[{"resourceId": str(self.other_resource),
                            "lineAmountIrr": "999999"}]))
            return draft.id, refusal.exception

        invoice_id, error = self.with_service(body)
        self.assertEqual(409, error.status)
        self.assertEqual("STALE_VERSION", error.code)
        row = self.stored(invoice_id)
        self.assertEqual("اولی", row["description"], "the winner's edit stands")
        self.assertEqual(2, row["version"])
        lines = self.stored_lines(invoice_id)
        self.assertEqual(1, len(lines))
        self.assertEqual(self.resource, lines[0]["resource_id"],
                         "and the loser's lines were never written")

    def test_changing_an_amount_without_restating_the_lines_is_refused(self):
        """`directAdjustmentAllocations` is consumed at calculation time and never stored,
        so a patch that moved the tax without restating the lines would make the server
        guess the targeting from per-line amounts."""
        with self.assertRaises(ValueError) as refusal:
            InvoicePatch(expectedVersion=1, taxIrr="5000")
        self.assertIn("requires the complete lines list", str(refusal.exception))

        # And the fields that touch no number are still patchable on their own.
        patch = InvoicePatch(expectedVersion=1, vendorName="فقط نام")
        self.assertEqual("فقط نام", patch.vendor_name)
        self.assertIsNone(patch.lines)


class AuditTests(EditingTestCase):
    def test_the_audit_records_the_whole_document_before_and_after(self):
        """A reviewer asking "what did this invoice say when it was approved" is asking
        about the DOCUMENT. A row listing three changed fields can only answer that in
        combination with every earlier row, correctly replayed."""
        async def body(service):
            draft = await self.a_draft(service, amount="1000000")
            return await service.update(self.scope, draft.id, InvoicePatch(
                expectedVersion=draft.version, vendorName="فروشندهٔ درست", taxIrr="50000",
                lines=[{"resourceId": str(self.other_resource), "lineAmountIrr": "600000"}]))

        after = self.with_service(body)
        events = self.audit(after.id)
        self.assertEqual(1, len(events))
        before, now = events[0]["before_values"], events[0]["after_values"]

        self.assertEqual("فروشنده", before["vendorName"])
        self.assertEqual("فروشندهٔ درست", now["vendorName"])
        self.assertEqual("1000000", before["finalAmountIrr"])
        self.assertEqual("650000", now["finalAmountIrr"])
        self.assertEqual("0", before["taxIrr"])
        self.assertEqual("50000", now["taxIrr"])
        self.assertEqual([1, 2], [before["version"], now["version"]])

        # The lines are in it too, on both sides -- which is what makes the row answer the
        # question on its own.
        self.assertEqual([str(self.resource)],
                         [x["resourceId"] for x in before["lines"]])
        self.assertEqual([str(self.other_resource)],
                         [x["resourceId"] for x in now["lines"]])
        # 600000 raw plus the whole 50000 tax, because there is one line to spread it over.
        # The audit records the DISTRIBUTED amount, which is what the line is actually
        # worth -- the raw figure the patch sent would not reconcile to the invoice total.
        self.assertEqual("650000", now["lines"][0]["finalLineAmountIrr"])
        self.assertEqual(ACTOR, events[0]["actor_user_id"])


if __name__ == "__main__":
    unittest.main()
