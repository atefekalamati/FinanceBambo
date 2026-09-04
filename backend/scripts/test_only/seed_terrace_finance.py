# -*- coding: utf-8 -*-
r"""TEST_ONLY -- LOCAL DEMO. Give `terrace` enough Finance data for the UI to show something.

    ..\..\..\.venv312\Scripts\python -m scripts.test_only.seed_terrace_finance --apply

WHAT IS REAL HERE AND WHAT IS NOT -- read this before believing a number on the screen.

REAL, read from Core:
  * which tasks exist, their names, their WBS and outline numbers;
  * `percent_complete` per task -- the progress the report divides by. 336 of the 1248 tasks
    in snapshot 40 carry a non-zero one, and that is what drives executed quantity.

NOT REAL, invented by this script and labelled as such in every row it writes:
  * the unit price. `msp_resources` is EMPTY in this database, so there is no rate to read.
  * the quantity, unless --quantity-field names a column that actually holds one.

WHY THE QUANTITY IS A PROBLEM
`msp_resource_assignments` is empty too, so there is no assignment quantity to take. What
remains are the NumberN columns, and this database gives no way to know what they mean --
the alias table that names them lives in the .mpp, not in Core, and Core stores only six of
the twenty. `--quantity-field` therefore defaults to a FLAT test quantity rather than
guessing that, say, number13 is a volume. Pass `--quantity-field number13` to use the file's
own varying values instead, understanding that their meaning is unverified.

So: the progress half of every figure is real; the money half is scaffolding. A screenshot
of this is a screenshot of the pipeline working, not of terrace's actual cost.

    DELETE FROM estimate_lines WHERE project_id = 'terrace';   -- to undo the lines
Prices cannot be undone: `price_versions_immutable` rejects DELETE, by design.
"""

import argparse
import sys
from decimal import Decimal
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

DSN = "postgresql://postgres@127.0.0.1:5432/bambo_canonical_test"
ORGANIZATION_ID = UUID("c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
PROJECT_ID = "terrace"
ACTOR_ID = UUID("53a1ac1b-d87f-4125-9ba9-a7d64166af88")

#: Deterministic ids, so a re-run reuses the same resources and their immutable prices.
NAMESPACE = UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

#: Databases this must never touch.
FORBIDDEN = frozenset({"bambo", "bambo_canonical_local"})

#: A flat test quantity, in the resource's unit. Deliberately round and identical on every
#: line so nobody mistakes it for a measurement.
TEST_QUANTITY = Decimal("1000")
#: A flat test rate in IRR. Same reasoning.
TEST_RATE = 1_000_000

#: Columns `msp_tasks` actually has for NumberN. The rest of MS Project's twenty are not
#: stored by Core at all.
QUANTITY_FIELDS = ("number1", "number3", "number4", "number13", "number14", "number18")


def say(label, detail=""):
    print("  %-40s %s" % (label, detail))


def seed_assignments(connection, rows, quantity_column):
    """Assignment rows for EVERY ACTUAL snapshot, so the feed can answer a quantity.

    Without these the report cannot compute anything at all, and that is not a bug:
    `resolve_progress_quantity` reads the FEED row, and a task-level feed states
    `plannedQuantity = None` because Core genuinely does not know how much of anything a
    task represents. Every line then resolves to `missing` with PROGRESS_MISSING -- which is
    the honest answer for a database whose `msp_resource_assignments` is empty, and useless
    for a demo.

    So this fills them. `planned_quantity` is the same figure the estimate line carries;
    `actual_quantity` is that figure times the task's OWN `percent_complete` in that
    snapshot. The percentage is real Core data and differs per snapshot, so the demo moves
    when the reporting date moves. The quantity it multiplies is not.

    Written for every ACTUAL snapshot rather than one, so any reporting date the UI asks for
    finds a feed instead of a 404.
    """
    snapshots = [row["id"] for row in connection.execute(
        "SELECT id FROM msp_snapshots WHERE project_id=%s "
        "AND snapshot_type = ANY(ARRAY['ACTUAL','RESCHEDULED']) ORDER BY id",
        (PROJECT_ID,)).fetchall()]
    uids = [row["uid"] for row in rows]
    quantity_by_uid = {}
    for row in rows:
        value = TEST_QUANTITY
        if quantity_column and row["quantity_source"] is not None and row["quantity_source"] > 0:
            value = Decimal(str(row["quantity_source"]))
        quantity_by_uid[row["uid"]] = value

    written = 0
    for snapshot in snapshots:
        connection.execute(
            "DELETE FROM msp_resource_assignments WHERE snapshot_id=%s", (snapshot,))
        connection.execute("DELETE FROM msp_resources WHERE snapshot_id=%s", (snapshot,))
        # One MATERIAL resource per task, so the resource sheet and the assignments agree.
        for row in connection.execute(
                "SELECT uid, name, percent_complete FROM msp_tasks "
                "WHERE snapshot_id=%s AND uid = ANY(%s)", (snapshot, uids)).fetchall():
            planned = quantity_by_uid.get(row["uid"], TEST_QUANTITY)
            percent = Decimal(str(row["percent_complete"] or 0))
            actual = (planned * percent / 100).quantize(Decimal("0.000001"))
            connection.execute("""
                INSERT INTO msp_resources
                    (snapshot_id, resource_uid, resource_name, native_type,
                     resource_quantity, resource_quantity_unit, quantity_unit_source,
                     standard_rate)
                VALUES (%s,%s,%s,'MATERIAL',%s,'unit','other',%s)
            """, (snapshot, row["uid"], (row["name"] or "بدون نام")[:120], planned,
                  TEST_RATE))
            connection.execute("""
                INSERT INTO msp_resource_assignments
                    (snapshot_id, assignment_uid, task_uid, resource_uid, units,
                     planned_quantity, actual_quantity, remaining_quantity, quantity_unit,
                     assignment_work_complete_percent)
                VALUES (%s,%s,%s,%s,100,%s,%s,%s,'unit',%s)
            """, (snapshot, row["uid"], row["uid"], row["uid"], planned, actual,
                  planned - actual, percent))
            written += 1
    say("msp_resources / assignments written",
        "%d rows across %d snapshot(s)" % (written, len(snapshots)))
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DSN)
    parser.add_argument("--snapshot-id", type=int, default=None,
                        help="default: the newest ACTUAL snapshot for terrace")
    parser.add_argument("--limit", type=int, default=120,
                        help="how many tasks become estimate lines")
    parser.add_argument("--quantity-field", default=None, choices=QUANTITY_FIELDS,
                        help="use this msp_tasks column as the quantity instead of a flat "
                             "test value; its meaning is UNVERIFIED")
    parser.add_argument("--gross-area", type=Decimal, default=Decimal("12000"),
                        help="test gross built area, so per-square-metre metrics compute")
    parser.add_argument("--with-assignments", action="store_true", default=True,
                        help="also fill msp_resources/msp_resource_assignments; "
                             "without them the report can compute nothing")
    parser.add_argument("--no-assignments", dest="with_assignments",
                        action="store_false")
    parser.add_argument("--apply", action="store_true", help="write; default is a dry run")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("\n  TEST_ONLY / LOCAL DEMO -- prices and quantities are scaffolding\n")

    with psycopg.connect(arguments.dsn, autocommit=True, row_factory=dict_row,
                         connect_timeout=10) as connection:
        database = connection.execute(
            "SELECT current_database() AS d").fetchone()["d"]
        if database in FORBIDDEN:
            raise SystemExit("STOP: %r is not a database this may write to." % database)
        say("database", database)

        snapshot = arguments.snapshot_id
        if snapshot is None:
            row = connection.execute("""
                SELECT id FROM msp_snapshots
                 WHERE project_id = %s AND snapshot_type = ANY(ARRAY['ACTUAL','RESCHEDULED'])
                 ORDER BY created_at DESC, id DESC LIMIT 1
            """, (PROJECT_ID,)).fetchone()
            if row is None:
                raise SystemExit("STOP: no ACTUAL snapshot for %s" % PROJECT_ID)
            snapshot = row["id"]
        say("snapshot", str(snapshot))

        # Leaf-ish tasks that report progress. A task with no percent contributes an
        # executed quantity of zero and makes the demo look emptier than the data is.
        quantity_column = arguments.quantity_field
        selected = ("t.%s AS quantity_source" % quantity_column) if quantity_column \
            else "NULL::numeric AS quantity_source"
        # `starts_with` rather than LIKE: a LIKE pattern needs a literal `%`, and psycopg
        # scans the whole statement for placeholders and rejects `%'` as malformed. Built by
        # concatenation too -- %-formatting would turn any escaped `%%` back into one.
        rows = connection.execute(
            "SELECT t.uid, t.name, t.wbs, t.outline_number, t.percent_complete, "
            + selected +
            "  FROM msp_tasks t"
            " WHERE t.snapshot_id = %s"
            "   AND t.outline_number IS NOT NULL"
            "   AND t.percent_complete > 0"
            "   AND NOT EXISTS (SELECT 1 FROM msp_tasks c"
            "                    WHERE c.snapshot_id = t.snapshot_id"
            "                      AND starts_with(c.outline_number,"
            "                                      t.outline_number || '.'))"
            " ORDER BY t.percent_complete DESC, t.uid"
            " LIMIT %s",
            (snapshot, arguments.limit)).fetchall()
        say("leaf tasks with progress", str(len(rows)))
        if not rows:
            raise SystemExit("STOP: no leaf task in snapshot %s reports progress." % snapshot)
        say("quantity source",
            quantity_column + "  (MEANING UNVERIFIED)" if quantity_column
            else "flat test value %s per line" % TEST_QUANTITY)
        say("unit price", "flat test value %s IRR (msp_resources is empty)" % TEST_RATE)

        if not arguments.apply:
            print("\n  DRY RUN -- nothing written. Add --apply.")
            return 0

        created = {"resources": 0, "prices": 0, "lines": 0, "reused_prices": 0}
        with connection.transaction():
            # Lines only. price_versions is immutable and finance_resources is its parent.
            connection.execute("DELETE FROM estimate_lines WHERE organization_id=%s "
                               "AND project_id=%s", (ORGANIZATION_ID, PROJECT_ID))

            settings = connection.execute(
                "SELECT id FROM finance_project_settings WHERE organization_id=%s "
                "AND project_id=%s", (ORGANIZATION_ID, PROJECT_ID)).fetchone()
            if settings is None:
                connection.execute("""
                    INSERT INTO finance_project_settings
                        (id, organization_id, project_id, revision, gross_built_area,
                         effective_from, reason, created_by)
                    VALUES (%s,%s,%s,1,%s,%s,%s,%s)
                """, (uuid4(), ORGANIZATION_ID, PROJECT_ID, arguments.gross_area,
                      date(2026, 1, 1), "TEST ONLY -- local demo gross area", ACTOR_ID))
                say("finance_project_settings", "created (gross area %s)"
                    % arguments.gross_area)
            else:
                say("finance_project_settings", "already present, left alone")

            for row in rows:
                resource_id = uuid5(NAMESPACE, "%s|task|%s" % (PROJECT_ID, row["uid"]))
                quantity = TEST_QUANTITY
                if row["quantity_source"] is not None and row["quantity_source"] > 0:
                    quantity = Decimal(str(row["quantity_source"]))

                inserted = connection.execute("""
                    INSERT INTO finance_resources
                        (id, organization_id, project_id, resource_type, code, title,
                         base_unit, dimension, external_resource_id, created_by)
                    VALUES (%s,%s,%s,'material',%s,%s,'unit','count',%s,%s)
                    ON CONFLICT (id) DO NOTHING
                    RETURNING id
                """, (resource_id, ORGANIZATION_ID, PROJECT_ID, "MSP-T%s" % row["uid"],
                      (row["name"] or "بدون نام")[:120], str(row["uid"]),
                      ACTOR_ID)).fetchone()
                if inserted:
                    created["resources"] += 1

                # Never deleted, never updated: read first, append only when different.
                price = connection.execute("""
                    SELECT version, unit_price_irr FROM price_versions
                     WHERE organization_id=%s AND project_id=%s AND resource_id=%s
                           AND scope_kind='project'
                     ORDER BY version DESC LIMIT 1
                """, (ORGANIZATION_ID, PROJECT_ID, resource_id)).fetchone()
                if price is not None and int(price["unit_price_irr"]) == TEST_RATE:
                    created["reused_prices"] += 1
                else:
                    connection.execute("""
                        INSERT INTO price_versions
                            (id, organization_id, project_id, resource_id, scope_kind,
                             version, unit_price_irr, effective_from, reason, created_by)
                        VALUES (%s,%s,%s,%s,'project',%s,%s,%s,%s,%s)
                    """, (uuid4(), ORGANIZATION_ID, PROJECT_ID, resource_id,
                          1 if price is None else int(price["version"]) + 1,
                          TEST_RATE, date(2026, 1, 1),
                          "TEST ONLY -- local demo rate", ACTOR_ID))
                    created["prices"] += 1

                # `activity_external_id` is the outline number because devhost wires the
                # adapters with ("outline_number", "wbs"). `assignment_external_id` is NULL
                # because a task-level feed emits assignmentExternalId=None, and the pair
                # has to match on both halves.
                connection.execute("""
                    INSERT INTO estimate_lines
                        (id, organization_id, project_id, resource_id, activity_external_id,
                         assignment_external_id, original_quantity, original_unit_price_irr,
                         source, created_by, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'manual_entry',%s,%s)
                """, (uuid4(), ORGANIZATION_ID, PROJECT_ID, resource_id,
                      row["outline_number"], str(row["uid"]), quantity, TEST_RATE,
                      ACTOR_ID, datetime(2026, 1, 1, tzinfo=timezone.utc)))
                created["lines"] += 1

            if arguments.with_assignments:
                created["assignments"] = seed_assignments(connection, rows, quantity_column)

        for key in ("resources", "prices", "reused_prices", "lines"):
            say(key, str(created[key]))

        total = connection.execute(
            "SELECT count(*) AS n FROM estimate_lines WHERE project_id=%s "
            "AND deleted_at IS NULL", (PROJECT_ID,)).fetchone()["n"]
        print()
        say("SELECT COUNT(*) FROM estimate_lines", str(total))
        print("\n  %s" % ("OK" if total else "STILL ZERO"))
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
