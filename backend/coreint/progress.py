"""The progress feed, assembled from Core's MSP tables.

WHAT CORE CAN AND CANNOT ANSWER
This is the honest shape of the integration, and the reason most of the feed's fields come
back empty:

  * `msp_snapshots` and `msp_file_versions` give a real snapshot identity, its lineage and
    the file it was parsed from. All of that maps cleanly.
  * `msp_tasks` gives task names, WBS, dates and **percentages**.
  * `msp_resources` and `msp_resource_assignments`, WHEN CORE CARRIES THEM, give the
    resource, the unit and the physical quantity per task. Those two tables are owned by
    Core/Planning and delivered by `docs/sql/msp_resource_assignment_apply.sql`.

So this adapter has two modes, decided per request by asking the catalogue which tables
exist. With both assignment tables present it reports real assignment rows carrying
`assignmentExternalId`, resource, unit and quantity. With neither present it falls back to
task-level rows with `assignmentExternalId` unset and every quantity field null -- Finance
then pairs by activity code, finds no quantity, and reports the line as `unavailable` with a
`PROGRESS_MISSING` warning. With exactly one present it raises `CoreSchemaMismatch`, because
a half-migrated Core that answered anyway would be indistinguishable from one nobody had
migrated at all.

The fallback is the correct outcome for a Core without the tables, not a gap to paper over.
The alternatives were considered and each is worse:

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
from decimal import Decimal
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
#: The value `progress_snapshot_refs.source_type` accepts. Revision 0005 constrains that
#: column to microsoft_project/primavera/manual/other, and Core snapshots come from MPP
#: files -- `msp_file_versions.file_type` is CHECKed to 'MPP'. The previous value here,
#: "mpp", belonged to the schedule-adapter vocabulary in domain/schedule.py, and the
#: database refused it the moment a reference was pinned from a Core snapshot.
SOURCE_TYPE = "microsoft_project"

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


#: Assignment-level rows, when Core carries them. Joined to the task so one query answers
#: the whole feed, and LEFT-joined to the resource because MSP leaves some assignments
#: unlinked -- 12 of 727 in the reference file -- and dropping those would lose work that
#: was really planned.
ASSIGNMENTS = """
    SELECT assignment.assignment_uid, assignment.task_uid, assignment.resource_uid,
           assignment.units, assignment.planned_work, assignment.actual_work,
           assignment.remaining_work, assignment.planned_quantity, assignment.actual_quantity,
           assignment.remaining_quantity, assignment.quantity_unit,
           assignment.assignment_work_complete_percent,
           resource.resource_name, resource.native_type, resource.bambo_resource_type,
           resource.resource_quantity_unit,
           task.id AS task_row_id, task.uid, task.guid, task.task_id, task.name, task.wbs,
           task.outline_number, task.outline_level, task.start, task.finish,
           task.percent_complete, task.percent_work_complete,
           task.physical_percent_complete, task.text1
      FROM msp_resource_assignments AS assignment
      JOIN msp_tasks AS task
        ON task.snapshot_id = assignment.snapshot_id AND task.uid = assignment.task_uid
      LEFT JOIN msp_resources AS resource
        ON resource.snapshot_id = assignment.snapshot_id
       AND resource.resource_uid = assignment.resource_uid
     WHERE assignment.snapshot_id = %(snapshot_id)s
     ORDER BY task.outline_number NULLS LAST, assignment.assignment_uid
"""

#: What has to exist before the assignment feed is used at all.
ASSIGNMENT_TABLES = ("msp_resources", "msp_resource_assignments")

CAPABILITY = """
    SELECT count(*) AS present FROM information_schema.tables
     WHERE table_schema = 'public' AND table_name = ANY(%(names)s)
"""


class CoreSchemaMismatch(RuntimeError):
    """Half of the assignment schema is present.

    Deliberately fatal rather than a fallback. With one table missing the adapter could
    still answer -- from task percentages, quietly, with no quantity -- and a half-migrated
    Core would look exactly like a Core that had never been migrated. The difference matters
    to whoever is running the migration, so it is raised instead of absorbed.
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


def activity_code(task, fields=ACTIVITY_CODE_FIELDS):
    """The first of `fields` this task actually fills."""
    for field in fields:
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


def task_progress(task):
    """How far along a task is: physical progress when stated, otherwise duration progress.

    `physical_percent_complete` is the planner's statement about work actually in place, and
    it is preferred whenever it says something. `percent_complete` is duration-based -- it
    says only that time has passed -- and stands in when physical progress says nothing.

    `percent_work_complete` is deliberately never used. It measures effort, and effort is not
    a proportion of a physical quantity; substituting it is the conflation the rest of this
    integration exists to avoid.

    WHY A PHYSICAL ZERO IS TREATED AS SILENCE
    Microsoft Project writes 0.0000 into this column for every task whether or not anyone
    entered physical progress, and offers no way to tell the two apart. Central snapshot 40
    is the case in point: all 1248 tasks carry physical 0.0000 while `percent_complete`
    carries real values up to 100. Preferring the zero reported every one of those tasks as
    untouched -- a confident, wrong statement on 1248 rows, and one that showed up as a
    report with no progress at all rather than as an error anybody would notice.

    So a physical zero yields to a non-zero duration figure. What is lost is a genuine
    measured "nothing has been built yet" on a task whose schedule has advanced; what is
    gained is not silently reporting a whole project as unstarted. When both are zero the
    answer is zero either way, which is the common case and is unaffected.
    """
    physical = task["physical_percent_complete"]
    duration = task["percent_complete"]
    if physical is None:
        return duration
    if physical == 0 and duration is not None and duration != 0:
        return duration
    return physical


def task_row(task, activity_code_fields=ACTIVITY_CODE_FIELDS):
    """One task as a progress-feed row.

    Every resource and quantity field is null, because Core states none of them. See the
    module docstring: this is the adapter reporting what it has rather than deriving what
    it does not.
    """
    progress = task_progress(task)
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
            "activityCode": activity_code(task, activity_code_fields),
            "parentTaskExternalId": None,
            "taskProgressPercent": _percent(progress),
            "taskStart": task["start"],
            "taskFinish": task["finish"],
        },
        "manualOverride": None,
    }


def _decimal(value):
    """A quantity as a string Finance can parse exactly, or None.

    None stays None. A quantity nobody reported is not a quantity of zero, and this is the
    last place that distinction could be lost before it reaches the report.
    """
    return None if value is None else format(Decimal(value), "f")


def assignment_row(row, activity_code_fields=ACTIVITY_CODE_FIELDS):
    """One assignment-level feed row, built from a joined assignment/resource/task row.

    Quantity and work are kept apart on purpose. `plannedQuantity` is physical -- kilograms
    of rebar, cubic metres of concrete -- and comes from MPXJ's Material field; `plannedWork`
    is hours. Finance's progress precedence prefers the first and treats the second as a
    weaker fallback, which only works if the two never arrive in the same field.

    `unit` comes from the assignment's own `quantity_unit`, falling back to the resource's.
    The assignment is preferred because it is the row the quantity belongs to; the fallback
    exists because a planner convention may record the unit once, on the resource.
    """
    return {
        "assignmentExternalId": (None if row["assignment_uid"] is None
                                 else str(row["assignment_uid"])),
        # Null on an assignment MSP left unlinked. Reported as unlinked rather than dropped,
        # so a line that names it fails to pair visibly instead of vanishing.
        "resourceExternalId": (None if row["resource_uid"] is None
                               else str(row["resource_uid"])),
        "resourceName": row["resource_name"],
        # Core's BAMBO classification, which is null for a WORK resource MSP gives no basis
        # to call labour or equipment. Finance shows those rather than guessing.
        "resourceType": row["bambo_resource_type"],
        "unit": row["quantity_unit"] or row["resource_quantity_unit"],
        "plannedQuantity": _decimal(row["planned_quantity"]),
        "actualQuantity": _decimal(row["actual_quantity"]),
        "remainingQuantity": _decimal(row["remaining_quantity"]),
        "plannedWork": _decimal(row["planned_work"]),
        "actualWork": _decimal(row["actual_work"]),
        "remainingWork": _decimal(row["remaining_work"]),
        "assignmentWorkCompletePercent": _percent(row["assignment_work_complete_percent"]),
        "task": task_row(row, activity_code_fields)["task"],
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

    def __init__(self, connection, *, progress_types=PROGRESS_SNAPSHOT_TYPES,
                 activity_code_fields=ACTIVITY_CODE_FIELDS):
        self._connection = connection
        self._progress_types = tuple(progress_types)
        # Which MSP field carries the activity code is a planning convention, not a schema
        # fact -- see ACTIVITY_CODE_FIELDS. A host that knows its planners' convention says
        # so here instead of relying on the default order, and does it without any change to
        # the port: the constructor is the host's side of the boundary.
        self._activity_code_fields = tuple(activity_code_fields)

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

    async def _assignments_available(self):
        """Whether Core carries the assignment tables -- and a refusal if it half does.

        Asked once per feed and not cached: a migration can land between two requests, and a
        provider that remembered "absent" would keep answering from task percentages long
        after the real data arrived.
        """
        rows = await self._rows(CAPABILITY, {"names": list(ASSIGNMENT_TABLES)})
        present = rows[0]["present"] if rows else 0
        if present == len(ASSIGNMENT_TABLES):
            return True
        if present == 0:
            return False
        raise CoreSchemaMismatch(
            f"{present} of {len(ASSIGNMENT_TABLES)} assignment tables exist "
            f"({', '.join(ASSIGNMENT_TABLES)}). Core is half migrated.")

    async def _feed(self, row):
        if await self._assignments_available():
            rows = await self._rows(ASSIGNMENTS, {"snapshot_id": row["id"]})
            # An empty assignment table for this snapshot is not the same as no schema. It
            # means this snapshot was imported before assignments were captured, and the
            # task-level feed is the honest answer for it.
            if rows:
                return self._envelope(
                    row, [assignment_row(entry, self._activity_code_fields) for entry in rows])
        tasks = await self._rows(TASKS, {"snapshot_id": row["id"]})
        return self._envelope(row, [task_row(task, self._activity_code_fields)
                                    for task in tasks])

    def _envelope(self, row, assignments):
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
            "assignments": assignments,
        }
