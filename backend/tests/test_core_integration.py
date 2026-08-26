# -*- coding: utf-8 -*-
"""The Core integration adapters, and the demo target gate that protects the Main database.

WHY THESE RUN WITHOUT A DATABASE
The suite has to pass on a machine with no PostgreSQL, so the adapters are exercised
against a fake connection that records the SQL it is given and replays programmed rows.
That is enough to test everything these adapters actually decide -- scope handling,
fail-closed refusals, identifier namespacing, what is and is not reported -- because the
decisions live in Python and in the shape of the SQL, not in the rows.

Two things a fake cannot prove, so they are covered another way:

  * that the SQL is valid and means what it says -- proved by running the whole set against
    a real PostgreSQL in `scripts/demo/prepare.py` plus the integration proof;
  * that the scope predicates are present at all -- asserted here directly against the
    query text, because a fake will happily return rows for a query that forgot its WHERE
    clause, and that particular omission is a cross-tenant leak.
"""

import re
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint import activities as core_activities
from coreint import progress as core_progress
from coreint import security as core_security
from scripts.demo import target as demo_target

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"


# --------------------------------------------------------------------------- test doubles
class FakeCursor:
    def __init__(self, answer, log):
        self._answer, self._log, self._rows = answer, log, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        self._log.append((str(sql), params))
        self._rows = self._answer(str(sql), params or {})

    async def fetchall(self):
        return list(self._rows)

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    """Answers queries from a callable, and remembers every statement it was given."""

    def __init__(self, answer):
        self._answer, self.log = answer, []

    def cursor(self, **_kwargs):
        return FakeCursor(self._answer, self.log)


def answering(**by_keyword):
    """Route a query to rows by the first keyword found in it."""
    def answer(sql, _params):
        for keyword, rows in by_keyword.items():
            if keyword in sql:
                return [dict(row) for row in rows]
        return []
    return answer


def context(user=USER, organization=ORG, project=PROJECT):
    return SimpleNamespace(user_id=user, organization_id=organization, project_id=project)


# --------------------------------------------------------------------------- permissions
class EffectivePermissionTests(unittest.IsolatedAsyncioTestCase):
    async def codes(self, rows, **kwargs):
        connection = FakeConnection(answering(WITH=rows))
        return await core_security.effective_permission_codes(
            connection, kwargs.get("user", USER), kwargs.get("organization", ORG), PROJECT)

    async def test_it_returns_what_core_grants(self):
        self.assertEqual({"finance.view", "finance.edit"},
                         set(await self.codes([{"code": "finance.view"},
                                               {"code": "finance.edit"}])))

    async def test_a_code_core_does_not_have_is_simply_absent(self):
        """`finance_report.issue` is the live case, and the reason issuing is refused."""
        granted = await self.codes([{"code": "finance.view"}, {"code": "finance_report.view"},
                                    {"code": "finance_report.export"}])
        self.assertNotIn("finance_report.issue", granted)

    async def test_a_malformed_code_is_dropped_rather_than_breaking_every_request(self):
        """AuthContext rejects a code it cannot parse, and would reject the whole context.

        One bad catalogue row would then be a total outage. Dropping it can only deny, so
        the failure mode of dropping is strictly safer than the failure mode of raising.
        """
        granted = await self.codes([{"code": "finance.view"}, {"code": "Finance.Edit"},
                                    {"code": "no_dot"}, {"code": None}])
        self.assertEqual({"finance.view"}, set(granted))

    async def test_nothing_granted_is_an_empty_set_not_an_error(self):
        self.assertEqual(frozenset(), await self.codes([]))

    def test_the_query_scopes_every_role_row(self):
        """The predicate that stops a role in another tenant from granting anything here.

        Asserted against the text because a fake connection returns whatever it is told
        regardless of the WHERE clause, and this clause going missing is exactly the bug
        that would not show up in a behavioural test with a cooperative double.
        """
        sql = core_security.EFFECTIVE_PERMISSIONS
        self.assertIn("assignment.organization_id = %(organization_id)s", sql)
        self.assertIn("assignment.project_id = %(project_id)s", sql)
        self.assertIn("organization_id IS NULL", sql)
        self.assertIn("project_id IS NULL", sql)

    def test_the_query_lets_an_explicit_denial_win(self):
        sql = core_security.EFFECTIVE_PERMISSIONS
        self.assertIn("WHERE NOT allowed", sql)
        self.assertIn("code NOT IN (SELECT code FROM override WHERE NOT allowed)", sql)
        # The grant side of an override adds; without this a positive override would be
        # collected and then never applied.
        self.assertIn("SELECT code FROM override WHERE allowed", sql)

    def test_only_active_roles_count(self):
        self.assertIn("role.is_active", core_security.EFFECTIVE_PERMISSIONS)


class PermissionGateTests(unittest.IsolatedAsyncioTestCase):
    async def require(self, rows, code):
        gate = core_security.CoreRbacPermissionAuthorizer(FakeConnection(answering(WITH=rows)))
        await gate.require(context(), code)

    async def test_a_granted_permission_passes(self):
        await self.require([{"code": "finance.view"}], "finance.view")

    async def test_a_missing_permission_is_refused_with_403(self):
        with self.assertRaises(Exception) as caught:
            await self.require([{"code": "finance.view"}], "finance_report.issue")
        self.assertEqual(403, caught.exception.status_code)
        self.assertIn("finance_report.issue", caught.exception.detail)

    async def test_it_asks_the_database_rather_than_trusting_the_context(self):
        """The two gates are meant to be independent.

        A context claiming a permission Core does not grant must still be refused, or the
        permission gate is only re-reading whatever the auth adapter decided earlier.
        """
        claiming = context()
        claiming.permission_codes = ("finance.edit",)
        gate = core_security.CoreRbacPermissionAuthorizer(FakeConnection(answering(WITH=[])))
        with self.assertRaises(Exception):
            await gate.require(claiming, "finance.edit")


# --------------------------------------------------------------------------- membership
class ScopeGateTests(unittest.IsolatedAsyncioTestCase):
    def gate(self, rows):
        return core_security.CoreScopeAuthorizer(
            FakeConnection(answering(organization_memberships=rows, project_memberships=rows)))

    async def test_a_member_is_admitted(self):
        await self.gate([{"?column?": 1}]).require_organization(context(), str(ORG))
        await self.gate([{"?column?": 1}]).require_project(context(), str(ORG), PROJECT)

    async def test_a_non_member_is_refused(self):
        for call in ("require_organization", "require_project"):
            with self.subTest(call):
                arguments = (context(), str(ORG)) if call == "require_organization" else (
                    context(), str(ORG), PROJECT)
                with self.assertRaises(Exception) as caught:
                    await getattr(self.gate([]), call)(*arguments)
                self.assertEqual(403, caught.exception.status_code)

    async def test_a_context_for_another_organization_is_refused_before_any_query(self):
        """No row can make this legitimate, so it never reaches the database."""
        connection = FakeConnection(answering(organization_memberships=[{"?column?": 1}],
                                              project_memberships=[{"?column?": 1}]))
        gate = core_security.CoreScopeAuthorizer(connection)
        with self.assertRaises(Exception):
            await gate.require_organization(context(organization=OTHER_ORG), str(ORG))
        with self.assertRaises(Exception):
            await gate.require_project(context(organization=OTHER_ORG), str(ORG), PROJECT)
        self.assertEqual([], connection.log)

    def test_the_project_query_joins_projects_to_pin_the_organization(self):
        """`project_memberships` records no organization of its own.

        Without the join, a membership in project P satisfies a request naming organization
        B -- a cross-organization read through an otherwise valid row.
        """
        sql = core_security.CoreScopeAuthorizer.PROJECT
        self.assertIn("JOIN projects", sql)
        self.assertIn("project.organization_id = %(organization_id)s", sql)

    def test_nothing_reads_the_contact_directory_tables(self):
        """`organization_members` and `project_members` allow a NULL user_id.

        A row describing somebody with no account cannot be an authorization decision, so
        neither table is read anywhere in this package.
        """
        source = "".join(
            (BACKEND_ROOT / "coreint" / name).read_text(encoding="utf-8")
            for name in ("security.py", "progress.py", "activities.py"))
        code = re.sub(r'""".*?"""', "", source, flags=re.S)
        code = re.sub(r"#.*", "", code)
        for table in ("organization_members", "project_members"):
            with self.subTest(table):
                self.assertNotIn(f"FROM {table}", code)
                self.assertNotIn(f"JOIN {table}", code)


class ScopedRoleTests(unittest.IsolatedAsyncioTestCase):
    async def roles(self, user_role_rows, membership):
        def answer(sql, _params):
            if "project_id IS NULL" in sql:
                return [dict(row) for row in user_role_rows.get("organization", [])]
            if "assignment.project_id = %(project_id)s" in sql:
                return [dict(row) for row in user_role_rows.get("project", [])]
            return [dict(membership)]
        return await core_security.scoped_roles(FakeConnection(answer), USER, ORG, PROJECT)

    async def test_the_rbac_role_is_preferred(self):
        organization, project = await self.roles(
            {"organization": [{"code": "org_chief"}], "project": [{"code": "project_admin"}]},
            {"organization_role": "org_admin", "project_role": "editor"})
        self.assertEqual(("org_chief", "project_admin"), (organization, project))

    async def test_org_chief_passes_through_unchanged(self):
        """Finance's settings policy compares against this exact string.

        `org_chief` was verified to exist in Core's `roles` table, so it is carried across
        as-is. A translation layer would be a second vocabulary to keep in step.
        """
        organization, _ = await self.roles(
            {"organization": [{"code": "org_chief"}]}, {"organization_role": None,
                                                        "project_role": None})
        self.assertEqual("org_chief", organization)

    async def test_the_membership_role_is_the_fallback(self):
        organization, project = await self.roles(
            {}, {"organization_role": "finance_viewer", "project_role": "viewer"})
        self.assertEqual(("finance_viewer", "viewer"), (organization, project))

    async def test_a_member_with_no_role_is_still_named(self):
        """AuthContext requires a non-empty role, and membership was already proven."""
        self.assertEqual((core_security.UNNAMED_ROLE, core_security.UNNAMED_ROLE),
                         await self.roles({}, {"organization_role": None, "project_role": None}))

    def test_org_chief_sorts_first_so_the_answer_does_not_depend_on_luck(self):
        self.assertIn("(role.code = 'org_chief') DESC", core_security.ORGANIZATION_ROLES)


# --------------------------------------------------------------------------- progress
SNAPSHOT_ROW = {
    "id": 9003, "project_id": PROJECT, "file_version_id": 1003, "snapshot_type": "ACTUAL",
    "previous_snapshot_id": 9002, "source_filename": "v3.mpp",
    "status_date_jalali": "1405-05-11", "created_by": USER,
    "created_at": datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc),
    "organization_id": ORG, "original_filename": "sample-progress-v3.mpp",
    "version_number": 3, "superseded": False,
}

TASK_ROW = {
    "id": 5, "uid": 1, "guid": "task-foundation", "task_id": 1, "name": "اجرای فونداسیون",
    "wbs": "1.2", "outline_number": "1.2", "outline_level": 2,
    "start": "2026-06-01", "finish": "2026-08-30",
    "percent_complete": Decimal("25.0000"), "percent_work_complete": Decimal("40.0000"),
    "physical_percent_complete": None, "text1": "ACT-102",
}


def progress_connection(snapshot=SNAPSHOT_ROW, tasks=(TASK_ROW,)):
    def answer(sql, _params):
        if "FROM msp_tasks" in sql:
            return [dict(row) for row in tasks]
        return [dict(snapshot)] if snapshot else []
    return FakeConnection(answer)


class ProgressHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def feed(self, **kwargs):
        provider = core_progress.CoreProgressSnapshotProvider(progress_connection(**kwargs))
        return await provider.get_snapshot(str(ORG), PROJECT, "9003")

    async def test_the_header_answers_with_the_identifier_it_was_asked_with(self):
        """Finance verifies the header against the id it sent.

        It asks with `host_snapshot_id` whenever the reference row has one, so the header
        has to echo the Core bigint -- not a Finance UUID, which this provider has never
        seen and does not mint.
        """
        header = (await self.feed())["snapshot"]
        self.assertEqual("9003", header["progressSnapshotId"])
        self.assertEqual(9003, header["hostSnapshotId"])
        self.assertEqual(1003, header["hostFileVersionId"])
        self.assertIsNone(header["sourceFileVersionId"])

    async def test_freshness_comes_from_lineage_not_from_snapshot_type(self):
        ready = (await self.feed())["snapshot"]
        self.assertEqual("ready", ready["status"])
        replaced = (await self.feed(snapshot={**SNAPSHOT_ROW, "superseded": True}))["snapshot"]
        self.assertEqual("superseded", replaced["status"])
        # The type is reported separately and never decides the status: all three Core
        # types describe what a snapshot *is*, not whether it is still current.
        self.assertEqual("ACTUAL", replaced["snapshotType"])

    async def test_a_target_baseline_is_not_a_progress_report(self):
        provider = core_progress.CoreProgressSnapshotProvider(progress_connection())
        self.assertNotIn("TARGET", provider._progress_types)
        self.assertEqual(("ACTUAL", "RESCHEDULED"), core_progress.PROGRESS_SNAPSHOT_TYPES)

    async def test_the_reporting_date_prefers_the_planner_status_date(self):
        header = (await self.feed())["snapshot"]
        self.assertEqual("2026-08-02", header["reportingDate"])

    async def test_an_absent_or_broken_status_date_falls_back_to_the_upload_date(self):
        for value in (None, "", "not-a-date", "1405-99-99"):
            with self.subTest(value=value):
                header = (await self.feed(
                    snapshot={**SNAPSHOT_ROW, "status_date_jalali": value}))["snapshot"]
                self.assertEqual("2026-08-03", header["reportingDate"])

    async def test_the_source_type_says_the_file_was_an_mpp(self):
        from app.finance.domain.schedule import SOURCE_TYPES
        header = (await self.feed())["snapshot"]
        self.assertIn(header["sourceType"], SOURCE_TYPES)
        self.assertEqual("mpp", header["sourceType"])


class ProgressRowTests(unittest.IsolatedAsyncioTestCase):
    async def rows(self, tasks):
        provider = core_progress.CoreProgressSnapshotProvider(progress_connection(tasks=tasks))
        return (await provider.get_snapshot(str(ORG), PROJECT, "9003"))["assignments"]

    async def test_no_assignment_is_invented(self):
        """Core has no assignment table. Reporting one would fabricate a link."""
        self.assertIsNone((await self.rows((TASK_ROW,)))[0]["assignmentExternalId"])

    async def test_no_resource_or_quantity_is_invented(self):
        row = (await self.rows((TASK_ROW,)))[0]
        for field in ("resourceExternalId", "resourceName", "resourceType", "unit",
                      "plannedQuantity", "actualQuantity", "remainingQuantity",
                      "plannedWork", "actualWork", "remainingWork"):
            with self.subTest(field):
                self.assertIsNone(row[field])

    async def test_effort_is_not_passed_off_as_an_assignment_percentage(self):
        """`percent_work_complete` measures effort, not a share of a physical quantity.

        Feeding it into `assignmentWorkCompletePercent` would multiply it by a planned
        quantity and produce a measured-looking number -- the same work-versus-quantity
        conflation `domain/progress.py` was changed to stop making.
        """
        row = (await self.rows((TASK_ROW,)))[0]
        self.assertIsNone(row["assignmentWorkCompletePercent"])
        self.assertNotEqual("40.0000", row["task"]["taskProgressPercent"])

    async def test_physical_progress_wins_over_elapsed_duration(self):
        physical = {**TASK_ROW, "physical_percent_complete": Decimal("18.0000")}
        self.assertEqual("18.0000", (await self.rows((physical,)))[0]["task"]["taskProgressPercent"])
        self.assertEqual("25.0000", (await self.rows((TASK_ROW,)))[0]["task"]["taskProgressPercent"])

    async def test_finance_reports_such_a_line_as_missing_rather_than_zero(self):
        """The end of the chain, stated here so the consequence is visible in one place."""
        from app.finance.domain.progress import resolve_progress_quantity
        with self.assertRaises(ValueError):
            resolve_progress_quantity((await self.rows((TASK_ROW,)))[0])

    async def test_the_activity_code_falls_back_through_documented_fields(self):
        cases = ((TASK_ROW, "ACT-102"),
                 ({**TASK_ROW, "text1": None}, "1.2"),
                 ({**TASK_ROW, "text1": "  "}, "1.2"),
                 ({**TASK_ROW, "text1": None, "outline_number": None}, "1.2"),
                 ({**TASK_ROW, "text1": None, "outline_number": None, "wbs": None}, None))
        for task, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, core_progress.activity_code(task))

    def test_task_identity_never_comes_from_the_name(self):
        """A name changes when somebody fixes a typo. That is not identity."""
        self.assertEqual("task-foundation", core_progress.task_external_id(TASK_ROW))
        self.assertEqual("1", core_progress.task_external_id({**TASK_ROW, "guid": None}))
        self.assertEqual("msp-task-5", core_progress.task_external_id(
            {**TASK_ROW, "guid": None, "uid": None, "task_id": None}))


class ProgressLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_finance_uuid_is_not_a_core_identifier(self):
        """Answering "not found" is correct: this provider never issued that id."""
        provider = core_progress.CoreProgressSnapshotProvider(progress_connection())
        for value in ("33333333-3333-4333-8333-333333333333", "", None, "abc", "0", "-3", True):
            with self.subTest(value=value):
                self.assertIsNone(await provider.get_snapshot(str(ORG), PROJECT, value))

    async def test_a_miss_is_none_rather_than_an_empty_header(self):
        """An empty header claims to describe a snapshot and then describes none.

        Finance rejects both shapes, but a provider that returns one teaches the wrong
        pattern -- that was how a scope miss used to surface as a 500.
        """
        provider = core_progress.CoreProgressSnapshotProvider(progress_connection(snapshot=None))
        self.assertIsNone(await provider.get_snapshot(str(ORG), PROJECT, "9003"))
        self.assertIsNone(await provider.current_snapshot(str(ORG), PROJECT, None))

    async def test_every_snapshot_query_actually_pins_the_organization(self):
        """Asserted against the SQL that ran, not against the shared prefix.

        `SNAPSHOT_COLUMNS` is a fragment and each call site appends its own WHERE clause, so
        a constant-level check would pass while one of those call sites had no organization
        predicate at all. Inspecting what was executed is the only version of this test that
        can fail for the reason it exists.
        """
        connection = progress_connection()
        provider = core_progress.CoreProgressSnapshotProvider(connection)
        await provider.get_snapshot(str(ORG), PROJECT, "9003")
        await provider.current_snapshot(str(ORG), PROJECT, None)

        activity_connection = FakeConnection(
            lambda sql, _p: [] if "FROM msp_tasks" in sql else [{"id": 9003}])
        await core_activities.CoreProjectActivityProvider(
            activity_connection).list_activities(str(ORG), PROJECT)

        # Matched on the outer FROM's alias. Plain "FROM msp_snapshots" would also catch
        # the correlated EXISTS that computes `superseded`, which is a subquery inside the
        # same statement rather than a call site of its own.
        snapshot_queries = [(sql, params) for sql, params in
                            connection.log + activity_connection.log
                            if "FROM msp_snapshots AS snapshot" in sql]
        self.assertEqual(3, len(snapshot_queries), "one per call site, all covered")
        for sql, params in snapshot_queries:
            with self.subTest(sql=" ".join(sql.split())[:60]):
                self.assertIn("JOIN projects", sql)
                self.assertIn("project.organization_id = %(organization_id)s", sql)
                self.assertEqual(str(ORG), params["organization_id"])
                self.assertIn("snapshot.project_id = %(project_id)s", sql)

    async def test_current_snapshot_will_not_return_one_reporting_after_the_asked_date(self):
        provider = core_progress.CoreProgressSnapshotProvider(progress_connection())
        self.assertIsNone(await provider.current_snapshot(str(ORG), PROJECT, date(2026, 7, 1)))
        found = await provider.current_snapshot(str(ORG), PROJECT, date(2026, 8, 2))
        self.assertEqual(9003, found["snapshot"]["hostSnapshotId"])

    def test_the_adapters_only_ever_read(self):
        for name in ("progress.py", "activities.py", "security.py"):
            source = (BACKEND_ROOT / "coreint" / name).read_text(encoding="utf-8")
            code = re.sub(r'""".*?"""', "", source, flags=re.S)
            code = re.sub(r"#.*", "", code)
            for statement in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER ",
                              "DROP ", "TRUNCATE ", "GRANT ", "REVOKE "):
                with self.subTest(name=name, statement=statement.strip()):
                    self.assertNotIn(statement, code.upper())


# --------------------------------------------------------------------------- activities
class ActivityTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, tasks=(TASK_ROW,), snapshot=SNAPSHOT_ROW):
        def answer(sql, _params):
            if "FROM msp_tasks" in sql:
                return [dict(row) for row in tasks]
            return [{"id": 9003}] if snapshot else []
        return core_activities.CoreProjectActivityProvider(FakeConnection(answer))

    async def test_activities_are_the_newest_snapshot_tasks(self):
        rows, total = await self.provider().list_activities(str(ORG), PROJECT)
        self.assertEqual(1, total)
        self.assertEqual("ACT-102", rows[0]["activityExternalId"])
        self.assertEqual("task-foundation", rows[0]["taskExternalId"])

    async def test_a_project_with_no_snapshot_has_no_activities(self):
        """Not an error. There genuinely is no breakdown yet."""
        self.assertEqual(([], 0), await self.provider(snapshot=None).list_activities(str(ORG), PROJECT))

    async def test_one_code_on_several_tasks_yields_one_activity(self):
        second = {**TASK_ROW, "id": 6, "guid": "task-foundation-b", "outline_number": "1.3"}
        rows, total = await self.provider(tasks=(TASK_ROW, second)).list_activities(str(ORG), PROJECT)
        self.assertEqual(1, total)
        self.assertEqual("task-foundation", rows[0]["taskExternalId"])

    async def test_a_task_with_no_code_is_not_an_activity(self):
        blank = {**TASK_ROW, "text1": None, "outline_number": None, "wbs": None}
        self.assertEqual(([], 0), await self.provider(tasks=(blank,)).list_activities(str(ORG), PROJECT))

    async def test_it_matches_the_response_contract_exactly(self):
        """`ActivityResponse` forbids extra fields, so a stray key is a 500 at the router."""
        from app.finance.schemas.activities import ActivityResponse
        rows, _ = await self.provider().list_activities(str(ORG), PROJECT)
        ActivityResponse.model_validate(rows[0])

    async def test_get_activity_finds_and_misses(self):
        provider = self.provider()
        self.assertIsNotNone(await provider.get_activity(str(ORG), PROJECT, "ACT-102"))
        self.assertIsNone(await provider.get_activity(str(ORG), PROJECT, "ACT-999"))

    def test_creating_an_activity_is_not_offered(self):
        """Absent rather than raising: `FinanceResourcesService` checks with hasattr and
        already answers `ActivityProviderUnavailable`, which is the right refusal."""
        self.assertFalse(hasattr(core_activities.CoreProjectActivityProvider, "create_activity"))


# --------------------------------------------------------------------------- the demo gate
class DemoTargetTests(unittest.TestCase):
    """The guard standing between a demo script and the production database."""

    DEMO = "postgresql://postgres@127.0.0.1:5432/bambo_finance_integration_demo"

    def test_the_approved_local_target_is_accepted(self):
        self.assertEqual(("127.0.0.1", 5432, demo_target.DEMO_DATABASE),
                         demo_target.assert_dsn_targets_demo(self.DEMO))

    def test_the_main_server_is_refused_by_name(self):
        for dsn in ("postgresql://u@192.168.100.200:5432/bambo",
                    "postgresql://u@192.168.100.200:5432/bambo_finance_integration_demo"):
            with self.subTest(dsn=dsn):
                with self.assertRaises(demo_target.UnsafeTarget) as caught:
                    demo_target.assert_dsn_targets_demo(dsn)
                self.assertIn("Main/Core", str(caught.exception))

    def test_the_main_database_is_refused_even_on_loopback(self):
        """A tunnel makes the production database answer on 127.0.0.1."""
        with self.assertRaises(demo_target.UnsafeTarget):
            demo_target.assert_dsn_targets_demo("postgresql://u@127.0.0.1:5432/bambo")

    def test_any_other_database_is_refused(self):
        with self.assertRaises(demo_target.UnsafeTarget):
            demo_target.assert_dsn_targets_demo("postgresql://u@127.0.0.1:5432/something_else")

    def test_the_maintenance_database_is_the_only_widening_and_only_when_asked(self):
        maintenance = "postgresql://postgres@127.0.0.1:5432/postgres"
        with self.assertRaises(demo_target.UnsafeTarget):
            demo_target.assert_dsn_targets_demo(maintenance)
        demo_target.assert_dsn_targets_demo(maintenance, allow_maintenance=True)
        # Widening the database must not widen the host.
        with self.assertRaises(demo_target.UnsafeTarget):
            demo_target.assert_dsn_targets_demo(
                "postgresql://u@192.168.100.200:5432/postgres", allow_maintenance=True)

    def test_a_different_port_is_refused(self):
        with self.assertRaises(demo_target.UnsafeTarget):
            demo_target.assert_dsn_targets_demo(
                "postgresql://u@127.0.0.1:55432/bambo_finance_integration_demo")

    def test_the_server_gate_refuses_what_the_server_says_it_is(self):
        """The check that survives a tunnel: the DSN is a claim, this is an answer."""
        class Server:
            def __init__(self, row):
                self._row = row

            def execute(self, _sql):
                return SimpleNamespace(fetchone=lambda: self._row)

        good = {"database": demo_target.DEMO_DATABASE, "host": "127.0.0.1", "port": 5432,
                "usr": "postgres", "version": "PostgreSQL 16"}
        demo_target.assert_server_is_demo(Server(good))
        for bad in ({**good, "database": "bambo"}, {**good, "host": "192.168.100.200"},
                    {**good, "port": 55432}, {**good, "database": "postgres"}):
            with self.subTest(bad=bad):
                with self.assertRaises(demo_target.UnsafeTarget):
                    demo_target.assert_server_is_demo(Server(bad))

    def test_no_credential_is_written_into_the_demo_scripts(self):
        for name in ("prepare.py", "target.py", "seed_core_mirror.py",
                     "generate_core_mirror.py"):
            source = (BACKEND_ROOT / "scripts" / "demo" / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIsNone(re.search(r"://[^/\s\"']*:[^/@\s\"']+@", source),
                                  "a connection string with a password appears in the script")


# --------------------------------------------------------------------------- host wiring
class DevelopmentHostWiringTests(unittest.TestCase):
    """Which set of adapters the development host installs, and when.

    `wire()` is called directly with a stand-in connection rather than by starting the host,
    because starting it would need a database and this is a question about wiring.
    """

    def wired(self, core):
        from fastapi import FastAPI
        from devhost.app import wire
        application = FastAPI()
        wire(application, FakeConnection(answering()), BACKEND_ROOT / "build" / "storage",
             core)
        return application.state

    def test_without_a_core_database_the_static_fixtures_are_used(self):
        """The previous behaviour, unchanged. Absent configuration changes nothing."""
        from devhost.ports import (ContextPermissionAuthorizer, SeededActivityProvider,
                                   SeededProgressSnapshotProvider,
                                   SingleTenantScopeAuthorizer, StaticAuthContextProvider)
        state = self.wired(None)
        self.assertIsInstance(state.auth_context_provider, StaticAuthContextProvider)
        self.assertIsInstance(state.scope_authorizer, SingleTenantScopeAuthorizer)
        self.assertIsInstance(state.permission_authorizer, ContextPermissionAuthorizer)
        self.assertIsInstance(state.progress_service.provider, SeededProgressSnapshotProvider)
        self.assertIsInstance(state.finance_resources_service._activity_provider,
                              SeededActivityProvider)

    def test_with_a_core_database_every_security_port_is_core_backed(self):
        state = self.wired(FakeConnection(answering()))
        self.assertIsInstance(state.auth_context_provider,
                              core_security.CoreAuthContextAssembler)
        self.assertIsInstance(state.scope_authorizer, core_security.CoreScopeAuthorizer)
        self.assertIsInstance(state.permission_authorizer,
                              core_security.CoreRbacPermissionAuthorizer)
        self.assertIsInstance(state.progress_service.provider,
                              core_progress.CoreProgressSnapshotProvider)
        self.assertIsInstance(state.finance_resources_service._activity_provider,
                              core_activities.CoreProjectActivityProvider)

    def test_the_eleven_finance_services_are_the_same_either_way(self):
        """The point of the port boundary: swapping the host changes no finance service."""
        static, cored = self.wired(None), self.wired(FakeConnection(answering()))
        # FastAPI's State keeps its attributes in `_state`, so vars() sees only that dict.
        names = [name for name in static._state if name.startswith("finance_")
                 or name in ("progress_service", "invoice_service", "unit_conversion_service")]
        self.assertEqual(11, len(names))
        for name in names:
            with self.subTest(name):
                self.assertIs(type(getattr(static, name)), type(getattr(cored, name)))

    def test_the_demo_user_header_exists_only_in_the_development_host(self):
        """It is a demonstration switch on a host that never authenticated anybody.

        It must not appear anywhere in the deployable library, where accepting identity from
        a request header would be an authentication bypass rather than a fixture.
        """
        from devhost.app import DEMO_USER_HEADER
        self.assertEqual("X-Demo-User", DEMO_USER_HEADER)
        for path in (BACKEND_ROOT / "app").rglob("*.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("X-Demo-User", path.read_text(encoding="utf-8"))
        for path in (BACKEND_ROOT / "coreint").rglob("*.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("X-Demo-User", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
