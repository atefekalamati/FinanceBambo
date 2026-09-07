# -*- coding: utf-8 -*-
"""The Finance-owned sync: one file, one version per content, one transaction.

What these defend: the same bytes never make a second version; a parse or an insert that
fails leaves nothing behind; a file the gate refuses never reaches the reader; and the
persisted rows carry the file's own identifiers, never a database id from another module.
"""

import asyncio
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_mpp_sync import FinanceMppSyncRefused, FinanceMppSyncService

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
        self._rows = list(self._c.existing) if "FROM finance_mpp_source_versions" in text else []

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class Connection:
    def __init__(self, existing=(), fail_on=None):
        self.existing, self.fail_on = list(existing), fail_on
        self.statements, self.log = [], []

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


if __name__ == "__main__":
    unittest.main()
