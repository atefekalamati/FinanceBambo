# -*- coding: utf-8 -*-
r"""TEST_ONLY -- NON_PRODUCTION -- DISPOSABLE. Build a scratch database from a fixture.

    python -m scripts.test_only.mpp_parser_probe.load_scratch \
        --fixture scripts/test_only/mpp_parser_probe/fixture.json --recreate --apply

WHAT IT DOES, IN THIS ORDER
  1. Prove the target is the local scratch database -- twice, once from the DSN and once by
     asking the server that answers. Nothing below runs until both agree.
  2. Create the database (`--recreate` drops it first).
  3. `alembic upgrade head`. The only way the Finance schema is ever created; there is no
     second code path that writes Finance DDL, so this database and a real one are built by
     the same revisions. This is what brings `msp_resources` and
     `msp_resource_assignments` into existence, at revision 0007.
  4. Apply `scripts/demo/core_mirror.sql`, which carries the Core-side tables --
     `msp_snapshots`, `msp_tasks` and their parents. Generated from the real Core schema
     export, and reused here rather than reinvented.
  5. Insert the Core parent chain one row deep: organization, project, file version,
     snapshot. Synthetic and obviously so.
  6. Insert `msp_tasks` from the fixture's `tasks` block.
  7. Hand `msp_resources` and `msp_resource_assignments` to the EXISTING seed script, run
     as a subprocess and completely unmodified.
  8. Validate.

WHY STEP 7 SHELLS OUT
`seed_msp_resource_assignments.py` is the thing being tested. Reimplementing its inserts
here would produce a second importer that agrees with itself and proves nothing -- and the
first time the two drifted, the copy would be the one that looked right. It runs verbatim,
with its own guards intact.

WHY THIS SCRIPT MAY WRITE msp_tasks WHEN THE SEED SCRIPT MAY NOT
The seed script refuses to touch Core-owned tables on purpose: it is aimed at real
databases where Core owns that data. This one only ever addresses a scratch database that
it created itself, on loopback, guarded by `scratch_target`. Different target, different
rule. Neither script's rule is relaxed.

THE CENTRAL DATABASE IS NEVER TOUCHED
Not read, not written, not connected to. `scratch_target` refuses it by name, along with
Core's own database, the shared development database and the demo database.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402
from psycopg.types.json import Jsonb                                    # noqa: E402

from scripts.test_only.mpp_parser_probe.scratch_target import (         # noqa: E402
    MAINTENANCE_DATABASE, SCRATCH_DATABASE, SCRATCH_HOST, SCRATCH_PORT, UnsafeTarget,
    assert_dsn_targets_scratch, assert_server_is_scratch)
from scripts.test_only.mpp_parser_probe.validate_scratch import validate  # noqa: E402

MIRROR_SQL = BACKEND_ROOT / "scripts" / "demo" / "core_mirror.sql"
SEED_MODULE = "scripts.test_only.seed_msp_resource_assignments"

DEFAULT_DSN = "postgresql://postgres@%s:%s/%s" % (SCRATCH_HOST, SCRATCH_PORT,
                                                  SCRATCH_DATABASE)

#: Fixed so a re-run addresses the same rows instead of accumulating new ones. Obviously
#: synthetic: nothing that reaches a real database is named this.
ORGANIZATION_ID = uuid.UUID("00000000-0000-4000-8000-00000000f001")
PROJECT_ID = "mpp-probe-project"
ORGANIZATION_NAME = "MPP PROBE (TEST ONLY)"
PROJECT_NAME = "MPP probe scratch project (TEST ONLY)"

#: Core's snapshot_type vocabulary is TARGET / ACTUAL / RESCHEDULED. TARGET is the honest
#: label for this file: it carries a plan and no recorded progress at all.
SNAPSHOT_TYPE = "TARGET"

#: Core column -> fixture key. Written as a map rather than a shared list of names because
#: the two vocabularies genuinely differ: Core calls it `uid`, the fixture calls it
#: `task_uid`. Assuming they matched silently inserted 328 tasks with a null uid, which the
#: seed script then reported as 266 missing task references -- a confusing way to learn it.
#: msp_tasks holds a good deal more (baselines, the NumberN fields); those stay null rather
#: than being invented.
TASK_COLUMNS = {
    "uid": "task_uid",
    "task_id": "task_id",
    "name": "name",
    "wbs": "wbs",
    "outline_number": "outline_number",
    "outline_level": "outline_level",
    "start": "start",
    "finish": "finish",
    "duration": "duration",
    "percent_complete": "percent_complete",
    "percent_work_complete": "percent_work_complete",
    "physical_percent_complete": "physical_percent_complete",
    "text1": "text1",
}


def say(step, detail=""):
    print("  %-42s %s" % (step, detail))


def maintenance_dsn(dsn):
    return dsn.replace("/%s" % SCRATCH_DATABASE, "/%s" % MAINTENANCE_DATABASE)


def ensure_database(dsn, recreate):
    """Create the scratch database, dropping it first when asked.

    Runs against the maintenance database, because CREATE DATABASE cannot be issued from
    inside the database being created. That is the only reason `allow_maintenance` exists,
    and it widens the database check alone -- host and port stay pinned.
    """
    admin = maintenance_dsn(dsn)
    assert_dsn_targets_scratch(admin, allow_maintenance=True)
    with psycopg.connect(admin, autocommit=True, row_factory=dict_row,
                         connect_timeout=10) as connection:
        server = assert_server_is_scratch(connection, allow_maintenance=True)
        say("server", server["version"].split(" on ")[0])
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                    (SCRATCH_DATABASE,)).fetchone()
        if exists and recreate:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (SCRATCH_DATABASE,))
            connection.execute('DROP DATABASE "%s"' % SCRATCH_DATABASE)
            say("dropped", SCRATCH_DATABASE)
            exists = None
        if not exists:
            connection.execute('CREATE DATABASE "%s"' % SCRATCH_DATABASE)
            say("created", SCRATCH_DATABASE)
        else:
            say("database already present", SCRATCH_DATABASE)


def migrate(dsn):
    """`alembic upgrade head`, in a subprocess with the DSN passed by environment.

    A subprocess so this runs the same command an operator would, and so nothing Alembic
    imports shares a connection with the steps that follow.
    """
    environment = dict(os.environ, FINANCE_MIGRATION_DSN=dsn)
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=BACKEND_ROOT, capture_output=True, text=True,
                            env=environment)
    if result.returncode != 0:
        # The DSN can appear inside a driver error, so nothing captured is echoed verbatim.
        print(result.stderr[-1500:] if result.stderr else "")
        raise SystemExit("alembic upgrade failed; re-run it directly to see the error")
    say("alembic", "upgrade head")


def apply_core_mirror(connection):
    if not MIRROR_SQL.is_file():
        raise SystemExit("STOP: %s is missing." % MIRROR_SQL)
    connection.execute(MIRROR_SQL.read_text(encoding="utf-8"))
    say("core mirror schema applied", MIRROR_SQL.name)


def core_parents(connection, fixture, snapshot_id, fixture_path):
    """Organization -> project -> file version -> snapshot, one row each.

    `msp_snapshots` cannot exist without them: it has foreign keys to `projects` and to
    `msp_file_versions(id, project_id)`. All four rows are synthetic and idempotent, so a
    re-run without `--recreate` addresses the same snapshot rather than stacking new ones.
    """
    connection.execute("""
        INSERT INTO organizations (id, name) VALUES (%s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (ORGANIZATION_ID, ORGANIZATION_NAME))
    connection.execute("""
        INSERT INTO projects (id, organization_id, name, status)
        VALUES (%s, %s, %s, 'active')
        ON CONFLICT (id) DO NOTHING
    """, (PROJECT_ID, ORGANIZATION_ID, PROJECT_NAME))

    # A real digest of the fixture. msp_file_versions has a CHECK requiring 64 hex
    # characters, and hashing something that exists beats inventing a string that satisfies
    # the pattern and means nothing.
    digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    source = fixture.get("source_file") or "unknown.mpp"
    version = connection.execute("""
        INSERT INTO msp_file_versions (project_id, version_number, original_filename,
                                       stored_rel_path, file_type, detected_role,
                                       size_bytes, sha256)
        VALUES (%s, 1, %s, %s, 'MPP', 'TARGET', %s, %s)
        ON CONFLICT (project_id, version_number) DO UPDATE SET original_filename = EXCLUDED.original_filename
        RETURNING id
    """, (PROJECT_ID, source, "test_only/%s" % source,
          max(fixture_path.stat().st_size, 1), digest)).fetchone()

    connection.execute("""
        INSERT INTO msp_snapshots (id, project_id, file_version_id, snapshot_type,
                                   source_filename, source_version_number, display_label,
                                   task_count, parser_engine, parser_warnings)
        VALUES (%(id)s, %(project)s, %(version)s, %(type)s, %(source)s, 1, %(label)s,
                %(tasks)s, %(engine)s, %(warnings)s)
        ON CONFLICT (id) DO UPDATE SET task_count = EXCLUDED.task_count,
                                       parser_engine = EXCLUDED.parser_engine
    """, {"id": snapshot_id, "project": PROJECT_ID, "version": version["id"],
          "type": SNAPSHOT_TYPE, "source": source,
          "label": "MPP probe scratch snapshot (TEST ONLY)",
          "tasks": len(fixture["tasks"]),
          # Not the production engine string. This snapshot was built by the probe, and the
          # column is the only place that distinction survives.
          "engine": "mpp_parser_probe/%s" % (fixture.get("mpxj_java_package") or "mpxj"),
          "warnings": Jsonb({"note": "TEST ONLY -- loaded by mpp_parser_probe, "
                                     "not by Core's importer"})})
    say("core parents", "org, project %s, file version %s, snapshot %s"
        % (PROJECT_ID, version["id"], snapshot_id))
    return version["id"]


def insert_tasks(connection, snapshot_id, tasks):
    """The fixture's tasks, as Core would hold them.

    Written here rather than by the seed script because the seed script refuses Core-owned
    tables by design. Without these rows its own `check_tasks` refuses the whole run: every
    assignment names a `task_uid` that has to exist in this snapshot first.

    This snapshot's tasks are always cleared first, whether or not the database is being
    recreated. `msp_tasks` has no unique key on `(snapshot_id, uid)` -- Core's schema does
    not declare one -- so a second run without the delete appends a whole duplicate set and
    nothing complains. It happened: 656 rows for 328 distinct UIDs, while the seed script
    refused its own re-run, leaving the two halves of the snapshot disagreeing. The fixture
    defines this snapshot's tasks completely, so replacing them is the only correct load.
    """
    removed = connection.execute(
        "DELETE FROM msp_tasks WHERE snapshot_id = %s", (snapshot_id,)).rowcount
    if removed:
        say("msp_tasks cleared", "%d existing row(s) for this snapshot" % removed)
    columns = tuple(TASK_COLUMNS)
    sql = ("INSERT INTO msp_tasks (snapshot_id, %s, raw_fields_json) VALUES (%%s, %s, %%s)"
           % (", ".join(columns), ", ".join(["%s"] * len(columns))))
    for task in tasks:
        # `name` is NOT NULL DEFAULT '' in Core. An unnamed task is a real thing in MSP --
        # the placeholder row at UID 0 is one -- so it becomes the empty string the column
        # already expects rather than failing the load.
        values = [task.get(TASK_COLUMNS[column]) for column in columns]
        values[columns.index("name")] = values[columns.index("name")] or ""
        connection.execute(sql, [snapshot_id] + values
                           + [Jsonb({"parentTaskUid": task.get("parent_task_uid"),
                                     "summary": task.get("summary"),
                                     "milestone": task.get("milestone"),
                                     "durationUnit": task.get("duration_unit"),
                                     "durationHours": task.get("duration_hours")})])
    say("msp_tasks inserted", str(len(tasks)))


def run_seed_script(dsn, snapshot_id, fixture_path):
    """The existing seed script, verbatim, as a subprocess.

    Its own guards run: it re-checks the target, the schema, the snapshot, the fixture's
    integrity and every task reference, and it writes both tables in one transaction.

    `--replace-test-data` is always passed. That flag exists so the seed script cannot
    quietly double a real snapshot's rows, and it is right to demand it -- but here the
    snapshot was created by this script, in a scratch database, and the fixture defines it
    completely. Without the flag a second run reloads the tasks and then has its resources
    and assignments refused, which leaves the two halves of one snapshot describing
    different loads. A load that cannot be repeated is worse than one that replaces itself.
    """
    command = [sys.executable, "-m", SEED_MODULE, "--dsn", dsn,
               "--snapshot-id", str(snapshot_id), "--fixture", str(fixture_path),
               "--apply", "--replace-test-data"]
    say("running", "python -m %s --apply" % SEED_MODULE)
    print()
    result = subprocess.run(command, cwd=BACKEND_ROOT,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    print()
    if result.returncode != 0:
        raise SystemExit("the seed script exited %s -- see its output above"
                         % result.returncode)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--snapshot-id", type=int, default=9001)
    parser.add_argument("--recreate", action="store_true",
                        help="drop the scratch database first")
    parser.add_argument("--apply", action="store_true",
                        help="actually build and load; without it nothing is written")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("\n  TEST_ONLY / NON_PRODUCTION / DISPOSABLE")
    print("  target: the local scratch database only -- never the central one\n")

    if not arguments.fixture.is_file():
        raise SystemExit("STOP: no such fixture: %s" % arguments.fixture)
    fixture = json.loads(arguments.fixture.read_text(encoding="utf-8"))
    fixture_path = arguments.fixture.resolve()
    say("fixture", "%s (%s)" % (fixture_path.name, fixture.get("source_file") or "unknown"))
    say("would load", "%d tasks, %d resources, %d assignments"
        % (len(fixture["tasks"]), len(fixture["resources"]), len(fixture["assignments"])))

    try:
        assert_dsn_targets_scratch(arguments.dsn)
    except UnsafeTarget as refusal:
        raise SystemExit("STOP: %s" % refusal)

    if not arguments.apply:
        print("\n  DRY RUN -- no database was created and nothing was written.")
        print("  Add --apply to build the scratch database.")
        return 0

    ensure_database(arguments.dsn, arguments.recreate)
    migrate(arguments.dsn)

    with psycopg.connect(arguments.dsn, autocommit=True, row_factory=dict_row,
                         connect_timeout=10) as connection:
        # Gate 2 again, on the connection about to write. The one in `ensure_database`
        # proved a different connection to a different database.
        server = assert_server_is_scratch(connection)
        say("write target confirmed", "%s:%s/%s" % (server["host"], server["port"],
                                                    server["database"]))
        apply_core_mirror(connection)
        with connection.transaction():
            core_parents(connection, fixture, arguments.snapshot_id, fixture_path)
            insert_tasks(connection, arguments.snapshot_id, fixture["tasks"])

    # Outside the connection above: the seed script opens its own, and holding a
    # transaction here while it tried to write would deadlock on the same rows.
    run_seed_script(arguments.dsn, arguments.snapshot_id, fixture_path)

    with psycopg.connect(arguments.dsn, row_factory=dict_row,
                         connect_timeout=10) as connection:
        assert_server_is_scratch(connection)
        failures = validate(connection, arguments.snapshot_id, fixture)

    print("\n  scratch database %r is disposable: drop it, or re-run with --recreate."
          % SCRATCH_DATABASE)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
