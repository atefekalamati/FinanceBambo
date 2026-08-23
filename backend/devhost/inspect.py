"""Look at what is actually in the development database.

    python -m devhost.inspect                 every finance table with its row count
    python -m devhost.inspect estimate_lines  the rows of one table
    python -m devhost.inspect --changes       only what was entered through the UI
    python -m devhost.inspect --export        one CSV per table, openable in Excel

PostgreSQL keeps each table in a binary file under its data directory, so those files
cannot be read directly. This asks the server instead, which is the only way to see the
data as rows.

Read-only: it issues nothing but SELECT.
"""

import argparse
import csv
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from . import seed
from .environment import MissingConfiguration, database_url, redacted

# Every finance table, with the column that says when the row appeared.
TABLES = (
    ("finance_project_settings", "created_at"),
    ("finance_resources", "created_at"),
    ("estimate_lines", "created_at"),
    ("estimate_revisions", "created_at"),
    ("price_versions", "created_at"),
    ("unit_conversions", "created_at"),
    ("progress_snapshot_refs", "imported_at"),
    ("progress_overrides", "created_at"),
    ("invoices", "created_at"),
    ("invoice_lines", "created_at"),
    ("finance_attachments", "uploaded_at"),
    ("extraction_drafts", "created_at"),
    ("report_snapshots", "issued_at"),
    ("finance_audit_events", "occurred_at"),
)

# A fixture is identified by its id, not by its `source` column: `source` is part of the
# data being mirrored and a seeded row can legitimately read "manual_entry". Rows created
# through the API get a generated UUID, which never lands in these families.
FIXTURE_PREFIXES = tuple(f"{prefix}-%" for prefix in seed.FIXTURE_ID_PREFIXES)


def connect():
    try:
        return psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=10)
    except MissingConfiguration as error:
        sys.exit(str(error))


def overview(connection) -> None:
    print(f"database: {redacted(database_url())}\n")
    print(f"  {'table':28} {'rows':>6}   newest row")
    print(f"  {'-' * 28} {'-' * 6}   {'-' * 19}")
    for table, stamp in TABLES:
        row = connection.execute(
            f"SELECT count(*) AS n, max({stamp}) AS newest FROM {table}").fetchone()
        newest = row["newest"].strftime("%Y-%m-%d %H:%M:%S") if row["newest"] else "-"
        print(f"  {table:28} {row['n']:>6}   {newest}")
    print("\n  python -m devhost.inspect <table>     rows of one table")
    print("  python -m devhost.inspect --changes   only what the UI created")
    print("  python -m devhost.inspect --export    one CSV per table")


def show(connection, table: str, limit: int) -> None:
    known = {name for name, _ in TABLES}
    if table not in known:
        sys.exit(f"unknown table: {table}\nknown tables: {', '.join(sorted(known))}")
    stamp = dict(TABLES)[table]
    rows = connection.execute(
        f"SELECT * FROM {table} ORDER BY {stamp} DESC LIMIT %s", (limit,)).fetchall()
    if not rows:
        print(f"{table}: no rows")
        return
    # Columns every finance table carries; hiding them keeps the output readable.
    hidden = {"organization_id", "project_id"}
    columns = [c for c in rows[0] if c not in hidden]
    print(f"{table}  ({len(rows)} row(s), newest first)\n")
    for index, row in enumerate(rows, 1):
        print(f"  [{index}]")
        for column in columns:
            value = row[column]
            if value is not None and value != "":
                print(f"      {column:28} {value}")
        print()


def changes(connection) -> None:
    """Rows that came through the API rather than the seed."""
    print("entered through the UI or API:\n")
    found = False
    lines = connection.execute("""
        SELECT l.activity_external_id, l.original_quantity, l.original_unit_price_irr,
               r.code AS resource, l.created_at
        FROM estimate_lines l JOIN finance_resources r ON r.id = l.resource_id
        WHERE l.id::text NOT LIKE ALL(%s) AND l.deleted_at IS NULL
        ORDER BY l.created_at DESC""", (list(FIXTURE_PREFIXES),)).fetchall()
    for row in lines:
        found = True
        amount = row["original_quantity"] or row["original_unit_price_irr"]
        print(f"  estimate_lines    {row['activity_external_id']:9} {row['resource']:12} "
              f"{amount}   {row['created_at']:%Y-%m-%d %H:%M}")

    for table in ("finance_resources", "price_versions", "invoices", "finance_project_settings"):
        rows = connection.execute(
            f"SELECT id, created_at FROM {table} WHERE id::text NOT LIKE ALL(%s) "
            "ORDER BY created_at DESC LIMIT 10", (list(FIXTURE_PREFIXES),)).fetchall()
        for row in rows:
            found = True
            print(f"  {table:18}{str(row['id'])[:36]}   {row['created_at']:%Y-%m-%d %H:%M}")

    events = connection.execute("""
        SELECT action, entity_type, occurred_at FROM finance_audit_events
        WHERE id::text NOT LIKE ALL(%s) ORDER BY occurred_at DESC LIMIT 25""",
        (list(FIXTURE_PREFIXES),)).fetchall()
    for row in events:
        found = True
        print(f"  audit             {row['action']:30} {row['entity_type']:24} "
              f"{row['occurred_at']:%Y-%m-%d %H:%M}")
    if not found:
        print("  nothing yet - the database holds only seed data")


def export(connection, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for table, stamp in TABLES:
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY {stamp}").fetchall()
        path = directory / f"{table}.csv"
        # utf-8-sig so Excel opens the Persian text without mangling it.
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            if rows:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            else:
                handle.write("")
        print(f"  {path}  ({len(rows)} rows)")
    print(f"\nopen any of these in Excel, or read them in a text editor.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="devhost.inspect", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("table", nargs="?", help="show the rows of one table")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--changes", action="store_true", help="only rows the UI created")
    parser.add_argument("--export", action="store_true", help="write one CSV per table")
    parser.add_argument("--into", default=str(Path(__file__).resolve().parent / ".export"))
    args = parser.parse_args()

    with connect() as connection:
        if args.export:
            export(connection, Path(args.into))
        elif args.changes:
            changes(connection)
        elif args.table:
            show(connection, args.table, args.limit)
        else:
            overview(connection)


if __name__ == "__main__":
    main()
