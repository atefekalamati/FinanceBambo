# -*- coding: utf-8 -*-
r"""TEST_ONLY -- DISPOSABLE. Does Finance actually SPEND the imported MSP data?

The previous check proved the adapter works. This one asks the harder question: does a
number from the .mpp reach a financial metric, or does the integration stop at the adapter?

    ..\..\..\..\.venv312\Scripts\python -m scripts.test_only.mpp_parser_probe.finance_e2e_check

Two phases, deliberately separate:

  PHASE 1 -- report the database exactly as it stands. If there are no estimate lines there
  is nothing for the progress to be consumed BY, and that is the honest headline answer.

  PHASE 2 -- seed estimate lines and run the real `FinanceLiveReportService`. The seeded
  lines are DERIVED FROM THE MPP, not invented: the quantity is the assignment's own
  planned quantity, the unit is the resource's own unit, the price is the resource's own
  standard rate, and the activity code is the one the configured provider emits. Nothing is
  made up, so a number appearing in the report can be traced back to a cell in the file.

  The one thing that is NOT from the file is the pairing itself -- deciding that estimate
  line X corresponds to assignment Y. In production a human or an import does that. Here it
  is done by construction, which is the point: it proves the calculation consumes the link,
  not that anybody has drawn the link for this project.

Scratch database only, guarded by `scratch_target`. No migration, no code change, and
nothing outside `bambo_mpp_probe` is touched.
"""

import argparse
import asyncio
import selectors
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

#: Namespace for deriving a stable finance_resources id from an MSP resource uid.
#: Any fixed UUID works; what matters is that it never changes, so the same MSP
#: resource maps to the same Finance resource on every run.
RESOURCE_NAMESPACE = UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

from app.finance.domain.errors import FinanceDomainError                # noqa: E402
from app.finance.repositories.reports import PsycopgLiveReportRepository  # noqa: E402
from app.finance.security.guards import FinanceScope                    # noqa: E402
from app.finance.services.reports import FinanceLiveReportService       # noqa: E402
from coreint.activities import CoreProjectActivityProvider              # noqa: E402
from coreint.progress import CoreProgressSnapshotProvider               # noqa: E402
from devhost.app import ACTIVITY_CODE_FIELDS as WIRED_FIELDS            # noqa: E402
from scripts.test_only.mpp_parser_probe.load_scratch import (ORGANIZATION_ID,  # noqa: E402
                                                             PROJECT_ID)
from scripts.test_only.mpp_parser_probe.scratch_target import (         # noqa: E402
    SCRATCH_DATABASE, SCRATCH_HOST, SCRATCH_PORT, UnsafeTarget,
    assert_dsn_targets_scratch)

DEFAULT_DSN = "postgresql://postgres@%s:%s/%s" % (SCRATCH_HOST, SCRATCH_PORT,
                                                  SCRATCH_DATABASE)
ACTOR_ID = UUID("00000000-0000-4000-8000-00000000fa01")
REPORTING_DATE = date(2026, 9, 2)

#: How many estimate lines phase 2 seeds. Enough to exercise the pairing and the rollup,
#: small enough that the report can be read by eye.
SEED_LIMIT = 40

problems = []


def say(label, detail=""):
    print("  %-44s %s" % (label, detail))


def problem(kind, text):
    problems.append((kind, text))
    say("  %s" % kind, text)


def money(value):
    """An IRR integer string as something readable. None stays None -- it means unknown."""
    if value is None:
        return "None (unknown)"
    return "{:,}".format(int(Decimal(str(value))))


async def phase_one(connection):
    """The database as it stands, table by table, before anything is added."""
    print("\n  === PHASE 1: the database as it stands ===")

    for table, columns in (("msp_file_versions",
                            "id, original_filename, size_bytes, version_number"),
                           ("msp_snapshots",
                            "id, snapshot_type, source_filename, task_count, parser_engine")):
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT %s FROM %s ORDER BY id" % (columns, table))
            rows = await cursor.fetchall()
        say(table, "%d row(s)" % len(rows))
        for row in rows:
            say("  ", "  ".join("%s=%s" % (k, v) for k, v in row.items()))

    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("""
            SELECT id, progress_snapshot_id, host_snapshot_id, host_file_version_id,
                   reporting_date, snapshot_status, source_file_name_safe
              FROM progress_snapshot_refs ORDER BY imported_at
        """)
        refs = await cursor.fetchall()
    say("progress_snapshot_refs", "%d row(s)" % len(refs))
    for row in refs:
        say("  ", "host_snapshot_id=%s reporting_date=%s status=%s file=%r"
            % (row["host_snapshot_id"], row["reporting_date"], row["snapshot_status"],
               row["source_file_name_safe"]))

    counts = {}
    for table in ("msp_tasks", "msp_resources", "msp_resource_assignments",
                  "finance_resources", "estimate_lines", "invoices", "invoice_lines",
                  "progress_overrides", "price_versions", "finance_project_settings"):
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT count(*) AS n FROM %s" % table)
            counts[table] = (await cursor.fetchone())["n"]
    print()
    for table, count in counts.items():
        say(table, str(count))

    if counts["estimate_lines"] == 0:
        print()
        problem("HEADLINE",
                "estimate_lines is EMPTY. The MSP data is loaded and the adapter reads it, "
                "but there is no financial item for it to be consumed by. Nothing in "
                "Finance currently spends this snapshot.")
    return counts


async def seed_estimates(connection, provider, scope):
    """Estimate lines derived from the MPP, so the calculation has something to consume.

    Every value comes from the file: quantity from the assignment, unit and price from the
    resource, activity code from the configured provider. The link between line and
    assignment is made by construction -- see the module docstring.
    """
    print("\n  === PHASE 2: seeding estimate lines derived from the MPP ===")

    feed = await provider.get_snapshot(str(scope.organization_id), scope.project_id, "9001")
    assignments = feed["assignments"]

    # Only assignments that carry a planned quantity AND a unit can become an estimate
    # line: a line with no quantity has nothing to price, and the report would exclude it.
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("""
            SELECT a.assignment_uid, a.task_uid, a.resource_uid, a.planned_quantity,
                   a.quantity_unit, r.resource_name, r.standard_rate, r.native_type
              FROM msp_resource_assignments a
              JOIN msp_resources r ON r.snapshot_id = a.snapshot_id
                                  AND r.resource_uid = a.resource_uid
             WHERE a.snapshot_id = 9001 AND a.planned_quantity IS NOT NULL
                   AND a.quantity_unit IS NOT NULL AND r.standard_rate > 0
             ORDER BY a.planned_quantity DESC
             LIMIT %s
        """, (SEED_LIMIT,))
        rows = await cursor.fetchall()
    say("candidate assignments", "%d (quantity + unit + a rate, largest first)" % len(rows))
    if not rows:
        problem("BLOCKER", "No assignment carries a quantity, a unit and a rate, so no "
                           "estimate line can be derived from this file.")
        return []

    # The activity code the provider actually emits for each task, so the seeded line pairs
    # the way a real one would. Read from the feed rather than recomputed.
    activity_by_task = {}
    assignment_by_uid = {}
    for row in assignments:
        assignment_by_uid[str(row.get("assignmentExternalId"))] = row
        task = row.get("task") or {}
        if task.get("taskExternalId"):
            activity_by_task[str(row.get("assignmentExternalId"))] = task.get("activityCode")

    reused_prices = new_prices = new_versions = 0
    seeded = []
    async with connection.transaction():
        # ONLY estimate_lines is cleared, and only because a re-run would otherwise stack a
        # second set of 40 on the first and report a project twice the size.
        #
        # price_versions is NEVER deleted. `price_versions_immutable` rejects both UPDATE
        # and DELETE -- a price a report was once issued against has to stay readable
        # forever, or the report can no longer be reproduced. An earlier version of this
        # script deleted them and hit `finance_reject_mutation()` on the first re-run
        # against a database that was not recreated. That guard was right and the script
        # was wrong.
        #
        # finance_resources is not deleted either. It carries no trigger, but price_versions
        # references it ON DELETE NO ACTION, so deleting a resource whose price survives is
        # a foreign-key violation -- the immutable row protects its parent too.
        async with connection.cursor() as cursor:
            await cursor.execute("DELETE FROM estimate_lines WHERE project_id = %s",
                                 (scope.project_id,))
        for row in rows:
            assignment_external = str(row["assignment_uid"])
            activity = activity_by_task.get(assignment_external)
            if activity is None:
                continue
            # Derived from the MSP resource uid rather than random, so the same MSP resource
            # maps to the same finance_resources row on every run. With uuid4() each run
            # minted a new resource, which is what made the delete-everything approach look
            # necessary in the first place.
            resource_id = uuid5(RESOURCE_NAMESPACE, "%s|%s" % (scope.project_id,
                                                               row["resource_uid"]))
            line_id = uuid4()
            unit = row["quantity_unit"]
            rate = int(Decimal(str(row["standard_rate"])).quantize(Decimal(1)))
            async with connection.cursor(row_factory=dict_row) as cursor:
                # Reused across runs. The resource is not immutable, but it is the parent of
                # a row that is, so it is created once and left alone.
                await cursor.execute("""
                    INSERT INTO finance_resources
                        (id, organization_id, project_id, resource_type, code, title,
                         base_unit, dimension, external_resource_id, created_by)
                    VALUES (%s,%s,%s,'material',%s,%s,%s,'count',%s,%s)
                    ON CONFLICT (id) DO NOTHING
                """, (resource_id, scope.organization_id, scope.project_id,
                      "MSP-%s" % row["resource_uid"], row["resource_name"] or "unnamed",
                      unit, str(row["resource_uid"]), ACTOR_ID))
                # original_unit_price_irr is numeric(18,0): integer rial. The MPP's rate is
                # a float; it is quantised here rather than rounded silently elsewhere.
                await cursor.execute("""
                    INSERT INTO estimate_lines
                        (id, organization_id, project_id, resource_id, activity_external_id,
                         assignment_external_id, original_quantity, original_unit_price_irr,
                         source, created_by, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'progress_feed',%s,%s)
                """, (line_id, scope.organization_id, scope.project_id, resource_id,
                      activity, assignment_external, row["planned_quantity"], rate,
                      ACTOR_ID, datetime(2026, 8, 1, tzinfo=timezone.utc)))

                # The CURRENT price. Without a price_versions row every line is excluded as
                # CURRENT_PRICE_MISSING and every money metric comes back None -- the
                # estimate's own price is the baseline, not the current one.
                #
                # Read before written, and never deleted or updated. Three outcomes:
                #   * no price yet          -> version 1
                #   * price already correct -> reuse it, write nothing
                #   * price differs         -> APPEND version n+1
                # The third is what an immutable price history is for: a rate that changed
                # becomes a new version beside the old one, so a report issued last month
                # can still be reproduced against the price it actually used.
                await cursor.execute("""
                    SELECT id, version, unit_price_irr FROM price_versions
                     WHERE organization_id = %s AND project_id = %s AND resource_id = %s
                           AND scope_kind = 'project'
                     ORDER BY version DESC LIMIT 1
                """, (scope.organization_id, scope.project_id, resource_id))
                current = await cursor.fetchone()

                if current is not None and int(current["unit_price_irr"]) == rate:
                    reused_prices += 1
                else:
                    version = 1 if current is None else int(current["version"]) + 1
                    await cursor.execute("""
                        INSERT INTO price_versions
                            (id, organization_id, project_id, resource_id, scope_kind,
                             version, unit_price_irr, effective_from, reason, created_by)
                        VALUES (%s,%s,%s,%s,'project',%s,%s,%s,%s,%s)
                    """, (uuid4(), scope.organization_id, scope.project_id, resource_id,
                          version, rate, date(2026, 8, 1),
                          "TEST ONLY -- MSP resource standard rate", ACTOR_ID))
                    if version == 1:
                        new_prices += 1
                    else:
                        new_versions += 1
            seeded.append({"line_id": line_id, "activity": activity,
                           "assignment": assignment_external,
                           "quantity": row["planned_quantity"], "unit": unit,
                           "rate": row["standard_rate"],
                           "resource": row["resource_name"]})
    say("estimate lines seeded", "%d (previous ones deleted; estimate_lines guards UPDATE, "
                                 "not DELETE)" % len(seeded))
    say("price_versions created", str(new_prices))
    say("price_versions reused unchanged", str(reused_prices))
    say("price_versions appended as a new version", str(new_versions))
    if new_versions:
        say("  note", "a rate differed from the stored one, so a version was ADDED beside "
                      "it -- nothing was overwritten")
    if seeded:
        first = seeded[0]
        say("  example", "%s  qty=%s %s  rate=%s  activity=%s  assignment=%s"
            % ((first["resource"] or "")[:18], first["quantity"], first["unit"],
               first["rate"], first["activity"], first["assignment"]))
    return seeded


def report_service(connection):
    """The real service, wired the way devhost wires it. One place, so 3a and 3b agree."""
    return FinanceLiveReportService(
        PsycopgLiveReportRepository(connection),
        CoreProgressSnapshotProvider(connection, activity_code_fields=WIRED_FIELDS),
        activity_provider=CoreProjectActivityProvider(
            connection, activity_code_fields=WIRED_FIELDS))


async def clone_as_actual(connection):
    """A second snapshot, identical in data, labelled ACTUAL. SYNTHETIC LABEL.

    Why this exists: snapshot 9001 is a `TARGET` baseline, and `current_snapshot` refuses
    those on purpose -- `PROGRESS_SNAPSHOT_TYPES` is `("ACTUAL", "RESCHEDULED")`, because
    reporting a plan as executed work would describe planned work as done. That refusal is
    correct and it is the honest answer for this file.

    But it also stops the calculation before it starts, which leaves the question that was
    actually asked unanswered: when the report DOES run, does it spend the MSP numbers or
    ignore them? This clone answers that and nothing else. The rows are byte-identical to
    9001; only `snapshot_type` differs, and that difference is a label this script invented,
    not something read from the .mpp. No conclusion about real progress may rest on it.
    """
    print("\n  === PHASE 2b: an ACTUAL-labelled clone (SYNTHETIC LABEL) ===")
    async with connection.transaction():
        async with connection.cursor() as cursor:
            # All three cleared explicitly. Deleting the snapshot cascades to `msp_tasks`
            # only -- `msp_resources` and `msp_resource_assignments` come from revision
            # 0007, which declares NO foreign key to msp_snapshots because the migration
            # role has no REFERENCES privilege on Core. So they survived the delete, the
            # re-insert doubled them, and the run after that died on
            # `msp_resources_snapshot_uid_key`. Neither table carries an immutability
            # trigger, so deleting this snapshot's rows is allowed.
            await cursor.execute(
                "DELETE FROM msp_resource_assignments WHERE snapshot_id = 9002")
            await cursor.execute("DELETE FROM msp_resources WHERE snapshot_id = 9002")
            await cursor.execute("DELETE FROM msp_tasks WHERE snapshot_id = 9002")
            await cursor.execute("DELETE FROM msp_snapshots WHERE id = 9002")
            await cursor.execute("""
                INSERT INTO msp_snapshots (id, project_id, file_version_id, snapshot_type,
                                           source_filename, source_version_number,
                                           display_label, task_count, parser_engine,
                                           status_date_jalali)
                SELECT 9002, project_id, file_version_id, 'ACTUAL', source_filename,
                       source_version_number,
                       'SYNTHETIC ACTUAL clone of 9001 -- label only', task_count,
                       parser_engine, '1405-06-11'
                  FROM msp_snapshots WHERE id = 9001
            """)
            for table, columns in (
                    ("msp_tasks",
                     "uid, task_id, name, wbs, outline_number, outline_level, start, "
                     "finish, duration, percent_complete, percent_work_complete, "
                     "physical_percent_complete, text1"),
                    ("msp_resources",
                     "resource_uid, resource_guid, resource_name, native_type, "
                     "bambo_resource_type, resource_quantity, resource_quantity_unit, "
                     "quantity_unit_source, initials, material_label, resource_group, code, "
                     "max_units, standard_rate, overtime_rate, cost_per_use, work, "
                     "actual_work, remaining_work, source_cost, source_actual_cost, "
                     "source_remaining_cost"),
                    ("msp_resource_assignments",
                     "assignment_uid, task_uid, resource_uid, units, planned_work, "
                     "actual_work, remaining_work, planned_quantity, actual_quantity, "
                     "remaining_quantity, quantity_unit, assignment_work_complete_percent, "
                     "source_cost, source_actual_cost, source_remaining_cost")):
                await cursor.execute("INSERT INTO %s (snapshot_id, %s) SELECT 9002, %s "
                                     "FROM %s WHERE snapshot_id = 9001"
                                     % (table, columns, columns, table))
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("""
            SELECT (SELECT count(*) FROM msp_tasks WHERE snapshot_id=9002) t,
                   (SELECT count(*) FROM msp_resources WHERE snapshot_id=9002) r,
                   (SELECT count(*) FROM msp_resource_assignments WHERE snapshot_id=9002) a
        """)
        row = await cursor.fetchone()
    say("cloned into snapshot 9002", "%d tasks, %d resources, %d assignments"
        % (row["t"], row["r"], row["a"]))
    say("what differs from 9001", "snapshot_type only -- ACTUAL instead of TARGET")


async def run_report(connection, scope, seeded):
    """The real FinanceLiveReportService, over the real repository."""
    print("\n  === PHASE 3b: the real Finance calculation, against the clone ===")
    service = report_service(connection)
    try:
        report = await service.live(scope, REPORTING_DATE)
    except FinanceDomainError as error:
        problem("BLOCKER", "the live report refused: %s (%s)"
                % (error, getattr(error, "code", "")))
        return None

    metrics = report["metrics"]
    say("calculation status", report["calculation_status"])
    say("progress snapshot", "%s (host %s)" % (report["progress_snapshot_id"],
                                               report["host_snapshot_id"]))
    print()
    for key in ("initialEstimateIrr", "actualCostIrr", "currentExecutedValueIrr",
                "remainingPhysicalCostIrr", "moneyRequiredToContinueIrr",
                "forecastFinalCostIrr"):
        say(key, money(metrics.get(key)))

    # EVERY line, not `top_quantity_variances` -- that is `[:10]`, and summing it reported
    # totals for ten lines while calling them the project's.
    page = await service.variances(scope, REPORTING_DATE, variance_type="quantity",
                                   page_size=10000)
    quantities = page["items"]
    print()
    say("estimate lines in the report", "%d (of %d reported by the service)"
        % (len(quantities), page["total_items"]))
    paired = [row for row in quantities if row.get("progressStatus") != "unavailable"]
    say("lines the progress feed answered for", str(len(paired)))
    say("lines it could not answer for",
        str(len(quantities) - len(paired)))

    executed = sum(Decimal(str(row.get("executedQuantity") or 0)) for row in quantities)
    revised = sum(Decimal(str(row.get("revisedQuantity") or 0)) for row in quantities)
    say("total revised (planned) quantity", format(revised, "f"))
    say("total executed quantity", format(executed, "f"))

    statuses = {}
    methods = {}
    for row in quantities:
        statuses[row.get("progressStatus")] = statuses.get(row.get("progressStatus"), 0) + 1
        methods[row.get("sourceMethod")] = methods.get(row.get("sourceMethod"), 0) + 1
    say("progress status", ", ".join("%s=%d" % kv for kv in sorted(
        statuses.items(), key=lambda p: str(p[0]))))
    say("source method", ", ".join("%s=%d" % kv for kv in sorted(
        methods.items(), key=lambda p: str(p[0]))))

    say("missing price count", str(report["missing_price_count"]))
    say("excluded estimate lines", str(report["excluded_estimate_line_count"]))
    if report["incomplete_metric_keys"]:
        say("metrics reported as unknown", ", ".join(report["incomplete_metric_keys"]))

    codes = {}
    for warning in report["warnings"]:
        codes[warning["code"]] = codes.get(warning["code"], 0) + 1
    say("warnings", ", ".join("%s=%d" % kv for kv in sorted(codes.items())) or "none")

    # The question this whole script exists to answer.
    print()
    if seeded and len(paired) == len(quantities) and quantities:
        say("VERDICT", "the MSP snapshot IS consumed: every seeded line was answered "
                       "by the feed")
    elif not quantities:
        problem("BLOCKER", "the report contains no estimate lines at all.")
    elif not paired:
        problem("MAPPING", "no seeded line was answered by the feed: the pairing between "
                           "estimate lines and MSP assignments does not resolve.")
    else:
        problem("MAPPING", "%d of %d lines were not answered by the feed."
                % (len(quantities) - len(paired), len(quantities)))
    return report


async def run(dsn):
    scope = FinanceScope(organization_id=ORGANIZATION_ID, project_id=PROJECT_ID,
                         actor_user_id=ACTOR_ID)
    async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, row_factory=dict_row, connect_timeout=10) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT current_database() d, host(inet_server_addr()) h")
            server = await cursor.fetchone()
        if server["d"] != SCRATCH_DATABASE or server["h"] != SCRATCH_HOST:
            raise SystemExit("STOP: the server answering is %s/%s" % (server["h"],
                                                                     server["d"]))
        say("target", "%s/%s" % (server["h"], server["d"]))
        say("activity code fields", "%s (from devhost.app)" % (WIRED_FIELDS,))

        await phase_one(connection)
        provider = CoreProgressSnapshotProvider(connection,
                                                activity_code_fields=WIRED_FIELDS)
        seeded = await seed_estimates(connection, provider, scope)

        # First against the file as it really is. A refusal here is a result, not a fault.
        print("\n  === PHASE 3a: the real calculation, against the TARGET baseline ===")
        service = report_service(connection)
        try:
            await service.live(scope, REPORTING_DATE)
            say("live report", "returned")
        except FinanceDomainError as error:
            say("live report", "REFUSED: %s" % error)
            say("  why", "snapshot 9001 is TARGET; current_snapshot only accepts "
                         "ACTUAL/RESCHEDULED")
            say("  verdict", "correct -- a baseline is not a progress report")
            problem("EXPECTED",
                    "With the file as it actually is, Finance produces NO live report at "
                    "all: the only snapshot is a TARGET baseline and the report refuses "
                    "to treat a plan as executed work. Correct behaviour, and it means "
                    "this file alone cannot drive a financial report.")

        await clone_as_actual(connection)
        await run_report(connection, scope, seeded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    arguments = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        assert_dsn_targets_scratch(arguments.dsn)
    except UnsafeTarget as refusal:
        raise SystemExit("STOP: %s" % refusal)

    print("\n  TEST_ONLY / DISPOSABLE -- end to end, scratch database only\n")
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    try:
        loop.run_until_complete(run(arguments.dsn))
    finally:
        loop.close()

    print("\n  === FINDINGS ===")
    if not problems:
        print("  none")
    for kind, text in problems:
        print("  [%s] %s" % (kind, text))
    return 1 if any(kind == "BLOCKER" for kind, _ in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
