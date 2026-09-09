# -*- coding: utf-8 -*-
"""Progress answered from Finance's OWN persisted rows. No MSP table, no file, no JVM.

This is the adapter a Finance report should read from. `finance_mpp_sync` reads the file
once and writes `finance_mpp_source_versions` + `finance_mpp_rows`; this reads those two
tables back into the same feed shape every other provider produces, so the calculation
never knows which adapter answered.

WHY NOT READ THE FILE AT REQUEST TIME
`MppFileProgressProvider` parses the schedule through a JVM on demand. That proves Finance
CAN read the file without MSP, and it is the right engine for the sync -- but a report
built from a parse held in memory is not reproducible: the file changes, the cache turns
over, and last month's issued figures can no longer be re-derived. The persisted rows are
the durable record, so they are what a report reads.

IDENTITY
A snapshot here is a Finance source version, named by its own UUID. `hostSnapshotId` is
null: no MSP snapshot is being referred to, and a report pinned to one of these versions
resolves without `progress_snapshot_refs` ever reaching `msp_snapshots`.

ONE SHAPE
Rows are handed to the same `task_row` / `assignment_row` builders the Core and file
adapters use, with the columns Finance did not persist set to None. `task_progress` then
reads the planner's own `actual_progress_percent` -- persisted -- and has nothing else to
fall back on, which is the truth: Finance did not keep MS Project's duration percentage,
so it does not report one.
"""

from psycopg.rows import dict_row

from .progress import (ACTIVITY_CODE_FIELDS, STATUS_READY, assignment_row, task_row)

#: `sourceType` names the KIND of source file, and its vocabulary is closed by the API
#: schema. A Finance source version was read from a Microsoft Project file, so that is
#: what it says. What makes it a FINANCE version rather than a Core snapshot is the pair
#: below: no host identifier, and a `sourceFileVersionId` naming the version itself.
SOURCE_TYPE_FINANCE_ROWS = "microsoft_project"

_VERSION = """
    SELECT id, organization_id, project_id, source_file_name_safe, source_sha256,
           row_count, imported_by, imported_at, reporting_date
      FROM finance_mpp_source_versions
     WHERE organization_id = %(organization_id)s AND project_id = %(project_id)s
       AND status = 'ready'
"""
_CURRENT = _VERSION + " ORDER BY imported_at DESC, id DESC LIMIT 1"
_BY_ID = _VERSION + " AND id = %(version_id)s"

_ROWS = """
    SELECT source_task_uid, source_assignment_uid, source_resource_uid,
           task_name, task_wbs, task_start, task_finish,
           resource_name, resource_type, resource_unit,
           quantity, quantity_unit,
           weight_rial, weight_time, weight_base, actual_progress,
           actual_progress_percent, physical_progress, planned_progress,
           progress_variance, source_cost, source_actual_cost, source_fixed_cost
      FROM finance_mpp_rows
     WHERE source_version_id = %(version_id)s
     ORDER BY source_task_uid, source_assignment_uid NULLS FIRST
"""


def _builder_row(row):
    """A persisted row in the vocabulary the shared feed builders read.

    Every column Finance chose not to persist is None -- MS Project's own duration and
    work percentages, and reported work hours. None, not a guess: the builders treat None
    as "not stated", which is exactly what Finance knows about those fields. Work is absent
    deliberately: `resolve_progress_quantity` would read it as an executed quantity for a
    labour or equipment resource, and that is a financial decision nobody has taken.
    """
    return {
        "id": None, "uid": row["source_task_uid"], "guid": None, "task_id": None,
        "name": row["task_name"], "wbs": row["task_wbs"],
        "outline_number": None, "outline_level": None,
        "start": row["task_start"], "finish": row["task_finish"],
        "percent_complete": None, "percent_work_complete": None,
        "physical_percent_complete": None, "text1": None,
        "item_quantity": None,
        "weight_rial": row["weight_rial"], "weight_time": row["weight_time"],
        "weight_base": row["weight_base"],
        "actual_progress": row["actual_progress"],
        "actual_progress_percent": row["actual_progress_percent"],
        "physical_progress": row["physical_progress"],
        "planned_progress": row["planned_progress"],
        "progress_variance": row["progress_variance"],
        "task_cost": row["source_cost"],
        "jalali_start": None, "jalali_finish": None,
        "assignment_uid": row["source_assignment_uid"],
        "task_uid": row["source_task_uid"],
        "resource_uid": row["source_resource_uid"],
        "units": None, "planned_work": None, "actual_work": None, "remaining_work": None,
        # The Finance quantity rule already applied at sync time: approved column or NULL.
        "planned_quantity": row["quantity"], "actual_quantity": None,
        "remaining_quantity": None, "quantity_unit": row["quantity_unit"],
        "assignment_work_complete_percent": None,
        "resource_name": row["resource_name"],
        "native_type": row["resource_type"],
        # MATERIAL is unambiguous; MS Project does not say whether a WORK resource is
        # labour or equipment, so that stays unclassified rather than guessed.
        "bambo_resource_type": ("material"
                                if (row["resource_type"] or "").upper() == "MATERIAL"
                                else None),
        "resource_quantity_unit": row["resource_unit"],
    }


class FinanceRowsProgressProvider:
    """`ProgressSnapshotProvider` over `finance_mpp_source_versions` / `finance_mpp_rows`."""

    def __init__(self, connection, activity_code_fields=ACTIVITY_CODE_FIELDS):
        self._connection = connection
        self._activity_code_fields = tuple(activity_code_fields)

    async def _fetch(self, sql, params):
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()

    async def _envelope(self, version):
        rows = [_builder_row(r) for r in await self._fetch(_ROWS, {"version_id": version["id"]})]
        if any(r["assignment_uid"] is not None for r in rows):
            feed = [assignment_row(r, self._activity_code_fields) for r in rows
                    if r["assignment_uid"] is not None]
        else:
            feed = [task_row(r, self._activity_code_fields) for r in rows]
        stated = any((r["actual_progress_percent"] or 0) != 0 for r in rows)
        return {
            "snapshot": {
                "organizationId": str(version["organization_id"]),
                "projectId": version["project_id"],
                "progressSnapshotId": str(version["id"]),
                "hostSnapshotId": None,
                "hostFileVersionId": None,
                # The version IS the source file version. Together with a null host id
                # this is how a reader -- and `reference_from_header` -- tells a Finance
                # source version from a Core snapshot.
                "sourceFileVersionId": str(version["id"]),
                "sourceFileNameSafe": version["source_file_name_safe"],
                "reportingDate": (version["reporting_date"]
                                  or version["imported_at"].date()).isoformat(),
                "status": STATUS_READY,
                "snapshotType": "ACTUAL" if stated else "TARGET",
                "sourceType": SOURCE_TYPE_FINANCE_ROWS,
                "importedBy": str(version["imported_by"]) if version["imported_by"] else None,
                "importedAt": version["imported_at"].isoformat(),
            },
            "assignments": feed,
        }

    async def current_snapshot(self, organization_id, project_id, as_of=None):
        found = await self._fetch(_CURRENT, {"organization_id": organization_id,
                                             "project_id": project_id})
        return await self._envelope(found[0]) if found else None

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        """The version named by its own UUID, or None for any identifier it never issued.

        A Core snapshot id, a file sha, a Finance-minted reference UUID -- none of those
        is a source version, and None is the honest answer; the composite provider then
        asks the next source, which is how a genuinely historical Core snapshot still
        resolves when the host wired Core.
        """
        try:
            version_id = str(snapshot_id)
            if len(version_id) != 36:
                return None
            found = await self._fetch(_BY_ID, {"organization_id": organization_id,
                                               "project_id": project_id,
                                               "version_id": version_id})
        except Exception:                                      # noqa: BLE001
            return None
        return await self._envelope(found[0]) if found else None
