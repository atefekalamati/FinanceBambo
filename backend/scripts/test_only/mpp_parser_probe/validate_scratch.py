# -*- coding: utf-8 -*-
"""TEST_ONLY -- DISPOSABLE. Did the scratch database receive what the fixture described?

Compares the fixture against the rows actually in the scratch database, and reports the
resource rollup. Read-only: it issues SELECTs and nothing else, so it is safe to re-run at
any point and safe to run against a database somebody else loaded.

Counting is the easy half. The half that matters is the rollup -- for every MATERIAL
resource, the Resource Sheet total against the sum of that resource's assignments. Counts
prove rows arrived; the rollup proves the right numbers landed in the right columns. A
fixture whose quantities were written into the work columns would pass every count here and
fail the rollup.

    ..\\..\\..\\..\\.venv312\\Scripts\\python -m scripts.test_only.mpp_parser_probe.validate_scratch \\
        --snapshot-id 9001 --fixture <path>/fixture.json
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

from scripts.test_only.mpp_parser_probe.scratch_target import (         # noqa: E402
    SCRATCH_DATABASE, SCRATCH_HOST, SCRATCH_PORT, UnsafeTarget,
    assert_dsn_targets_scratch, assert_server_is_scratch)

DEFAULT_DSN = "postgresql://postgres@%s:%s/%s" % (SCRATCH_HOST, SCRATCH_PORT,
                                                  SCRATCH_DATABASE)

#: How close a rollup has to be. The same tolerance the seed script's own post-apply check
#: uses, so the two agree rather than disagreeing by a digit.
TOLERANCE = Decimal("0.01")


def say(label, detail=""):
    print("  %-42s %s" % (label, detail))


def compare(label, expected, actual, failures):
    ok = expected == actual
    say(label, "fixture=%-6s database=%-6s %s" % (expected, actual, "OK" if ok else "MISMATCH"))
    if not ok:
        failures.append("%s: fixture %s, database %s" % (label, expected, actual))


def counts(connection, snapshot_id, fixture, failures):
    row = connection.execute("""
        SELECT (SELECT count(*) FROM msp_tasks WHERE snapshot_id = %(id)s) AS tasks,
               (SELECT count(*) FROM msp_resources WHERE snapshot_id = %(id)s) AS resources,
               (SELECT count(*) FROM msp_resource_assignments WHERE snapshot_id = %(id)s)
                   AS assignments,
               (SELECT task_count FROM msp_snapshots WHERE id = %(id)s) AS declared
    """, {"id": snapshot_id}).fetchone()

    compare("task count", len(fixture["tasks"]), row["tasks"], failures)
    compare("resource count", len(fixture["resources"]), row["resources"], failures)
    compare("assignment count", len(fixture["assignments"]), row["assignments"], failures)
    # msp_snapshots.task_count is Core's own declared figure. A snapshot claiming a
    # different number of tasks than it holds is the kind of drift that makes a later report
    # quietly wrong, so it is checked rather than assumed.
    compare("snapshot.task_count vs msp_tasks", row["tasks"], row["declared"], failures)
    return row


def references(connection, snapshot_id, failures):
    """Rows pointing at things that are not there.

    There are no foreign keys for these -- the production migration role has no REFERENCES
    privilege on Core, so 0007 declares none -- which is exactly why they are checked.
    """
    row = connection.execute("""
        SELECT (SELECT count(*) FROM msp_resource_assignments a
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
                 WHERE snapshot_id = %(id)s AND planned_quantity IS NOT NULL
                   AND quantity_unit IS NULL) AS quantity_without_unit,
               (SELECT count(*) FROM msp_resource_assignments
                 WHERE snapshot_id = %(id)s AND resource_uid IS NULL) AS unlinked
    """, {"id": snapshot_id}).fetchone()

    for label, key in (("assignments pointing at a missing task", "broken_task_refs"),
                       ("assignments pointing at a missing resource", "broken_resource_refs"),
                       ("quantity with no unit (a CHECK forbids it)", "quantity_without_unit")):
        say(label, "%d %s" % (row[key], "OK" if row[key] == 0 else "FAIL"))
        if row[key]:
            failures.append("%s: %d" % (label, row[key]))
    # Expected, not a fault: MSP leaves some assignments unattached to any resource.
    say("assignments with no resource (expected)", str(row["unlinked"]))
    return row


def rollup(connection, snapshot_id, failures):
    """Each MATERIAL resource's sheet total against the sum of its assignments."""
    rows = connection.execute("""
        SELECT r.resource_uid, r.resource_name, r.resource_quantity AS sheet_total,
               coalesce(sum(a.planned_quantity), 0) AS assignment_total
          FROM msp_resources r
          LEFT JOIN msp_resource_assignments a
                 ON a.snapshot_id = r.snapshot_id AND a.resource_uid = r.resource_uid
         WHERE r.snapshot_id = %s AND r.native_type = 'MATERIAL'
               AND r.resource_quantity IS NOT NULL
         GROUP BY r.resource_uid, r.resource_name, r.resource_quantity
         ORDER BY r.resource_uid
    """, (snapshot_id,)).fetchall()

    matching = [r for r in rows
                if abs(r["sheet_total"] - r["assignment_total"]) <= TOLERANCE]
    mismatched = [r for r in rows if r not in matching]
    say("MATERIAL resources rolled up", str(len(rows)))
    say("rollup matching", "%d" % len(matching))
    say("rollup mismatched", "%d %s" % (len(mismatched), "OK" if not mismatched else "FAIL"))
    for row in mismatched[:10]:
        say("  %s" % (row["resource_name"] or row["resource_uid"]),
            "sheet=%s assignments=%s" % (row["sheet_total"], row["assignment_total"]))
    if mismatched:
        failures.append("%d MATERIAL resource(s) do not roll up" % len(mismatched))
    return rows


def quantities(connection, snapshot_id):
    """What actually landed in the quantity columns, zero told apart from null.

    Not a pass/fail check -- it is the reading that says whether this data can exercise the
    progress side of Finance at all. `actual_quantity = 0` and `actual_quantity IS NULL`
    mean different things, and a report that treats a missing figure as zero is the specific
    defect worth being able to see here.
    """
    row = connection.execute("""
        SELECT count(*) FILTER (WHERE planned_quantity IS NULL) AS planned_null,
               count(*) FILTER (WHERE planned_quantity = 0) AS planned_zero,
               count(*) FILTER (WHERE planned_quantity > 0) AS planned_positive,
               count(*) FILTER (WHERE actual_quantity IS NULL) AS actual_null,
               count(*) FILTER (WHERE actual_quantity = 0) AS actual_zero,
               count(*) FILTER (WHERE actual_quantity > 0) AS actual_positive
          FROM msp_resource_assignments WHERE snapshot_id = %s
    """, (snapshot_id,)).fetchone()
    say("planned_quantity null/zero/positive",
        "%d / %d / %d" % (row["planned_null"], row["planned_zero"], row["planned_positive"]))
    say("actual_quantity  null/zero/positive",
        "%d / %d / %d" % (row["actual_null"], row["actual_zero"], row["actual_positive"]))
    if row["actual_positive"] == 0:
        say("note", "no actual quantity anywhere: this data cannot exercise progress")
    return row


def validate(connection, snapshot_id, fixture):
    failures = []
    print("\n  --- counts ---")
    counts(connection, snapshot_id, fixture, failures)
    print("\n  --- references ---")
    references(connection, snapshot_id, failures)
    print("\n  --- resource rollup ---")
    rollup(connection, snapshot_id, failures)
    print("\n  --- quantities as stored ---")
    quantities(connection, snapshot_id)

    print()
    if failures:
        print("  VALIDATION FAILED (%d)" % len(failures))
        for line in failures:
            print("    - %s" % line)
    else:
        print("  VALIDATION PASSED -- counts, references and rollup all agree.")
    return len(failures)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--snapshot-id", type=int, required=True)
    parser.add_argument("--fixture", required=True, type=Path)
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    fixture = json.loads(arguments.fixture.read_text(encoding="utf-8"))
    try:
        assert_dsn_targets_scratch(arguments.dsn)
    except UnsafeTarget as refusal:
        raise SystemExit("STOP: %s" % refusal)

    with psycopg.connect(arguments.dsn, row_factory=dict_row,
                         connect_timeout=10) as connection:
        server = assert_server_is_scratch(connection)
        say("target", "%s:%s/%s as %s" % (server["host"], server["port"],
                                          server["database"], server["usr"]))
        return 1 if validate(connection, arguments.snapshot_id, fixture) else 0


if __name__ == "__main__":
    raise SystemExit(main())
