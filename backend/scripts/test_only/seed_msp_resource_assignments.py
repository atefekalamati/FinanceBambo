# -*- coding: utf-8 -*-
"""TEST_ONLY -- NON_PRODUCTION -- MANUAL_EXECUTION_ONLY

Fills `msp_resources` and `msp_resource_assignments` for one snapshot from a JSON fixture,
so the Finance side of the integration can be exercised end to end before the real importer
exists.

THIS IS NOT THE MSP PARSER AND MUST NEVER BECOME ONE.
The production path is: MPP -> Core's MPXJ importer -> these tables. That importer runs on a
JVM (`parser_engine` reads `mpxj-16.4.1/jvm-17`) and lives outside this repository. This
script reads JSON. It cannot open a .mpp, has no MPXJ dependency, and is not on any
deployment path -- which is the point: a convenient second importer inside Finance would
quietly become the real one.

WHAT IT REFUSES TO DO
  * infer a quantity. A value absent from the fixture is written NULL, never zero and never
    derived from work, duration or a percentage;
  * classify a WORK resource. MSP has no labour/equipment distinction, so
    `bambo_resource_type` stays NULL unless the fixture states it;
  * touch `msp_tasks`, `msp_snapshots` or `msp_file_versions`. It reads them to validate and
    writes neither;
  * write anything at all without `--apply`. The default is a dry run.

    python -m scripts.test_only.seed_msp_resource_assignments \
        --dsn postgresql://... --snapshot-id 40 --fixture bridge.json          # dry run
    python -m ... --apply                                                      # writes
    python -m ... --apply --replace-test-data                                  # re-seed
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402
from psycopg.types.json import Jsonb                                    # noqa: E402

#: The one central database this may ever touch, and only with --allow-central.
CENTRAL_DATABASE = "bambo_canonical_local"
#: Refused outright. `bambo` is Core's own database and nothing here belongs in it.
FORBIDDEN_DATABASES = frozenset({"bambo", "bambo_finance_dev"})

RESOURCE_COLUMNS = (
    "resource_uid", "resource_guid", "resource_name", "native_type", "bambo_resource_type",
    "resource_quantity", "resource_quantity_unit", "quantity_unit_source", "initials",
    "material_label", "resource_group", "code", "max_units", "standard_rate",
    "overtime_rate", "cost_per_use", "work", "actual_work", "remaining_work",
    "source_cost", "source_actual_cost", "source_remaining_cost",
)
ASSIGNMENT_COLUMNS = (
    "assignment_uid", "task_uid", "resource_uid", "units", "planned_work", "actual_work",
    "remaining_work", "planned_quantity", "actual_quantity", "remaining_quantity",
    "quantity_unit", "assignment_work_complete_percent", "source_cost",
    "source_actual_cost", "source_remaining_cost",
)


class Refused(SystemExit):
    """A guard said no. Always carries the reason."""


def say(step, detail=""):
    print("  %-44s %s" % (step, detail))


def decimal_or_none(value):
    """Fixture values arrive as strings so they never pass through a float.

    An absent value stays absent. This is the single place a missing quantity could have
    become a zero, and it does not.
    """
    if value is None or value == "":
        return None
    return Decimal(str(value))


def check_target(connection, allow_central):
    row = connection.execute("""
        SELECT current_database() AS database, current_user AS usr,
               host(inet_server_addr()) AS host, inet_server_port() AS port
    """).fetchone()
    database = row["database"]
    if database in FORBIDDEN_DATABASES:
        raise Refused("STOP: %r is not a database this script may write to." % database)
    if database == CENTRAL_DATABASE and not allow_central:
        raise Refused(
            "STOP: %r is the central database. Re-run with --allow-central once a human has\n"
            "      decided this test data belongs there." % database)
    if database != CENTRAL_DATABASE and allow_central:
        say("note", "--allow-central given but the target is local; the flag changes nothing")
    say("target", "%s:%s/%s as %s" % (row["host"], row["port"], database, row["usr"]))
    return row


def check_schema(connection):
    missing = [name for name in ("msp_snapshots", "msp_tasks", "msp_resources",
                                 "msp_resource_assignments")
               if connection.execute("SELECT to_regclass(%s)", ("public." + name,))
               .fetchone()["to_regclass"] is None]
    if missing:
        raise Refused("STOP: missing table(s): %s. Run Alembic 0007 first." % ", ".join(missing))


def check_snapshot(connection, snapshot_id):
    row = connection.execute("""
        SELECT id, project_id, snapshot_type, task_count, status_date_jalali
          FROM msp_snapshots WHERE id = %s
    """, (snapshot_id,)).fetchone()
    if row is None:
        raise Refused("STOP: snapshot %s does not exist." % snapshot_id)
    say("snapshot", "%s  project=%s  type=%s  tasks=%s"
        % (row["id"], row["project_id"], row["snapshot_type"], row["task_count"]))
    return row


def check_tasks(connection, snapshot_id, assignments):
    """Every task_uid must belong to this snapshot.

    There is no foreign key for this -- the production migration role has no REFERENCES
    privilege on Core -- so it is checked here, before anything is written. An assignment
    pointing at a task from another snapshot would look perfectly valid in the table and
    quietly attach a quantity to the wrong work.
    """
    known = {row["uid"] for row in connection.execute(
        "SELECT uid FROM msp_tasks WHERE snapshot_id = %s AND uid IS NOT NULL",
        (snapshot_id,)).fetchall()}
    wanted = {row["task_uid"] for row in assignments}
    missing = sorted(wanted - known)
    say("task references", "%d distinct task_uid, %d missing" % (len(wanted), len(missing)))
    if missing:
        raise Refused(
            "STOP: %d task_uid value(s) are not in snapshot %s: %s%s"
            % (len(missing), snapshot_id, missing[:10],
               " ..." if len(missing) > 10 else ""))


def check_resources(resources, assignments):
    """Every non-null resource_uid must be in the fixture, and UIDs must be unique."""
    uids = [row["resource_uid"] for row in resources]
    duplicates = sorted({uid for uid in uids if uids.count(uid) > 1})
    if duplicates:
        raise Refused("STOP: duplicate resource_uid in the fixture: %s" % duplicates[:10])
    assignment_uids = [row["assignment_uid"] for row in assignments]
    duplicated = sorted({uid for uid in assignment_uids if assignment_uids.count(uid) > 1})
    if duplicated:
        raise Refused("STOP: duplicate assignment_uid in the fixture: %s" % duplicated[:10])
    referenced = {row["resource_uid"] for row in assignments if row["resource_uid"] is not None}
    unknown = sorted(referenced - set(uids))
    if unknown:
        raise Refused("STOP: assignments reference resource_uid not in the fixture: %s"
                      % unknown[:10])
    unlinked = sum(1 for row in assignments if row["resource_uid"] is None)
    say("fixture integrity", "%d resources, %d assignments, %d unlinked"
        % (len(resources), len(assignments), unlinked))


def check_existing(connection, snapshot_id, replace):
    counts = connection.execute("""
        SELECT (SELECT count(*) FROM msp_resources WHERE snapshot_id = %(id)s) AS resources,
               (SELECT count(*) FROM msp_resource_assignments WHERE snapshot_id = %(id)s)
                   AS assignments
    """, {"id": snapshot_id}).fetchone()
    present = counts["resources"] + counts["assignments"]
    say("already present for this snapshot",
        "resources=%d assignments=%d" % (counts["resources"], counts["assignments"]))
    if present and not replace:
        raise Refused(
            "STOP: snapshot %s already holds %d row(s). Re-run with --replace-test-data to\n"
            "      delete them first -- and only if they are test data."
            % (snapshot_id, present))
    return counts


def summarise(resources, assignments):
    """What the fixture would write, printed before anything is written."""
    kinds = {}
    for row in resources:
        kinds[row["native_type"]] = kinds.get(row["native_type"], 0) + 1
    with_quantity = sum(1 for row in assignments if row.get("planned_quantity") is not None)
    with_actual = sum(1 for row in assignments if row.get("actual_quantity") is not None)
    no_unit = sum(1 for row in assignments
                  if row.get("planned_quantity") is not None and not row.get("quantity_unit"))
    unclassified = sum(1 for row in resources if not row.get("bambo_resource_type"))
    say("resources by MSP type", ", ".join("%s=%d" % kv for kv in sorted(kinds.items())))
    say("resources with no BAMBO type", "%d (WORK is deliberately unclassified)" % unclassified)
    say("assignments with planned quantity", str(with_quantity))
    say("assignments with actual quantity", "%d (0 is expected: none reported yet)" % with_actual)
    say("planned quantity with no unit", "%d (must be 0 -- a CHECK forbids it)" % no_unit)
    if no_unit:
        raise Refused("STOP: %d assignment(s) carry a quantity with no unit." % no_unit)


def insert(connection, snapshot_id, resources, assignments, replace):
    """Resources first: the assignment foreign key points at them."""
    if replace:
        connection.execute("DELETE FROM msp_resource_assignments WHERE snapshot_id = %s",
                           (snapshot_id,))
        connection.execute("DELETE FROM msp_resources WHERE snapshot_id = %s", (snapshot_id,))
        say("replaced", "existing rows for this snapshot deleted")

    resource_sql = ("INSERT INTO msp_resources (snapshot_id, %s, raw_fields_json) "
                    "VALUES (%%s, %s, %%s)"
                    % (", ".join(RESOURCE_COLUMNS),
                       ", ".join(["%s"] * len(RESOURCE_COLUMNS))))
    for row in resources:
        connection.execute(resource_sql, [snapshot_id] + [
            _value(name, row.get(name)) for name in RESOURCE_COLUMNS
        ] + [Jsonb(row.get("raw_fields_json") or {})])
    say("resources inserted", str(len(resources)))

    assignment_sql = ("INSERT INTO msp_resource_assignments (snapshot_id, %s, raw_fields_json) "
                      "VALUES (%%s, %s, %%s)"
                      % (", ".join(ASSIGNMENT_COLUMNS),
                         ", ".join(["%s"] * len(ASSIGNMENT_COLUMNS))))
    for row in assignments:
        connection.execute(assignment_sql, [snapshot_id] + [
            _value(name, row.get(name)) for name in ASSIGNMENT_COLUMNS
        ] + [Jsonb(row.get("raw_fields_json") or {})])
    say("assignments inserted", str(len(assignments)))


#: Which fixture fields are numbers. Everything else is passed through as text or None.
_NUMERIC = frozenset({
    "resource_quantity", "max_units", "standard_rate", "overtime_rate", "cost_per_use",
    "work", "actual_work", "remaining_work", "source_cost", "source_actual_cost",
    "source_remaining_cost", "units", "planned_work", "planned_quantity", "actual_quantity",
    "remaining_quantity", "assignment_work_complete_percent",
})


def _value(name, raw):
    if name in _NUMERIC:
        return decimal_or_none(raw)
    return raw


def verify(connection, snapshot_id):
    """The same checks the operational validation SQL runs, on this snapshot only."""
    row = connection.execute("""
        SELECT (SELECT count(*) FROM msp_resources WHERE snapshot_id = %(id)s) AS resources,
               (SELECT count(*) FROM msp_resource_assignments WHERE snapshot_id = %(id)s)
                   AS assignments,
               (SELECT count(*) FROM (SELECT resource_uid FROM msp_resources
                 WHERE snapshot_id = %(id)s GROUP BY 1 HAVING count(*) > 1) d)
                   AS duplicate_resource_uid,
               (SELECT count(*) FROM (SELECT assignment_uid FROM msp_resource_assignments
                 WHERE snapshot_id = %(id)s GROUP BY 1 HAVING count(*) > 1) d)
                   AS duplicate_assignment_uid,
               (SELECT count(*) FROM msp_resource_assignments a
                 WHERE a.snapshot_id = %(id)s
                   AND NOT EXISTS (SELECT 1 FROM msp_tasks t
                                    WHERE t.snapshot_id = a.snapshot_id AND t.uid = a.task_uid))
                   AS broken_task_refs,
               (SELECT count(*) FROM msp_resource_assignments a
                 WHERE a.snapshot_id = %(id)s AND a.resource_uid IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM msp_resources r
                                    WHERE r.snapshot_id = a.snapshot_id
                                      AND r.resource_uid = a.resource_uid))
                   AS broken_resource_refs,
               (SELECT count(*) FROM msp_resource_assignments
                 WHERE snapshot_id = %(id)s AND planned_quantity IS NOT NULL)
                   AS with_planned_quantity,
               (SELECT count(*) FROM msp_resource_assignments
                 WHERE snapshot_id = %(id)s AND actual_quantity IS NOT NULL)
                   AS with_actual_quantity,
               (SELECT count(*) FROM msp_resource_assignments
                 WHERE snapshot_id = %(id)s AND quantity_unit IS NULL
                   AND planned_quantity IS NOT NULL) AS quantity_without_unit
    """, {"id": snapshot_id}).fetchone()
    print()
    say("VERIFY resources / assignments", "%d / %d" % (row["resources"], row["assignments"]))
    say("VERIFY duplicate uids", "resource=%d assignment=%d"
        % (row["duplicate_resource_uid"], row["duplicate_assignment_uid"]))
    say("VERIFY broken references", "task=%d resource=%d"
        % (row["broken_task_refs"], row["broken_resource_refs"]))
    say("VERIFY quantities", "planned=%d actual=%d without unit=%d"
        % (row["with_planned_quantity"], row["with_actual_quantity"],
           row["quantity_without_unit"]))

    rolled = connection.execute("""
        WITH rolled AS (
            SELECT r.resource_quantity AS sheet_total,
                   coalesce(sum(a.planned_quantity), 0) AS assignment_total
              FROM msp_resources r
              LEFT JOIN msp_resource_assignments a
                     ON a.snapshot_id = r.snapshot_id AND a.resource_uid = r.resource_uid
             WHERE r.snapshot_id = %s AND r.native_type = 'MATERIAL'
                   AND r.resource_quantity IS NOT NULL
             GROUP BY r.id, r.resource_quantity)
        SELECT count(*) FILTER (WHERE abs(sheet_total - assignment_total) <= 0.01) AS matching,
               count(*) FILTER (WHERE abs(sheet_total - assignment_total) >  0.01) AS mismatched
          FROM rolled
    """, (snapshot_id,)).fetchone()
    say("VERIFY resource total vs assignment sum",
        "matching=%d mismatched=%d" % (rolled["matching"], rolled["mismatched"]))
    failures = (row["duplicate_resource_uid"] + row["duplicate_assignment_uid"]
                + row["broken_task_refs"] + row["broken_resource_refs"]
                + row["quantity_without_unit"] + rolled["mismatched"])
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", required=True, help="target database")
    parser.add_argument("--snapshot-id", type=int, required=True)
    parser.add_argument("--fixture", required=True, help="JSON produced from an MPP probe")
    parser.add_argument("--apply", action="store_true",
                        help="actually write; without it this is a dry run")
    parser.add_argument("--replace-test-data", action="store_true",
                        help="delete this snapshot's existing rows first")
    parser.add_argument("--allow-central", action="store_true",
                        help="permit writing to %s" % CENTRAL_DATABASE)
    arguments = parser.parse_args(argv)

    print("\n  TEST_ONLY / NON_PRODUCTION / MANUAL_EXECUTION_ONLY")
    print("  this is not the MSP parser -- it reads JSON, never a .mpp\n")

    fixture = json.loads(Path(arguments.fixture).read_text(encoding="utf-8"))
    resources = fixture["resources"]
    assignments = fixture["assignments"]
    say("fixture", "%s (%s)" % (Path(arguments.fixture).name,
                                fixture.get("source_file") or "unknown source"))

    # Checked here, before connecting, as well as against the server afterwards. The DSN is
    # only a claim -- which is why check_target asks the server too -- but a guard that runs
    # only after connecting cannot fire when the server is unreachable, and "it hung" is not
    # a refusal. Both checks earn their place.
    database = urlsplit(arguments.dsn).path.lstrip("/")
    if database in FORBIDDEN_DATABASES:
        raise Refused("STOP: the DSN names %r." % database)
    if database == CENTRAL_DATABASE and not arguments.allow_central:
        raise Refused(
            "STOP: the DSN names %r, the central database. Re-run with --allow-central once\n"
            "      a human has decided this test data belongs there." % database)

    with psycopg.connect(arguments.dsn, row_factory=dict_row, connect_timeout=15) as connection:
        check_target(connection, arguments.allow_central)
        check_schema(connection)
        check_snapshot(connection, arguments.snapshot_id)
        check_resources(resources, assignments)
        check_tasks(connection, arguments.snapshot_id, assignments)
        check_existing(connection, arguments.snapshot_id, arguments.replace_test_data)
        summarise(resources, assignments)

        if not arguments.apply:
            print("\n  DRY RUN -- nothing was written. Add --apply to write.")
            return 0

        # One transaction for both tables. A snapshot with resources but no assignments
        # would look importable and be wrong, so either both land or neither does.
        with connection.transaction():
            insert(connection, arguments.snapshot_id, resources, assignments,
                   arguments.replace_test_data)
        failures = verify(connection, arguments.snapshot_id)
        print("\n  %s" % ("APPLIED -- all checks clean." if failures == 0
                          else "APPLIED, but %d check(s) failed above." % failures))
        return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
