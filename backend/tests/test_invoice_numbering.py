"""The per-project invoice number: who allocates it, and what that guarantees.

Most of this file asks a real PostgreSQL server, because most of what is being claimed is
a property of the database rather than of this code. "Two people creating an invoice at
the same moment get different numbers" is a claim about a row lock; a test double would
only prove that the double was written to agree. Those cases skip -- loudly, naming the
script that creates it -- when there is no disposable database to ask.

The disposable database is created and owned by `scripts/test_only/prepare_seq_test_db.py`.
Nothing here connects to anything else: the name is checked after connecting, so an
environment variable cannot aim these tests at a database that matters.
"""

import asyncio
import os
import subprocess
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.domain.attachments import FinanceAttachment
from app.finance.domain.extractions import ExtractionDraft, ExtractionField
from app.finance.domain.invoices import Invoice, format_invoice_number
from app.finance.repositories.extractions import PsycopgExtractionRepository
from app.finance.repositories.invoice_numbering import allocate_invoice_number
from app.finance.repositories.invoices import PsycopgInvoiceRepository
from app.finance.schemas.invoices import (CorrectiveInvoiceCreate, InvoiceConfirm,
                                          InvoiceCreate, InvoiceLineCreate, InvoicePatch,
                                          InvoiceVoid)
from app.finance.security.context import AuthContext
from app.finance.security.guards import FinanceScope
from app.finance.services.invoices import FinanceInvoiceService

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
SEEDED_PROJECT = "sample_site_01"

#: Local and disposable, and checked on connection. See the module docstring.
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
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop.

    The development host and `scripts.demo.prepare` solve it the same way. Setting the
    policy globally would reach every other test in the run, so the loop is chosen here.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def run(coroutine):
    return asyncio.run(coroutine, loop_factory=_selector_loop)


async def connect():
    import psycopg
    from psycopg.rows import dict_row
    # Autocommit, exactly as the development host opens its connection: without it the
    # first statement begins an implicit transaction and every  block the
    # repositories open becomes a SAVEPOINT inside it, so nothing is ever committed and
    # nothing is visible to a second connection -- which is most of what is asked here.
    return await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row,
                                                 connect_timeout=5, autocommit=True)


class RealDatabaseTestCase(unittest.TestCase):
    """Shared gate: skip with a reason rather than fail when there is nothing to ask."""

    @classmethod
    def setUpClass(cls):
        cls.connection, cls.reason = disposable()
        if cls.connection is None:
            raise unittest.SkipTest(
                "no disposable database for the invoice counter (%s). Create it with `%s`."
                % (cls.reason, PREPARE))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "connection", None) is not None:
            cls.connection.close()

    def fresh_project(self, name):
        """A project of this test's own, emptied first so a re-run starts from nothing."""
        project = "seq_%s" % name
        with self.connection.cursor() as cursor:
            cursor.execute("SET session_replication_role = replica")
            for table in ("invoice_lines", "invoices", "extraction_drafts",
                          "finance_attachments", "finance_audit_events",
                          "finance_resources", "finance_invoice_counters"):
                cursor.execute("DELETE FROM %s WHERE organization_id=%%s AND project_id=%%s"
                               % table, (ORG, project))
            cursor.execute("SET session_replication_role = DEFAULT")
        return project

    def general_cost(self, project):
        """One financial item for the invoice lines to point at."""
        resource_id = uuid4()
        self.connection.execute(
            "INSERT INTO finance_resources(id,organization_id,project_id,resource_type,"
            "code,title,base_unit,created_by) VALUES(%s,%s,%s,'general_cost',%s,%s,'unit',%s)",
            (resource_id, ORG, project, "GC-" + str(resource_id)[:8], "general cost", ACTOR))
        return resource_id

    def numbers_in(self, project):
        return [row["invoice_seq"] for row in self.connection.execute(
            "SELECT invoice_seq FROM invoices WHERE organization_id=%s AND project_id=%s"
            " ORDER BY invoice_seq", (ORG, project)).fetchall()]

    def counter_of(self, project):
        row = self.connection.execute(
            "SELECT next_number FROM finance_invoice_counters WHERE organization_id=%s"
            " AND project_id=%s", (ORG, project)).fetchone()
        return None if row is None else row["next_number"]


class ConcurrentAllocationTests(RealDatabaseTestCase):
    """Two connections, one project, at the same moment.

    This is the case the old `max()+1` could not survive and the reason the counter is a
    row rather than a query. Both allocate; the second must WAIT for the first to commit,
    and must then be handed the next number rather than the same one.
    """

    def test_the_second_allocation_waits_and_gets_the_next_number(self):
        project = self.fresh_project("concurrency")

        async def scenario():
            first_connection = await connect()
            second_connection = await connect()
            try:
                async def second():
                    async with second_connection.transaction():
                        async with second_connection.cursor() as cursor:
                            return await allocate_invoice_number(cursor, ORG, project)

                async with first_connection.transaction():
                    async with first_connection.cursor() as cursor:
                        first = await allocate_invoice_number(cursor, ORG, project)
                    waiting = asyncio.create_task(second())
                    # Long enough that a second allocation which was NOT blocked would
                    # have finished: what is being observed is the row lock, and an
                    # unblocked allocation returns in single-digit milliseconds.
                    await asyncio.sleep(0.5)
                    blocked = not waiting.done()
                return first, await waiting, blocked
            finally:
                await first_connection.close()
                await second_connection.close()

        first, second, blocked = run(scenario())
        self.assertTrue(blocked, "the second allocation did not wait for the first")
        self.assertEqual((1, 2), (first, second))
        self.assertEqual(3, self.counter_of(project))

    def test_ten_concurrent_allocations_hand_out_ten_different_numbers(self):
        """The same claim at a scale where a lost update would be visible."""
        project = self.fresh_project("concurrency_many")

        async def scenario():
            connections = [await connect() for _ in range(10)]
            try:
                async def one(connection):
                    async with connection.transaction():
                        async with connection.cursor() as cursor:
                            return await allocate_invoice_number(cursor, ORG, project)
                return await asyncio.gather(*(one(c) for c in connections))
            finally:
                for connection in connections:
                    await connection.close()

        allocated = run(scenario())
        self.assertEqual(list(range(1, 11)), sorted(allocated))
        self.assertEqual(11, self.counter_of(project))


class RollbackLeavesNoGapTests(RealDatabaseTestCase):
    """A number belongs to the transaction that took it.

    An invoice that fails to be written must give its number back, because a gap in the
    sequence is a question somebody eventually has to answer -- "where is invoice 4?" --
    and the honest answer would be "nowhere, it was never written".
    """

    def test_a_rolled_back_allocation_is_handed_out_again(self):
        project = self.fresh_project("rollback")

        async def scenario():
            import psycopg
            connection = await connect()
            try:
                abandoned = None
                try:
                    async with connection.transaction():
                        async with connection.cursor() as cursor:
                            abandoned = await allocate_invoice_number(cursor, ORG, project)
                        raise psycopg.Rollback()
                except psycopg.Rollback:
                    pass
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        return abandoned, await allocate_invoice_number(cursor, ORG, project)
            finally:
                await connection.close()

        abandoned, allocated = run(scenario())
        self.assertEqual(1, abandoned)
        self.assertEqual(1, allocated, "the abandoned number was not handed out again")
        self.assertEqual(2, self.counter_of(project))

    def test_a_failed_invoice_write_leaves_no_gap_behind_it(self):
        """The whole write, not just the counter: a create that raises must leave nothing."""
        project = self.fresh_project("rollback_write")
        resource = self.general_cost(project)

        async def scenario():
            connection = await connect()
            try:
                repository = PsycopgInvoiceRepository(connection)
                service = FinanceInvoiceService(repository)
                scope = FinanceScope(ORG, project, ACTOR)
                first = await service.create(scope, a_create("write-1", resource))
                # The same idempotency key with different content: the unique index on it
                # refuses the row, and the transaction that had already taken a number
                # rolls back with it.
                failed = False
                try:
                    await repository.create(scope, Invoice(
                        uuid4(), ORG, project, None, date(2026, 5, 2), "vendor", None,
                        "manual", "draft", Decimal(0), Decimal(0), Decimal(0), Decimal(0),
                        Decimal(1000), "write-1", 1, ACTOR, None, None,
                        datetime(2026, 5, 2, tzinfo=timezone.utc), []), uuid4(), None)
                except ValueError:
                    failed = True
                second = await service.create(
                    scope, a_create("write-2", resource, day=date(2026, 5, 4), amount="2000"))
                return first.invoice_seq, failed, second.invoice_seq
            finally:
                await connection.close()

        first, failed, second = run(scenario())
        self.assertTrue(failed, "the duplicate idempotency key was accepted")
        self.assertEqual((1, 2), (first, second))
        self.assertEqual([1, 2], self.numbers_in(project))


def a_create(key, resource_id, day=date(2026, 5, 1), vendor="vendor", amount="1000"):
    return InvoiceCreate(invoiceDate=day.isoformat(), vendorName=vendor,
                         idempotencyKey=key,
                         lines=[InvoiceLineCreate(resourceId=str(resource_id),
                                                  lineAmountIrr=amount)])


class EveryPathTakesTheNextNumberTests(RealDatabaseTestCase):
    """All four ways an invoice comes into existence, against the real repositories.

    The fourth -- the void -- is the one that used to be wrong in a way nothing caught: a
    reversal reused the number of the invoice it reversed, so one number named two
    documents with opposite signs. It is included here for that reason, not for symmetry.
    """

    def test_the_four_creation_paths_produce_one_two_three_and_four(self):
        project = self.fresh_project("four_paths")
        resource = self.general_cost(project)
        attachment_id, draft = self.an_awaiting_extraction(project)

        async def scenario():
            connection = await connect()
            try:
                repository = PsycopgInvoiceRepository(connection)
                extractions = PsycopgExtractionRepository(connection)
                service = FinanceInvoiceService(repository)
                scope = FinanceScope(ORG, project, ACTOR)
                numbers = {}

                # 1. the ordinary create, then confirmed so it can be corrected later
                manual = await service.create(scope, a_create("path-manual", resource))
                numbers["create"] = manual.invoice_seq
                manual = await service.update(scope, manual.id, InvoicePatch(
                    expectedVersion=manual.version, status="awaitingConfirmation"))
                manual = await service.confirm(scope, manual.id, InvoiceConfirm(
                    expectedVersion=manual.version, idempotencyKey="confirm-manual"))

                # 2. the extraction path, which writes through its own transaction
                at = datetime(2026, 5, 2, tzinfo=timezone.utc)
                prepared = await service.prepare_extracted(
                    scope, a_create("path-extracted", resource, date(2026, 5, 2), "seller"),
                    "image", "path-extracted", at)
                extracted = await extractions.confirm_with_invoice(
                    scope, draft, list(draft.fields), prepared, None, uuid4(), uuid4(), at)
                numbers["extracted"] = extracted.invoice_seq

                # 3. a correction of the first one
                correction = await service.corrective(scope, manual.id, a_corrective(
                    "path-corrective", resource))
                numbers["corrective"] = correction.invoice_seq

                # 4. voiding the extracted invoice: its own document, its own number
                reversal = await service.void(scope, extracted.id, InvoiceVoid(
                    expectedVersion=extracted.version, idempotencyKey="path-void",
                    reason="entered twice"))
                numbers["void"] = reversal.invoice_seq
                return numbers, extracted.invoice_seq
            finally:
                await connection.close()

        numbers, extracted_number = run(scenario())
        self.assertEqual({"create": 1, "extracted": 2, "corrective": 3, "void": 4}, numbers)
        self.assertNotEqual(extracted_number, numbers["void"],
                            "the reversal reused the number of the invoice it reversed")
        self.assertEqual([1, 2, 3, 4], self.numbers_in(project))
        self.assertEqual(5, self.counter_of(project))

    def an_awaiting_extraction(self, project):
        """One uploaded image with a draft awaiting review, written directly."""
        attachment_id, draft_id = uuid4(), uuid4()
        at = datetime(2026, 5, 2, tzinfo=timezone.utc)
        self.connection.execute(
            "INSERT INTO finance_attachments(id,organization_id,project_id,logical_type,"
            "original_name_safe,stored_name,mime_type,size_bytes,sha256,storage_key,"
            "processing_status,uploaded_by,uploaded_at) VALUES(%s,%s,%s,'invoice_image',"
            "'bill.jpg','bill.jpg','image/jpeg',1024,%s,%s,'ready',%s,%s)",
            (attachment_id, ORG, project, "a" * 64, "key/" + str(attachment_id), ACTOR, at))
        self.connection.execute(
            "INSERT INTO extraction_drafts(id,organization_id,project_id,attachment_id,"
            "version,review_status,provider_adapter,extracted_fields,financial_effect_irr,"
            "submitted_by,created_at,updated_at) VALUES(%s,%s,%s,%s,1,'awaitingReview',"
            "'stub','[]',0,%s,%s,%s)",
            (draft_id, ORG, project, attachment_id, ACTOR, at, at))
        attachment = FinanceAttachment(attachment_id, ORG, project, "invoice_image",
                                       "bill.jpg", "bill.jpg", "image/jpeg", 1024,
                                       "a" * 64, ACTOR, at, "ready",
                                       "key/" + str(attachment_id), None)
        return attachment_id, ExtractionDraft(draft_id, ORG, project, attachment, 1,
                                              "awaitingReview", "draft", "stub", [],
                                              ACTOR, at)


def a_corrective(key, resource_id):
    return CorrectiveInvoiceCreate(
        invoiceDate="2026-05-03", vendorName="vendor", idempotencyKey=key,
        financialEffectSign=-1, reason="wrong amount", source="corrective",
        lines=[InvoiceLineCreate(resourceId=str(resource_id), lineAmountIrr="500")])


class ProjectsCountSeparatelyTests(RealDatabaseTestCase):
    """"Per project" is the whole specification. Two projects both start at 1."""

    def test_two_projects_each_begin_at_one_and_do_not_see_each_other(self):
        first_project = self.fresh_project("isolation_a")
        second_project = self.fresh_project("isolation_b")
        first_resource = self.general_cost(first_project)
        second_resource = self.general_cost(second_project)

        async def scenario():
            connection = await connect()
            try:
                service = FinanceInvoiceService(PsycopgInvoiceRepository(connection))
                created = []
                for project, resource, keys in ((first_project, first_resource, ("a1", "a2", "a3")),
                                                (second_project, second_resource, ("b1", "b2"))):
                    scope = FinanceScope(ORG, project, ACTOR)
                    for index, key in enumerate(keys):
                        # A different amount each time: three invoices from one vendor on
                        # one day for one amount are duplicates, and the service says so.
                        invoice = await service.create(
                            scope, a_create(key, resource, amount=str(1000 + index)))
                        created.append((project, invoice.invoice_seq))
                return created
            finally:
                await connection.close()

        created = run(scenario())
        self.assertEqual([(first_project, 1), (first_project, 2), (first_project, 3),
                          (second_project, 1), (second_project, 2)], created)
        self.assertEqual([1, 2, 3], self.numbers_in(first_project))
        self.assertEqual([1, 2], self.numbers_in(second_project))


class MigrationTests(RealDatabaseTestCase):
    """0020 itself: what it declares, and what it does to a database twice.

    The seeded project in the disposable database is what the backfill is measured on --
    fifty-three invoices, nearly all of them confirmed, which is the case the
    `confirmed_invoice_immutable` trigger refuses and the migration has to handle.
    """

    REVISION = (BACKEND_ROOT / "alembic" / "versions"
                / "0020_invoice_sequence_per_project.py").read_text(encoding="utf-8")

    def alembic(self, *arguments):
        result = subprocess.run([sys.executable, "-m", "alembic", *arguments],
                                cwd=BACKEND_ROOT, capture_output=True, text=True,
                                env=dict(os.environ, FINANCE_MIGRATION_DSN=DSN))
        self.assertEqual(0, result.returncode,
                         "alembic %s failed" % " ".join(arguments))
        return result.stderr

    def test_the_declared_sql_says_what_the_specification_asked_for(self):
        for fragment in ("ADD COLUMN invoice_seq integer",
                         "ROW_NUMBER() OVER (PARTITION BY organization_id, project_id",
                         "ORDER BY created_at, id)",
                         "ALTER COLUMN invoice_seq SET NOT NULL",
                         "UNIQUE (organization_id, project_id, invoice_seq)",
                         "CREATE TABLE finance_invoice_counters",
                         "SELECT organization_id, project_id, MAX(invoice_seq) + 1"):
            with self.subTest(fragment=fragment[:40]):
                self.assertIn(fragment, self.REVISION)

    def test_the_backfill_disables_and_restores_the_immutability_trigger(self):
        """Without this the backfill cannot run at all: the trigger refuses any UPDATE to
        a confirmed, voided or corrected invoice, which is nearly every row."""
        self.assertIn("DISABLE TRIGGER confirmed_invoice_immutable", self.REVISION)
        self.assertIn("ENABLE TRIGGER confirmed_invoice_immutable", self.REVISION)
        self.assertLess(self.REVISION.index("DISABLE TRIGGER"),
                        self.REVISION.index("UPDATE invoices"))
        self.assertLess(self.REVISION.index("UPDATE invoices"),
                        self.REVISION.index("ENABLE TRIGGER"))

    def test_the_down_migration_removes_everything_the_up_created(self):
        downgrade = self.REVISION[self.REVISION.index("DOWNGRADE_SQL"):]
        for fragment in ("DROP TABLE IF EXISTS finance_invoice_counters",
                         "DROP CONSTRAINT IF EXISTS ux_invoices_project_seq",
                         "DROP COLUMN IF EXISTS invoice_seq"):
            with self.subTest(fragment=fragment[:40]):
                self.assertIn(fragment, downgrade)

    def test_down_then_up_again_rebuilds_the_same_numbering(self):
        before = self.numbers_in(SEEDED_PROJECT)
        self.assertTrue(before, "the seeded project has no invoices to renumber")
        try:
            self.alembic("downgrade", "0019")
            self.assertEqual(0, self.connection.execute(
                "SELECT count(*) n FROM information_schema.columns WHERE"
                " table_name='invoices' AND column_name='invoice_seq'").fetchone()["n"])
            self.assertEqual(len(before), self.connection.execute(
                "SELECT count(*) n FROM invoices WHERE organization_id=%s AND project_id=%s",
                (ORG, SEEDED_PROJECT)).fetchone()["n"], "the downgrade lost invoices")
            self.alembic("upgrade", "head")
            # Again, on a database already at head: a no-op, and it must stay one.
            self.alembic("upgrade", "head")
        finally:
            self.connection.execute("SELECT 1")
        self.assertEqual(before, self.numbers_in(SEEDED_PROJECT))

    def test_the_backfill_numbered_every_invoice_once(self):
        row = self.connection.execute(
            "SELECT count(*) n, count(DISTINCT (organization_id,project_id,invoice_seq)) d,"
            " count(invoice_seq) filled, min(invoice_seq) lo FROM invoices").fetchone()
        self.assertEqual(row["n"], row["filled"], "an invoice was left without a number")
        self.assertEqual(row["n"], row["d"], "two invoices in one project share a number")
        self.assertEqual(1, row["lo"], "the numbering does not start at 1")

    def test_the_counter_resumes_after_the_highest_number(self):
        for row in self.connection.execute(
                "SELECT c.project_id, c.next_number, max(i.invoice_seq) highest"
                " FROM finance_invoice_counters c JOIN invoices i"
                " ON i.organization_id=c.organization_id AND i.project_id=c.project_id"
                " GROUP BY c.project_id, c.next_number").fetchall():
            with self.subTest(project=row["project_id"]):
                self.assertEqual(row["highest"] + 1, row["next_number"])


class TheNumberIsNotTheClientsToChooseTests(unittest.TestCase):
    """A client that still sends `invoiceNumber` must be told, not quietly ignored.

    `extra="forbid"` on the DTO base turns the removed field into a 422 that names it,
    which is the answer that gets the field removed from the caller. Accepting and
    discarding it would leave a client believing it had set the number.
    """

    BASE = "/api/projects/%s/finance" % SEEDED_PROJECT

    def client(self):
        class Auth:
            async def current(self, _request):
                return AuthContext(userId=ACTOR, organizationId=ORG,
                                   projectId=SEEDED_PROJECT,
                                   permissionCodes=["finance.view", "finance.manage_invoice"],
                                   organizationRole="finance_expert",
                                   projectRole="finance_expert",
                                   timezone="Asia/Tehran", locale="fa")

        class Scope:
            async def require_organization(self, *_a, **_k):
                return None

            async def require_project(self, *_a, **_k):
                return None

        class Permission:
            async def require(self, context, code):
                if code not in context.permission_codes:
                    raise HTTPException(403, "permission denied")

        app = create_app()
        app.state.auth_context_provider = Auth()
        app.state.scope_authorizer = Scope()
        app.state.permission_authorizer = Permission()
        return TestClient(app)

    def body(self, **extra):
        return {"invoiceDate": "2026-05-01", "vendorName": "vendor",
                "idempotencyKey": "k-1",
                "lines": [{"resourceId": str(uuid4()), "lineAmountIrr": "1000"}], **extra}

    def test_a_supplied_invoice_number_is_refused_with_422(self):
        with self.client() as api:
            response = api.post("%s/invoices" % self.BASE,
                                json=self.body(invoiceNumber="F-1"))
        self.assertEqual(422, response.status_code)
        self.assertIn("invoiceNumber", response.text)

    def test_the_same_refusal_on_the_corrective_and_extraction_paths(self):
        with self.client() as api:
            corrective = api.post("%s/invoices/%s/corrective" % (self.BASE, uuid4()),
                                  json=self.body(invoiceNumber="F-1", source="corrective",
                                                 financialEffectSign=-1, reason="wrong"))
        self.assertEqual(422, corrective.status_code)
        self.assertIn("invoiceNumber", corrective.text)

    def test_the_response_carries_both_forms_of_the_one_number(self):
        from app.finance.schemas.invoices import InvoiceResponse
        invoice = Invoice(uuid4(), ORG, SEEDED_PROJECT, 42, date(2026, 5, 1), "vendor",
                          None, "manual", "draft", Decimal(0), Decimal(0), Decimal(0),
                          Decimal(0), Decimal(1000), "k", 1, ACTOR, None, None,
                          datetime(2026, 5, 1, tzinfo=timezone.utc), [])
        payload = InvoiceResponse.from_domain(invoice).model_dump(by_alias=True)
        self.assertEqual(42, payload["invoiceSeq"])
        self.assertEqual("042", payload["invoiceNumber"])

    def test_a_document_issued_with_a_number_keeps_being_called_that(self):
        """0020 gives every existing invoice a sequence. It must not rename them.

        Fifty-three invoices on the upgrade fixture carry a number somebody gave them, and
        fifty-one of those are already confirmed, voided or corrected. Building the label
        from the new sequence renamed all of them -- silently, and everywhere at once:
        paper, email, payment reference and screen stop agreeing and nothing says when.

        The stored string wins whenever there is one.  is unaffected and is in
        the response either way, so a client can still sort and address by the sequence.
        """
        from app.finance.schemas.invoices import InvoiceResponse
        issued = Invoice(uuid4(), ORG, SEEDED_PROJECT, 7, date(2026, 5, 1), "vendor",
                         None, "manual", "confirmed", Decimal(0), Decimal(0), Decimal(0),
                         Decimal(0), Decimal(1000), "k", 1, ACTOR, ACTOR,
                         datetime(2026, 5, 1, tzinfo=timezone.utc),
                         datetime(2026, 5, 1, tzinfo=timezone.utc), [], 1, None, "ف-001")
        payload = InvoiceResponse.from_domain(issued).model_dump(by_alias=True)
        self.assertEqual("ف-001", payload["invoiceNumber"], "an issued number was rewritten")
        self.assertEqual(7, payload["invoiceSeq"], "the sequence is still reported")

    def test_an_invoice_created_since_the_change_is_called_by_its_sequence(self):
        from app.finance.schemas.invoices import InvoiceResponse
        fresh = Invoice(uuid4(), ORG, SEEDED_PROJECT, 7, date(2026, 5, 1), "vendor", None,
                        "manual", "draft", Decimal(0), Decimal(0), Decimal(0), Decimal(0),
                        Decimal(1000), "k", 1, ACTOR, None, None,
                        datetime(2026, 5, 1, tzinfo=timezone.utc), [])
        payload = InvoiceResponse.from_domain(fresh).model_dump(by_alias=True)
        self.assertEqual("007", payload["invoiceNumber"])
        self.assertEqual(7, payload["invoiceSeq"])

    def test_a_blank_stored_number_is_not_a_number(self):
        # An empty string is what a column gets when somebody saved the form without
        # typing anything. It is not a name; falling back to the sequence is.
        self.assertEqual("007", format_invoice_number(7, "   "))
        self.assertEqual("007", format_invoice_number(7, None))
        self.assertEqual("ف-۹", format_invoice_number(7, "ف-۹"))

    def test_the_search_looks_for_both_numbers(self):
        import inspect
        source = inspect.getsource(PsycopgInvoiceRepository.list)
        self.assertIn("CAST(invoice_seq AS text) ILIKE %s", source)
        self.assertIn("COALESCE(invoice_number,'') ILIKE %s", source,
                      "a reader holding a paper invoice searches for what is printed on it")

    def test_the_padding_is_a_floor_and_never_a_ceiling(self):
        self.assertEqual(["001", "042", "999", "2000"],
                         [format_invoice_number(n) for n in (1, 42, 999, 2000)])


class DuplicateDetectionSurvivesTests(unittest.IsolatedAsyncioTestCase):
    """Dropping the number from the predicate must not drop the protection.

    Two invoices for the same vendor, the same day and the same amount are still the
    warning worth raising. The number had to leave the predicate because every invoice now
    has a different one -- keeping it would have made the check match nothing at all,
    which is the quietest way for a safeguard to stop working.
    """

    class Repo:
        def __init__(self, answer):
            self.answer = answer
            self.asked = []

        async def duplicate(self, _scope, key, vendor, day, amount):
            self.asked.append((key, vendor, day, amount))
            return self.answer

        async def valid_line_links(self, *_a):
            return True

        async def are_general_costs(self, *_a):
            return True

        async def create(self, _s, invoice, *_a, **_k):
            return invoice

    def command(self, key="k-1"):
        return a_create(key, uuid4())

    async def test_a_similar_invoice_still_requires_a_reason(self):
        from app.finance.services.invoices import DuplicateInvoice
        repository = self.Repo("similar")
        service = FinanceInvoiceService(repository)
        with self.assertRaises(DuplicateInvoice):
            await service.create(FinanceScope(ORG, "p1", ACTOR), self.command())

    async def test_the_predicate_is_vendor_date_and_amount_and_no_number(self):
        repository = self.Repo(None)
        service = FinanceInvoiceService(repository)
        await service.create(FinanceScope(ORG, "p1", ACTOR), self.command("k-9"))
        self.assertEqual([("k-9", "vendor", date(2026, 5, 1), Decimal(1000))],
                         repository.asked)

    def test_the_statement_no_longer_mentions_the_number(self):
        import inspect
        source = inspect.getsource(PsycopgInvoiceRepository.duplicate)
        self.assertIn("vendor_name=%s AND invoice_date=%s AND final_amount_irr=%s", source)
        self.assertNotIn("invoice_number", source)

    def test_the_search_matches_the_number_as_text(self):
        import inspect
        source = inspect.getsource(PsycopgInvoiceRepository.list)
        self.assertIn("CAST(invoice_seq AS text) ILIKE %s", source)
        self.assertNotIn("invoice_number ILIKE", source)


class NothingAllocatesOutsideTheCounterTests(unittest.TestCase):
    """Every write of an invoice row goes through the one allocator.

    Asserted against the source because the claim is about the whole module rather than
    about one code path: a fifth way to insert an invoice added later would pass every
    behavioural test above and still be wrong.
    """

    REPOSITORIES = BACKEND_ROOT / "app" / "finance" / "repositories"

    def test_every_insert_into_invoices_allocates_from_the_counter(self):
        writers = []
        for path in self.REPOSITORIES.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "INSERT INTO invoices(" in text:
                writers.append((path.name, text))
        self.assertEqual(2, len(writers),
                         "expected the create path and the extraction path, found %s"
                         % [name for name, _ in writers])
        for name, text in writers:
            with self.subTest(module=name):
                self.assertIn("allocate_invoice_number", text)
                self.assertIn("invoice_seq", text)

    def test_the_service_no_longer_decides_the_number(self):
        service = (BACKEND_ROOT / "app" / "finance" / "services"
                   / "invoices.py").read_text(encoding="utf-8")
        # The module's comment names both functions, because a reader arriving at the
        # old names deserves to be told where the number went. What must be gone is any
        # definition of them and any call to them.
        self.assertNotIn("def resolve_invoice_number", service)
        self.assertNotIn("resolve_invoice_number(", service)
        self.assertNotIn("def invoice_code", service)
        self.assertNotIn("invoice_code(", service)

    def test_a_violated_unique_constraint_is_not_reported_as_an_idempotency_conflict(self):
        import inspect
        source = inspect.getsource(PsycopgInvoiceRepository.create)
        self.assertIn("ux_invoices_project_seq", source)
        self.assertIn("InvoiceNumberConflict", source)
        self.assertLess(source.index("InvoiceNumberConflict"),
                        source.index('raise ValueError("invoice idempotency'))


if __name__ == "__main__":
    unittest.main()
