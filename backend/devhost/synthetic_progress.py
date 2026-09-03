"""A deterministic progress source for tests and local development.

DEVELOPMENT ONLY. This is not a stand-in for a real schedule and must never become the
production adapter. Two things keep it from drifting into production quietly: it lives in
`devhost/`, which the Finance library never imports, and `assert_development_only()`
refuses to build one unless the environment says it is a development host.

What it is for: exercising the contract. `ProgressSnapshotInput` declares what a source
owes Finance, and until a real reader exists this is the only thing that owes it. The data
below is fixed so a test can assert exact values, and shaped so the interesting cases are
all present rather than a happy path repeated:

  - task UID 100 / assignment UID 1001 — measured quantities, the well-behaved case
  - task UID 200 / assignment UID 1002 — effort only, no measured quantity at all
  - assignment UID 1003 — an activity with a baseline but nothing reported yet

Identifiers come from `external_ids`, so the fixture cannot disagree with the convention
the rest of the system would apply.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.finance.domain.external_ids import activity_external_id, assignment_external_id
from app.finance.domain.schedule import (
    ProgressSnapshotInput, SnapshotAssignment, SnapshotTask)

from .environment import seeding_allowed

FOUNDATION_UID = "100"
STRUCTURE_UID = "200"
REBAR_UID = "1001"
CRANE_UID = "1002"
FORMWORK_UID = "1003"


class SyntheticAdapterRefused(RuntimeError):
    """Raised when a non-development host tries to build the synthetic source."""


def assert_development_only():
    """Refuse outside development, so this cannot become the production adapter by accident.

    `seeding_allowed()` is the same switch that already gates writing fixture rows into a
    database, so a host permitted to invent progress is exactly a host permitted to invent
    data — one decision, not two that can disagree.
    """
    if not seeding_allowed():
        raise SyntheticAdapterRefused(
            "the synthetic progress source is development-only; "
            "set the development environment or inject a real ProgressSourceAdapter")


def _tasks():
    return (
        SnapshotTask(
            task_external_id=activity_external_id(FOUNDATION_UID),
            task_uid=FOUNDATION_UID,
            activity_code=activity_external_id(FOUNDATION_UID),
            title="فونداسیون نمونه",
            wbs_code="1.1",
            planned_start=date(2026, 5, 1), planned_finish=date(2026, 6, 30),
            baseline_start=date(2026, 5, 1), baseline_finish=date(2026, 6, 15),
            percent_complete=Decimal("25.0000"),
            planned_work=Decimal("400.0000"), actual_work=Decimal("100.0000"),
            remaining_work=Decimal("300.0000")),
        SnapshotTask(
            task_external_id=activity_external_id(STRUCTURE_UID),
            task_uid=STRUCTURE_UID,
            activity_code=activity_external_id(STRUCTURE_UID),
            title="اسکلت نمونه",
            wbs_code="2.1",
            parent_task_external_id=activity_external_id(FOUNDATION_UID),
            planned_start=date(2026, 7, 1), planned_finish=date(2026, 9, 15),
            # No baseline was ever set for this activity, and none is invented.
            percent_complete=Decimal("28.0000"),
            planned_work=Decimal("800.0000"), actual_work=Decimal("224.0000"),
            remaining_work=Decimal("576.0000")),
    )


def _assignments():
    return (
        # Measured quantities in the resource's own unit.
        SnapshotAssignment(
            assignment_external_id=assignment_external_id(REBAR_UID),
            task_external_id=activity_external_id(FOUNDATION_UID),
            assignment_uid=REBAR_UID,
            resource_external_id="res-rebar", resource_name="میلگرد نمونه", unit="kg",
            planned_quantity=Decimal("10000.0000"), actual_quantity=Decimal("2500.0000"),
            remaining_quantity=Decimal("7500.0000"),
            percent_complete=Decimal("25.0000")),
        # Effort only. The quantity fields stay None rather than being filled from hours:
        # what Finance does with an effort-only assignment is Finance's existing rule, and
        # this fixture must not pre-empt it by inventing kilograms.
        SnapshotAssignment(
            assignment_external_id=assignment_external_id(CRANE_UID),
            task_external_id=activity_external_id(STRUCTURE_UID),
            assignment_uid=CRANE_UID,
            resource_external_id="res-crane", resource_name="جرثقیل نمونه", unit="hour",
            planned_work=Decimal("160.0000"), actual_work=Decimal("48.0000"),
            remaining_work=Decimal("112.0000"),
            percent_complete=Decimal("30.0000")),
        # Planned, but nothing reported. Every progress field is None — a source with
        # nothing to say says nothing, rather than reporting zero.
        SnapshotAssignment(
            assignment_external_id=assignment_external_id(FORMWORK_UID),
            task_external_id=activity_external_id(STRUCTURE_UID),
            assignment_uid=FORMWORK_UID,
            resource_external_id="res-formwork", resource_name="قالب‌بندی نمونه", unit="m2",
            planned_quantity=Decimal("900.0000")),
    )


class SyntheticProgressSourceAdapter:
    """A `ProgressSourceAdapter` that returns the same schedule every time.

    Determinism is the point: a test asserting an exact quantity should fail because the
    code changed, never because the fixture moved.
    """

    def __init__(self, organization_id, project_id, reporting_date=date(2026, 6, 1),
                 created_by=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3"), enforce_environment=True):
        if enforce_environment:
            assert_development_only()
        self.organization_id = UUID(str(organization_id))
        self.project_id = project_id
        self.reporting_date = reporting_date
        self.created_by = created_by

    async def get_snapshot_input(self, organization_id, project_id):
        """Return the fixture, or an empty snapshot for any other tenant.

        The empty case is still a valid `ProgressSnapshotInput`, not None and not a raised
        error: a caller asking about a project this source knows nothing about should get
        "no progress", which is what it would get from a real source too.
        """
        if str(organization_id) != str(self.organization_id) or project_id != self.project_id:
            return ProgressSnapshotInput(
                organization_id=UUID(str(organization_id)), project_id=project_id,
                reporting_date=self.reporting_date, source_type="synthetic",
                source_reference="synthetic:empty",
                created_by=self.created_by,
                created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
        return ProgressSnapshotInput(
            organization_id=self.organization_id, project_id=self.project_id,
            reporting_date=self.reporting_date, source_type="synthetic",
            source_reference="synthetic:deterministic-v1",
            created_by=self.created_by,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            tasks=_tasks(), assignments=_assignments())
