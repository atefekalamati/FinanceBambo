# -*- coding: utf-8 -*-
"""The import service, exercised with doubles: a scripted database, a canned parse.

No JVM and no PostgreSQL run here. The reader double returns exactly the shape
``MpxjMppReader`` produces, the connection double scripts every query the service is
allowed to ask, and the assertions pin the promises that matter:

  * one transaction, rolled back whole on any failure;
  * refusal codes are stable and precede any write where they claim to;
  * matching is UID-inside-scope and NEVER by name;
  * a value the file does not state stays None -- absent is not zero;
  * Work (hours) and Quantity (physical) never substitute for one another;
  * unmapped resources are REPORTED, not invented, and the status says so.
"""

import asyncio
import sys
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.mpp_files import OLE2_MAGIC
from coreint.mpp_import import MppImportRefused, MppImportService, validate_mapping_scope
from coreint.mpp_reader import ParsedMppProject

ORG = "0d3c0000-0000-4000-8000-00000000000d"
OTHER_ORG = "0d3c0000-0000-4000-8000-0000000000ff"
PROJECT = "terrace"


def run(coroutine):
    return asyncio.new_event_loop().run_until_complete(coroutine)


# --------------------------------------------------------------------------- the doubles
def task(uid, name="pour", percent=None):
    return {"uid": uid, "guid": None, "task_id": uid, "name": name, "wbs": None,
            "outline_number": None, "outline_level": 1, "summary": False,
            "start": None, "finish": None, "baseline_start": None,
            "baseline_finish": None, "duration": None, "percent_complete": percent,
            "percent_work_complete": None, "physical_percent_complete": None,
            "text1": None}


def resource(uid, name, quantity=None, unit=None):
    return {"uid": uid, "guid": None, "name": name, "native_type": "MATERIAL",
            "initials": None, "material_label": unit, "quantity": quantity,
            "quantity_unit": unit, "quantity_unit_source": "material_label" if unit else None,
            "group": None, "code": None, "max_units": None, "standard_rate": None,
            "overtime_rate": None, "cost_per_use": None, "work": None,
            "actual_work": None, "remaining_work": None, "cost": None,
            "actual_cost": None, "remaining_cost": None}


def assignment(auid, task_uid, resource_uid, planned_work=None, planned_quantity=None):
    return {"assignment_uid": auid, "task_uid": task_uid, "resource_uid": resource_uid,
            "units": None, "planned_work": planned_work, "actual_work": None,
            "remaining_work": None, "planned_quantity": planned_quantity,
            "actual_quantity": None, "remaining_quantity": None,
            "work_complete_percent": None, "cost": None, "actual_cost": None,
            "remaining_cost": None}


def parsed_project(tasks, resources, assignments, warnings=(), status_date=None):
    return ParsedMppProject(application="Microsoft.Project 16.0", tasks=tasks,
                            resources=resources, assignments=assignments,
                            warnings=list(warnings), status_date=status_date)


class CannedReader:
    def __init__(self, project):
        self.project = project
        self.reads = 0

    def read(self, file_path):
        self.reads += 1
        return self.project


class ScriptedCursor:
    """Answers the exact queries the service may ask, and records every write."""

    def __init__(self, state):
        self.state = state
        self._pending = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        state = self.state
        statement = " ".join(sql.split())
        state.statements.append((statement, params))
        if state.fail_on and state.fail_on in statement:
            raise RuntimeError("scripted failure on: %s" % state.fail_on)
        if "FROM projects WHERE id" in statement:
            self._pending = state.projects.get(params[0])
        elif "pg_try_advisory_xact_lock" in statement:
            self._pending = {"locked": state.lock_available}
        elif "SELECT id, sha256 FROM msp_file_versions" in statement:
            self._pending = state.latest_version
        elif "SELECT sha256 FROM msp_file_versions" in statement:
            self._pending = state.latest_version
        elif "INSERT INTO msp_file_versions" in statement:
            self._pending = {"id": 501, "version_number": 7}
            state.writes.append("file_version")
        elif "INSERT INTO msp_snapshots" in statement:
            self._pending = {"id": 9001}
            state.writes.append("snapshot")
        elif "INSERT INTO msp_tasks" in statement:
            state.task_rows.append(params)
            self._pending = {"id": 7000 + len(state.task_rows)}
            state.writes.append("task")
        elif "INSERT INTO msp_resources" in statement:
            state.resource_rows.append(params)
            state.writes.append("resource")
        elif "INSERT INTO msp_resource_assignments" in statement:
            state.assignment_rows.append(params)
            state.writes.append("assignment")
        elif "SELECT id, external_resource_id" in statement:
            self._pending = list(state.finance_resources)
        elif "INSERT INTO finance_task_resource_map" in statement:
            state.mapping_rows.append(params)
            state.writes.append("mapping")
        else:
            self._pending = None

    async def fetchone(self):
        value, self._pending = self._pending, None
        return value

    async def fetchall(self):
        value, self._pending = self._pending, []
        return value


class ScriptedTransaction:
    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        self.state.transactions_opened += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.state.transactions_closed.append(
            "rolled_back" if exc_type else "committed")
        return False


class ScriptedConnection:
    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return ScriptedTransaction(self.state)

    def cursor(self, row_factory=None):
        return ScriptedCursor(self.state)


class DatabaseState:
    def __init__(self):
        self.projects = {PROJECT: {"id": PROJECT, "organization_id": ORG}}
        self.lock_available = True
        self.latest_version = None
        self.finance_resources = []
        self.fail_on = None
        self.statements = []
        self.writes = []
        self.task_rows = []
        self.resource_rows = []
        self.assignment_rows = []
        self.mapping_rows = []
        self.transactions_opened = 0
        self.transactions_closed = []


# ----------------------------------------------------------------------------- the tests
class MppImportServiceTests(unittest.TestCase):
    def setUp(self):
        self._root = tempfile.TemporaryDirectory()
        self.root = Path(self._root.name)
        (self.root / ("%s.mpp" % PROJECT)).write_bytes(OLE2_MAGIC + b"\x00" * 64)
        self.state = DatabaseState()

    def tearDown(self):
        self._root.cleanup()

    def service(self, project, state=None):
        state = state or self.state

        async def connect():
            return ScriptedConnection(state)

        return MppImportService(connect, CannedReader(project),
                                import_root=self.root, id_factory=uuid.uuid4)

    def import_file(self, service):
        return run(service.run_import(ORG, PROJECT, "%s.mpp" % PROJECT))

    def refusal(self, service, organization=ORG, name="%s.mpp" % PROJECT):
        with self.assertRaises(MppImportRefused) as caught:
            run(service.run_import(organization, PROJECT, name))
        return caught.exception

    # -------------------------------------------------------------------- the happy path
    def test_a_valid_file_lands_as_one_committed_snapshot_with_its_mapping(self):
        self.state.finance_resources = [
            {"id": "res-94", "external_resource_id": "94", "code": "REBAR",
             "title": "rebar"}]
        project = parsed_project(
            [task(1, "roof"), task(2, "pour", percent="35")],
            [resource(94, "آرماتور", quantity="1329121.22", unit="کیلوگرم")],
            [assignment(11, 1, 94), assignment(12, 2, 94)])
        result = self.import_file(self.service(project))

        self.assertEqual("completed", result["status"])
        self.assertIsNone(result["error"])
        self.assertEqual(2, result["taskCount"])
        self.assertEqual(1, result["resourceCount"])
        self.assertEqual(2, result["assignmentCount"])
        self.assertEqual(2, result["mappedCount"])
        self.assertEqual(0, result["unmappedCount"])
        self.assertEqual(9001, result["snapshotId"])
        self.assertEqual(501, result["fileVersionId"])
        self.assertEqual(64, len(result["fileSha256"]))
        self.assertEqual(["committed"], self.state.transactions_closed)
        self.assertEqual(2, len(self.state.mapping_rows))

    def test_the_result_carries_the_full_documented_contract(self):
        project = parsed_project([task(1)], [], [])
        result = self.import_file(self.service(project))
        self.assertEqual(
            {"importId", "projectId", "fileVersionId", "snapshotId",
             "reportingPeriodId", "fileSha256", "fileName", "taskCount",
             "resourceCount", "assignmentCount", "mappedCount", "unmappedCount",
             "warningCount", "unmappedResources", "warnings", "status", "error"},
            set(result))
        # No period logic exists in this repository, so none is invented.
        self.assertIsNone(result["reportingPeriodId"])

    def test_the_file_status_date_is_stored_as_the_snapshots_jalali_date(self):
        project = parsed_project([task(1)], [], [], status_date=date(2026, 8, 2))
        self.import_file(self.service(project))
        params = next(params for statement, params in self.state.statements
                      if "INSERT INTO msp_snapshots" in statement)
        self.assertEqual("1405-05-11", params[-2])

    def test_physical_progress_alone_still_marks_the_version_actual(self):
        # A physically-tracked actuals file keeps duration-percent at 0 everywhere;
        # stamping it TARGET would file real actuals as a baseline.
        tracked = task(1)
        tracked["percent_complete"] = "0"
        tracked["physical_percent_complete"] = "30"
        self.import_file(self.service(parsed_project([tracked], [], [])))
        params = next(p for s, p in self.state.statements
                      if "INSERT INTO msp_file_versions" in s)
        self.assertIn("ACTUAL", params)

    def test_zero_spelled_oddly_is_still_zero(self):
        # Decimal("0.00") == 0: the role is decided by the NUMBER, not its spelling.
        oddly = task(1, percent="0.00")
        self.import_file(self.service(parsed_project([oddly], [], [])))
        params = next(p for s, p in self.state.statements
                      if "INSERT INTO msp_file_versions" in s)
        self.assertIn("TARGET", params)

    def test_an_assignment_naming_an_absent_resource_is_refused_before_the_database(self):
        # The composite FK would reject it mid-transaction as a raw 500; the importer
        # names the inconsistency first, symmetrically with the task-uid check.
        broken = parsed_project([task(1)], [resource(94, "rebar")],
                                [assignment(11, 1, 999)])
        refused = self.refusal(self.service(broken))
        self.assertEqual("MPP_PARSE_FAILED", refused.code)
        self.assertIn("999", str(refused))
        self.assertEqual(0, self.state.transactions_opened)

    def test_a_quantity_without_any_unit_anywhere_is_refused_with_a_code(self):
        # The schema forbids a quantity with no unit; without this refusal the CHECK
        # constraint would fire mid-transaction as an uncoded 500.
        unitless = resource(94, "mystery dust")
        quantified = assignment(11, 1, 94)
        quantified["planned_quantity"] = "12"
        refused = self.refusal(
            self.service(parsed_project([task(1)], [unitless], [quantified])))
        self.assertEqual("MPP_PARSE_FAILED", refused.code)
        self.assertIn("names no unit", str(refused))

    def test_a_blank_quantity_cell_does_not_orphan_the_assignments_unit(self):
        # The Resource Sheet's quantity CELL may be empty while the resource still
        # names its measure; the assignment's unit comes from material_label directly.
        sheet_row = resource(94, "آرماتور")
        sheet_row["material_label"] = "کیلوگرم"      # stated, but quantity cell blank
        remaining_only = assignment(11, 1, 94)
        remaining_only["remaining_quantity"] = "250"
        self.import_file(self.service(parsed_project([task(1)], [sheet_row],
                                                     [remaining_only])))
        row = self.state.assignment_rows[0]
        self.assertEqual("کیلوگرم", row[11], "unit taken from the file, not invented")

    def test_a_crash_leaves_a_findable_generic_record(self):
        self.state.fail_on = "INSERT INTO msp_snapshots"
        service = self.service(parsed_project([task(1)], [], []))
        with self.assertRaises(RuntimeError):
            self.import_file(service)
        (record,) = service.recent.values()
        self.assertEqual("MPP_IMPORT_CRASHED", record["error"]["code"])
        self.assertNotIn("scripted failure", record["error"]["message"],
                         "raw driver text stays out of the registry")

    def test_progress_in_the_file_marks_the_version_actual_and_none_marks_target(self):
        with_progress = parsed_project([task(1, percent="35")], [], [])
        self.import_file(self.service(with_progress))
        actual = next(p for s, p in self.state.statements
                      if "INSERT INTO msp_file_versions" in s)
        self.assertIn("ACTUAL", actual)

        fresh = DatabaseState()
        untouched = parsed_project([task(1)], [], [])
        run(self.service(untouched, fresh).run_import(ORG, PROJECT,
                                                      "%s.mpp" % PROJECT))
        target = next(p for s, p in fresh.statements
                      if "INSERT INTO msp_file_versions" in s)
        self.assertIn("TARGET", target)

    # ----------------------------------------------------------- absent is never zero
    def test_values_the_file_does_not_state_stay_null(self):
        project = parsed_project([task(1)], [resource(94, "rebar")],
                                 [assignment(11, 1, 94)])
        self.import_file(self.service(project))
        inserted_task = self.state.task_rows[0]
        self.assertIn(None, inserted_task)      # percent_complete travels as None
        self.assertNotIn("0", [v for v in inserted_task if isinstance(v, str)])
        inserted_assignment = self.state.assignment_rows[0]
        self.assertIsNone(inserted_assignment[5], "planned_work stays None")
        self.assertIsNone(inserted_assignment[8], "planned_quantity stays None")

    def test_work_hours_never_masquerade_as_physical_quantity(self):
        project = parsed_project(
            [task(1)], [resource(94, "crane")],
            [assignment(11, 1, 94, planned_work="48")])   # 48 HOURS of crane time
        self.import_file(self.service(project))
        row = self.state.assignment_rows[0]
        self.assertEqual("48", row[5], "work column carries the hours")
        self.assertIsNone(row[8], "quantity column does NOT inherit them")

    # ------------------------------------------------------------------- the mapping
    def test_a_resource_unknown_to_finance_is_reported_never_invented(self):
        project = parsed_project([task(1)], [resource(95, "بتن آماده")],
                                 [assignment(11, 1, 95)])
        result = self.import_file(self.service(project))
        self.assertEqual("completed_with_warnings", result["status"])
        self.assertEqual(0, result["mappedCount"])
        self.assertEqual(
            [{"resourceExternalId": "95", "resourceName": "بتن آماده",
              "status": "unmapped", "reason": "FINANCE_RESOURCE_NOT_FOUND"}],
            result["unmappedResources"])
        self.assertEqual([], self.state.mapping_rows)
        self.assertNotIn("INSERT INTO finance_resources",
                         " ".join(s for s, _ in self.state.statements))

    def test_matching_is_by_uid_inside_scope_and_never_by_name(self):
        # The finance resource is NAMED identically but carries a different external id.
        self.state.finance_resources = [
            {"id": "res-77", "external_resource_id": "77", "code": "REBAR",
             "title": "آرماتور"}]
        project = parsed_project([task(1)], [resource(94, "آرماتور")],
                                 [assignment(11, 1, 94)])
        result = self.import_file(self.service(project))
        self.assertEqual(0, result["mappedCount"], "a same-name match is no match")
        self.assertEqual("94", result["unmappedResources"][0]["resourceExternalId"])

    def test_two_assignments_on_the_same_pair_write_one_mapping_row(self):
        self.state.finance_resources = [
            {"id": "res-94", "external_resource_id": "94", "code": "R", "title": "r"}]
        project = parsed_project([task(1)], [resource(94, "rebar")],
                                 [assignment(11, 1, 94), assignment(12, 1, 94)])
        self.import_file(self.service(project))
        self.assertEqual(1, len(self.state.mapping_rows))

    def test_an_assignment_with_no_resource_is_kept_but_not_mapped(self):
        project = parsed_project([task(1)], [], [assignment(11, 1, None)],
                                 warnings=["1 assignment(s) name no resource"])
        result = self.import_file(self.service(project))
        self.assertEqual(1, result["assignmentCount"])
        self.assertEqual(0, result["mappedCount"] + result["unmappedCount"])
        self.assertEqual("completed_with_warnings", result["status"])

    # ------------------------------------------------------------------ the refusals
    def test_a_missing_file_refuses_with_its_stable_code(self):
        (self.root / ("%s.mpp" % PROJECT)).unlink()
        refused = self.refusal(self.service(parsed_project([task(1)], [], [])))
        self.assertEqual("MPP_FILE_NOT_FOUND", refused.code)
        self.assertEqual([], self.state.writes)

    def test_only_the_projects_own_file_may_be_imported(self):
        """The import root is shared by every project; a foreign name is refused
        BEFORE the filesystem is consulted, with one code whether it exists or not --
        no cross-project read, and no existence oracle."""
        (self.root / "other.mpp").write_bytes(OLE2_MAGIC + b"\x00" * 64)  # exists
        service = self.service(parsed_project([task(1)], [], []))
        for name in ("other.mpp", "ghost.mpp"):     # one staged, one imaginary
            with self.subTest(name=name):
                refused = self.refusal(service, name=name)
                self.assertEqual("MPP_PATH_NOT_ALLOWED", refused.code)
                self.assertIn("terrace.mpp", str(refused))
        self.assertEqual([], self.state.writes)
        self.assertEqual(0, self.state.transactions_opened)

    def test_the_run_registry_is_bounded(self):
        from coreint.mpp_import import RECENT_LIMIT
        service = self.service(parsed_project([task(1)], [], []))
        for _ in range(RECENT_LIMIT + 5):
            with self.assertRaises(MppImportRefused):
                run(service.run_import(ORG, PROJECT, "ghost.mpp"))
        self.assertEqual(RECENT_LIMIT, len(service.recent),
                         "a refusal loop must not grow memory for the process lifetime")

    def test_a_byte_identical_file_refuses_and_writes_nothing(self):
        sha = self.import_file(
            self.service(parsed_project([task(1)], [], [])))["fileSha256"]
        again = DatabaseState()
        again.latest_version = {"id": 500, "sha256": sha}
        refused = self.refusal(self.service(parsed_project([task(1)], [], []), again))
        self.assertEqual("MPP_DUPLICATE_FILE", refused.code)
        self.assertEqual([], again.writes)
        self.assertEqual(["rolled_back"], again.transactions_closed)

    def test_a_foreign_organization_is_refused_before_any_write(self):
        refused = self.refusal(self.service(parsed_project([task(1)], [], [])),
                               organization=OTHER_ORG)
        self.assertEqual("MPP_IMPORT_REFUSED", refused.code)
        self.assertEqual([], self.state.writes)

    def test_an_unknown_project_is_refused(self):
        self.state.projects = {}
        refused = self.refusal(self.service(parsed_project([task(1)], [], [])))
        self.assertEqual("MPP_IMPORT_REFUSED", refused.code)

    def test_a_running_import_holds_the_project_lock(self):
        self.state.lock_available = False
        refused = self.refusal(self.service(parsed_project([task(1)], [], [])))
        self.assertEqual("MPP_IMPORT_ALREADY_RUNNING", refused.code)
        self.assertEqual([], self.state.writes)

    def test_an_internally_inconsistent_file_is_refused_before_the_database(self):
        broken = parsed_project([task(1)], [], [assignment(11, 999, None)])
        refused = self.refusal(self.service(broken))
        self.assertEqual("MPP_PARSE_FAILED", refused.code)
        self.assertEqual(0, self.state.transactions_opened,
                         "validation happens before any connection is used")

    def test_a_file_with_no_tasks_is_refused(self):
        refused = self.refusal(self.service(parsed_project([], [], [])))
        self.assertEqual("MPP_PARSE_FAILED", refused.code)

    def test_every_refusal_is_recorded_for_the_status_endpoint(self):
        (self.root / ("%s.mpp" % PROJECT)).unlink()
        service = self.service(parsed_project([task(1)], [], []))
        self.refusal(service)
        (result,) = service.recent.values()
        self.assertEqual("failed", result["status"])
        self.assertEqual("MPP_FILE_NOT_FOUND", result["error"]["code"])

    # ------------------------------------------------------- atomicity and the retry
    def test_a_failure_mid_import_rolls_the_whole_transaction_back(self):
        self.state.finance_resources = [
            {"id": "res-94", "external_resource_id": "94", "code": "R", "title": "r"}]
        self.state.fail_on = "INSERT INTO msp_resource_assignments"
        project = parsed_project([task(1)], [resource(94, "rebar")],
                                 [assignment(11, 1, 94)])
        with self.assertRaises(RuntimeError):
            self.import_file(self.service(project))
        self.assertEqual(["rolled_back"], self.state.transactions_closed)
        self.assertEqual([], self.state.mapping_rows,
                         "the mapping never outlives its snapshot")

    def test_the_retry_after_a_failure_succeeds_cleanly(self):
        project = parsed_project([task(1)], [resource(94, "rebar")],
                                 [assignment(11, 1, 94)])
        self.state.fail_on = "INSERT INTO msp_snapshots"
        service = self.service(project)
        with self.assertRaises(RuntimeError):
            self.import_file(service)
        # The operator fixes the cause; the SAME service retries the SAME file.
        self.state.fail_on = None
        result = self.import_file(service)
        self.assertIn(result["status"], ("completed", "completed_with_warnings"))
        self.assertEqual(["rolled_back", "committed"],
                         self.state.transactions_closed)


class PeriodicTickTests(unittest.TestCase):
    def setUp(self):
        self._root = tempfile.TemporaryDirectory()
        self.root = Path(self._root.name)
        self.state = DatabaseState()

    def tearDown(self):
        self._root.cleanup()

    def tick(self, project):
        async def connect():
            return ScriptedConnection(self.state)

        service = MppImportService(connect, CannedReader(project),
                                   import_root=self.root, id_factory=uuid.uuid4)
        return run(service.periodic_tick())

    def test_a_file_named_for_a_project_is_imported(self):
        (self.root / ("%s.mpp" % PROJECT)).write_bytes(OLE2_MAGIC + b"\x00" * 64)
        outcomes = self.tick(parsed_project([task(1)], [], []))
        self.assertEqual(1, len(outcomes))
        self.assertEqual("completed", outcomes[0]["status"])

    def test_a_stray_file_matching_no_project_is_ignored(self):
        (self.root / "not-a-project.mpp").write_bytes(OLE2_MAGIC + b"\x00" * 64)
        self.assertEqual([], self.tick(parsed_project([task(1)], [], [])))
        self.assertEqual([], self.state.writes)

    def test_an_unchanged_file_reports_unchanged_and_writes_nothing(self):
        (self.root / ("%s.mpp" % PROJECT)).write_bytes(OLE2_MAGIC + b"\x00" * 64)
        first = self.tick(parsed_project([task(1)], [], []))
        self.state.latest_version = {"id": 500, "sha256": first[0]["fileSha256"]}
        self.state.writes.clear()
        outcomes = self.tick(parsed_project([task(1)], [], []))
        self.assertEqual([{"projectId": PROJECT, "status": "unchanged",
                           "reason": "MPP_DUPLICATE_FILE"}], outcomes)
        self.assertEqual([], self.state.writes)

    def test_an_unchanged_tick_leaves_no_failed_entry_in_the_registry(self):
        # The hourly no-op is decided by hash BEFORE run_import, so `latest` keeps
        # showing the last real import instead of an eternal duplicate refusal.
        (self.root / ("%s.mpp" % PROJECT)).write_bytes(OLE2_MAGIC + b"\x00" * 64)

        async def connect():
            return ScriptedConnection(self.state)

        service = MppImportService(connect, CannedReader(parsed_project([task(1)], [], [])),
                                   import_root=self.root, id_factory=uuid.uuid4)
        completed = run(service.periodic_tick())
        self.state.latest_version = {"id": 500,
                                     "sha256": completed[0]["fileSha256"]}
        before = dict(service.recent)
        run(service.periodic_tick())
        self.assertEqual(before, service.recent,
                         "an unchanged tick must not append any run report")

    def test_one_crashing_project_does_not_starve_the_rest_of_the_tick(self):
        (self.root / "aaa-crash.mpp").write_bytes(OLE2_MAGIC + b"\x00" * 64)
        (self.root / ("%s.mpp" % PROJECT)).write_bytes(OLE2_MAGIC + b"\x00" * 64)
        self.state.projects["aaa-crash"] = {"id": "aaa-crash",
                                            "organization_id": ORG}
        real_execute = ScriptedCursor.execute

        async def sabotaged(cursor, sql, params=None):
            if params and params[0] == "aaa-crash" and "INSERT INTO msp_snapshots" in sql:
                raise RuntimeError("driver fell over")
            return await real_execute(cursor, sql, params)

        self.state.fail_on = None
        original = ScriptedCursor.execute
        ScriptedCursor.execute = sabotaged
        try:
            outcomes = self.tick(parsed_project([task(1)], [], []))
        finally:
            ScriptedCursor.execute = original
        self.assertEqual(2, len(outcomes))
        self.assertEqual("completed", outcomes[1]["status"],
                         "terrace still imported after aaa-crash blew up")

    def test_one_broken_project_does_not_stop_the_others(self):
        (self.root / "aaa-broken.mpp").write_bytes(b"not ole2 at all" + b"\x00" * 40)
        (self.root / ("%s.mpp" % PROJECT)).write_bytes(OLE2_MAGIC + b"\x00" * 64)
        self.state.projects["aaa-broken"] = {"id": "aaa-broken",
                                             "organization_id": ORG}
        outcomes = self.tick(parsed_project([task(1)], [], []))
        self.assertEqual(["failed", "completed"],
                         [o.get("status") for o in outcomes])
        self.assertEqual("MPP_FORMAT_UNSUPPORTED", outcomes[0]["reason"])


class MappingScopeValidatorTests(unittest.TestCase):
    """The service-level half of cross-project protection, on a scripted cursor."""

    class Cursor:
        def __init__(self, row):
            self.row = row

        async def execute(self, sql, params=None):
            pass

        async def fetchone(self):
            return self.row

    def check(self, row):
        return run(validate_mapping_scope(self.Cursor(row), 1, "res-1"))

    def test_matching_scope_passes(self):
        self.assertIsNone(self.check(
            {"task_project": "terrace", "task_org": ORG,
             "resource_project": "terrace", "resource_org": ORG}))

    def test_a_different_project_is_named(self):
        self.assertEqual(
            "task and finance resource belong to different projects",
            self.check({"task_project": "terrace", "task_org": ORG,
                        "resource_project": "bridge", "resource_org": ORG}))

    def test_a_different_organization_is_named(self):
        self.assertEqual(
            "task and finance resource belong to different organizations",
            self.check({"task_project": "terrace", "task_org": ORG,
                        "resource_project": "terrace", "resource_org": OTHER_ORG}))

    def test_a_vanished_row_fails_closed(self):
        self.assertEqual("task or resource does not exist", self.check(None))


if __name__ == "__main__":
    unittest.main()
