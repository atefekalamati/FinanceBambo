# -*- coding: utf-8 -*-
"""Turning persisted schedule rows into the financial records a report is built from.

`finance_mpp_rows` is what the file said. `finance_resources` and `estimate_lines` are what
Finance owns. This is the one place that carries a row across that line, and it does so on
identity alone: the MPP resource uid names the financial item, the MPP assignment uid names
the estimate line, and anything without those identifiers is left alone.

WHAT AN ASSIGNMENT IS
"This resource, on this activity" -- which is exactly what an estimate line is, so the two
correspond one to one. That is why the assignment uid is the key and not the task: one
resource serves many activities («ترک میکسر» appears on sixty-four of them in the current
file) and one activity draws on many resources. Keying on the task would collapse the first;
keying on the resource would collapse the second.

WHAT THIS REFUSES TO DO
  * invent a quantity. The current file states no approved quantity column, so every line
    is created with `original_quantity` NULL. Work, duration, cost, units and percentages
    are all present in the file and none of them is a quantity; a line with a NULL quantity
    reports itself as unmeasured, which is true, where a line with a fabricated one would
    report a number nobody wrote down.
  * invent a price. `original_unit_price_irr` is NULL for the same reason: the schedule
    prices tasks, not the estimate, and Finance's price belongs to `price_versions`.
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
from uuid import uuid4

from psycopg.rows import dict_row

LOG = logging.getLogger("coreint.finance_mpp_mapping")

#: What a resource read from a schedule is called on the Finance side. The MPP resource uid
#: makes it unique and legible; the code is a label, never the identity the mapping keys on.
RESOURCE_CODE_PREFIX = "MPP-R"

#: How the file's own resource kinds land in Finance's vocabulary. MATERIAL is unambiguous.
#: A WORK resource is labour or equipment and MS Project does not say which, so it becomes
#: the one Finance value that claims nothing about which -- and a COST resource is a general
#: cost. An unrecognised kind maps to nothing and the resource is left unmapped.
RESOURCE_TYPE_BY_NATIVE = {"MATERIAL": "material", "COST": "general_cost"}

#: The Finance type for a resource the file calls WORK. `labor` is a claim MS Project does
#: not make, so it is NOT used here; `equipment` likewise. See `_finance_type`.
UNCLASSIFIED_WORK_TYPE = None

_SOURCE_ROWS = """
    SELECT source_task_uid, source_assignment_uid, source_resource_uid,
           task_name, task_wbs, resource_name, resource_type, resource_unit
      FROM finance_mpp_rows
     WHERE source_version_id = %(version_id)s
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

_INSERT_LINE = """
    INSERT INTO estimate_lines
        (id, organization_id, project_id, resource_id, activity_external_id,
         assignment_external_id, original_quantity, original_unit_price_irr, source,
         source_assignment_uid, source_task_uid, created_by)
    VALUES (%s,%s,%s,%s,%s,%s,NULL,NULL,'progress_feed',%s,%s,%s)
    ON CONFLICT DO NOTHING
"""


def _finance_type(native_type):
    """Finance's kind for a schedule resource, or None when the file does not say.

    Returning None is what keeps a WORK resource out: Finance's vocabulary separates labour
    from equipment and MS Project does not, so calling it either would be a guess dressed as
    data. Such a resource is reported unmapped and a person classifies it.
    """
    return RESOURCE_TYPE_BY_NATIVE.get((native_type or "").upper(), UNCLASSIFIED_WORK_TYPE)


#: What a person may decide a WORK resource is. `material` and `general_cost` are not
#: here: the file states those unambiguously and nobody needs to choose them.
CLASSIFIABLE_TYPES = ("labor", "equipment")

_UNCLASSIFIED = """
    SELECT m.source_resource_uid AS uid,
           min(m.resource_name)  AS name,
           min(m.resource_unit)  AS file_unit,
           count(*)              AS assignment_count,
           min(m.task_name)      AS sample_task
      FROM finance_mpp_rows m
     WHERE m.organization_id = %(organization_id)s AND m.project_id = %(project_id)s
       AND m.source_resource_uid IS NOT NULL
       AND upper(coalesce(m.resource_type, '')) = 'WORK'
       AND NOT EXISTS (SELECT 1 FROM finance_resources fr
                        WHERE fr.organization_id = m.organization_id
                          AND fr.project_id = m.project_id
                          AND fr.source_resource_uid = m.source_resource_uid
                          AND fr.deleted_at IS NULL)
     GROUP BY m.source_resource_uid
     ORDER BY count(*) DESC, m.source_resource_uid
"""


class FinanceMppClassificationRefused(RuntimeError):
    """A classification that must not be recorded. `code` is the stable API contract."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class FinanceMppMappingService:
    """Creates or matches Finance resources and estimate lines from persisted MPP rows.

    Also owns the one decision the file cannot make for us. MS Project calls a resource
    WORK and Finance separates labour from equipment; nothing in the file distinguishes
    them, so a person does, once per resource, and the decision is stored as the resource
    itself -- its `resource_type` beside its `source_resource_uid`. There is no separate
    override table because there is nothing a separate table would record that the
    resource row does not already say, and `ux_finance_resources_source_resource` already
    enforces exactly one decision per (organization, project, resource).
    """

    def __init__(self, connection_factory, id_factory=uuid4):
        self._connect = connection_factory
        self._ids = id_factory

    async def current_version_id(self, organization_id, project_id):
        """The newest ready source version for this project, or None."""
        async with await self._connect() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("""
                    SELECT id FROM finance_mpp_source_versions
                     WHERE organization_id=%s AND project_id=%s AND status='ready'
                     ORDER BY imported_at DESC, id DESC LIMIT 1
                """, (organization_id, project_id))
                found = await cursor.fetchone()
        return None if found is None else found["id"]

    async def list_unclassified(self, organization_id, project_id):
        """Every WORK resource nobody has decided about yet, commonest first."""
        async with await self._connect() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(_UNCLASSIFIED, {"organization_id": organization_id,
                                                     "project_id": project_id})
                rows = await cursor.fetchall()
        return [{"sourceResourceUid": r["uid"], "name": r["name"],
                 # The file's own unit for a WORK resource is MS Project's `initials`,
                 # which defaults to the first letter of the name -- reported so a reader
                 # can see it is not a unit, never used as one.
                 "fileUnit": r["file_unit"], "assignmentCount": r["assignment_count"],
                 "sampleTask": r["sample_task"], "nativeType": "WORK"} for r in rows]

    async def classify(self, organization_id, project_id, source_resource_uid,
                       resource_type, base_unit, actor_user_id=None):
        """Record one person's decision about one WORK resource, as a Finance resource.

        Refuses rather than guesses: an unknown type, a unit the registry does not define,
        or a resource uid the current source never mentions all end as a coded refusal. A
        resource already decided is returned unchanged -- the decision is not re-opened by
        repeating the request.
        """
        from app.finance.domain.unit_registry import UNIT_REGISTRY

        if resource_type not in CLASSIFIABLE_TYPES:
            raise FinanceMppClassificationRefused(
                "FINANCE_MPP_TYPE_NOT_CLASSIFIABLE",
                "a WORK resource is labour or equipment; %r is neither" % (resource_type,))
        unit = UNIT_REGISTRY.get(str(base_unit or ""))
        if unit is None:
            raise FinanceMppClassificationRefused(
                "FINANCE_MPP_UNIT_UNKNOWN",
                "the unit registry defines no unit %r" % (base_unit,))

        async with await self._connect() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    # What the FILE says comes first. A material or a general cost is
                    # already decided by the schedule, and answering "unchanged" to a
                    # request to reclassify one would report success for a decision that
                    # was never anyone's to make.
                    await cursor.execute("""
                        SELECT min(resource_name) AS name, min(resource_type) AS native
                          FROM finance_mpp_rows
                         WHERE organization_id=%s AND project_id=%s AND source_resource_uid=%s
                    """, (organization_id, project_id, source_resource_uid))
                    row = await cursor.fetchone()
                    if row is None or row["name"] is None:
                        raise FinanceMppClassificationRefused(
                            "FINANCE_MPP_RESOURCE_NOT_FOUND",
                            "no persisted schedule row names resource %r"
                            % (source_resource_uid,))
                    if (row["native"] or "").upper() != "WORK":
                        raise FinanceMppClassificationRefused(
                            "FINANCE_MPP_NOT_A_WORK_RESOURCE",
                            "resource %r is %s in the file and needs no decision"
                            % (source_resource_uid, row["native"]))

                    # Already decided. Returned unchanged rather than re-opened: a repeat
                    # of the same request is not a new decision.
                    await cursor.execute("""
                        SELECT id, resource_type FROM finance_resources
                         WHERE organization_id=%s AND project_id=%s
                           AND source_resource_uid=%s AND deleted_at IS NULL
                    """, (organization_id, project_id, source_resource_uid))
                    existing = await cursor.fetchone()
                    if existing is not None:
                        return {"status": "unchanged", "resourceId": str(existing["id"]),
                                "resourceType": existing["resource_type"],
                                "sourceResourceUid": source_resource_uid}

                    resource_id = str(self._ids())
                    await cursor.execute(
                        _INSERT_RESOURCE,
                        (resource_id, organization_id, project_id, resource_type,
                         "%s%s" % (RESOURCE_CODE_PREFIX, source_resource_uid),
                         (row["name"] or "منبع بدون نام")[:120],
                         unit.code, unit.dimension, source_resource_uid, actor_user_id))
        return {"status": "classified", "resourceId": resource_id,
                "resourceType": resource_type, "baseUnit": unit.code,
                "sourceResourceUid": source_resource_uid}

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
                  "unmappedRows": 0, "unclassifiedResources": []}

        async with await self._connect() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(_SOURCE_ROWS, {"version_id": str(version_id)})
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
                            # The file states a kind Finance cannot name, and nobody has
                            # named it either. Left for a person; see `classify`.
                            result["unclassifiedResources"].append(
                                {"sourceResourceUid": uid, "name": row["resource_name"],
                                 "nativeType": row["resource_type"]})
                            continue
                        resource_id = str(self._ids())
                        await cursor.execute(
                            _INSERT_RESOURCE,
                            (resource_id, organization_id, project_id, kind,
                             "%s%s" % (RESOURCE_CODE_PREFIX, uid),
                             (row["resource_name"] or "منبع بدون نام")[:120],
                             # A general cost is an amount, not a measured thing, so it
                             # carries no unit -- the same rule the resource form applies.
                             None if kind == "general_cost" else row["resource_unit"],
                             None if kind == "general_cost" else "count",
                             uid, actor_user_id))
                        by_uid[uid] = resource_id
                        result["resourcesCreated"] += 1

                    # 2. One estimate line per assignment, quantity and price both NULL.
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
                        await cursor.execute(
                            _INSERT_LINE,
                            (str(self._ids()), organization_id, project_id, resource_id,
                             # The identifiers the report's pairing reads, written from the
                             # file's own values so a line and its feed row agree.
                             row["task_wbs"], str(row["source_assignment_uid"]),
                             row["source_assignment_uid"], row["source_task_uid"],
                             actor_user_id))
                        result["linesCreated"] += 1

        LOG.info("finance mpp mapping project=%s resources=+%d/=%d lines=+%d/=%d unmapped=%d",
                 project_id, result["resourcesCreated"], result["resourcesMatched"],
                 result["linesCreated"], result["linesMatched"], result["unmappedRows"])
        return result
