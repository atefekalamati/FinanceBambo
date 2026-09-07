# -*- coding: utf-8 -*-
"""The activity catalogue, read from Finance's own rows. No MSP table is touched.

`CoreProjectActivityProvider` answers the same questions from `msp_snapshots` and
`msp_tasks`. That was the last thing in the Finance runtime that still needed Core: the
WBS rollup asks for the activity catalogue, and without it `by_wbs` returns nothing --
so a Finance-only deployment could compute every figure except the one broken down by
stage. This provider closes that hole by reading `finance_mpp_rows`, which already holds
the WBS code and the task name for every row Finance persisted.

WHAT AN ACTIVITY IS HERE
One distinct activity code in the current Finance source version. The code is the task's
WBS, which is the same rule the feed uses (`ACTIVITY_CODE_FIELDS`), so an estimate line
that pairs with a feed row pairs with the same activity in the catalogue. Rows are
de-duplicated by code: many assignments share one task, and a stage is named once.

The shape is `CoreProjectActivityProvider`'s exactly -- `activityExternalId`,
`taskExternalId`, `title`, `wbsCode`, `status` -- because `ActivityResponse` forbids
unknown fields and `domain/wbs.py` reads these names. Two providers answering one port
must answer it identically or a report changes meaning with its deployment.
"""

from psycopg.rows import dict_row

#: Everything present in the current source version is part of the current plan. Finance
#: records no lifecycle for a schedule row, and a task dropped from the plan is simply
#: absent from the next version rather than marked inactive.
ACTIVE = "active"

_CURRENT_VERSION = """
    SELECT id FROM finance_mpp_source_versions
     WHERE organization_id = %(organization_id)s AND project_id = %(project_id)s
       AND status = 'ready'
     ORDER BY imported_at DESC, id DESC LIMIT 1
"""

#: One row per distinct WBS code. `min(...)` picks a stable representative for the name and
#: task id: several assignments repeat one task, and the catalogue names each stage once.
_ACTIVITIES = """
    SELECT task_wbs AS code,
           min(task_name) AS title,
           min(source_task_uid) AS task_uid,
           -- The SCHEDULE's cost for this task. It belongs to the task, not to one
           -- assignment: `finance_mpp_sync` copies the task's figure onto every assignment
           -- row, and MS Project's own Task.getCost() rolls a summary task's children into
           -- it. Reported at the activity, therefore, where it is true -- never per item,
           -- where it would be counted once for every item the activity has.
           -- The rows of one task agree on it, and the CASE says so rather than assuming
           -- it: if they ever disagree the answer is no cost at all, because `min` would
           -- then be picking one of several figures and presenting the choice as fact.
           CASE WHEN count(DISTINCT source_cost) = 1 THEN min(source_cost) END AS task_cost
      FROM finance_mpp_rows
     WHERE source_version_id = %(version_id)s
       AND task_wbs IS NOT NULL AND btrim(task_wbs) <> ''
     GROUP BY task_wbs
     ORDER BY task_wbs
"""


class FinanceRowsActivityProvider:
    """`ProjectActivityProvider` over `finance_mpp_rows`. Read-only, Finance-owned."""

    def __init__(self, connection):
        self._connection = connection

    async def _rows(self, sql, params):
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()

    async def _activities(self, organization_id, project_id):
        version = await self._rows(_CURRENT_VERSION, {"organization_id": organization_id,
                                                      "project_id": project_id})
        if not version:
            # No source imported yet. An empty catalogue, not an error: every other report
            # still answers, and `by_wbs` reports no stages rather than failing.
            return {}
        rows = await self._rows(_ACTIVITIES, {"version_id": version[0]["id"]})
        return {row["code"]: {"activityExternalId": row["code"],
                              "taskExternalId": (None if row["task_uid"] is None
                                                 else str(row["task_uid"])),
                              "title": row["title"],
                              "wbsCode": row["code"],
                              "mppTaskCostIrr": row["task_cost"],
                              "status": ACTIVE}
                for row in rows}

    async def list_activities(self, organization_id, project_id, query=None, status=None,
                              page=1, page_size=50):
        """`(rows, total)` for one page, filtered the way the Core provider filters.

        Paged in memory over a catalogue that is one row per stage -- hundreds, not
        millions -- which is what the Core provider does and what keeps the two
        interchangeable.
        """
        activities = await self._activities(organization_id, project_id)
        rows = list(activities.values())
        if status is not None:
            rows = [row for row in rows if row["status"] == status]
        if query:
            term = str(query).casefold()
            rows = [row for row in rows
                    if term in (row["title"] or "").casefold()
                    or term in row["activityExternalId"].casefold()]
        start = (page - 1) * page_size
        return rows[start:start + page_size], len(rows)
