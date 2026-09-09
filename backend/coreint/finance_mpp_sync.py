# -*- coding: utf-8 -*-
"""Reading a schedule file into Finance's OWN tables. No MSP table is touched or needed.

This is the Finance half of the shared reader's output. The MSP importer writes `msp_*`
from the same parse; this writes `finance_mpp_source_versions` and `finance_mpp_rows`, and
neither knows about the other. A deployment running Finance alone has this and nothing
else, and every number a Finance report needs from the schedule is recoverable from these
two tables months later.

IDEMPOTENCE IS THE FILE'S HASH
A version is one row per distinct file CONTENT. Re-reading unchanged bytes finds the
existing version and writes nothing; changed bytes make a new version and leave the old one
intact, so a report issued against the old content stays reproducible.

QUANTITY
`quantity` is written only when the schedule states an APPROVED quantity column -- an alias
the planners agreed means exactly that. Nothing else becomes a quantity: not work, not a
duration, not a cost, not a percentage, and not a custom column that merely holds a number.
The file in front of us states no such column, so every row's quantity is NULL and the
report says so instead of inventing one.
"""

import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from psycopg.rows import dict_row

from .finance_quantity import _decimal, approved_quantity
from .mpp_files import MppFileError, resolve_import_file

LOG = logging.getLogger("coreint.finance_mpp_sync")


class FinanceMppSyncRefused(RuntimeError):
    """A sync that must not proceed. ``code`` is the stable API contract."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def finance_rows(parsed):
    """Finance-relevant rows from a parsed file, keyed by the file's own identifiers.

    One row per assignment, plus one row per task that has no assignment at all. The
    second kind is what names a WBS stage: summary tasks carry no resources, so without
    them the report knows a stage exists but not what it is called. They hold no
    assignment and no resource, and the feed is built only from rows that name an
    assignment, so they label the tree without entering any sum.

    The MSP identifiers travel as data; no database identity from any module appears.
    """
    tasks = {task["uid"]: task for task in parsed.tasks if task["uid"] is not None}
    resources = {r["uid"]: r for r in parsed.resources if r["uid"] is not None}

    def base(task):
        metrics = task.get("metrics") or {}
        quantity, unit = approved_quantity(task)
        return {
            "source_task_uid": task["uid"],
            "task_name": task["name"],
            "task_wbs": task["wbs"],
            # As the file states them. No timezone is invented for a wall-clock date.
            "task_start": task.get("start"),
            "task_finish": task.get("finish"),
            "quantity": quantity,
            "quantity_unit": unit,
            "progress_variance": _decimal(metrics.get("progress_variance")),
            "weight_rial": _decimal(metrics.get("weight_rial")),
            "weight_time": _decimal(metrics.get("weight_time")),
            "weight_base": _decimal(metrics.get("weight_base")),
            "actual_progress": _decimal(metrics.get("actual_progress")),
            "actual_progress_percent": _decimal(metrics.get("actual_progress_percent")),
            "physical_progress": _decimal(metrics.get("physical_progress")),
            "planned_progress": _decimal(metrics.get("planned_progress")),
            # The SCHEDULE's own cost. Finance actual cost comes from confirmed
            # invoices; the prefix is what keeps the two from being read as one.
            "source_cost": _decimal(metrics.get("task_cost")),
            "source_actual_cost": _decimal(metrics.get("task_actual_cost")),
            "source_fixed_cost": _decimal(metrics.get("task_fixed_cost")),
        }

    rows = []
    assigned = set()
    if parsed.assignments:
        for assignment in parsed.assignments:
            task = tasks.get(assignment["task_uid"])
            if task is None:
                continue
            resource = resources.get(assignment["resource_uid"]) or {}
            row = base(task)
            row.update({
                "source_assignment_uid": assignment["assignment_uid"],
                "source_resource_uid": assignment["resource_uid"],
                "resource_name": resource.get("name"),
                "resource_type": resource.get("native_type"),
                # The resource's own unit -- never the approved quantity's, which is
                # `quantity_unit` and belongs to a different number.
                "resource_unit": (resource.get("quantity_unit")
                                  or resource.get("material_label")
                                  or resource.get("initials")),
            })
            rows.append(row)
            assigned.add(task["uid"])

    # A row for every task that produced none above. A summary task carries no resource
    # assignment -- MS Project rolls its children up instead -- so it was absent from
    # Finance entirely, and the WBS report had no name for the stage it heads: the page
    # showed the bare code "1.5" where "اجرای عملیات سیویل" belongs. These rows exist to
    # carry that name.
    #
    # They state NO assignment and NO resource, which is what they are, and that is also
    # what keeps them out of the calculation: `FinanceRowsProgressProvider` builds feed
    # rows only from rows that name an assignment, so a stage heading can never pair with
    # an estimate line or contribute an executed quantity. It is a label, and it is stored
    # as one.
    for task in parsed.tasks:
        if task["uid"] is None or task["uid"] in assigned:
            continue
        row = base(task)
        row.update({"source_assignment_uid": None, "source_resource_uid": None,
                    "resource_name": None, "resource_type": None,
                    "resource_unit": None})
        rows.append(row)
    return rows


_COLUMNS = ("source_task_uid", "source_assignment_uid", "source_resource_uid",
            "task_name", "task_wbs", "task_start", "task_finish",
            "resource_name", "resource_type", "resource_unit",
            "quantity", "quantity_unit",
            "weight_rial", "weight_time", "weight_base", "actual_progress",
            "actual_progress_percent", "physical_progress", "planned_progress",
            "progress_variance",
            "source_cost", "source_actual_cost", "source_fixed_cost")

_INSERT_ROW = (
    "INSERT INTO finance_mpp_rows (id, organization_id, project_id, source_version_id, "
    + ", ".join(_COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * (4 + len(_COLUMNS))) + ")")


class FinanceMppSyncService:
    """Reads the project's schedule file into Finance's own tables, atomically."""

    async def periodic_tick(self):
        """Sync every Finance project whose file is staged. Never raises.

        A project "has MPP active" when ``<project_id>.mpp`` sits under the configured root,
        exactly as the MSP importer decides it -- but the project list is FINANCE'S: the
        (organization, project) pairs in ``finance_project_settings``, not the host's
        ``projects`` table, so a Finance-only deployment ticks without any MSP schema.
        An unchanged file costs one hash and writes nothing; one project's failure never
        stops the next.
        """
        from pathlib import Path
        root = Path(self._import_root) if self._import_root else None
        if root is None or not root.is_dir():
            return []
        outcomes = []
        for candidate in sorted(root.glob("*.mpp")):
            project_id = candidate.stem
            try:
                async with await self._connect() as connection:
                    async with connection.cursor(row_factory=dict_row) as cursor:
                        await cursor.execute(
                            "SELECT DISTINCT organization_id FROM finance_project_settings "
                            "WHERE project_id = %s", (project_id,))
                        scopes = await cursor.fetchall()
                if not scopes:
                    continue                    # a stray file is not a Finance project
                for scope in scopes:
                    outcome = await self.sync(str(scope["organization_id"]), project_id)
                    outcomes.append({"projectId": project_id,
                                     "organizationId": str(scope["organization_id"]),
                                     "status": outcome["status"],
                                     "rowCount": outcome["rowCount"]})
            except FinanceMppSyncRefused as refused:
                outcomes.append({"projectId": project_id, "status": "refused",
                                 "code": refused.code})
            except Exception as error:                                 # noqa: BLE001
                LOG.exception("finance mpp periodic sync failed project=%s", project_id)
                outcomes.append({"projectId": project_id, "status": "failed",
                                 "code": "FINANCE_MPP_SYNC_CRASHED"})
        return outcomes

    def __init__(self, connection_factory, reader, *, import_root, max_size_mb=100,
                 id_factory=uuid4):
        self._connect = connection_factory
        self._reader = reader
        self._import_root = import_root
        self._max_size_mb = max_size_mb
        self._ids = id_factory

    def _file_name(self, project_id, file_name=None):
        """Which file to read: the caller's choice, else the project's own name.

        A name is only ever a name here -- `resolve_import_file` decides whether it is
        reachable, and it answers that question against the configured root alone. The
        default keeps every existing caller and the periodic tick working unchanged.
        """
        return file_name or ("%s.mpp" % project_id)

    async def sync(self, organization_id, project_id, actor_user_id=None, refresh=False,
                   file_name=None):
        """One sync. Returns what happened; raises `FinanceMppSyncRefused` on refusal.

        The whole write is one transaction: a parse that fails or a row that will not
        insert leaves NO version behind, so a partial read can never be mistaken for a
        complete one.

        `refresh` re-reads an UNCHANGED file and replaces the rows of its existing version.
        The ordinary answer for unchanged bytes is to write nothing, and that is right when
        only the file can change -- but the row shape can change too, and after a migration
        adds a column the stored rows are missing something the file has always stated.
        The version row itself is untouched, so every `progress_snapshot_refs` row and
        every report that pinned this version still resolves. Issued reports are unaffected
        by construction: `report_snapshots.snapshot_payload` freezes the whole feed at
        issue time and is never re-read from these tables.
        """
        import asyncio

        try:
            resolved = resolve_import_file(self._import_root,
                                           self._file_name(project_id, file_name),
                                           self._max_size_mb)
        except MppFileError as error:
            raise FinanceMppSyncRefused(error.code, str(error)) from error

        parsed = await asyncio.to_thread(self._reader.read, resolved.path)
        rows = finance_rows(parsed)
        if not rows:
            raise FinanceMppSyncRefused(
                "MPP_NO_FINANCE_ROWS",
                "the schedule states no task Finance could record")

        async with await self._connect() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute("""
                        SELECT id, row_count, source_file_name_safe, reporting_date
                          FROM finance_mpp_source_versions
                         WHERE organization_id=%s AND project_id=%s AND source_sha256=%s
                    """, (organization_id, project_id, resolved.sha256))
                    existing = await cursor.fetchone()
                    if existing is not None and not refresh:
                        # Same bytes, so the same version -- but possibly a different file.
                        # An operator restages a schedule under the name it arrived with,
                        # and the version would go on naming the file it was first read
                        # from, which is no longer a file anyone has. The CONTENT identity
                        # (the hash) and the history (imported_at, the rows) are untouched;
                        # only the provenance label catches up with where the bytes live
                        # now. Issued reports are unaffected either way: each froze its own
                        # copy of the feed at issue time.
                        if existing["source_file_name_safe"] != resolved.relative_name:
                            await cursor.execute("""
                                UPDATE finance_mpp_source_versions
                                   SET source_file_name_safe = %s WHERE id = %s
                            """, (resolved.relative_name, existing["id"]))
                        if (existing.get("reporting_date") is None
                                and getattr(parsed, "status_date", None) is not None):
                            await cursor.execute("""
                                UPDATE finance_mpp_source_versions
                                   SET reporting_date = %s WHERE id = %s
                            """, (parsed.status_date, existing["id"]))
                        return {"status": "unchanged",
                                "sourceVersionId": str(existing["id"]),
                                "fileSha256": resolved.sha256,
                                "rowCount": existing["row_count"],
                                "quantityRowCount": 0,
                                "fileName": resolved.relative_name}
                    if existing is not None:
                        version_id = str(existing["id"])
                        await cursor.execute("""
                            UPDATE finance_mpp_source_versions
                               SET reporting_date = %s WHERE id = %s
                        """, (getattr(parsed, "status_date", None), version_id))
                        await cursor.execute(
                            "DELETE FROM finance_mpp_rows WHERE source_version_id = %s",
                            (version_id,))
                        for row in rows:
                            await cursor.execute(
                                _INSERT_ROW,
                                [str(self._ids()), organization_id, project_id, version_id]
                                + [row.get(column) for column in _COLUMNS])
                        stated = sum(1 for row in rows if row["quantity"] is not None)
                        return {"status": "refreshed", "sourceVersionId": version_id,
                                "fileSha256": resolved.sha256, "rowCount": len(rows),
                                "quantityRowCount": stated,
                                "fileName": resolved.relative_name}

                    version_id = str(self._ids())
                    await cursor.execute("""
                        INSERT INTO finance_mpp_source_versions
                            (id, organization_id, project_id, source_file_name_safe,
                             source_sha256, source_size_bytes, reader_engine, status,
                             row_count, imported_by, reporting_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,'ready',%s,%s,%s)
                    """, (version_id, organization_id, project_id,
                          resolved.relative_name, resolved.sha256, resolved.size_bytes,
                          getattr(parsed, "parser_engine", None), len(rows),
                          actor_user_id, getattr(parsed, "status_date", None)))
                    for row in rows:
                        await cursor.execute(
                            _INSERT_ROW,
                            [str(self._ids()), organization_id, project_id, version_id]
                            + [row.get(column) for column in _COLUMNS])
        stated = sum(1 for row in rows if row["quantity"] is not None)
        LOG.info("finance mpp sync project=%s rows=%d quantities=%d",
                 project_id, len(rows), stated)
        return {"status": "imported", "sourceVersionId": version_id,
                "fileSha256": resolved.sha256, "rowCount": len(rows),
                "quantityRowCount": stated, "fileName": resolved.relative_name}
