# -*- coding: utf-8 -*-
"""One MPP file becoming one snapshot, atomically, with its Finance mapping.

Core owns this service. It is the only writer of ``msp_file_versions``, ``msp_snapshots``
and ``msp_tasks`` in this repository's import path, and the only builder of
``finance_task_resource_map`` rows. Finance consumes the results through read-only feeds
and never sees a file.

THE TRANSACTION IS THE DESIGN. Everything between "the file was validated" and "the import
is recorded" happens inside one database transaction, so a failure at ANY step leaves
nothing: no file version without its snapshot, no snapshot with half its tasks, no mapping
row pointing at work that was rolled back. The alternative -- partial imports cleaned up by
a janitor -- is how a report ends up computed against a snapshot that only half exists.

Idempotency is the file's SHA-256. An unchanged file never produces a second snapshot;
the periodic tick relies on exactly this, so retry is safe by construction.

Concurrency is a transaction-scoped advisory lock per project
(``pg_try_advisory_xact_lock``): two imports of one project cannot interleave, the lock
dies with the transaction (no leak on crash), and imports of DIFFERENT projects do not
queue behind each other.

WHAT MATCHING NEVER DOES: match by name. A resource named "میلگرد" in the file and a
Finance item titled "میلگرد" are connected only if someone recorded the MPP resource UID in
``finance_resources.external_resource_id``. Unmatched resources are REPORTED, not invented
-- ``completed_with_warnings`` with an explicit unmapped list is the honest outcome, and a
silent auto-created Finance item would be a financial record nobody approved.
"""

import asyncio
import json
import logging
from decimal import Decimal
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .mpp_files import MppFileError, resolve_import_file
from .mpp_reader import MppReaderError
from app.finance.domain.persian_calendar import gregorian_to_persian

LOG = logging.getLogger("coreint.mpp_import")

#: Fallback for ``msp_snapshots.parser_engine`` when the reader cannot say what it is
#: (a test double, an exotic port implementation). The REAL string is derived at JVM
#: boot from the installed mpxj distribution and the running Java -- provenance is
#: recorded, never invented -- and arrives on ``ParsedMppProject.parser_engine``.
PARSER_ENGINE = "mpp-reader-unversioned;finance-repo-importer"


class MppImportRefused(RuntimeError):
    """An import that must not happen. ``code`` is the stable API contract."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _advisory_key(project_id):
    """One lock number per project. hashtext() is done SQL-side; this is the tag."""
    return "mpp_import:%s" % project_id


def _states_progress(value):
    """Whether a percent field states real progress. ``value`` is a clean decimal
    string or None (the reader guarantees it), so Decimal() cannot fail here."""
    return value is not None and Decimal(value) != 0


#: How many run reports the in-process registry keeps. The durable record of a
#: successful import is the snapshot row; this registry only serves the GET endpoints
#: for RECENT runs -- and without a bound, a loop of refused imports (or just the hourly
#: tick's own refusals) would grow it for the life of the process.
RECENT_LIMIT = 200


class MppImportService:
    """Reads one configured file, writes one snapshot, builds the Finance mapping.

    ``connection_factory`` returns a NEW async psycopg connection per call. The importer
    must not share the dev host's single request-serialised connection: the periodic tick
    runs beside requests, and an import transaction held on the shared connection would
    stall the whole host for the length of a parse.
    """

    def __init__(self, connection_factory, reader, *, import_root, max_size_mb=100,
                 id_factory=uuid4):
        self._connect = connection_factory
        self._reader = reader
        self._import_root = import_root
        self._max_size_mb = max_size_mb
        self._ids = id_factory
        #: Import results by importId, for GET endpoints. In-process and deliberately so:
        #: the durable record of a successful import IS the snapshot row; this registry
        #: only lets an operator fetch the report of a recent run, including failed ones
        #: that -- by design -- left nothing in the database to point at.
        self.recent = {}

    def _remember(self, import_id, result):
        """Record a run report, evicting oldest-first past RECENT_LIMIT.

        Dict insertion order makes ``next(iter(...))`` the oldest entry, which keeps the
        latest-endpoint's reversed iteration meaning exactly "most recent first".
        """
        self.recent[import_id] = result
        while len(self.recent) > RECENT_LIMIT:
            del self.recent[next(iter(self.recent))]

    # ------------------------------------------------------------------------ public API
    async def run_import(self, organization_id, project_id, relative_name,
                         actor_user_id=None):
        """One atomic import. Returns the result contract; raises MppImportRefused."""
        import_id = str(self._ids())
        result = {
            "importId": import_id, "projectId": project_id,
            "fileVersionId": None, "snapshotId": None, "reportingPeriodId": None,
            "fileSha256": None, "fileName": relative_name,
            "taskCount": 0, "resourceCount": 0, "assignmentCount": 0,
            "mappedCount": 0, "unmappedCount": 0, "warningCount": 0,
            "unmappedResources": [], "warnings": [],
            "status": "failed", "error": None,
        }
        try:
            outcome = await self._run(organization_id, project_id, relative_name,
                                      actor_user_id, result)
        except (MppFileError, MppReaderError) as error:
            result["error"] = {"code": error.code, "message": str(error)}
            self._remember(import_id, result)
            # %r, not %s: the name is caller-supplied text and must not be able to
            # write its own extra log lines.
            LOG.warning("mpp import failed project=%s file=%r %s: %s",
                        project_id, relative_name, error.code, error)
            raise MppImportRefused(error.code, str(error)) from error
        except MppImportRefused as error:
            result["error"] = {"code": error.code, "message": str(error)}
            self._remember(import_id, result)
            LOG.warning("mpp import refused project=%s file=%r %s: %s",
                        project_id, relative_name, error.code, error)
            raise
        except Exception:
            # A crash (a driver error, an unexpected constraint) must still leave a
            # findable record: the transaction rolled everything back, so this
            # registry entry is the ONLY trace an operator can query. The message is
            # deliberately generic -- raw driver text can carry paths or SQL.
            result["error"] = {"code": "MPP_IMPORT_CRASHED",
                               "message": "the import crashed before completing; "
                                          "details are in the server log"}
            self._remember(import_id, result)
            LOG.exception("mpp import crashed project=%s file=%r",
                          project_id, relative_name)
            raise
        self._remember(import_id, outcome)
        return outcome

    async def periodic_tick(self):
        """Import every project whose configured file changed. Never raises.

        A project "has MPP active" when a file named ``<project_id>.mpp`` exists inside
        the import root -- configuration by presence, with the root itself behind an
        explicit setting. An unchanged hash produces no work; a failure on one project
        does not stop the others.
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
                            "SELECT organization_id FROM projects WHERE id = %s",
                            (project_id,))
                        row = await cursor.fetchone()
                        if row is None or row["organization_id"] is None:
                            continue      # a stray file is not a project
                        # An unchanged file is checked HERE, by hash, before run_import:
                        # the hourly no-op must not append a refusal to the registry --
                        # `latest` would forever read "failed" on a healthy project.
                        try:
                            unchanged_sha = resolve_import_file(
                                self._import_root, candidate.name,
                                self._max_size_mb).sha256
                        except MppFileError:
                            unchanged_sha = None       # let run_import name the refusal
                        if unchanged_sha is not None:
                            await cursor.execute("""
                                SELECT sha256 FROM msp_file_versions
                                 WHERE project_id = %s
                                 ORDER BY version_number DESC LIMIT 1
                            """, (project_id,))
                            latest = await cursor.fetchone()
                            if latest is not None and latest["sha256"] == unchanged_sha:
                                outcomes.append({"projectId": project_id,
                                                 "status": "unchanged",
                                                 "reason": "MPP_DUPLICATE_FILE"})
                                continue
                outcomes.append(await self.run_import(
                    str(row["organization_id"]), project_id, candidate.name))
            except MppImportRefused as refused:
                status = ("unchanged" if refused.code == "MPP_DUPLICATE_FILE"
                          else "failed")
                outcomes.append({"projectId": project_id, "status": status,
                                 "reason": refused.code})
            except Exception:                             # noqa: BLE001
                # One project's unexpected failure (a dropped connection, a driver
                # error) must not silently starve every project after it in the sort
                # order for the whole interval.
                LOG.exception("mpp periodic import crashed project=%s", project_id)
                outcomes.append({"projectId": project_id, "status": "failed",
                                 "reason": "MPP_IMPORT_CRASHED"})
        return outcomes

    # ------------------------------------------------------------------- the actual work
    async def _run(self, organization_id, project_id, relative_name, actor_user_id,
                   result):
        # 0. The file IS the project's file, by name, before anything touches the
        # filesystem. The import root is shared by every MPP-active project on the host,
        # and the caller was authorized for THIS project only -- accepting any other
        # name would let msp.upload on one project read a sibling project's staged
        # schedule into a snapshot the caller can see (names, rates, costs, all of it).
        # Refusing before resolution keeps the answer identical whether the foreign
        # file exists or not, so the endpoint is no existence oracle either.
        expected = "%s.mpp" % project_id
        if str(relative_name) != expected:
            raise MppImportRefused(
                "MPP_PATH_NOT_ALLOWED",
                "only the project's own schedule file (%s) may be imported" % expected)

        # 1. The file, through the one door. Outside the transaction: nothing DB-side has
        # happened yet, and a refused path must not consume a connection or a lock.
        resolved = resolve_import_file(self._import_root, relative_name,
                                       self._max_size_mb)
        result["fileSha256"] = resolved.sha256

        # 5. Parse. CPU-and-JVM-bound and seconds long, so it leaves the event loop.
        # Parsed BEFORE the transaction opens: a corrupt file must fail before any row or
        # lock exists, and the parse result is immutable input to everything after.
        parsed = await asyncio.to_thread(self._reader.read, resolved.path)
        result["warnings"] = list(parsed.warnings)

        # 5b. The bytes MPXJ just read must be the bytes that were hashed. The parser
        # re-opens the file from disk, so a write landing between the hash and the parse
        # would record a sha256 describing different content than the snapshot holds --
        # and that hash is the idempotency key everything later trusts.
        if resolve_import_file(self._import_root, relative_name,
                               self._max_size_mb).sha256 != resolved.sha256:
            raise MppImportRefused(
                "MPP_PARSE_FAILED",
                "the file changed while it was being imported; retry when the copy "
                "is finished")

        # 6. Validate the parsed project before touching the database.
        task_uids = {task["uid"] for task in parsed.tasks if task["uid"] is not None}
        broken = [a for a in parsed.assignments if a["task_uid"] not in task_uids]
        if broken:
            raise MppImportRefused(
                "MPP_PARSE_FAILED",
                "%d assignment(s) reference task uids that are not in the file "
                "(first: %s) -- the file is internally inconsistent"
                % (len(broken), broken[0]["task_uid"]))
        # The symmetric check for the resource side. NULL stays allowed -- that is the
        # reader's documented unlinked-assignment case -- but a NAMED resource that is
        # not on the sheet would otherwise die mid-transaction as a raw FK violation.
        resource_uids = {r["uid"] for r in parsed.resources if r["uid"] is not None}
        broken = [a for a in parsed.assignments
                  if a["resource_uid"] is not None
                  and a["resource_uid"] not in resource_uids]
        if broken:
            raise MppImportRefused(
                "MPP_PARSE_FAILED",
                "%d assignment(s) reference resource uids that are not in the file "
                "(first: %s) -- the file is internally inconsistent"
                % (len(broken), broken[0]["resource_uid"]))
        # A quantity with no unit would violate the schema's CHECK mid-transaction;
        # refusing here keeps the raw constraint error out of the API and names the
        # actual problem. Nothing is guessed -- a unit the file states somewhere on
        # the resource is used (see _assignment_unit), so only a truly unit-less
        # quantity refuses.
        for assignment in parsed.assignments:
            if (self._assignment_unit(assignment, parsed.resources) is None
                    and any(assignment[key] is not None
                            for key in ("planned_quantity", "actual_quantity",
                                        "remaining_quantity"))):
                raise MppImportRefused(
                    "MPP_PARSE_FAILED",
                    "assignment %s carries a material quantity but resource %s "
                    "names no unit anywhere in the file"
                    % (assignment["assignment_uid"], assignment["resource_uid"]))
        if not parsed.tasks:
            raise MppImportRefused("MPP_PARSE_FAILED", "the file contains no tasks")

        async with await self._connect() as connection:
            async with connection.transaction():
                cursor = connection.cursor(row_factory=dict_row)
                async with cursor:
                    # 2. Resolve project and organization -- the server's answer, not the
                    # caller's claim.
                    await cursor.execute(
                        "SELECT id, organization_id FROM projects WHERE id = %s",
                        (project_id,))
                    project = await cursor.fetchone()
                    if project is None:
                        raise MppImportRefused("MPP_IMPORT_REFUSED",
                                               "project does not exist: %s" % project_id)
                    if str(project["organization_id"]) != str(organization_id):
                        raise MppImportRefused(
                            "MPP_IMPORT_REFUSED",
                            "project %s does not belong to the caller's organization"
                            % project_id)

                    # Concurrency: one import per project at a time. Transaction-scoped,
                    # so a crash cannot leak the lock.
                    # hashtextextended: a 64-bit lock key. The 32-bit hashtext() gave
                    # cross-project collisions a small but real chance of a spurious
                    # MPP_IMPORT_ALREADY_RUNNING between unrelated projects.
                    await cursor.execute(
                        "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) "
                        "AS locked",
                        (_advisory_key(project_id),))
                    if not (await cursor.fetchone())["locked"]:
                        raise MppImportRefused("MPP_IMPORT_ALREADY_RUNNING",
                                               "an import for this project is running")

                    # 4. Idempotency: the LATEST version's hash. An unchanged file is not
                    # an error for the periodic path, but a manual import of identical
                    # bytes deserves to hear it did nothing -- both get the same code.
                    await cursor.execute("""
                        SELECT id, sha256 FROM msp_file_versions
                         WHERE project_id = %s
                         ORDER BY version_number DESC LIMIT 1
                    """, (project_id,))
                    latest = await cursor.fetchone()
                    if latest is not None and latest["sha256"] == resolved.sha256:
                        raise MppImportRefused(
                            "MPP_DUPLICATE_FILE",
                            "the file is byte-identical to the latest imported version")

                    # 7. The file version row.
                    # Progress is a NUMBER, not a spelling: Decimal("0.00") is zero
                    # however the source typed it. Physical % complete counts too --
                    # a physically-tracked actuals file keeps duration-percent at 0
                    # on every task and would otherwise be stamped as a baseline.
                    has_progress = any(
                        _states_progress(task["percent_complete"])
                        or _states_progress(task["physical_percent_complete"])
                        for task in parsed.tasks)
                    detected_role = "ACTUAL" if has_progress else "TARGET"
                    await cursor.execute("""
                        INSERT INTO msp_file_versions
                            (project_id, version_number, original_filename,
                             stored_rel_path, file_type, detected_role, size_bytes,
                             sha256, uploaded_by)
                        VALUES (%s,
                                COALESCE((SELECT max(version_number) + 1
                                            FROM msp_file_versions
                                           WHERE project_id = %s), 1),
                                %s, %s, 'MPP', %s, %s, %s, %s)
                        RETURNING id, version_number
                    """, (project_id, project_id, resolved.relative_name,
                          "mpp-import/%s" % resolved.relative_name, detected_role,
                          resolved.size_bytes, resolved.sha256, actor_user_id))
                    version = await cursor.fetchone()
                    result["fileVersionId"] = version["id"]

                    # 8. The snapshot. MPXJ exposes the file's Gregorian status date;
                    # Core stores that field in Jalali text, so convert it explicitly.
                    # An absent date remains NULL and the feed's documented created_at
                    # fallback applies. Import time must never replace a date the file did
                    # state merely because the two calendars differ.
                    status_date_jalali = None
                    if getattr(parsed, "status_date", None) is not None:
                        jy, jm, jd = gregorian_to_persian(parsed.status_date)
                        status_date_jalali = f"{jy:04d}-{jm:02d}-{jd:02d}"
                    await cursor.execute("""
                        INSERT INTO msp_snapshots
                            (project_id, file_version_id, snapshot_type, source_filename,
                             source_version_number, display_label, task_count,
                             parser_engine, parser_warnings, status_date_jalali, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (project_id, version["id"], detected_role,
                          resolved.relative_name, version["version_number"],
                          "MPP import v%s" % version["version_number"],
                          len(parsed.tasks),
                          getattr(parsed, "parser_engine", None) or PARSER_ENGINE,
                          Jsonb({"warnings": parsed.warnings}), status_date_jalali,
                          actor_user_id))
                    snapshot_id = (await cursor.fetchone())["id"]
                    result["snapshotId"] = snapshot_id

                    # 9. Tasks. Summary rows are KEPT -- a tree missing its summaries is a
                    # different tree from the one in the file, and existing snapshots
                    # (task_count=1248) demonstrably include them.
                    task_row_ids = {}
                    for task in parsed.tasks:
                        await cursor.execute("""
                            INSERT INTO msp_tasks
                                (snapshot_id, uid, guid, task_id, name, wbs,
                                 outline_number, outline_level, start, finish, duration,
                                 percent_complete, percent_work_complete,
                                 physical_percent_complete, baseline_start,
                                 baseline_finish, text1, raw_fields_json)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            RETURNING id
                        """, (snapshot_id, task["uid"], task["guid"], task["task_id"],
                              task["name"] or "", task["wbs"], task["outline_number"],
                              task["outline_level"], task["start"], task["finish"],
                              task["duration"], task["percent_complete"],
                              task["percent_work_complete"],
                              task["physical_percent_complete"],
                              task["baseline_start"], task["baseline_finish"],
                              task["text1"],
                              # The complete raw column set the file states, keyed by the
                              # planner's own alias, so a column nobody has mapped yet is
                              # preserved rather than lost. The typed subset also lands in
                              # msp_task_metrics below.
                              Jsonb({"summary": task["summary"],
                                     "raw_fields": task.get("raw_fields") or {}})))
                        row_id = (await cursor.fetchone())["id"]
                        if task["uid"] is not None:
                            task_row_ids[task["uid"]] = row_id
                    result["taskCount"] = len(parsed.tasks)

                    # 9b. The snapshot's own resource sheet and assignments, exactly as
                    # the file states them. Work and quantity in separate columns; a
                    # value the file does not state is NULL, never zero.
                    for resource in parsed.resources:
                        await cursor.execute("""
                            INSERT INTO msp_resources
                                (snapshot_id, resource_uid, resource_guid, resource_name,
                                 native_type, resource_quantity, resource_quantity_unit,
                                 quantity_unit_source, initials, material_label,
                                 resource_group, code, max_units, standard_rate,
                                 overtime_rate, cost_per_use, work, actual_work,
                                 remaining_work, source_cost, source_actual_cost,
                                 source_remaining_cost)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                    %s,%s,%s,%s,%s,%s)
                        """, (snapshot_id, resource["uid"], resource["guid"],
                              resource["name"], resource["native_type"],
                              resource["quantity"], resource["quantity_unit"],
                              resource["quantity_unit_source"], resource["initials"],
                              resource["material_label"], resource["group"],
                              resource["code"], resource["max_units"],
                              resource["standard_rate"], resource["overtime_rate"],
                              resource["cost_per_use"], resource["work"],
                              resource["actual_work"], resource["remaining_work"],
                              resource["cost"], resource["actual_cost"],
                              resource["remaining_cost"]))
                    result["resourceCount"] = len(parsed.resources)

                    for assignment in parsed.assignments:
                        await cursor.execute("""
                            INSERT INTO msp_resource_assignments
                                (snapshot_id, assignment_uid, task_uid, resource_uid,
                                 units, planned_work, actual_work, remaining_work,
                                 planned_quantity, actual_quantity, remaining_quantity,
                                 quantity_unit, assignment_work_complete_percent,
                                 source_cost, source_actual_cost, source_remaining_cost)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (snapshot_id, assignment["assignment_uid"],
                              assignment["task_uid"], assignment["resource_uid"],
                              assignment["units"], assignment["planned_work"],
                              assignment["actual_work"], assignment["remaining_work"],
                              assignment["planned_quantity"],
                              assignment["actual_quantity"],
                              assignment["remaining_quantity"],
                              self._assignment_unit(assignment, parsed.resources),
                              assignment["work_complete_percent"], assignment["cost"],
                              assignment["actual_cost"], assignment["remaining_cost"]))
                    result["assignmentCount"] = len(parsed.assignments)

                    # 10-11. The Finance mapping. Matching is UID-in-scope and nothing
                    # else -- never by name. Unmatched resources are reported, not
                    # invented; `finance_resources` is never auto-created.
                    mapped, unmapped = await self._build_mapping(
                        cursor, organization_id, project_id, parsed, task_row_ids)
                    result["mappedCount"] = mapped
                    result["unmappedResources"] = unmapped
                    result["unmappedCount"] = len(unmapped)

                    # 12. Reporting-period linkage. This repository contains no logic
                    # that assigns a snapshot to a period (the column and FKs exist; the
                    # writer lives in Core's own platform), so none is INVENTED here:
                    # the snapshot is left unlinked and the fact is reported. A guessed
                    # period would silently redate financial reports.
                    result["reportingPeriodId"] = None

        result["warningCount"] = len(result["warnings"]) + len(result["unmappedResources"])
        result["status"] = ("completed_with_warnings"
                            if result["unmappedResources"] or result["warnings"]
                            else "completed")
        result["error"] = None
        LOG.info("mpp import ok project=%s snapshot=%s tasks=%d mapped=%d unmapped=%d",
                 project_id, result["snapshotId"], result["taskCount"],
                 result["mappedCount"], result["unmappedCount"])
        return result

    @staticmethod
    def _assignment_unit(assignment, resources):
        """The unit an assignment quantity is measured in, from its own resource.

        Only when there IS a quantity -- and the guard lists exactly the three columns
        the schema's CHECK lists, so a remaining-only assignment still gets its unit.
        The unit falls back to the resource's material_label/initials directly: a
        Resource Sheet whose quantity CELL is blank still names the measure its
        assignments are counted in, and refusing such a file over a blank cell would
        be wrong. Nothing is invented -- every candidate string comes from the file.
        """
        if (assignment["planned_quantity"] is None
                and assignment["actual_quantity"] is None
                and assignment["remaining_quantity"] is None):
            return None
        for resource in resources:
            if resource["uid"] == assignment["resource_uid"]:
                return (resource["quantity_unit"] or resource["material_label"]
                        or resource["initials"])
        return None

    async def _build_mapping(self, cursor, organization_id, project_id, parsed,
                             task_row_ids):
        """``finance_task_resource_map`` rows for every assignment whose resource is known.

        The path is exactly the documented one:

            assignment.resource_uid -> finance_resources.external_resource_id (in scope)
            assignment.task_uid     -> the task row JUST inserted in THIS snapshot

        Scope is enforced twice: here, by matching only inside (organization, project),
        and again by the database trigger -- service checks catch mistakes politely,
        triggers make them impossible.
        """
        await cursor.execute("""
            SELECT id, external_resource_id, code, title
              FROM finance_resources
             WHERE organization_id = %s AND project_id = %s
               AND external_resource_id IS NOT NULL AND deleted_at IS NULL
        """, (organization_id, project_id))
        finance_by_external = {row["external_resource_id"]: row
                               for row in await cursor.fetchall()}

        mapped = 0
        unmapped = {}
        seen_pairs = set()
        for assignment in parsed.assignments:
            resource_uid = assignment["resource_uid"]
            if resource_uid is None:
                continue                      # unlinked in the file; already a warning
            finance_row = finance_by_external.get(str(resource_uid))
            if finance_row is None:
                if str(resource_uid) not in unmapped:
                    name = next((r["name"] for r in parsed.resources
                                 if r["uid"] == resource_uid), None)
                    unmapped[str(resource_uid)] = {
                        "resourceExternalId": str(resource_uid),
                        "resourceName": name,
                        "status": "unmapped",
                        "reason": "FINANCE_RESOURCE_NOT_FOUND",
                    }
                continue
            task_row_id = task_row_ids.get(assignment["task_uid"])
            if task_row_id is None:
                # Cannot happen after validation, and must not be silently skipped if it
                # somehow does: this is exactly the inconsistency the transaction exists
                # to reject as a whole.
                raise MppImportRefused(
                    "MPP_PARSE_FAILED",
                    "assignment %s maps a task uid with no inserted row"
                    % assignment["assignment_uid"])
            pair = (task_row_id, str(finance_row["id"]))
            if pair in seen_pairs:
                continue                      # two assignments, same task+resource: one row
            seen_pairs.add(pair)
            # ON CONFLICT DO NOTHING covers ONLY the duplicate-pair race. Scope errors and
            # missing rows are NOT conflicts and surface as the FK/trigger failures they
            # are, aborting the whole import.
            await cursor.execute("""
                INSERT INTO finance_task_resource_map (id, task_id, resource_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (task_id, resource_id) DO NOTHING
            """, (self._ids(), task_row_id, finance_row["id"]))
            mapped += 1
        return mapped, list(unmapped.values())


async def validate_mapping_scope(cursor, task_row_id, finance_resource_id):
    """The service-level half of cross-project protection, importable by tests.

    Proves Task.project == Resource.project and Task.organization == Resource.organization
    by walking task -> snapshot -> project. The database trigger enforces the same rule
    unconditionally; this exists so a service can refuse with a readable error before the
    constraint fires.
    """
    await cursor.execute("""
        SELECT project.id AS task_project, project.organization_id AS task_org,
               resource.project_id AS resource_project,
               resource.organization_id AS resource_org
          FROM msp_tasks AS task
          JOIN msp_snapshots AS snapshot ON snapshot.id = task.snapshot_id
          JOIN projects AS project ON project.id = snapshot.project_id
          CROSS JOIN (SELECT project_id, organization_id FROM finance_resources
                       WHERE id = %s) AS resource
         WHERE task.id = %s
    """, (finance_resource_id, task_row_id))
    row = await cursor.fetchone()
    if row is None:
        return "task or resource does not exist"
    if row["task_project"] != row["resource_project"]:
        return "task and finance resource belong to different projects"
    if str(row["task_org"]) != str(row["resource_org"]):
        return "task and finance resource belong to different organizations"
    return None
