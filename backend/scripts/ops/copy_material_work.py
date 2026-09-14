# -*- coding: utf-8 -*-
r"""Copy material-price work from one local database into another, additively.

    python -m scripts.ops.copy_material_work --source postgresql://u@127.0.0.1:5432/bambo_material_price_demo \
                                             --target postgresql://u@127.0.0.1:5432/bambo_canonical_test
    ... --apply

Dry run by default. It reads both databases, reports exactly what it would insert, what is
already present, and every conflict it found, and writes nothing until `--apply`.

WHAT "ADDITIVE" MEANS HERE, PRECISELY

Every statement is `INSERT ... ON CONFLICT DO NOTHING`. There is no UPDATE, no DELETE, no
TRUNCATE and no trigger or replication-role change anywhere in this file. A row already in
the target is counted as already present and left exactly as it is -- including when its
values differ from the source's, which is reported as a conflict rather than resolved.
Resolving it would mean choosing which of two databases is right, and this script is not
in a position to know.

UUIDs ARE PRESERVED ONLY WHEN THAT IS SAFE

Preserving them keeps provenance intact, so it is preferred. It is checked, not assumed:
before copying, every id that exists on both sides is listed, and if any of those rows
differ the copy stops. Mapping ids instead would be possible but it is where provenance
goes to die, so it is deliberately not offered -- a genuine id collision is a situation for
a person, not for a flag.

The source is opened read-only. `price_versions` is never copied: an observation is
evidence, and an official Finance price is a decision that belongs to the database that
made it.
"""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from scripts.ops._common import (CANONICAL_TEST, Refused, dry_run_banner, identity,
                                 refuse_protected, require_dsn)

#: Parents before children, in the order the foreign keys require. `price_versions` is
#: absent on purpose and must stay absent.
COPY_ORDER = (
    "price_providers",
    "provider_items",
    "price_collection_runs",
    "price_observations",
    "material_unit_settings",
    "provider_item_unit_factors",
    "provider_item_labels",
)


def columns_of(db, table):
    return [r["column_name"] for r in db.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,)).fetchall()]


def json_columns(db, table):
    return {r["column_name"] for r in db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public'"
        " AND table_name=%s AND data_type IN ('json','jsonb')", (table,)).fetchall()}


def compare(source_rows, target_rows, shared):
    """Ids on both sides whose values differ. These are conflicts, never overwrites."""
    target_by_id = {row["id"]: row for row in target_rows}
    differing = []
    for row in source_rows:
        other = target_by_id.get(row["id"])
        if other is None:
            continue
        for column in shared:
            if column == "id":
                continue
            if row[column] != other.get(column):
                differing.append((row["id"], column, row[column], other.get(column)))
                break
    return differing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="source DSN; or set FINANCE_OPS_SOURCE_DSN")
    parser.add_argument("--target", help="target DSN; or set FINANCE_OPS_DSN")
    parser.add_argument("--target-database", default=CANONICAL_TEST,
                        help="the database the target DSN must reach (default: %s)"
                             % CANONICAL_TEST)
    parser.add_argument("--apply", action="store_true",
                        help="actually insert (default: dry run)")
    arguments = parser.parse_args(argv)

    source_dsn = require_dsn(arguments.source, "FINANCE_OPS_SOURCE_DSN", "source DSN")
    target_dsn = require_dsn(arguments.target, "FINANCE_OPS_DSN", "target DSN")
    refuse_protected(source_dsn, action="read from")
    refuse_protected(target_dsn, action="write to")

    print("### source (opened read-only) ###")
    source = psycopg.connect(source_dsn, row_factory=dict_row, autocommit=True)
    source.execute("SET default_transaction_read_only = on")
    identity(source)

    print()
    print("### target ###")
    target = psycopg.connect(target_dsn, row_factory=dict_row, autocommit=True)
    from scripts.ops._common import confirm_identity
    confirm_identity(target, arguments.target_database)

    print()
    dry_run_banner(arguments.apply)

    conflicts = []
    totals = {"inserted": 0, "present": 0, "conflicts": 0}

    print()
    print("### parents before children ###")
    try:
        for table in COPY_ORDER:
            source_columns = columns_of(source, table)
            target_columns = set(columns_of(target, table))
            if not source_columns:
                print("   %-30s absent in the source" % table)
                continue
            if not target_columns:
                raise Refused("%s does not exist in the target. Migrate it first:"
                              " python -m scripts.ops.migrate_canonical_test" % table)

            shared = [c for c in source_columns if c in target_columns]
            dropped = sorted(set(source_columns) - target_columns)
            rows = source.execute("SELECT * FROM " + table).fetchall()
            if not rows:
                print("   %-30s source has none" % table)
                continue

            existing = target.execute(
                "SELECT * FROM %s WHERE id = ANY(%%s)" % table,
                ([row["id"] for row in rows],)).fetchall()
            differing = compare(rows, existing, shared)
            if differing:
                conflicts.extend((table,) + item for item in differing)
                totals["conflicts"] += len(differing)

            if arguments.apply:
                if differing:
                    raise Refused(
                        "%d row(s) in %s exist in the target with different values. "
                        "Nothing was written for this table. See the conflict report below;"
                        " resolving it is a person's decision." % (len(differing), table))
                jsonb = json_columns(source, table)
                statement = ("INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (id) DO NOTHING"
                             % (table, ", ".join('"%s"' % c for c in shared),
                                ", ".join(["%s"] * len(shared))))
                inserted = 0
                with target.cursor() as cursor:
                    for row in rows:
                        values = tuple(
                            Jsonb(row[c]) if c in jsonb and row[c] is not None else row[c]
                            for c in shared)
                        cursor.execute(statement, values)
                        inserted += cursor.rowcount
                present = len(rows) - inserted
            else:
                inserted = len(rows) - len(existing)
                present = len(existing)

            totals["inserted"] += inserted
            totals["present"] += present
            note = ("  (columns only in source, not copied: %s)" % ", ".join(dropped)) if dropped else ""
            print("   %-30s source %5d  %s %5d  already present %5d  conflicts %d%s"
                  % (table, len(rows), "inserted" if arguments.apply else "would insert",
                     inserted, present, len(differing), note))
    finally:
        source.close()

    print()
    if conflicts:
        print("### CONFLICT REPORT -- nothing differing was overwritten ###")
        for table, row_id, column, mine, theirs in conflicts[:25]:
            print("   %s %s  column %s" % (table, row_id, column))
            print("      source: %r" % (str(mine)[:70],))
            print("      target: %r" % (str(theirs)[:70],))
        if len(conflicts) > 25:
            print("   ... and %d more" % (len(conflicts) - 25))
    else:
        print("   no conflicts: no id exists on both sides with different values.")

    print()
    print("   totals: %s %d, already present %d, conflicts %d"
          % ("inserted" if arguments.apply else "would insert",
             totals["inserted"], totals["present"], totals["conflicts"]))
    if not arguments.apply:
        print("   Nothing was written. Re-run with --apply, after a backup.")
    target.close()
    return 1 if conflicts and arguments.apply else 0


if __name__ == "__main__":
    raise SystemExit(main())
