# -*- coding: utf-8 -*-
"""Turning persisted schedule rows into the financial records a report is built from.

`finance_mpp_rows` is what the file said. `finance_resources` and `estimate_lines` are what
Finance owns. This is the one place that carries a row across that line, and it does so on
identity alone: the MPP resource uid names the financial item, the MPP assignment uid names
the estimate line, and anything without those identifiers is left alone.

WHAT A TASK'S OWN MONEY IS
An assignment is not the only place MS Project puts a cost. A task carries a Fixed Cost of
its own -- money that belongs to the ACTIVITY and to no resource on it -- and that becomes a
general cost line keyed on the task instead of on an assignment. See `_map_fixed_costs`; it
is a second reading of the same file, not a second guess at the same money, and the two
never touch the same rial.

WHAT AN ASSIGNMENT IS
"This resource, on this activity" -- which is exactly what an estimate line is, so the two
correspond one to one. That is why the assignment uid is the key and not the task: one
resource serves many activities («ترک میکسر» appears on sixty-four of them in the current
file) and one activity draws on many resources. Keying on the task would collapse the first;
keying on the resource would collapse the second.

WHAT THIS REFUSES TO DO
  * invent a quantity. Work, duration, units and percentages are all present in the file
    and none of them is a quantity. What IS a quantity is the Material field, which MS
    Project keeps per assignment for material resources, and a line is created with that
    when the row carries one -- and with `original_quantity` NULL when it does not, which
    reports itself as unmeasured rather than reporting a number nobody wrote down.
  * invent a price. `original_unit_price_irr` is the resource's own standard rate, and only
    where `source_rate_basis` proved that rate is per material unit -- quantity x rate
    reproducing the assignment's own cost. A rate nothing proves, and the cost of an
    assignment (which is a total, not a rate), are both refused. This is the ESTIMATE'S
    basis, not a market price: `price_versions` still holds the price of the day and
    nothing here writes one.
  * match on anything but an identifier. No name comparison, no WBS similarity, no
    positional guessing. A row whose resource uid is absent (twelve of them here) produces
    nothing at all and is reported as unmapped.
  * touch a legacy record. Rows created by the old seed have no `source_resource_uid` and
    no `source_assignment_uid`, so no lookup here can ever find them, and nothing here
    updates or deletes them.

IDEMPOTENCE
Both writes are `ON CONFLICT DO NOTHING` against the partial unique indexes 0013 adds, so
reading the same file twice matches what exists rather than duplicating it. The estimate
line's own immutability trigger guarantees the rest: an existing line is never rewritten,
which is what makes a re-sync safe to run on a timer.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.finance.domain import resource_types
from app.finance.domain.mpp_source_version import active_source_version
from app.finance.domain.unit_registry import UNIT_REGISTRY

from .finance_mpp_sync import MATERIAL_UNIT_RATE

LOG = logging.getLogger("coreint.finance_mpp_mapping")

#: What a resource read from a schedule is called on the Finance side. The MPP resource uid
#: makes it unique and legible; the code is a label, never the identity the mapping keys on.
RESOURCE_CODE_PREFIX = "MPP-R"

#: How the file's own resource kinds land in Finance's vocabulary. The three kinds MS
#: Project has are the three kinds Finance has (0038): MATERIAL is bought by quantity, WORK
#: by the hour -- crews and machines alike -- and COST is a general cost. Until 0038 a
#: WORK resource waited for a person to call it labour or equipment, a claim the file
#: never makes; on the product nobody could make it either, so every crew and machine
#: stayed unmapped. An unrecognised kind still maps to nothing and is left unmapped.
RESOURCE_TYPE_BY_NATIVE = resource_types.RESOURCE_TYPE_BY_NATIVE

#: What a WORK resource is measured in. MS Project states every WORK resource's work in
#: hours; its `initials` column, which arrives as `resource_unit`, is the first letter of
#: the name and is not a unit. So the unit is the file's own convention, not a guess.
WORK_UNIT = "hour"

_SOURCE_ROWS = """
    SELECT source_task_uid, source_assignment_uid, source_resource_uid,
           task_name, task_wbs, resource_name, resource_type, resource_unit,
           source_material_quantity, source_resource_rate_irr, source_rate_basis
      FROM finance_mpp_rows
     WHERE source_version_id = %(version_id)s
       AND organization_id = %(organization_id)s AND project_id = %(project_id)s
       AND source_assignment_uid IS NOT NULL
       AND source_resource_uid IS NOT NULL
     ORDER BY source_assignment_uid
"""

_INSERT_RESOURCE = """
    INSERT INTO finance_resources
        (id, organization_id, project_id, resource_type, code, title, base_unit,
         dimension, source_resource_uid, created_by)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT DO NOTHING
"""

#: The decision itself, as an event. `before_values` states what the file said -- a WORK
#: resource Finance refuses to type -- and `after_values` what the person chose, so the
#: pair reads as the judgement it is rather than as a row appearing from nowhere.
_INSERT_LINE = """
    INSERT INTO estimate_lines
        (id, organization_id, project_id, resource_id, activity_external_id,
         assignment_external_id, original_quantity, original_unit_price_irr, source,
         source_assignment_uid, source_task_uid, created_by)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'progress_feed',%s,%s,%s)
    ON CONFLICT DO NOTHING
"""

#: The code of the one financial item that carries a schedule's task-level fixed costs.
#: Not `RESOURCE_CODE_PREFIX + something`: that prefix means "the MPP resource with this
#: uid", and a fixed cost names no resource at all -- which is the whole point of it.
FIXED_COST_RESOURCE_CODE = "MPP-FIXEDCOST"

#: What that item is called on screen. A general cost, so it carries no unit and no
#: dimension -- the same rule the resource form applies, and the CHECK on the table.
FIXED_COST_RESOURCE_TITLE = "هزینه ثابت فعالیت (برنامه زمان‌بندی)"

#: Below one whole unit of the file's own currency, a Fixed Cost is not an amount anybody
#: entered.
#:
#: MS Project holds the identity `Task.Cost = sum of its assignments + Fixed Cost`, and
#: stores all three as doubles. Where a planner entered no fixed cost, what remains in the
#: column is the residue of that reconciliation. This project's file shows the two kinds
#: side by side and they are not close: twenty-four tasks state a non-zero Fixed Cost, and
#: twenty-one of them state values between -0.25 and 0.5 of a toman, while the other three
#: state 2,829,688,000, -2,972,160,000 and 5,290,960,000.5 -- the whole of it.
#:
#: So the rule is stated in the file's OWN units, where "one unit of the currency someone
#: typed in" is a sentence that means something, rather than in rials, where the same
#: threshold would silently depend on the currency decision. Residue is counted and
#: reported, and its SUM is carried as one line rather than dropped: each piece is too
#: small to be an amount anybody entered, but together they are the difference between
#: this project's total and MS Project's own, and a difference nobody can see is worse
#: than a small line somebody can.
FIXED_COST_MINIMUM_FILE_UNITS = Decimal(1)

#: The task the aggregated residue line is keyed on.
#:
#: Zero, because MS Project numbers its own tasks from 1 and reserves 0 for the project
#: summary -- which has no Fixed Cost of its own and never appears in `finance_mpp_rows`
#: as a costed task. So it is a key no real task can claim, which is what a synthetic line
#: needs. `_FIXED_COST_TASKS` excludes it explicitly rather than relying on that: if a
#: future file ever did state a fixed cost on task 0, the two would collide silently and
#: the aggregate would be matched as though it were the file's own figure.
FIXED_COST_RESIDUE_TASK_UID = 0

#: Every task of a source version that states a fixed cost, once per task.
#:
#: `DISTINCT ON` is load-bearing. A task's fixed cost is repeated on every row the task
#: has -- `source_cost` has the same shape, and summing it across rows overcounts by the
#: number of assignments -- so the de-duplication belongs here, in the one query that
#: reads it, rather than in the arithmetic downstream.
_FIXED_COST_TASKS = """
    SELECT DISTINCT ON (source_task_uid)
           source_task_uid, task_wbs, task_name,
           source_fixed_cost, source_fixed_cost_irr
      FROM finance_mpp_rows
     WHERE source_version_id = %(version_id)s
       AND organization_id = %(organization_id)s AND project_id = %(project_id)s
       AND source_task_uid IS NOT NULL
       AND source_task_uid <> 0
       AND source_fixed_cost_irr IS NOT NULL
       AND source_fixed_cost IS NOT NULL
       AND source_fixed_cost <> 0
     ORDER BY source_task_uid
"""

_FIND_FIXED_COST_RESOURCE = """
    SELECT id FROM finance_resources
     WHERE organization_id=%s AND project_id=%s AND code=%s AND deleted_at IS NULL
"""

_INSERT_FIXED_COST_RESOURCE = """
    INSERT INTO finance_resources
        (id, organization_id, project_id, resource_type, code, title, base_unit,
         dimension, created_by)
    VALUES (%s,%s,%s,'general_cost',%s,%s,NULL,NULL,%s)
    ON CONFLICT DO NOTHING
"""

#: A fixed cost line, keyed on the TASK. `original_quantity` is NULL because a general cost
#: has no quantity to measure -- the amount is the whole of it, and it goes in the price
#: column, which is exactly the shape the Excel importer already gives a general cost.
#: `assignment_external_id` is NULL because there is no assignment; the report pairs
#: progress by that column and skips general cost lines before it ever looks.
_INSERT_FIXED_COST_LINE = """
    INSERT INTO estimate_lines
        (id, organization_id, project_id, resource_id, activity_external_id,
         assignment_external_id, original_quantity, original_unit_price_irr, source,
         source_assignment_uid, source_task_uid, created_by)
    VALUES (%s,%s,%s,%s,%s,NULL,NULL,%s,'progress_feed',NULL,%s,%s)
    ON CONFLICT DO NOTHING
"""


def estimate_basis(row):
    """The quantity and unit rate a line may be created with, or `(None, None)`.

    Both or neither. A quantity with no rate prices nothing and a rate with no quantity
    measures nothing, so a half-stated row states nothing here; and neither travels at all
    unless `source_rate_basis` says the file's own arithmetic proved the rate is per unit
    of that quantity. `(None, None)` becomes two NULL columns, which is the line saying it
    was never given an estimate -- not that its estimate is zero.
    """
    if row.get("source_rate_basis") != MATERIAL_UNIT_RATE:
        return None, None
    quantity = row.get("source_material_quantity")
    rate = row.get("source_resource_rate_irr")
    if quantity is None or rate is None:
        return None, None
    return quantity, rate


def _resource_title(stated):
    """A resource's name as Finance stores it: trimmed, bounded, never blank.

    The trim is not cosmetic. `ResourceResponse` inherits `ResourceCreate.nonblank`, which
    strips `title` -- so a resource created through the API is stored trimmed, while one
    created here kept whatever padding the schedule carried. Nine of this project's 189
    resources hold a trailing space for that reason, and the API strips it again on the way
    out, which HIDES the difference: the page shows one string and the table holds another,
    so an export, a report payload or anything joining on the title disagrees with the UI.

    Trimmed on both sides of the length bound: before, so the file's own padding goes, and
    after, because cutting at 120 characters can itself leave a trailing space.
    """
    title = (stated or "").strip()[:120].strip()
    # A name of nothing but whitespace is a name the file did not give.
    return title or "منبع بدون نام"


def _finance_type(native_type):
    """Finance's kind for a schedule resource, or None when the file states none.

    None keeps a resource out rather than guessing it in: such a resource is reported
    unmapped. Since 0038 the file's three kinds all have a Finance kind, so this answers
    None only for a kind MS Project itself does not have.
    """
    return RESOURCE_TYPE_BY_NATIVE.get((native_type or "").upper())


#: Every row of the current schedule, in exactly one state.
#:
#: The states are mutually exclusive and exhaustive by construction, so the three counts
#: always sum to the total: a reader who sees them add up knows nothing was quietly left
#: out of the reckoning, which is the only reason to publish a status at all.
#:
#:   assignment_mapped  a resource is assigned here, and Finance carries the estimate line
#:                      for it. This is the ordinary state.
#:   activity_only      the schedule states an activity and no resource behind it -- a
#:                      stage heading, or a milestone like «شروع», «تحویل زمین», «گرفتن
#:                      مجوز». Nothing was bought, so there is nothing to estimate, and
#:                      the absence of a line is the correct answer rather than a gap.
#:   unclassified       a resource IS assigned and yet no estimate line names it. Nothing
#:                      is expected to be here; anything that appears is worth a person.
_MAPPING_STATUS = """
    SELECT CASE
             WHEN m.source_assignment_uid IS NULL THEN 'activity_only'
             WHEN m.source_resource_uid IS NULL THEN 'activity_only'
             WHEN EXISTS (SELECT 1 FROM estimate_lines l
                           WHERE l.organization_id = m.organization_id
                             AND l.project_id = m.project_id
                             AND l.source_assignment_uid = m.source_assignment_uid
                             AND l.deleted_at IS NULL) THEN 'assignment_mapped'
             ELSE 'unclassified'
           END AS status,
           count(*) AS rows,
           count(*) FILTER (WHERE m.source_assignment_uid IS NULL) AS stage_labels,
           count(*) FILTER (WHERE m.source_assignment_uid IS NOT NULL
                              AND m.source_resource_uid IS NULL) AS assignments_without_resource
      FROM finance_mpp_rows m
     WHERE m.source_version_id = %(version_id)s
     GROUP BY 1
"""

#: The rows a person may want to look at: the ones in a state nobody planned for.
_UNCLASSIFIED_ROWS = """
    SELECT m.source_assignment_uid AS assignment_uid,
           m.source_resource_uid   AS resource_uid,
           m.task_wbs, m.task_name, m.resource_name
      FROM finance_mpp_rows m
     WHERE m.source_version_id = %(version_id)s
       AND m.source_assignment_uid IS NOT NULL
       AND m.source_resource_uid IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM estimate_lines l
                        WHERE l.organization_id = m.organization_id
                          AND l.project_id = m.project_id
                          AND l.source_assignment_uid = m.source_assignment_uid
                          AND l.deleted_at IS NULL)
     ORDER BY m.source_assignment_uid
     LIMIT 200
"""


class FinanceMppClassificationRefused(RuntimeError):
    """A classification that must not be recorded. `code` is the stable API contract."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class FinanceMppMappingService:
    """Creates or matches Finance resources and estimate lines from persisted MPP rows.

    Every resource the file names is typed by the file: MATERIAL, WORK and COST are
    Finance's three kinds (0038). Resources a person classified as `labor` or `equipment`
    before that are matched by `source_resource_uid` exactly as before -- the lookup runs
    ahead of the kind rule -- and read as `work` everywhere else.
    """

    def __init__(self, connection_factory, id_factory=uuid4):
        self._connect = connection_factory
        self._ids = id_factory

    async def current_version_id(self, organization_id, project_id):
        """The newest ready source version for this project, or None."""
        async with await self._connect() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    active_source_version(organization="%s", project="%s"),
                    (organization_id, project_id))
                found = await cursor.fetchone()
        return None if found is None else found["id"]

    async def current_version_detail(self, organization_id, project_id):
        """Which file the active version was read from, and when. Reads only; None if none.

        The same statement `current_version_id` uses, asked for more columns, so the
        provenance a reader is shown can never belong to a different version from the one
        the counts were taken over. A separate query ordered the same way would usually
        agree -- and would stop agreeing exactly when an import lands between the two.
        """
        async with await self._connect() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    active_source_version(
                        columns="id, source_file_name_safe, imported_at, reporting_date,"
                                " row_count",
                        organization="%s", project="%s"),
                    (organization_id, project_id))
                return await cursor.fetchone()

    async def mapping_status(self, organization_id, project_id):
        """What became of every row of the current schedule. Reads only.

        Nothing here computes a financial figure or touches one: it counts rows and says
        which state each is in. A schedule the project has not imported yet reports zero
        of everything rather than failing -- there is nothing to say, and that is a
        different answer from an error.
        """
        version = await self.current_version_id(organization_id, project_id)
        if version is None:
            return {"sourceVersionId": None, "total": 0, "assignmentMapped": 0,
                    "activityOnly": 0, "unclassified": 0,
                    "activityOnlyDetail": {"stageLabelRows": 0,
                                           "assignmentsWithoutResource": 0},
                    "unclassifiedRows": []}
        async with await self._connect() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(_MAPPING_STATUS, {"version_id": version})
                counted = {row["status"]: row for row in await cursor.fetchall()}
                await cursor.execute(_UNCLASSIFIED_ROWS, {"version_id": version})
                stray = await cursor.fetchall()
        activity_only = counted.get("activity_only") or {}
        return {
            "sourceVersionId": str(version),
            "total": sum(row["rows"] for row in counted.values()),
            "assignmentMapped": (counted.get("assignment_mapped") or {}).get("rows", 0),
            "activityOnly": activity_only.get("rows", 0),
            "unclassified": (counted.get("unclassified") or {}).get("rows", 0),
            # The two kinds of "no resource behind it", told apart because they are
            # different things: a stage heading never had an assignment, while a
            # milestone has one that names nobody.
            "activityOnlyDetail": {
                "stageLabelRows": activity_only.get("stage_labels", 0),
                "assignmentsWithoutResource": activity_only.get(
                    "assignments_without_resource", 0)},
            "unclassifiedRows": [
                {"sourceAssignmentUid": r["assignment_uid"],
                 "sourceResourceUid": r["resource_uid"], "wbsCode": r["task_wbs"],
                 "taskName": r["task_name"], "resourceName": r["resource_name"]}
                for r in stray],
        }

    async def map_source_version(self, organization_id, project_id, version_id,
                                 actor_user_id=None):
        """One pass over a source version. Returns what was created, matched and refused.

        `actor_user_id` is required: a financial record names who created it, and
        `estimate_lines.created_by` is NOT NULL. Refusing here names the missing thing;
        letting it through would surface as a constraint violation halfway through a
        transaction, with nothing on screen to say an actor was what was missing.
        """
        if actor_user_id is None:
            raise FinanceMppClassificationRefused(
                "FINANCE_MPP_ACTOR_REQUIRED",
                "mapping creates financial records and must name who asked for them")
        result = {"sourceVersionId": str(version_id),
                  "resourcesCreated": 0, "resourcesMatched": 0,
                  "linesCreated": 0, "linesMatched": 0,
                  # Of the lines created, how many the file could give an estimate to. The
                  # difference is not a failure: a row the file states no material quantity
                  # for has no estimate to give, and says so by staying NULL.
                  "linesWithEstimate": 0,
                  # The task's own money, which belongs to no resource on it. Counted
                  # apart from the assignment lines because it is a different reading of
                  # the file, and a reader comparing a total against MS Project needs to
                  # know which half moved.
                  "fixedCostLinesCreated": 0, "fixedCostLinesMatched": 0,
                  "fixedCostIrr": "0",
                  # How much of the fixed cost arrived as reconciliation residue rather
                  # than as an amount somebody entered. See FIXED_COST_MINIMUM_FILE_UNITS:
                  # below one unit of the file's own currency, a fixed cost is what is left
                  # of MS Project's own arithmetic. Those rows do not become lines of their
                  # own -- twenty-one lines of a fraction of a rial would be noise -- but
                  # their SUM does, on FIXED_COST_RESIDUE_TASK_UID, so the project total
                  # still reconciles to the file. These two say how many rows and how much,
                  # in the file's units, went into that one line.
                  "fixedCostResidueRows": 0, "fixedCostResidueFileUnits": "0",
                  "unmappedRows": 0, "unclassifiedResources": []}

        async with await self._connect() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(_SOURCE_ROWS, {"version_id": str(version_id),
                                                       "organization_id": organization_id,
                                                       "project_id": project_id})
                    rows = await cursor.fetchall()

                    # 1. One financial item per distinct schedule resource. Built from the
                    #    resource's own facts -- never from the task it happens to serve.
                    resources = {}
                    for row in rows:
                        uid = row["source_resource_uid"]
                        if uid not in resources:
                            resources[uid] = row
                    by_uid = {}
                    for uid, row in sorted(resources.items()):
                        # The lookup comes FIRST, before the kind rule, because a person
                        # may already have classified this resource. Asking the rule first
                        # would keep skipping a WORK resource that someone has since
                        # decided is equipment -- the decision would be stored and ignored.
                        await cursor.execute("""
                            SELECT id FROM finance_resources
                             WHERE organization_id=%s AND project_id=%s
                               AND source_resource_uid=%s AND deleted_at IS NULL
                        """, (organization_id, project_id, uid))
                        found = await cursor.fetchone()
                        if found is not None:
                            by_uid[uid] = found["id"]
                            result["resourcesMatched"] += 1
                            continue
                        kind = _finance_type(row["resource_type"])
                        if kind is None:
                            # The file states a kind Finance cannot name. Left unmapped
                            # and reported; nothing is guessed.
                            result["unclassifiedResources"].append(
                                {"sourceResourceUid": uid, "name": row["resource_name"],
                                 "nativeType": row["resource_type"]})
                            continue
                        if kind == "general_cost":
                            # A general cost is an amount, not a measured thing, so it
                            # carries no unit -- the same rule the resource form applies.
                            unit, dimension = None, None
                        elif kind == "work":
                            # Hours, by the file's own convention; see WORK_UNIT.
                            unit, dimension = WORK_UNIT, UNIT_REGISTRY[WORK_UNIT].dimension
                        else:
                            unit, dimension = row["resource_unit"], "count"
                        resource_id = str(self._ids())
                        await cursor.execute(
                            _INSERT_RESOURCE,
                            (resource_id, organization_id, project_id, kind,
                             "%s%s" % (RESOURCE_CODE_PREFIX, uid),
                             _resource_title(row["resource_name"]),
                             unit, dimension, uid, actor_user_id))
                        by_uid[uid] = resource_id
                        result["resourcesCreated"] += 1

                    # 2. One estimate line per assignment, carrying the file's own
                    #    quantity and unit rate where the file proved both.
                    for row in rows:
                        resource_id = by_uid.get(row["source_resource_uid"])
                        if resource_id is None:
                            result["unmappedRows"] += 1
                            continue
                        await cursor.execute("""
                            SELECT id FROM estimate_lines
                             WHERE organization_id=%s AND project_id=%s
                               AND source_assignment_uid=%s AND deleted_at IS NULL
                        """, (organization_id, project_id, row["source_assignment_uid"]))
                        if await cursor.fetchone() is not None:
                            result["linesMatched"] += 1
                            continue
                        quantity, unit_rate = estimate_basis(row)
                        await cursor.execute(
                            _INSERT_LINE,
                            (str(self._ids()), organization_id, project_id, resource_id,
                             # The identifiers the report's pairing reads, written from the
                             # file's own values so a line and its feed row agree.
                             row["task_wbs"], str(row["source_assignment_uid"]),
                             quantity, unit_rate,
                             row["source_assignment_uid"], row["source_task_uid"],
                             actor_user_id))
                        if quantity is not None:
                            result["linesWithEstimate"] += 1
                        result["linesCreated"] += 1

                    # 3. One estimate line per task that states a fixed cost of its own.
                    #    Separate from the loop above because a fixed cost is the task's,
                    #    not any resource's: it has no assignment to be keyed on and no
                    #    resource to be attributed to, which is exactly why the two
                    #    readings cannot share a pass.
                    await self._map_fixed_costs(cursor, organization_id, project_id,
                                                version_id, actor_user_id, result)

        LOG.info("finance mpp mapping project=%s resources=+%d/=%d lines=+%d/=%d "
                 "fixed=+%d/=%d unmapped=%d",
                 project_id, result["resourcesCreated"], result["resourcesMatched"],
                 result["linesCreated"], result["linesMatched"],
                 result["fixedCostLinesCreated"], result["fixedCostLinesMatched"],
                 result["unmappedRows"])
        return result

    async def _map_fixed_costs(self, cursor, organization_id, project_id, version_id,
                               actor_user_id, result):
        """The money the file puts on the task itself, as general cost estimate lines.

        MS Project states a task's cost in two places: on its assignments, and on the task
        as Fixed Cost. The first is a resource's money and became the lines above; the
        second is the ACTIVITY'S -- a permit, a mobilisation, a lump sum nobody broke into
        resources -- and has no resource to be attributed to. PRD FR-010 already has the
        shape for that: a general cost carries an amount and no quantity or unit, and §9
        defines its initial estimate as the amount itself.

        What this refuses to do is the same list as everywhere else in this module. It does
        not attribute the money to a resource on the task: every one of this project's
        equipment assignments shares its task with a material assignment, so anything moved
        from the task to a resource would be the material's cost counted twice. It does not
        invent a quantity for it -- there is none, and NULL says so. And it does not read
        `source_fixed_cost` as rials: `source_fixed_cost_irr` is the same figure through the
        file's own currency decision, and a file whose currency was never decided has NULL
        there and produces nothing here.
        """
        await cursor.execute(_FIXED_COST_TASKS, {"version_id": str(version_id),
                                                 "organization_id": organization_id,
                                                 "project_id": project_id})
        tasks = await cursor.fetchall()
        priced = []
        residue = Decimal(0)
        residue_irr = Decimal(0)
        for row in tasks:
            stated = Decimal(row["source_fixed_cost"])
            if abs(stated) < FIXED_COST_MINIMUM_FILE_UNITS:
                result["fixedCostResidueRows"] += 1
                residue += stated
                # Summed in rials as well as in the file's units, because the file's units
                # are what the THRESHOLD is stated in and rials are what a line is stored
                # in. Rounding each piece on its own would round twenty-one numbers smaller
                # than a rial to nothing and lose the sum; the sum is rounded once, below.
                residue_irr += Decimal(row["source_fixed_cost_irr"])
                continue
            priced.append(row)
        result["fixedCostResidueFileUnits"] = format(residue, "f")

        # The aggregate, decided before anything is written so an empty pass stays empty.
        # Same rounding policy as every other amount here: whole rials, ROUND_HALF_UP.
        aggregate = residue_irr.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        # Zero is not a line. A residue that rounds away states nothing a reader could act
        # on, and a general cost of nought would sit in the estimate forever saying it.
        if aggregate == 0:
            aggregate = None
        if not priced and aggregate is None:
            return

        # The item they hang on, created once per project. Looked up first and inserted
        # only if absent, the same order the resource loop above uses and for the same
        # reason: a project that already has it must not get a second one.
        await cursor.execute(_FIND_FIXED_COST_RESOURCE,
                             (organization_id, project_id, FIXED_COST_RESOURCE_CODE))
        found = await cursor.fetchone()
        if found is None:
            await cursor.execute(
                _INSERT_FIXED_COST_RESOURCE,
                (str(self._ids()), organization_id, project_id, FIXED_COST_RESOURCE_CODE,
                 FIXED_COST_RESOURCE_TITLE, actor_user_id))
            # Read back rather than trusting the insert: ON CONFLICT DO NOTHING means a
            # concurrent pass may have won, and then the id to use is theirs, not ours.
            await cursor.execute(_FIND_FIXED_COST_RESOURCE,
                                 (organization_id, project_id, FIXED_COST_RESOURCE_CODE))
            found = await cursor.fetchone()
            if found is not None:
                result["resourcesCreated"] += 1
        if found is None:
            return
        resource_id = found["id"]

        # (task uid, activity, amount) for everything this pass would write. The aggregate
        # is built into the same list rather than written separately, so it is matched,
        # counted and totalled by exactly the rules the file's own fixed costs are -- and
        # a second pass over an unchanged schedule matches it instead of adding another.
        writes = [(row["source_task_uid"], row["task_wbs"],
                   # Whole rials, like every other amount Finance stores, and like the
                   # standard rate the assignment lines carry. The column is numeric(18,0)
                   # and would round anyway; doing it here means the number written is the
                   # number decided.
                   Decimal(row["source_fixed_cost_irr"]).quantize(
                       Decimal(1), rounding=ROUND_HALF_UP))
                  for row in priced]
        if aggregate is not None:
            # No activity: this line is the residue of many tasks and belongs to none of
            # them, and naming one of their WBS codes would attribute it to that activity.
            writes.append((FIXED_COST_RESIDUE_TASK_UID, None, aggregate))

        total = Decimal(0)
        for task_uid, activity, amount in writes:
            await cursor.execute("""
                SELECT id FROM estimate_lines
                 WHERE organization_id=%s AND project_id=%s
                   AND source_task_uid=%s AND source_assignment_uid IS NULL
                   AND deleted_at IS NULL
            """, (organization_id, project_id, task_uid))
            if await cursor.fetchone() is not None:
                result["fixedCostLinesMatched"] += 1
                continue
            await cursor.execute(
                _INSERT_FIXED_COST_LINE,
                (str(self._ids()), organization_id, project_id, resource_id,
                 activity, amount, task_uid, actor_user_id))
            result["fixedCostLinesCreated"] += 1
            total += amount
        result["fixedCostIrr"] = format(total, "f")
