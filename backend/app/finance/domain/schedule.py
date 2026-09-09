"""The normalized schedule contract a progress source must produce.

Today the host hands Finance a bare `dict` and `schemas/progress.py` types the payload as
`assignments: list[dict]` — every field is unvalidated passthrough. That was workable
while one seeded fake was the only producer. It stops being workable the moment a real
schedule importer exists, because nothing states what the importer owes Finance.

These structures are that statement. They sit between a schedule source and Finance:

    schedule source -> ProgressSnapshotInput -> (existing feed) -> Finance

Finance never reads a schedule file. It reads this.

WHAT IS DELIBERATELY NULLABLE
Almost everything except identity. The fields below were taken from what the existing
feed already carries plus what a scheduling tool is normally able to state; none of them
is confirmed against a real MPP file yet. A source that cannot supply baseline dates says
None, and the reader can tell "not supplied" from "zero". Guessing a value here would put
a number Finance cannot justify in front of a reader.

Nothing in this module computes money, quantity, or progress. It carries what the source
said, unchanged.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

SOURCE_TYPES = ("synthetic", "mpp", "host_feed")


@dataclass(frozen=True, slots=True)
class SnapshotTask:
    """One schedule activity as the source reported it.

    `task_external_id` is the stable identity (see `external_ids`); `task_uid` keeps the
    raw source UID beside it so an audit can tell what the identifier was derived from
    without re-reading the source file.
    """

    task_external_id: str
    task_uid: str | None = None
    activity_code: str | None = None
    title: str | None = None
    wbs_code: str | None = None
    parent_task_external_id: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    baseline_start: date | None = None
    baseline_finish: date | None = None
    percent_complete: Decimal | None = None
    planned_work: Decimal | None = None
    actual_work: Decimal | None = None
    remaining_work: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SnapshotAssignment:
    """One resource assigned to one activity, as the source reported it.

    Quantities and work are kept apart on purpose. `planned_quantity` and
    `actual_quantity` are measured amounts in the resource's own unit; `planned_work`,
    `actual_work` and `remaining_work` are effort. A source that only knows effort leaves
    the quantity fields None rather than filling them from hours — how Finance treats that
    is Finance's existing rule, not something this contract decides.
    """

    assignment_external_id: str
    task_external_id: str
    assignment_uid: str | None = None
    resource_external_id: str | None = None
    resource_name: str | None = None
    unit: str | None = None
    planned_quantity: Decimal | None = None
    actual_quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None
    planned_work: Decimal | None = None
    actual_work: Decimal | None = None
    remaining_work: Decimal | None = None
    percent_complete: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ProgressSnapshotInput:
    """Everything a source must state to produce one snapshot of a project's progress.

    `version` is not carried here. A snapshot's version is its position in the project's
    own history, which only the receiving side can know; a source that numbered its own
    output would collide with every other source. See `derive_snapshot_versions`.
    """

    organization_id: UUID
    project_id: str
    reporting_date: date
    source_type: str
    source_reference: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    tasks: tuple[SnapshotTask, ...] = field(default_factory=tuple)
    assignments: tuple[SnapshotAssignment, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.source_type not in SOURCE_TYPES:
            raise ValueError("unknown progress source type: %s" % self.source_type)
        known = {task.task_external_id for task in self.tasks}
        orphans = sorted(
            {a.assignment_external_id for a in self.assignments if a.task_external_id not in known})
        if orphans:
            # An assignment whose activity is absent cannot be reported against a schedule,
            # and letting it through would surface later as progress with no activity.
            raise ValueError("assignments reference unknown tasks: %s" % ", ".join(orphans))


def derive_snapshot_versions(refs):
    """Number a project's snapshots by their position in its own history.

    `progress_snapshot_refs` carries no version column, and adding one would mean a
    backfill over production rows nobody has audited. It does not need one: the table is
    append-only by database trigger, so the ordering of its rows is itself the history.
    Version 1 is the oldest snapshot and stays version 1 forever, because no later import
    can insert itself earlier or alter what is already there.

    `refs` are rows ordered newest-first, as the repository returns them. The returned
    rows keep that order and gain `version` and `is_latest`.
    """
    ordered = list(refs)
    total = len(ordered)
    return [{**row, "version": total - index, "is_latest": index == 0}
            for index, row in enumerate(ordered)]


def mark_active_source(refs, active_source_version_id):
    """Say which snapshot came from the schedule this project's estimate is priced on.

    `is_latest` answers a question about HISTORY: which row arrived last. That is not the
    same question as which schedule the project is running on, and on a project that has
    received snapshots from more than one file the two answers differ -- a snapshot of
    somebody else's schedule carrying a later reporting date is still the newest row, and
    still the wrong file to read progress from.

    So the two are separate flags. `is_active_source` marks the row whose source file
    version IS the project's active one, as `mpp_source_version` decides it: the same file
    the estimate lines were mapped to and the same file the item table prices from. A
    reader that wants ONE project on ONE schedule follows this flag; a reader that wants
    the project's history follows `version`.

    False is the honest answer, not a fallback: on a project with no imported source
    version, or for a snapshot ingested from the host with no Finance file version of its
    own, there is nothing here claiming to be the active schedule. Choosing what to do
    with that belongs to the caller, not to this function.
    """
    active = None if active_source_version_id is None else str(active_source_version_id)
    return [{**row,
             "is_active_source": (active is not None
                                  and str(row.get("source_file_version_id") or "") == active)}
            for row in refs]
