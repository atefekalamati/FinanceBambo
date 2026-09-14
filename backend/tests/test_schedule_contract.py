"""The schedule contract, its identifiers, its versioning, and the synthetic source.

Everything here runs on synthetic data. Nothing in this file reads a schedule file,
touches a database, or asserts anything about production — the point is to pin the
boundary Finance depends on, so that when a real source is written there is something for
it to satisfy.

Two behaviours are asserted by omission as much as by assertion: the synthetic source
never fills a quantity it was not given, and no code path here parses anything.
"""

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.adapters.schedule_ports import (
    MppAdapterNotAvailable, MppScheduleAdapter, ProgressSourceAdapter)
from app.finance.domain.external_ids import (
    ExternalIdentifierError, activity_external_id, assignment_external_id, is_conventional)
from app.finance.domain.schedule import (
    ProgressSnapshotInput, SnapshotAssignment, SnapshotTask, derive_snapshot_versions,
    mark_active_source)
from app.finance.schemas.progress import ProgressSnapshotResponse
from app.finance.security.context import AuthContext
from app.finance.services.progress import ProgressService
from app.main import create_app
from devhost.synthetic_progress import (
    SyntheticAdapterRefused, SyntheticProgressSourceAdapter, assert_development_only)

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"
SCOPE = SimpleNamespace(organization_id=ORG, project_id=PROJECT, actor_user_id=ACTOR)

SNAP_1 = UUID("33333333-3333-4333-8333-333333333331")
SNAP_2 = UUID("33333333-3333-4333-8333-333333333332")
SNAP_3 = UUID("33333333-3333-4333-8333-333333333333")


def ref(snapshot_id, reporting_day, imported_day):
    return {"organization_id": ORG, "project_id": PROJECT, "progress_snapshot_id": snapshot_id,
            "source_file_version_id": UUID(int=1), "source_file_name_safe": "schedule.mpp",
            "imported_at": f"2026-08-{imported_day:02d}T08:30:00Z", "imported_by": ACTOR,
            "status": "ready", "reporting_date": date(2026, 7, reporting_day),
            "source_type": "microsoft_project" if reporting_day > 1 else None}


# Newest first, exactly as the repository returns them.
REFS = [ref(SNAP_3, 3, 3), ref(SNAP_2, 2, 2), ref(SNAP_1, 1, 1)]


class ExternalIdentifierTests(unittest.TestCase):
    def test_the_convention_is_applied_in_one_place(self):
        self.assertEqual("ACT-100", activity_external_id("100"))
        self.assertEqual("ASG-1001", assignment_external_id(1001))

    def test_a_uid_is_required_and_a_blank_one_is_refused(self):
        for missing in (None, "", "   "):
            with self.assertRaises(ExternalIdentifierError):
                activity_external_id(missing)

    def test_a_boolean_is_not_a_uid(self):
        # bool subclasses int, so True would otherwise become "ACT-1" and collide with
        # the real task 1.
        with self.assertRaises(ExternalIdentifierError):
            assignment_external_id(True)

    def test_a_uid_containing_a_separator_is_refused(self):
        # "ACT-1-2" could not be split back apart, and a space would not survive a URL.
        for hostile in ("1 2", "1/2", "a,b", "1	2"):
            with self.assertRaises(ExternalIdentifierError):
                activity_external_id(hostile)

    def test_conventional_ids_are_recognised_without_being_enforced(self):
        self.assertTrue(is_conventional("ACT-100"))
        self.assertTrue(is_conventional("ASG-1001"))
        # Values that predate any convention report False rather than raising: this is a
        # counter for a future production audit, not a validator.
        self.assertFalse(is_conventional("ACT-FOUNDATION-1 "))
        self.assertFalse(is_conventional("act-100"))
        self.assertFalse(is_conventional(None))
        self.assertFalse(is_conventional("100"))


class ScheduleContractTests(unittest.TestCase):
    def test_a_source_may_leave_everything_but_identity_unknown(self):
        task = SnapshotTask(task_external_id="ACT-100")
        self.assertIsNone(task.baseline_start)
        self.assertIsNone(task.percent_complete)
        # None means "the source did not say", which a reader can tell from a real zero.
        self.assertNotEqual(Decimal(0), task.percent_complete)

    def test_an_assignment_with_only_effort_leaves_quantity_unknown(self):
        assignment = SnapshotAssignment(
            assignment_external_id="ASG-1002", task_external_id="ACT-200",
            actual_work=Decimal("48.0000"))
        self.assertEqual(Decimal("48.0000"), assignment.actual_work)
        self.assertIsNone(assignment.actual_quantity)

    def test_the_contract_is_frozen_so_a_snapshot_cannot_be_edited_in_place(self):
        task = SnapshotTask(task_external_id="ACT-100")
        with self.assertRaises(Exception):
            task.percent_complete = Decimal("50")

    def test_an_assignment_pointing_at_an_absent_task_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            ProgressSnapshotInput(
                organization_id=ORG, project_id=PROJECT, reporting_date=date(2026, 6, 1),
                source_type="synthetic",
                tasks=(SnapshotTask(task_external_id="ACT-100"),),
                assignments=(SnapshotAssignment(assignment_external_id="ASG-9",
                                                task_external_id="ACT-999"),))
        self.assertIn("ASG-9", str(caught.exception))

    def test_an_unknown_source_type_is_refused(self):
        with self.assertRaises(ValueError):
            ProgressSnapshotInput(organization_id=ORG, project_id=PROJECT,
                                  reporting_date=date(2026, 6, 1), source_type="guesswork")


class SnapshotVersioningTests(unittest.TestCase):
    def test_versions_number_the_history_oldest_first(self):
        versioned = derive_snapshot_versions(REFS)
        self.assertEqual([3, 2, 1], [row["version"] for row in versioned])
        self.assertEqual([True, False, False], [row["is_latest"] for row in versioned])

    def test_a_new_snapshot_does_not_renumber_the_first_one(self):
        # The whole point of deriving from an append-only table: snapshot 1 is version 1
        # before and after snapshot 2 arrives, so a report pinned to it stays pinned.
        first_pass = derive_snapshot_versions(REFS[2:])
        second_pass = derive_snapshot_versions(REFS[1:])
        third_pass = derive_snapshot_versions(REFS)
        for rows in (first_pass, second_pass, third_pass):
            oldest = [row for row in rows if row["progress_snapshot_id"] == SNAP_1][0]
            self.assertEqual(1, oldest["version"])

    def test_a_new_snapshot_does_not_alter_the_earlier_row(self):
        earlier = derive_snapshot_versions(REFS[2:])[0]
        later = [r for r in derive_snapshot_versions(REFS) if r["progress_snapshot_id"] == SNAP_1][0]
        self.assertEqual(earlier["reporting_date"], later["reporting_date"])
        self.assertEqual(earlier["source_file_version_id"], later["source_file_version_id"])
        # Only its position changed, and only in that it is no longer the latest.
        self.assertEqual((True, False), (earlier["is_latest"], later["is_latest"]))

    def test_derivation_never_mutates_the_rows_it_was_given(self):
        original = dict(REFS[0])
        derive_snapshot_versions(REFS)
        self.assertEqual(original, REFS[0])
        self.assertNotIn("version", REFS[0])

    def test_an_empty_history_produces_no_versions(self):
        self.assertEqual([], derive_snapshot_versions([]))


#: The project's own schedule, imported by Finance. Deliberately the OLDEST reporting date
#: here, because that is the shape the bug had in production: three snapshots ingested from
#: the host carried later dates than the one file the estimate is actually mapped to.
OURS = UUID(int=77)
THEIRS = UUID(int=1)
MIXED = [{**ref(SNAP_3, 3, 3), "source_file_name_safe": "AB11_V13.mpp"},
         {**ref(SNAP_2, 2, 2), "source_file_name_safe": "B10.mpp"},
         {**ref(SNAP_1, 1, 1), "source_file_version_id": OURS,
          "source_file_name_safe": "test_progress.mpp"}]


class ActiveSourceTests(unittest.TestCase):
    """Which snapshot is the project's own, as distinct from which arrived last."""

    def test_the_projects_own_schedule_is_marked_and_nothing_else_is(self):
        marked = mark_active_source(MIXED, OURS)
        self.assertEqual([False, False, True], [row["is_active_source"] for row in marked])
        self.assertEqual("test_progress.mpp",
                         next(r for r in marked if r["is_active_source"])["source_file_name_safe"])

    def test_the_active_source_is_not_the_same_question_as_the_latest(self):
        # Both flags on one list. The newest row is a snapshot of somebody else's file, and
        # a reader following `is_latest` to choose what to report on lands on it.
        marked = derive_snapshot_versions(mark_active_source(MIXED, OURS))
        latest = next(row for row in marked if row["is_latest"])
        active = next(row for row in marked if row["is_active_source"])
        self.assertNotEqual(latest["progress_snapshot_id"], active["progress_snapshot_id"])
        self.assertEqual("AB11_V13.mpp", latest["source_file_name_safe"])

    def test_a_project_that_has_imported_nothing_marks_nothing(self):
        marked = mark_active_source(MIXED, None)
        self.assertEqual([False, False, False], [row["is_active_source"] for row in marked])

    def test_a_host_snapshot_with_no_file_version_is_never_the_active_source(self):
        # Core-ingested rows carry no Finance file version. A null must not be read as
        # "matches whatever is active" -- that would flag every host row on the list.
        rows = [{**ref(SNAP_2, 2, 2), "source_file_version_id": None}]
        self.assertEqual([False], [r["is_active_source"] for r in mark_active_source(rows, OURS)])
        self.assertEqual([False], [r["is_active_source"] for r in mark_active_source(rows, None)])

    def test_the_comparison_survives_the_driver_returning_text(self):
        # psycopg gives UUIDs, a fake or an older column type gives strings. The same row
        # must not be the active source in one deployment and not in another.
        rows = [{**ref(SNAP_1, 1, 1), "source_file_version_id": str(OURS)}]
        self.assertTrue(mark_active_source(rows, OURS)[0]["is_active_source"])
        self.assertTrue(mark_active_source(rows, str(OURS))[0]["is_active_source"])

    def test_the_rows_handed_in_are_left_alone(self):
        original = dict(MIXED[0])
        mark_active_source(MIXED, OURS)
        self.assertEqual(original, MIXED[0])
        self.assertNotIn("is_active_source", MIXED[0])


class Repo:
    def __init__(self, refs=REFS, active=None):
        self.refs = refs
        self.active = active

    async def active_source_version(self, scope):
        """Which source version this project is running on, as the shared rule decides."""
        return self.active

    async def list_snapshots(self, scope):
        return [row for row in self.refs
                if row["organization_id"] == scope.organization_id
                and row["project_id"] == scope.project_id]


class ProgressSnapshotServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self, refs=REFS):
        return ProgressService(Repo(refs), provider=None)

    async def test_the_list_carries_the_derived_version(self):
        rows = await self.service().list_snapshots(SCOPE)
        self.assertEqual([3, 2, 1], [row["version"] for row in rows])

    async def test_one_snapshot_reports_the_same_version_as_the_list(self):
        listed = {str(r["progress_snapshot_id"]): r["version"]
                  for r in await self.service().list_snapshots(SCOPE)}
        row = await self.service().snapshot(SCOPE, SNAP_2)
        self.assertEqual(listed[str(SNAP_2)], row["version"])
        self.assertFalse(row["is_latest"])

    async def test_a_snapshot_from_another_project_is_concealed(self):
        from app.finance.domain.resources import FinanceRecordNotFound
        other = SimpleNamespace(organization_id=ORG, project_id="other_project", actor_user_id=ACTOR)
        with self.assertRaises(FinanceRecordNotFound):
            await self.service().snapshot(other, SNAP_2)

    async def test_a_snapshot_from_another_organization_is_concealed(self):
        from app.finance.domain.resources import FinanceRecordNotFound
        other = SimpleNamespace(organization_id=OTHER_ORG, project_id=PROJECT, actor_user_id=ACTOR)
        with self.assertRaises(FinanceRecordNotFound):
            await self.service().snapshot(other, SNAP_2)

    async def test_the_list_says_which_snapshot_is_the_projects_own_schedule(self):
        rows = await ProgressService(Repo(MIXED, active=OURS), provider=None).list_snapshots(SCOPE)
        self.assertEqual([False, False, True], [row["is_active_source"] for row in rows])
        # And it is not the one a date-ordered reader would have taken.
        self.assertTrue(rows[0]["is_latest"])
        self.assertFalse(rows[0]["is_active_source"])

    async def test_one_snapshot_reports_the_same_active_flag_as_the_list(self):
        service = ProgressService(Repo(MIXED, active=OURS), provider=None)
        listed = {str(r["progress_snapshot_id"]): r["is_active_source"]
                  for r in await service.list_snapshots(SCOPE)}
        row = await service.snapshot(SCOPE, SNAP_1)
        self.assertTrue(row["is_active_source"])
        self.assertEqual(listed[str(SNAP_1)], row["is_active_source"])

    async def test_an_unknown_snapshot_id_is_not_found(self):
        from app.finance.domain.resources import FinanceRecordNotFound
        with self.assertRaises(FinanceRecordNotFound):
            await self.service().snapshot(SCOPE, UUID(int=999))


class SyntheticSourceTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        # enforce_environment=False because the test process is not a dev host; the guard
        # itself is asserted separately below.
        return SyntheticProgressSourceAdapter(ORG, PROJECT, enforce_environment=False)

    async def test_it_satisfies_the_source_adapter_protocol(self):
        self.assertIsInstance(self.adapter(), ProgressSourceAdapter)

    async def test_it_returns_the_same_snapshot_every_time(self):
        first = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        second = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        self.assertEqual(first, second)

    async def test_the_fixture_uses_the_declared_identifier_convention(self):
        snapshot = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        self.assertEqual(["ACT-100", "ACT-200"],
                         sorted(task.task_external_id for task in snapshot.tasks))
        self.assertEqual(["ASG-1001", "ASG-1002", "ASG-1003"],
                         sorted(a.assignment_external_id for a in snapshot.assignments))
        self.assertTrue(all(is_conventional(a.assignment_external_id) for a in snapshot.assignments))

    async def test_every_assignment_maps_to_a_task_in_the_same_snapshot(self):
        snapshot = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        tasks = {task.task_external_id for task in snapshot.tasks}
        self.assertTrue(all(a.task_external_id in tasks for a in snapshot.assignments))

    async def test_an_effort_only_assignment_reports_no_quantity(self):
        snapshot = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        crane = [a for a in snapshot.assignments if a.assignment_external_id == "ASG-1002"][0]
        self.assertEqual(Decimal("48.0000"), crane.actual_work)
        # The fixture must not invent a measured quantity from hours; how Finance treats
        # an effort-only assignment is Finance's rule, not the fixture's.
        self.assertIsNone(crane.actual_quantity)
        self.assertIsNone(crane.planned_quantity)

    async def test_an_unreported_assignment_says_nothing_rather_than_zero(self):
        snapshot = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        formwork = [a for a in snapshot.assignments if a.assignment_external_id == "ASG-1003"][0]
        self.assertEqual(Decimal("900.0000"), formwork.planned_quantity)
        self.assertIsNone(formwork.actual_quantity)
        self.assertIsNone(formwork.actual_work)

    async def test_an_activity_without_a_baseline_leaves_it_unknown(self):
        snapshot = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        structure = [t for t in snapshot.tasks if t.task_external_id == "ACT-200"][0]
        self.assertIsNone(structure.baseline_start)
        self.assertIsNone(structure.baseline_finish)
        self.assertEqual(date(2026, 7, 1), structure.planned_start)

    async def test_another_tenant_gets_an_empty_snapshot_not_this_project_data(self):
        for organization, project in ((str(OTHER_ORG), PROJECT), (str(ORG), "other_project")):
            snapshot = await self.adapter().get_snapshot_input(organization, project)
            self.assertEqual(((), ()), (snapshot.tasks, snapshot.assignments))
            self.assertEqual("synthetic:empty", snapshot.source_reference)

    async def test_it_declares_itself_synthetic(self):
        snapshot = await self.adapter().get_snapshot_input(str(ORG), PROJECT)
        self.assertEqual("synthetic", snapshot.source_type)

    def test_it_refuses_to_be_built_outside_a_development_host(self):
        import devhost.synthetic_progress as module
        original = module.seeding_allowed
        module.seeding_allowed = lambda: False
        try:
            with self.assertRaises(SyntheticAdapterRefused):
                SyntheticProgressSourceAdapter(ORG, PROJECT)
            with self.assertRaises(SyntheticAdapterRefused):
                assert_development_only()
        finally:
            module.seeding_allowed = original

    def test_it_lives_outside_the_finance_library(self):
        # Finance must not be able to reach the fixture. If this module ever moves under
        # app/finance, that isolation is gone.
        import devhost.synthetic_progress as module
        self.assertNotIn("app%sfinance" % Path("/").as_posix()[0],
                         str(Path(module.__file__).as_posix()).replace("/", ""))
        self.assertIn("devhost", Path(module.__file__).parts)


class MppBoundaryTests(unittest.TestCase):
    def test_no_real_mpp_reader_is_implemented(self):
        # A stub returning plausible tasks would be worse than an error: the numbers would
        # reach a financial report with nothing marking them as invented.
        with self.assertRaises(NotImplementedError):
            raise MppAdapterNotAvailable()

    def test_the_boundary_names_every_normalisation_a_reader_must_supply(self):
        required = {"normalize_project", "normalize_tasks", "normalize_resources",
                    "normalize_assignments", "normalize_dependencies", "get_snapshot_input"}
        self.assertTrue(required <= set(dir(MppScheduleAdapter)))

    def test_finance_never_parses_a_schedule_file(self):
        """No module under app/finance may import a schedule reader.

        Checked by reading each module's imports rather than by searching its text: the
        word "mpp" appears legitimately as a source-type label and in prose, and a test
        that cannot tell a label from a dependency would either fail on a comment or pass
        on a real import hidden inside a docstring.
        """
        import ast
        readers = {"mpxj", "jpype", "pympxj", "mspdi", "python_mpp", "xer"}
        offenders = []
        for path in (BACKEND_ROOT / "app" / "finance").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if name.split(".")[0].lower() in readers:
                        offenders.append("%s imports %s" % (path.name, name))
        self.assertEqual([], offenders)

    def test_finance_never_reaches_into_the_development_fixture(self):
        import ast
        offenders = []
        for path in (BACKEND_ROOT / "app" / "finance").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = (node.module or "") if isinstance(node, ast.ImportFrom) else ""
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [module]
                if any(name.split(".")[0] == "devhost" for name in names if name):
                    offenders.append(path.name)
        self.assertEqual([], offenders)


class AuthProvider:
    def __init__(self, permissions): self.permissions = tuple(permissions)
    async def current(self, _request):
        return AuthContext(userId=ACTOR, organizationId=ORG, projectId=PROJECT,
                           organizationRole="finance_viewer", projectRole="viewer",
                           permissionCodes=self.permissions, locale="fa-IR", timezone="Asia/Tehran")


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


def client(permissions=("finance.view",)):
    app = create_app()
    app.state.auth_context_provider = AuthProvider(permissions)
    app.state.scope_authorizer = ScopeAuthorizer()
    app.state.permission_authorizer = PermissionAuthorizer()
    app.state.progress_service = ProgressService(Repo(), provider=None)
    return TestClient(app)


class ProgressSnapshotApiTests(unittest.TestCase):
    URL = "/api/projects/%s/finance/progress-snapshots" % PROJECT

    def test_one_snapshot_can_be_read_without_pulling_the_whole_feed(self):
        with client() as api:
            body = api.get("%s/%s" % (self.URL, SNAP_2))
        self.assertEqual(200, body.status_code)
        self.assertEqual((2, False), (body.json()["version"], body.json()["isLatest"]))

    def test_the_listing_and_the_single_read_agree_on_the_version(self):
        with client() as api:
            listed = api.get(self.URL).json()
            single = api.get("%s/%s" % (self.URL, SNAP_1)).json()
        by_id = {row["progressSnapshotId"]: row["version"] for row in listed}
        self.assertEqual(by_id[str(SNAP_1)], single["version"])

    def test_reading_a_snapshot_needs_the_finance_view_permission(self):
        with client(("finance_report.view",)) as api:
            denied = api.get("%s/%s" % (self.URL, SNAP_2))
        self.assertEqual(403, denied.status_code)

    def test_another_project_is_refused_before_any_lookup(self):
        with client() as api:
            denied = api.get("/api/projects/other_project/finance/progress-snapshots/%s" % SNAP_2)
        self.assertEqual(403, denied.status_code)
        self.assertEqual("FINANCE_FORBIDDEN", denied.json()["error"]["code"])

    def test_a_missing_snapshot_is_a_not_found_rather_than_an_empty_body(self):
        with client() as api:
            missing = api.get("%s/%s" % (self.URL, UUID(int=999)))
        self.assertEqual(404, missing.status_code)
        self.assertEqual("FINANCE_NOT_FOUND", missing.json()["error"]["code"])

    def test_a_malformed_snapshot_id_is_refused(self):
        with client() as api:
            self.assertEqual(422, api.get("%s/not-a-uuid" % self.URL).status_code)

    def test_the_listing_publishes_the_recorded_source_and_leaves_the_rest_blank(self):
        with client() as api:
            rows = api.get(self.URL).json()
        by_id = {row["progressSnapshotId"]: row["sourceType"] for row in rows}
        self.assertEqual("microsoft_project", by_id[str(SNAP_3)])
        # A snapshot imported before the column existed reports nothing rather than a
        # guess; a filename extension is not evidence of a tool.
        self.assertIsNone(by_id[str(SNAP_1)])

    def test_every_published_source_is_one_the_contract_allows(self):
        allowed = {"microsoft_project", "primavera", "manual", "other", None}
        with client() as api:
            rows = api.get(self.URL).json()
        self.assertTrue({row["sourceType"] for row in rows} <= allowed)

    def test_an_unrecognised_source_is_refused_rather_than_passed_through(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ProgressSnapshotResponse(**{**{k.replace("_", ""): v for k, v in ref(SNAP_1, 1, 1).items()},
                                        "sourceType": "msp"})

    def test_the_version_stays_optional_so_the_feed_contract_is_unchanged(self):
        # The feed's header comes from the host provider, which cannot know the version.
        # Making it required would have broken every feed response.
        self.assertIsNone(ProgressSnapshotResponse.model_fields["version"].default)
        self.assertFalse(ProgressSnapshotResponse.model_fields["version"].is_required())

    def test_an_uncomputed_active_source_flag_says_nothing_rather_than_no(self):
        """The three ranking fields must be unknown together, or they contradict.

        `version` and `is_latest` were already None by default because the feed's header
        comes from the provider and cannot know them. `is_active_source` defaulted to
        False, so one snapshot came back active from the listing and NOT active from its
        own feed -- seen for real on `test_progress.mpp`, which IS this project's active
        schedule. False is a claim, and an endpoint that did not compute the answer must
        not make it.
        """
        for name in ("version", "is_latest", "is_active_source"):
            with self.subTest(field=name):
                self.assertIsNone(ProgressSnapshotResponse.model_fields[name].default)

    def test_the_listing_still_states_the_flag_outright(self):
        # None is only for "nobody computed this". Where the question IS answered both
        # answers stay explicit -- a project with no active version says False, not null,
        # because "no schedule is active" is a fact and not an absence of one.
        # Two snapshots from two DIFFERENT files: `ref` gives every row the same file
        # version, and marking that one would make both true -- correctly, but it would
        # not show the flag discriminating.
        rows = [dict(ref(SNAP_1, 1, 1), source_file_version_id=UUID(int=1)),
                dict(ref(SNAP_2, 2, 2), source_file_version_id=UUID(int=2))]
        self.assertEqual([False, False],
                         [row["is_active_source"] for row in mark_active_source(rows, None)])
        self.assertEqual([False, True],
                         [row["is_active_source"]
                          for row in mark_active_source(rows, UUID(int=2))])


if __name__ == "__main__":
    unittest.main()
