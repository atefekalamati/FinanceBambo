# -*- coding: utf-8 -*-
r"""TEST_ONLY -- DISPOSABLE. Upload a real .mpp to Finance, and see what happens.

    ..\..\..\..\.venv312\Scripts\python -m scripts.test_only.mpp_parser_probe.msp_upload_e2e

Three phases:

  A. Try to upload `test_progress.mpp` through the REAL HTTP API, against a real FastAPI
     app wired by `devhost.wire`. Every file-accepting route is enumerated from the app's
     own OpenAPI schema and the file is offered to each one. Whatever they answer is the
     answer -- this phase asserts nothing in advance.

  B. Drive the ingestion path that does exist locally: the MPXJ probe, the fixture, and the
     existing seed script, into the scratch database. Then report what rows exist.

  C. Run the real `FinanceLiveReportService` over the result.

Nothing here is a production path and none of it may become one. Phase B in particular
stands in for Core's importer, which lives outside this repository.
"""

import argparse
import asyncio
import json
import selectors
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

from scripts.test_only.mpp_parser_probe.scratch_target import (         # noqa: E402
    SCRATCH_DATABASE, SCRATCH_HOST, SCRATCH_PORT, UnsafeTarget,
    assert_dsn_targets_scratch)

DEFAULT_DSN = "postgresql://postgres@%s:%s/%s" % (SCRATCH_HOST, SCRATCH_PORT,
                                                  SCRATCH_DATABASE)
MPP = BACKEND_ROOT.parent / "Sources" / "test_progress.mpp"
FIXTURE = Path(__file__).resolve().parent / "fixture.json"
PROBE_PYTHON = Path(__file__).resolve().parent / "probe-env" / "Scripts" / "python.exe"

findings = []


def say(label, detail=""):
    print("  %-44s %s" % (label, detail))


def finding(kind, text):
    findings.append((kind, text))
    say("  %s" % kind, text)


async def phase_a(dsn):
    """Offer the .mpp to every file-accepting route the API actually exposes."""
    print("\n  === PHASE A: uploading through the real HTTP API ===")
    import httpx
    from app.main import create_app
    from devhost import seed
    from devhost.app import wire

    # `create_app()`, not a bare FastAPI: the router is mounted there. Building an empty app
    # and wiring it gave zero routes and a 404 for every upload -- which looks exactly like
    # "the endpoint does not exist" and would have been reported as the answer.
    application = create_app()
    connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True,
                                                       row_factory=dict_row)
    try:
        # core=None: the static development identity, so this tests the FILE handling
        # rather than Core's authorization. A 401 would prove nothing about .mpp support.
        wire(application, connection, BACKEND_ROOT / "build" / "storage", None)

        schema = application.openapi()
        uploaders = []
        for path, methods in schema["paths"].items():
            for method, spec in methods.items():
                body = (spec.get("requestBody") or {}).get("content") or {}
                if any("multipart/form-data" in kind for kind in body):
                    uploaders.append((method.upper(), path))
        say("routes that accept a file upload", str(len(uploaders)))
        for method, path in uploaders:
            say("  %s" % method, path)
        if not any("mpp" in path.lower() or "schedule" in path.lower()
                   or "msp" in path.lower() for _m, path in uploaders):
            finding("ANSWER",
                    "No route in the Finance API accepts a schedule file. The %d upload "
                    "routes are for invoice attachments and Excel imports." % len(uploaders))

        content = MPP.read_bytes()
        say("file", "%s (%d bytes)" % (MPP.name, len(content)))

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://devhost") as client:
            project = seed.PROJECT_ID
            attempts = [
                ("/api/projects/%s/finance/files" % project,
                 {"logicalType": "invoice_image"}),
                ("/api/projects/%s/finance/imports/estimate/preview" % project, None),
                ("/api/projects/%s/finance/imports/prices/preview" % project, None),
            ]
            for url, data in attempts:
                files = {"file": (MPP.name, content,
                                  "application/vnd.ms-project")}
                response = await client.post(url, files=files, data=data or {})
                body = response.text
                try:
                    body = json.dumps(response.json(), ensure_ascii=False)[:150]
                except ValueError:
                    body = body[:150]
                say("POST %s" % url.split("/finance/")[-1],
                    "%s  %s" % (response.status_code, body))
                if response.status_code < 300:
                    finding("UNEXPECTED",
                            "%s ACCEPTED a .mpp with status %s -- that route was not "
                            "supposed to take a schedule file."
                            % (url, response.status_code))
    finally:
        await connection.close()

    # The declared shape of an MPP reader, and whether anything implements it.
    from app.finance.adapters.schedule_ports import MppAdapterNotAvailable
    try:
        raise MppAdapterNotAvailable()
    except NotImplementedError as error:
        say("MppScheduleAdapter", "not implemented: %s" % str(error)[:70])
        finding("ANSWER",
                "No real MPP parser is wired anywhere in this repository. "
                "`MppScheduleAdapter` is an unimplemented Protocol and "
                "`MppAdapterNotAvailable` raises NotImplementedError; a test in "
                "test_schedule_contract.py forbids any module under app/finance from "
                "importing a schedule reader. The only thing that reads a .mpp here is "
                "this probe.")


def run(command, label, cwd=None, timeout=900):
    """A subprocess, with its own working directory and a timeout.

    `cwd` matters: `parse_mpp.py` lives in this directory and the seed script is a module
    resolved from `backend/`. A timeout matters more -- the JVM and the loader both take
    tens of seconds, and without one a wedged child hangs the whole check with no output,
    because `capture_output` swallows everything until it exits.
    """
    say(label, "running")
    result = subprocess.run(command, cwd=str(cwd or BACKEND_ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode != 0:
        print(result.stdout[-1200:])
        print(result.stderr[-800:])
        raise SystemExit("%s failed (exit %s)" % (label, result.returncode))
    return result.stdout


def phase_b(dsn):
    """The ingestion that does work locally: MPXJ probe -> fixture -> seed script."""
    print("\n  === PHASE B: the path that does exist (probe -> fixture -> database) ===")
    if not PROBE_PYTHON.is_file():
        raise SystemExit("STOP: probe-env is missing; see README.md")

    out = run([str(PROBE_PYTHON), str(Path(__file__).resolve().parent / "parse_mpp.py"),
               "--input", str(MPP), "--output", str(FIXTURE)],
              "parse the .mpp with MPXJ", cwd=Path(__file__).resolve().parent)
    for line in out.splitlines():
        if any(key in line for key in ("Tasks count", "Resources count",
                                       "Assignments count", "written by")):
            say("  ", line.strip())

    run([sys.executable, "-m", "scripts.test_only.mpp_parser_probe.load_scratch",
         "--fixture", str(FIXTURE), "--recreate", "--apply"],
        "load into the scratch database")
    say("  ", "loaded")


async def phase_b_report(dsn):
    """What the five tables hold after the load."""
    print("\n  --- records created ---")
    async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, row_factory=dict_row) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("""
                SELECT id, project_id, version_number, original_filename, file_type,
                       detected_role, size_bytes FROM msp_file_versions ORDER BY id
            """)
            for row in await cursor.fetchall():
                say("msp_file_versions", "id=%s v%s %r type=%s role=%s"
                    % (row["id"], row["version_number"], row["original_filename"],
                       row["file_type"], row["detected_role"]))
            await cursor.execute("""
                SELECT id, snapshot_type, source_filename, task_count, parser_engine,
                       status_date_jalali FROM msp_snapshots ORDER BY id
            """)
            for row in await cursor.fetchall():
                say("msp_snapshots", "id=%s type=%s %r tasks=%s engine=%s"
                    % (row["id"], row["snapshot_type"], row["source_filename"],
                       row["task_count"], row["parser_engine"]))
            for table in ("msp_tasks", "msp_resources", "msp_resource_assignments"):
                await cursor.execute("SELECT count(*) AS n FROM %s" % table)
                say(table, str((await cursor.fetchone())["n"]))
            # msp_tasks carries percentages, not hours: Core stores no actual_work column
            # on a task. The hours live on the assignment, which is queried below.
            await cursor.execute("""
                SELECT count(*) FILTER (WHERE percent_complete > 0) AS pct,
                       count(*) FILTER (WHERE percent_work_complete > 0) AS work_pct,
                       count(*) FILTER (WHERE physical_percent_complete > 0) AS physical
                  FROM msp_tasks
            """)
            row = await cursor.fetchone()
            say("  tasks with percent_complete > 0", str(row["pct"]))
            say("  tasks with percent_work_complete > 0", str(row["work_pct"]))
            say("  tasks with physical_percent_complete > 0", str(row["physical"]))
            await cursor.execute("""
                SELECT count(*) FILTER (WHERE actual_quantity > 0) AS q,
                       count(*) FILTER (WHERE actual_work > 0) AS w
                  FROM msp_resource_assignments
            """)
            row = await cursor.fetchone()
            say("  assignments with actual quantity > 0", str(row["q"]))
            say("  assignments with actual work > 0", str(row["w"]))


async def phase_c(dsn):
    """The real Finance calculation, over what phase B loaded."""
    print("\n  === PHASE C: the real FinanceLiveReportService ===")
    from app.finance.domain.errors import FinanceDomainError
    from scripts.test_only.mpp_parser_probe import finance_e2e_check as e2e

    async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, row_factory=dict_row) as connection:
        scope = e2e.FinanceScope(organization_id=e2e.ORGANIZATION_ID,
                                 project_id=e2e.PROJECT_ID, actor_user_id=e2e.ACTOR_ID)
        provider = e2e.CoreProgressSnapshotProvider(
            connection, activity_code_fields=e2e.WIRED_FIELDS)
        seeded = await e2e.seed_estimates(connection, provider, scope)

        service = e2e.report_service(connection)
        try:
            await service.live(scope, e2e.REPORTING_DATE)
            say("live report on the TARGET snapshot", "returned")
        except FinanceDomainError as error:
            say("live report on the TARGET snapshot", "REFUSED: %s" % error)
            finding("EXPECTED",
                    "The snapshot the loader creates is TARGET, and a live report refuses "
                    "a baseline: PROGRESS_SNAPSHOT_TYPES is ACTUAL/RESCHEDULED. Correct, "
                    "and it means a snapshot has to be labelled ACTUAL before any "
                    "financial report can be produced from it.")

        await e2e.clone_as_actual(connection)
        report = await e2e.run_report(connection, scope, seeded)
        findings.extend(e2e.problems)
        return report


async def main_async(dsn):
    await phase_a(dsn)
    phase_b(dsn)
    await phase_b_report(dsn)
    await phase_c(dsn)


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
    if not MPP.is_file():
        raise SystemExit("STOP: %s is missing" % MPP)

    print("\n  TEST_ONLY / DISPOSABLE -- MSP upload end to end, scratch database only\n")
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    try:
        loop.run_until_complete(main_async(arguments.dsn))
    finally:
        loop.close()

    print("\n  === FINDINGS ===")
    seen = set()
    for kind, text in findings:
        if text in seen:
            continue
        seen.add(text)
        print("  [%s] %s" % (kind, text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
