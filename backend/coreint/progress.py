"""The progress feed, assembled from Core's MSP tables.

WHAT CORE CAN AND CANNOT ANSWER
This is the honest shape of the integration, and the reason most of the feed's fields come
back empty:

  * `msp_snapshots` and `msp_file_versions` give a real snapshot identity, its lineage and
    the file it was parsed from. All of that maps cleanly.
  * `msp_tasks` gives task names, WBS, dates and **percentages**.
  * Nothing in Core gives a resource, a unit, or a quantity. There is no assignment table,
    and `msp_tasks` has no resource columns at all.

So this adapter reports task-level rows with `assignmentExternalId` unset, and every
quantity field null. Finance pairs those rows to estimate lines by activity code, finds no
quantity, and reports the line as `unavailable` with a `PROGRESS_MISSING` warning.

That is the correct outcome, not a gap to paper over. The alternatives were considered and
each is worse:

  * Inventing an assignment id would fabricate a link Core does not assert.
  * Multiplying a task percentage by the estimate line's own quantity would report the
    plan back as if it were measured progress -- a number that always agrees with the
    estimate and therefore never reveals a problem.
  * Passing `percent_work_complete` through as an assignment percentage would repeat
    exactly the work-versus-quantity conflation `domain/progress.py` was changed to stop
    making.

Assignment-level quantities have to come from whatever publishes them -- the host's
progress module -- and that remains a production blocker recorded in the demo documents.

ONE MORE LIMIT WORTH SEEING
Because pairing falls back to the activity code, two estimate lines on the same activity
pair with the same task row. With no quantities in play they both simply report
`unavailable`, so nothing wrong is computed here -- but a provider that did supply
task-level quantities would give both lines the same number regardless of resource. That
is a known defect in the pairing rule, not in this adapter, and it is recorded rather than
worked around locally.
"""

import re
from datetime import date

from psycopg.rows import dict_row

from app.finance.domain.persian_calendar import persian_to_gregorian

#: Snapshot types that can carry executed progress. `TARGET` is a baseline -- a statement
#: about the plan, not about what happened -- so treating it as a progress report would
#: describe planned work as done. Core's CHECK constraint permits exactly these three
#: values, so this list is the complete set minus the one that does not belong.
PROGRESS_SNAPSHOT_TYPES = ("ACTUAL", "RESCHEDULED")

#: `snapshot_type` is a *type*, and Finance's `status` is about *freshness*; they are not
#: the same question, so one is never mapped onto the other. A snapshot is `ready` unless
#: something newer in its own lineage has replaced it.
STATUS_READY = "ready"
STATUS_SUPERSEDED = "superseded"

#: Core parses MPP files, and `msp_file_versions.file_type` says so.
SOURCE_TYPE = "mpp"

#: A Jalali date as Core stores it: `1405-05-31` or `1405/05/31`.
JALALI_DATE = re.compile(r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$")

#: Where a task's activity code is looked for, in order.
#:
#: **This is a planning convention, not a schema fact.** Core has no column named for an
#: activity code; MSP custom fields are whatever the planner decided to use, and `Text1`
#: holding a code is a common convention rather than a guarantee. The chain falls back to
#: the outline number and then the WBS, both of which are structural and always present.
#: Which field the BAMBO planners actually use has to be confirmed before this integration
#: is trusted in production -- until then a wrong guess here shows up as unmapped lines,
#: which is visible, rather than as wrong pairings, which would not be.
ACTIVITY_CODE_FIELDS = ("text1", "outline_number", "wbs")

SNAPSHOT_COLUMNS = """
    SELECT snapshot.id,
           snapshot.project_id,
           snapshot.file_version_id,
           snapshot.snapshot_type,
           snapshot.previous_snapshot_id,
           snapshot.source_filename,
           snapshot.status_date_jalali,
           snapshot.created_by,
           snapshot.created_at,
           project.organization_id,
           version.original_filename,
           version.version_number,
           EXISTS (SELECT 1 FROM msp_snapshots AS later
                    WHERE later.previous_snapshot_id = snapshot.id) AS superseded
    FROM msp_snapshots AS snapshot
    JOIN projects AS project ON project.id = snapshot.project_id
    LEFT JOIN msp_file_versions AS version ON version.id = snapshot.file_version_id
"""

TASKS = """
    SELECT id, uid, guid, task_id, name, wbs, outline_number, outline_level,
           start, finish, percent_complete, percent_work_complete,
           physical_percent_complete, text1
    FROM msp_tasks
    WHERE snapshot_id = %(snapshot_id)s
    ORDER BY outline_number NULLS LAST, id
"""


def _bigint(value):
    """The value as a Core bigint, or None if it is not one.

    Booleans are refused explicitly: `True` is an `int` in Python and would otherwise become
    snapshot 1.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def reporting_date(row) -> date:
    """The date this snapshot reports as of.

    `status_date_jalali` is the planner's own status date and is the right answer whenever
    it is present and parses. It is stored as text in the Jalali calendar, converted here by
    the same module the reports use, so a snapshot cannot report one date to Finance and
    another to a Persian-calendar view of the same data.

    `created_at` is the fallback and is a weaker claim: it is when the file was uploaded,
    which can be days after the status it describes. Anything financial computed against it
    is dated by the upload rather than by the site.
    """
    match = JALALI_DATE.match(row.get("status_date_jalali") or "")
    if match:
        try:
            return persian_to_gregorian(*(int(part) for part in match.groups()))
        except (ValueError, OverflowError):
            pass                      # a malformed date is not worth failing the feed over
    return row["created_at"].date()


def activity_code(task):
    """The first field in `ACTIVITY_CODE_FIELDS` this task actually fills."""
    for field in ACTIVITY_CODE_FIELDS:
        value = (task.get(field) or "").strip()
        if value:
            return value
    return None


def task_external_id(task):
    """A stable identity for the task across snapshots.

    `guid` first: MSP keeps it across saves, so the same task in two snapshots is
    recognisable as the same task. `uid` and `task_id` are per-file and get reused when
    tasks are deleted, so they are only a last resort. The task name is never used -- it is
    edited constantly, and identity that changes when someone fixes a typo is not identity.
    """
    for field in ("guid", "uid", "task_id"):
        value = task.get(field)
        if value not in (None, ""):
            return str(value)
    return f"msp-task-{task['id']}"


def _percent(value):
    return None if value is None else format(value, "f")


def task_row(task):
    """One task as a progress-feed row.

    Every resource and quantity field is null, because Core states none of them. See the
    module docstring: this is the adapter reporting what it has rather than deriving what
    it does not.
    """
    # `physical_percent_complete` first: it is the planner's statement about work actually
    # in place. `percent_complete` is duration-based and says only that time has passed.
    # `percent_work_complete` is deliberately not used -- it measures effort, and effort is
    # not a proportion of a physical quantity.
    progress = task["physical_percent_complete"]
    if progress is None:
        progress = task["percent_complete"]
    return {
        "assignmentExternalId": None,
        "resourceExternalId": None,
        "resourceName": None,
        "resourceType": None,
        "unit": None,
        "plannedQuantity": None,
        "actualQuantity": None,
        "remainingQuantity": None,
        "plannedWork": None,
        "actualWork": None,
        "remainingWork": None,
        "assignmentWorkCompletePercent": None,
        "task": {
            "taskExternalId": task_external_id(task),
            "taskName": task["name"],
            "wbsCode": task["wbs"],
            "activityCode": activity_code(task),
            "parentTaskExternalId": None,
            "taskProgressPercent": _percent(progress),
            "taskStart": task["start"],
            "taskFinish": task["finish"],
        },
        "manualOverride": None,
    }


class CoreProgressSnapshotProvider:
    """`ProgressSnapshotProvider` over `msp_snapshots` / `msp_file_versions` / `msp_tasks`.

    Read-only in the strongest sense: it issues SELECT statements and nothing else. Core
    owns these tables and Finance has no business writing to them.

    Identifiers stay in their own namespaces. Core's are bigint and are what this adapter
    answers to; Finance's `progress_snapshot_id` is a UUID Finance mints for its own
    reference row. The header carries the Core id in `progressSnapshotId` because that is
    what the caller asked with, and repeats it in `hostSnapshotId` so the reference row can
    record what to ask with next time.
    """

    def __init__(self, connection, *, progress_types=PROGRESS_SNAPSHOT_TYPES):
        self._connection = connection
        self._progress_types = tuple(progress_types)

    async def _rows(self, sql, params):
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()

    async def current_snapshot(self, organization_id, project_id, as_of=None):
        """The newest progress-bearing snapshot for this project, or None.

        Ordered by `created_at` rather than by id, because publication order is what
        "current" means, and ids only agree with it while nothing is ever backfilled.

        `as_of` filters on the reporting date the caller would see, not on `created_at`, so
        asking for a past date cannot return a snapshot that reports on a later one. It is
        applied after the rows are read because the reporting date can come from a Jalali
        text column that SQL cannot order on.
        """
        rows = await self._rows(
            SNAPSHOT_COLUMNS + """
                WHERE snapshot.project_id = %(project_id)s
                  AND project.organization_id = %(organization_id)s
                  AND snapshot.snapshot_type = ANY(%(types)s)
                ORDER BY snapshot.created_at DESC, snapshot.id DESC
            """,
            {"project_id": project_id, "organization_id": str(organization_id),
             "types": list(self._progress_types)})
        limit = as_of if isinstance(as_of, date) else None
        for row in rows:
            if limit is None or reporting_date(row) <= limit:
                return await self._feed(row)
        return None

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        """One snapshot by its Core bigint id, or None.

        None rather than an exception for every miss -- unknown id, wrong project, wrong
        organization, or an id that is not a Core id at all. Finance turns a None into a
        404, and a caller who may not see a snapshot gets the same answer as one asking for
        a snapshot that does not exist.

        Being handed a Finance UUID is one of those misses. It happens when a reference row
        has no `host_snapshot_id` recorded, and answering "not found" is correct: this
        provider has genuinely never issued that identifier.
        """
        identifier = _bigint(snapshot_id)
        if identifier is None:
            return None
        rows = await self._rows(
            SNAPSHOT_COLUMNS + """
                WHERE snapshot.id = %(snapshot_id)s
                  AND snapshot.project_id = %(project_id)s
                  AND project.organization_id = %(organization_id)s
            """,
            {"snapshot_id": identifier, "project_id": project_id,
             "organization_id": str(organization_id)})
        return await self._feed(rows[0]) if rows else None

    async def _feed(self, row):
        tasks = await self._rows(TASKS, {"snapshot_id": row["id"]})
        return {
            "snapshot": {
                "organizationId": str(row["organization_id"]),
                "projectId": row["project_id"],
                # The Core id, because that is the identifier the caller asked with and the
                # only one this provider has ever issued.
                "progressSnapshotId": str(row["id"]),
                "hostSnapshotId": row["id"],
                "hostFileVersionId": row["file_version_id"],
                # Finance's own UUID for a source file. Core files are bigint, so there is
                # nothing to put here; `hostFileVersionId` above carries the real one.
                "sourceFileVersionId": None,
                "sourceFileNameSafe": (row["original_filename"] or row["source_filename"] or ""),
                "reportingDate": reporting_date(row).isoformat(),
                "status": STATUS_SUPERSEDED if row["superseded"] else STATUS_READY,
                "snapshotType": row["snapshot_type"],
                "sourceType": SOURCE_TYPE,
                "importedBy": str(row["created_by"]) if row["created_by"] else None,
                "importedAt": row["created_at"].isoformat(),
            },
            "assignments": [task_row(task) for task in tasks],
        }
