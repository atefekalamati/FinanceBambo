"""The project's activity list, derived from the tasks of its newest MSP snapshot.

WHY MSP TASKS ARE THE SOURCE
Core has no activity or WBS registry of its own. The only place a project's breakdown
exists is inside the schedule snapshots parsed from MPP files, so that is where this reads
from. It is a real source, but a narrower one than the port implies, and the difference
matters in two ways worth stating plainly:

  * A project with no snapshot has no activities. Not an error -- there genuinely is no
    breakdown yet.
  * Activities appear and disappear as the schedule is re-planned. An estimate line bound
    to an activity code that the newest snapshot no longer contains will stop resolving.
    That is Core's reality showing through, not a bug here, and it is exactly the kind of
    thing an estimate should surface rather than hide.

WHY THERE IS NO `create_activity`
Deliberately absent, not stubbed. Core's only activity-like rows live in `msp_tasks`, which
are the parsed contents of an uploaded file: inserting a row there would put something in a
snapshot that the file it claims to come from does not contain, and the next upload would
silently erase it.

`FinanceResourcesService.create_activity` checks for the method with `hasattr` and raises
`ActivityProviderUnavailable` when it is missing, so leaving it out produces the correct,
explicit refusal at the API boundary with no extra code. Adding a method that raises would
say the same thing less clearly and invite someone to "finish" it later.
"""

from psycopg.rows import dict_row

from .progress import PROGRESS_SNAPSHOT_TYPES, activity_code, task_external_id

#: The snapshot activities are read from: the newest one that carries progress. `TARGET`
#: baselines are excluded for the same reason as in the progress adapter -- see there.
NEWEST_SNAPSHOT = """
    SELECT snapshot.id
    FROM msp_snapshots AS snapshot
    JOIN projects AS project ON project.id = snapshot.project_id
    WHERE snapshot.project_id = %(project_id)s
      AND project.organization_id = %(organization_id)s
      AND snapshot.snapshot_type = ANY(%(types)s)
    ORDER BY snapshot.created_at DESC, snapshot.id DESC
    LIMIT 1
"""

TASKS = """
    SELECT id, uid, guid, task_id, name, wbs, outline_number, outline_level, text1
    FROM msp_tasks
    WHERE snapshot_id = %(snapshot_id)s
    ORDER BY outline_number NULLS LAST, id
"""


class CoreProjectActivityProvider:
    """`ProjectActivityProvider` over the newest MSP snapshot's tasks. Read-only."""

    def __init__(self, connection, *, progress_types=PROGRESS_SNAPSHOT_TYPES):
        self._connection = connection
        self._progress_types = tuple(progress_types)

    async def _rows(self, sql, params):
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()

    async def _activities(self, organization_id, project_id):
        """Every distinct activity in the newest snapshot, in outline order.

        Keyed by activity code, first task wins. Several tasks can carry one code -- a code
        naming a phase that was broken into steps -- and the first in outline order is the
        outermost, which is the one that represents the phase.
        """
        snapshot = await self._rows(NEWEST_SNAPSHOT, {
            "project_id": project_id, "organization_id": str(organization_id),
            "types": list(self._progress_types)})
        if not snapshot:
            return {}
        activities = {}
        for task in await self._rows(TASKS, {"snapshot_id": snapshot[0]["id"]}):
            code = activity_code(task)
            if code is None or code in activities:
                continue
            activities[code] = {
                "activityExternalId": code,
                "taskExternalId": task_external_id(task),
                "title": task["name"],
                "wbsCode": task["wbs"],
                # Core records no lifecycle for a task. Every task present in the newest
                # snapshot is part of the current plan, which is what "active" means here;
                # a task that has been removed from the plan is absent rather than inactive.
                # `ActivityResponse` forbids unknown fields, and it has no parent of its
                # own -- so a parent link is deliberately not reported here. Core does
                # record hierarchy through `outline_level`, and adding it would mean
                # widening the public contract rather than quietly attaching a field the
                # schema would reject.
                "status": "active",
            }
        return activities

    async def list_activities(self, organization_id, project_id, query=None, status=None,
                              page=1, page_size=50):
        rows = list((await self._activities(organization_id, project_id)).values())
        if query:
            term = query.casefold()
            rows = [r for r in rows
                    if term in (r["title"] or "").casefold()
                    or term in r["activityExternalId"].casefold()]
        if status:
            rows = [r for r in rows if r["status"] == status]
        start = (page - 1) * page_size
        return rows[start:start + page_size], len(rows)

    async def get_activity(self, organization_id, project_id, activity_external_id):
        return (await self._activities(organization_id, project_id)).get(activity_external_id)
