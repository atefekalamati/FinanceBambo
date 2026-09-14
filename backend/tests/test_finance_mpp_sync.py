# -*- coding: utf-8 -*-
"""The Finance-owned sync: one file, one version per content, one transaction.

What these defend: the same bytes never make a second version; a parse or an insert that
fails leaves nothing behind; a file the gate refuses never reaches the reader; and the
persisted rows carry the file's own identifiers, never a database id from another module.
"""

import asyncio
import hashlib
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_mpp_sync import FinanceMppSyncRefused, FinanceMppSyncService
from coreint.mpp_files import ResolvedMppFile

ORG = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")
#: An OLE2 compound-file header: what the file gate accepts as an MPP.
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504


class ParsedFile:
    def __init__(self, tasks, resources=(), assignments=()):
        self.tasks, self.resources, self.assignments = list(tasks), list(resources), list(assignments)
        self.warnings, self.parser_engine = [], "test-engine"


def task(uid, name="تخریب جداول", **metrics):
    base = {"weight_rial": None, "weight_time": None, "weight_base": None,
            "actual_progress": None, "actual_progress_percent": None,
            "physical_progress": None, "planned_progress": None,
            "task_cost": None, "task_actual_cost": None, "task_fixed_cost": None}
    base.update(metrics)
    return {"uid": uid, "name": name, "wbs": "1.%d" % uid, "metrics": base, "raw_fields": {}}


def assignment(uid, task_uid, resource_uid=94):
    return {"assignment_uid": uid, "task_uid": task_uid, "resource_uid": resource_uid}


class Reader:
    def __init__(self, parsed=None, error=None):
        self._parsed, self._error, self.reads = parsed, error, 0

    def read(self, path):
        self.reads += 1
        if self._error:
            raise self._error
        return self._parsed


# ----------------------------------------------------------- a transaction-aware fake
class Transaction:
    def __init__(self, log):
        self._log = log

    async def __aenter__(self):
        self._log.append("BEGIN")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._log.append("ROLLBACK" if exc_type else "COMMIT")
        return False


class Cursor:
    def __init__(self, connection):
        self._c = connection
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        if self._c.fail_on and self._c.fail_on in text:
            raise RuntimeError("simulated failure on: " + self._c.fail_on)
        self._c.statements.append(text)
        # Parameters too: a statement's text says what was asked, and only the parameters
        # say what it was asked ABOUT -- which is the whole question for a lock key.
        self._c.parameters.append(params)
        self._rows = [dict(row, actual_row_count=self._c.actual_rows,
                           quantity_row_count=self._c.quantity_rows)
                      for row in self._c.existing] if "FROM finance_mpp_source_versions" in text else []

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        # The periodic tick's project lookup uses this. An empty list is the honest answer
        # for a file whose stem names no project, which is exactly the case under test.
        return list(self._rows)


class Connection:
    def __init__(self, existing=(), fail_on=None, actual_rows=2, quantity_rows=0):
        self.existing, self.fail_on = list(existing), fail_on
        self.actual_rows, self.quantity_rows = actual_rows, quantity_rows
        self.statements, self.parameters, self.log = [], [], []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return Transaction(self.log)

    def cursor(self, **_kwargs):
        return Cursor(self)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        (Path(self.root.name) / "terrace.mpp").write_bytes(OLE2)
        self.parsed = ParsedFile(
            [task(1, weight_rial="1.5", actual_progress_percent="84"), task(2)],
            [{"uid": 94, "name": "آرماتور"}],
            [assignment(10, 1), assignment(11, 2)])

    def tearDown(self):
        self.root.cleanup()

    def service(self, connection, reader):
        async def factory():
            return connection
        return FinanceMppSyncService(factory, reader, import_root=self.root.name,
                                     id_factory=lambda: VERSION)

    def test_a_new_file_becomes_a_ready_version_with_every_row_inside_one_transaction(self):
        connection = Connection()
        result = run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        self.assertEqual("imported", result["status"])
        self.assertEqual(2, result["rowCount"])
        self.assertEqual(0, result["quantityRowCount"], "no approved quantity column here")
        self.assertEqual(1, sum("INSERT INTO finance_mpp_source_versions" in s for s in connection.statements))
        self.assertEqual(2, sum("INSERT INTO finance_mpp_rows" in s for s in connection.statements))
        self.assertEqual(["BEGIN", "COMMIT"], connection.log)

    def test_the_same_bytes_are_one_version_and_write_no_rows(self):
        connection = Connection(existing=[{"id": VERSION, "row_count": 2,
                                           "source_file_name_safe": "terrace.mpp"}])
        result = run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        self.assertEqual("unchanged", result["status"])
        self.assertEqual(str(VERSION), result["sourceVersionId"])
        self.assertFalse(any("INSERT" in s for s in connection.statements))

    def test_restaging_the_same_bytes_under_a_new_name_updates_only_the_label(self):
        # An operator restages a schedule under the name it arrived with. The content is
        # the same, so the version is the same -- but going on naming a file nobody has
        # any more is a record that has stopped being true. Rows and hash are untouched.
        connection = Connection(existing=[{"id": VERSION, "row_count": 2,
                                           "source_file_name_safe": "old_name.mpp"}])
        result = run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        self.assertEqual("unchanged", result["status"])
        self.assertEqual("terrace.mpp", result["fileName"])
        updates = [s for s in connection.statements if s.startswith("UPDATE")]
        self.assertEqual(1, len(updates))
        self.assertIn("SET source_file_name_safe", updates[0])
        self.assertFalse(any("INSERT" in s for s in connection.statements))

    def test_an_unchanged_name_is_not_rewritten(self):
        connection = Connection(existing=[{"id": VERSION, "row_count": 2,
                                           "source_file_name_safe": "terrace.mpp"}])
        run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        self.assertFalse(any(s.startswith("UPDATE") for s in connection.statements))

    def test_unchanged_sync_reports_stored_counts_and_repairs_only_stale_metadata(self):
        connection = Connection(existing=[{"id": VERSION, "row_count": 727,
                                           "source_file_name_safe": "terrace.mpp"}],
                                actual_rows=789, quantity_rows=3)
        result = run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        self.assertEqual("unchanged", result["status"])
        self.assertEqual(789, result["rowCount"])
        self.assertEqual(3, result["quantityRowCount"])
        writes = [s for s in connection.statements if s.startswith(("INSERT", "DELETE", "UPDATE"))]
        self.assertEqual(["UPDATE finance_mpp_source_versions SET row_count=%s WHERE id=%s"], writes)

    def test_the_request_may_name_a_file_inside_the_configured_root(self):
        import pathlib
        (pathlib.Path(self.root.name) / "test_progress.mpp").write_bytes(OLE2)
        connection = Connection()
        result = run(self.service(connection, Reader(self.parsed)).sync(
            ORG, "terrace", file_name="test_progress.mpp"))
        self.assertEqual("imported", result["status"])
        self.assertEqual("test_progress.mpp", result["fileName"])

    def test_a_request_naming_a_file_outside_the_root_is_refused(self):
        with self.assertRaises(FinanceMppSyncRefused) as caught:
            run(self.service(Connection(), Reader(self.parsed)).sync(
                ORG, "terrace", file_name="../escape.mpp"))
        self.assertEqual("MPP_PATH_NOT_ALLOWED", caught.exception.code)

    def test_a_failing_row_insert_rolls_the_whole_version_back(self):
        connection = Connection(fail_on="INSERT INTO finance_mpp_rows")
        with self.assertRaises(RuntimeError):
            run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        self.assertIn("ROLLBACK", connection.log)
        self.assertNotIn("COMMIT", connection.log)

    def test_a_parse_failure_never_touches_the_database(self):
        connection = Connection()
        with self.assertRaises(ValueError):
            run(self.service(connection, Reader(error=ValueError("corrupt"))).sync(ORG, "terrace"))
        self.assertEqual([], connection.statements)
        self.assertEqual([], connection.log)

    def test_a_missing_file_is_refused_before_the_reader_runs(self):
        reader = Reader(self.parsed)
        with self.assertRaises(FinanceMppSyncRefused) as caught:
            run(self.service(Connection(), reader).sync(ORG, "no-such-project"))
        self.assertEqual("MPP_FILE_NOT_FOUND", caught.exception.code)
        self.assertEqual(0, reader.reads)

    def test_a_file_with_nothing_finance_can_record_is_refused(self):
        with self.assertRaises(FinanceMppSyncRefused) as caught:
            run(self.service(Connection(), Reader(ParsedFile([]))).sync(ORG, "terrace"))
        self.assertEqual("MPP_NO_FINANCE_ROWS", caught.exception.code)

    def test_rows_are_written_with_the_files_identifiers_and_persisted_metrics(self):
        connection = Connection()
        run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        row_inserts = [s for s in connection.statements if "INSERT INTO finance_mpp_rows" in s]
        # The column list is the contract with 0011: identifiers first, quantity nullable.
        for column in ("source_task_uid", "source_assignment_uid", "source_resource_uid",
                       "quantity", "quantity_unit", "weight_rial", "actual_progress_percent",
                       "cost"):
            self.assertIn(column, row_inserts[0])
        for forbidden in ("msp_tasks", "snapshot_id", "bridge"):
            self.assertNotIn(forbidden, row_inserts[0])


class HashedBytesAreParsedBytesTests(SyncTests):
    """The sha a version is stored under must describe the rows stored beside it.

    The first version of this guarantee compared digests before and after the parse. That
    was close and measurably not all the way: on an isolated database, a file changed
    DURING the parse and changed back before it returned satisfied both digests, was
    accepted, and stored a version whose sha described bytes nobody had parsed.

    So the parse reads a private copy instead. The copy is made under a directory only that
    call knows, its digest is checked against the staged file's before the parser is allowed
    near it, and it is removed afterwards. "The sha describes the bytes parsed" is then true
    because there was only ever one set of bytes -- a structural answer rather than a
    timing one.

    A consequence worth stating: changing the staged file while the parse runs is now
    HARMLESS rather than fatal. The copy already holds bytes that really existed, and the
    version describing them is correct; the next sync picks up the new bytes. The old test
    asserted a refusal there, and that refusal was over-strict.
    """

    class RecordingReader(Reader):
        """Notes which path it was handed and what was in it."""

        def __init__(self, parsed):
            super().__init__(parsed)
            self.seen_path = None
            self.seen_bytes = None

        def read(self, file_path):
            self.seen_path = Path(file_path)
            self.seen_bytes = self.seen_path.read_bytes()
            return super().read(file_path)

    class MeddlingReader(RecordingReader):
        """Overwrites the STAGED file while the parse is under way."""

        def __init__(self, parsed, staged):
            super().__init__(parsed)
            self._staged = staged

        def read(self, file_path):
            result = super().read(file_path)
            self._staged.write_bytes(OLE2 + b"the host restaged this mid-parse")
            return result

    def staged(self):
        return Path(self.root.name) / "terrace.mpp"

    def test_the_parser_is_handed_a_private_copy_and_never_the_staged_file(self):
        connection = Connection()
        reader = self.RecordingReader(self.parsed)
        result = run(self.service(connection, reader).sync(ORG, "terrace"))
        self.assertEqual("imported", result["status"])
        self.assertIsNotNone(reader.seen_path)
        self.assertNotEqual(self.staged().resolve(), reader.seen_path.resolve(),
                            "the parse must not read the file a host can still write")
        self.assertEqual(self.staged().read_bytes(), reader.seen_bytes,
                         "and the copy must be the same bytes")

    def test_the_private_copy_does_not_outlive_the_parse(self):
        # A temporary directory per sync that nobody removes is a disk that fills up
        # quietly, on a timer.
        connection = Connection()
        reader = self.RecordingReader(self.parsed)
        run(self.service(connection, reader).sync(ORG, "terrace"))
        self.assertFalse(reader.seen_path.exists())
        self.assertFalse(reader.seen_path.parent.exists())

    def test_a_file_changed_after_it_was_hashed_is_refused(self):
        # Driven through the digest the resolver reported rather than by racing the disk:
        # a `resolved` whose sha does not match the bytes on disk is exactly the state a
        # file replaced between hashing and copying leaves behind.
        connection = Connection()
        service = self.service(connection, Reader(self.parsed))
        wrong = ResolvedMppFile(self.staged(), "terrace.mpp",
                                self.staged().stat().st_size, "0" * 64)
        with self.assertRaises(FinanceMppSyncRefused) as caught:
            service._parse_a_private_copy(wrong)
        self.assertEqual("MPP_FILE_NOT_STABLE", caught.exception.code)
        self.assertEqual([], [s for s in connection.statements
                              if s.startswith(("INSERT", "UPDATE", "DELETE"))],
                         "nothing may be written when the bytes are in doubt")

    def test_changing_the_staged_file_during_the_parse_no_longer_refuses(self):
        # The case the digest-before/after design got wrong in both directions: it refused
        # a change that did not matter, and accepted a change-and-revert that did.
        connection = Connection()
        reader = self.MeddlingReader(self.parsed, self.staged())
        result = run(self.service(connection, reader).sync(ORG, "terrace"))
        self.assertEqual("imported", result["status"])
        self.assertEqual(hashlib.sha256(reader.seen_bytes).hexdigest(),
                         result["fileSha256"],
                         "the stored sha describes the bytes the parser actually read")
        self.assertNotEqual(reader.seen_bytes, self.staged().read_bytes(),
                            "the staged file really did move on")

    def test_an_ordinary_import_still_states_the_files_own_digest(self):
        connection = Connection()
        reader = self.RecordingReader(self.parsed)
        result = run(self.service(connection, reader).sync(ORG, "terrace"))
        self.assertEqual(hashlib.sha256(OLE2).hexdigest(), result["fileSha256"])
        self.assertEqual(2, result["rowCount"])


class ConcurrentFirstImportTests(SyncTests):
    """Two callers, the same never-seen content, at the same moment.

    Measured on an isolated database before this was here: one call imported and the other
    raised a raw UniqueViolation from the index on (organization, project, sha256). The
    DATA was right -- one version, ready, with its rows -- and the answer was a 500 on a
    request whose honest reply is "somebody else just imported these exact bytes".

    A fake connection cannot race, so what this pins is the thing that removes the race:
    the transaction takes an advisory lock on the content identity BEFORE it looks the
    version up, so the second caller waits and then finds the first one's row. After the
    change, the same two concurrent syncs answer `imported` and `unchanged`.
    """

    def statements_of(self, connection):
        return [" ".join(str(s).split()) for s in connection.statements]

    def test_the_content_identity_is_locked_before_it_is_looked_up(self):
        connection = Connection()
        run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        statements = self.statements_of(connection)
        locks = [index for index, text in enumerate(statements)
                 if "pg_advisory_xact_lock" in text]
        lookups = [index for index, text in enumerate(statements)
                   if "FROM finance_mpp_source_versions v" in text]
        self.assertTrue(locks, "no advisory lock was taken")
        self.assertTrue(lookups, "the version look-up did not happen")
        self.assertLess(locks[0], lookups[0],
                        "locking after the look-up leaves the race exactly where it was")

    def test_the_lock_is_keyed_on_the_tenant_and_the_content(self):
        # A lock on the project alone would serialise unrelated files; one on the sha alone
        # would serialise across tenants. The key is all three.
        connection = Connection()
        run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        key = next(params for text, params in
                   [(" ".join(str(s).split()), p) for s, p in
                    zip(connection.statements, connection.parameters)]
                   if "pg_advisory_xact_lock" in text)
        self.assertIn(ORG, key[0])
        self.assertIn("terrace", key[0])
        self.assertIn(hashlib.sha256(OLE2).hexdigest(), key[0])

    def test_the_lock_needs_no_unlocking(self):
        # `pg_advisory_xact_lock` is released by the commit or the rollback. A session-scoped
        # lock would need an explicit unlock on every path out, including the failing ones.
        connection = Connection()
        run(self.service(connection, Reader(self.parsed)).sync(ORG, "terrace"))
        statements = self.statements_of(connection)
        self.assertFalse([s for s in statements if "advisory_unlock" in s])
        self.assertFalse([s for s in statements if "pg_advisory_lock(" in s])


class WhichFileBelongsToWhichProjectTests(unittest.TestCase):
    """The periodic tick's selection rule, stated so it cannot quietly become a guess.

    THE RULE: a staged file belongs to a project when its stem IS the project id, and that
    project exists in `finance_project_settings`. Nothing else. No sorting, no newest-wins,
    no prefix or fuzzy match, and no "there is only one file, so it must be the one".

    That matters most when an operator stages a SECOND file. `terrace-v2.mpp`,
    `terrace (1).mpp` and `terrace_final.mpp` all look like they belong to `terrace` to a
    human, and to none of them does this rule apply -- so the version already imported stays
    active and no ambiguity is ever settled by picking. What changed is that such a file is
    now REPORTED as naming no project instead of vanishing, because an operator who staged a
    file and saw nothing happen could not tell that from an importer that was not running.

    Changing which file a project reads is therefore an explicit act: the `fileName` body
    parameter on `POST /finance/mpp-sync`, which goes through the same path gate. The next
    step for a host that needs that standing rather than per-request is a project-level
    active-file setting -- one row naming one file -- which this rule leaves room for and
    which no filename convention can substitute for.
    """

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.parsed = ParsedFile([task(1)], [{"uid": 94, "name": "آرماتور"}],
                                 [assignment(10, 1)])

    def tearDown(self):
        self.root.cleanup()

    def stage(self, *names):
        for name in names:
            (Path(self.root.name) / name).write_bytes(OLE2)

    def tick(self, connection=None):
        connection = connection or Connection()

        async def factory():
            return connection
        service = FinanceMppSyncService(factory, Reader(self.parsed),
                                        import_root=self.root.name,
                                        id_factory=lambda: VERSION)
        return run(service.periodic_tick()), connection

    def asked_for(self, connection):
        """Every project id the tick actually looked up."""
        return [p[0] for text, p in
                zip([" ".join(str(s).split()) for s in connection.statements],
                    connection.parameters)
                if "FROM finance_project_settings" in text]

    def test_each_file_is_looked_up_as_itself_and_never_as_another_project(self):
        """Every stem is asked about under its OWN name.

        `terrace-v2.mpp` does cause a lookup -- for a project literally called
        `terrace-v2`, which does not exist, so the file is ignored. That is the rule
        working. What must never happen is the stem being mapped onto a DIFFERENT project
        id: `terrace-v2` resolving to `terrace` is how a stale or foreign schedule would
        overwrite a live one, and no amount of it looking obvious to a human makes it a
        fact the file states.
        """
        self.stage("terrace.mpp", "terrace-v2.mpp", "terrace (1).mpp")
        _outcomes, connection = self.tick()
        self.assertEqual({"terrace", "terrace-v2", "terrace (1)"},
                         set(self.asked_for(connection)),
                         "each stem is asked about as itself, and nothing else is invented")

    def test_a_versioned_sibling_is_reported_rather_than_silently_skipped(self):
        self.stage("terrace-v2.mpp")
        outcomes, _ = self.tick()
        ignored = [o for o in outcomes if o["status"] == "ignored"]
        self.assertEqual(["terrace-v2.mpp"], [o["fileName"] for o in ignored])
        self.assertEqual("FINANCE_MPP_FILE_NAMES_NO_PROJECT", ignored[0]["code"])
        self.assertIsNone(ignored[0]["projectId"],
                          "naming a project for it would be the guess this rule prevents")

    def test_nothing_is_written_for_a_file_that_names_no_project(self):
        self.stage("terrace-v2.mpp", "test_progress.mpp")
        outcomes, connection = self.tick()
        self.assertEqual([], [o for o in outcomes if o["status"] != "ignored"])
        statements = [" ".join(str(s).split()) for s in connection.statements]
        self.assertFalse([s for s in statements if s.startswith("INSERT INTO")],
                         "a file naming no project must not write anything")

    def test_the_staged_test_file_is_never_picked_up_by_the_tick(self):
        # `test_progress.mpp` is imported by naming it explicitly and never by being
        # present -- which is what keeps it from becoming a permanent special case.
        self.stage("test_progress.mpp")
        outcomes, _ = self.tick()
        self.assertEqual(["ignored"], [o["status"] for o in outcomes])

    def test_an_empty_root_reports_nothing_at_all(self):
        outcomes, _ = self.tick()
        self.assertEqual([], outcomes)


if __name__ == "__main__":
    unittest.main()
