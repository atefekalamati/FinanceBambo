# -*- coding: utf-8 -*-
"""Fill the typed specification columns from metadata, using the declared parser.

WHY THIS IS NOT IN THE MIGRATION

The extraction is per-category and per-column, it refuses text where a number is required,
and it reads a unit out of the cell when the cell gives one. That is tested Python in
`domain/material_specs.py`. Rewriting it as SQL regex inside a migration would be a second
copy of the rules, and the two would drift -- the first time a sheet gained a column, one
of them would learn about it.

WHAT IT WILL NOT DO

It never overwrites. A column that already holds a value is left alone and, when the sheet
now disagrees, the disagreement is recorded in `spec_conflicts` for a person to look at.
Yesterday's 22 becoming today's 220 is a parser or a source having gone wrong far more
often than a product having changed weight tenfold, and applying it silently is how the
wrong number gets into a report.

    NULL + a value            -> written
    the same value            -> nothing
    a DIFFERENT value         -> not written; recorded as a conflict

IDEMPOTENT

Running it twice writes nothing the second time: every column it would set is already set,
and every conflict it would record is already recorded.

    python -m scripts.ops.backfill_material_specs --dsn ... [--apply]

Without `--apply` it reports and writes nothing.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from app.finance.domain.material_specs import (FROM_METADATA, SPEC_COLUMNS,
                                               conflicts_with, extract_specs)




def local_only(dsn):
    """Refuse anything that is not a loopback host. This writes financial reference data."""
    from psycopg.conninfo import conninfo_to_dict
    host = (conninfo_to_dict(dsn).get("host") or "").strip()
    if host not in ("127.0.0.1", "localhost", "::1", ""):
        raise SystemExit("STOP: refusing a non-loopback host %r" % host)
    name = (conninfo_to_dict(dsn).get("dbname") or "")
    if "local" in name or "prod" in name:
        raise SystemExit("STOP: refusing database %r" % name)
    return dsn


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--apply", action="store_true",
                        help="write; without it nothing is changed")
    args = parser.parse_args(argv)
    dsn = local_only(args.dsn)

    written = conflicted = unchanged = skipped = 0
    per_column = {}
    conflict_examples = []

    with psycopg.connect(dsn, row_factory=dict_row) as db:
        print("database:", db.execute("select current_database()").fetchone()["current_database"])
        rows = db.execute(
            "SELECT id, category, metadata, " + ", ".join(SPEC_COLUMNS)
            + " FROM provider_items ORDER BY id").fetchall()
        print("listings:", len(rows))

        for row in rows:
            metadata = row["metadata"] or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            values, _leftovers = extract_specs(row["category"], metadata)
            if not values:
                skipped += 1
                continue

            existing = {c: row.get(c) for c in SPEC_COLUMNS}
            disagreements = conflicts_with(existing, values)
            # Only the columns that are genuinely empty are written. The rest either agree
            # already or are in `disagreements`, and neither is a reason to overwrite.
            writable = {c: v for c, v in values.items()
                        if c in SPEC_COLUMNS
                        and (existing.get(c) is None or str(existing.get(c)).strip() == "")}

            if not writable and not disagreements:
                unchanged += 1
                continue

            if disagreements:
                conflicted += 1
                if len(conflict_examples) < 5:
                    conflict_examples.append((str(row["id"])[:8], disagreements))

            if args.apply and (writable or disagreements):
                sets, params = [], []
                for column, value in writable.items():
                    sets.append("%s = %%s" % column)
                    params.append(value)
                    per_column[column] = per_column.get(column, 0) + 1
                if writable:
                    sets.append("spec_source = %s")
                    params.append(FROM_METADATA)
                if disagreements:
                    sets.append("spec_conflicts = %s")
                    params.append(json.dumps(disagreements, ensure_ascii=False))
                params.append(row["id"])
                db.execute("UPDATE provider_items SET " + ", ".join(sets)
                           + " WHERE id = %s", params)
            elif writable:
                for column in writable:
                    per_column[column] = per_column.get(column, 0) + 1
            if writable:
                written += 1

        if args.apply:
            db.commit()

    print()
    print("  listings the sheet says nothing about :", skipped)
    print("  listings already complete             :", unchanged)
    print("  listings with columns to write        :", written)
    print("  listings whose sheet now DISAGREES    :", conflicted)
    print()
    print("  columns %s:" % ("written" if args.apply else "that WOULD be written"))
    for column in sorted(per_column):
        print("     %-22s %s" % (column, per_column[column]))
    if conflict_examples:
        print()
        print("  conflicts (recorded, never applied):")
        for item_id, found in conflict_examples:
            print("     %s %s" % (item_id, json.dumps(found, ensure_ascii=False)[:120]))
    if not args.apply:
        print()
        print("  DRY RUN -- nothing was written. Pass --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
