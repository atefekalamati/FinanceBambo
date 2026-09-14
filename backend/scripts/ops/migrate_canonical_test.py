# -*- coding: utf-8 -*-
r"""Migrate a local Finance test database, and measure that nothing was lost.

    python -m scripts.ops.migrate_canonical_test --dsn postgresql://user@127.0.0.1:5432/bambo_canonical_test
    python -m scripts.ops.migrate_canonical_test --dsn ... --apply

Dry run by default: it prints the exact range of revisions that WOULD run and the counts it
would be checking, and writes nothing. `--apply` runs them.

WHAT IT IS ACTUALLY GUARDING

An Alembic chain is linear, so reaching a revision you want means running every revision in
between, including ones that touch data. This script does not decide whether that is
acceptable -- a person does -- but it makes the decision an informed one by printing the
range first, and it makes the outcome checkable by counting every business table and every
immutability trigger on both sides. If any count falls, it stops and says which.

It never disables a trigger and never downgrades. A downgrade is not a safer version of a
migration; it is a different operation with its own risks, and it is not this script's job.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from scripts.ops._common import (CANONICAL_TEST, Refused, confirm_identity, dry_run_banner,
                                 refuse_protected, require_dsn)

#: Everything holding business data. Counted on both sides; none may fall.
#: Listed rather than discovered, so a table added later is a deliberate edit here and not
#: a silent gap in what is being protected.
BUSINESS_TABLES = (
    "finance_resources", "estimate_lines", "estimate_revisions", "price_versions",
    "unit_conversions", "invoices", "invoice_lines", "finance_attachments",
    "finance_audit_events", "finance_import_batches", "finance_project_settings",
    "report_snapshots", "progress_overrides", "progress_snapshot_refs",
    "finance_mpp_rows", "finance_mpp_source_versions", "finance_task_resource_map",
    "msp_resources", "msp_resource_assignments", "price_observations", "provider_items",
)


def snapshot(dsn, expected):
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as db:
        confirm_identity(db, expected)
        try:
            version = db.execute(
                "SELECT version_num FROM finance_alembic_version").fetchone()["version_num"]
        except psycopg.Error:
            version = None
        counts = {}
        for table in BUSINESS_TABLES:
            if db.execute("SELECT to_regclass(%s) AS r", ("public." + table,)).fetchone()["r"]:
                counts[table] = db.execute("SELECT count(*) AS n FROM " + table).fetchone()["n"]
        triggers = [r["t"] for r in db.execute(
            "SELECT c.relname || '.' || t.tgname AS t FROM pg_trigger t"
            " JOIN pg_class c ON c.oid = t.tgrelid"
            " WHERE NOT t.tgisinternal ORDER BY 1").fetchall()]
    return version, counts, triggers


def chain():
    """Every revision on disk, in order, read from the files themselves."""
    import re

    versions = BACKEND_ROOT / "alembic" / "versions"
    found = {}
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        # Both quote styles. The early revisions are written with single quotes and the
        # later ones with double; a pattern that read only one of them reported four extra
        # heads, which would have made the check at the end -- is the database at head --
        # accept almost anything.
        revision = re.search(r"""^revision\s*=\s*['"]([^'"]+)['"]""", text, re.M)
        down = re.search(r"""^down_revision\s*=\s*(?:['"]([^'"]+)['"]|None)""", text, re.M)
        if revision:
            parent = down.group(1) if down and down.group(1) else None
            found[revision.group(1)] = (path.stem, parent)
    return found


def pending(current, revisions):
    """The revisions between `current` and head, in the order they would run."""
    order = []
    seen = set()

    def walk(name):
        if name in seen or name not in revisions:
            return
        seen.add(name)
        walk(revisions[name][1])
        order.append(name)

    for name in revisions:
        walk(name)
    if current is None:
        return order
    if current not in order:
        return []
    return order[order.index(current) + 1:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="target DSN; or set FINANCE_OPS_DSN")
    parser.add_argument("--database", default=CANONICAL_TEST)
    parser.add_argument("--apply", action="store_true",
                        help="actually run the migrations (default: dry run)")
    arguments = parser.parse_args(argv)

    dsn = require_dsn(arguments.dsn, "FINANCE_OPS_DSN", "target DSN")
    refuse_protected(dsn, action="migrate")

    print("### before ###")
    version_before, before, triggers_before = snapshot(dsn, arguments.database)
    revisions = chain()
    parents = {revisions[name][1] for name in revisions}
    head = sorted(name for name in revisions if name not in parents)
    to_run = pending(version_before, revisions)
    print("   alembic       : %s" % (version_before or "(none)"))
    print("   head on disk  : %s" % (", ".join(sorted(head)) or "(unknown)"))
    print("   business rows : %d across %d tables" % (sum(before.values()), len(before)))
    print("   triggers      : %d" % len(triggers_before))

    print()
    print("### the exact range that would run ###")
    if not to_run:
        print("   nothing pending; the database is already at head.")
        return 0
    for name in to_run:
        print("   %s  (%s)" % (name, revisions[name][0]))

    print()
    if not dry_run_banner(arguments.apply):
        print("   Re-run with --apply to migrate. Take a backup first:")
        print("     python -m scripts.ops.backup_canonical_test --dsn <dsn>")
        return 0

    print()
    print("### alembic upgrade head ###")
    finished = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                              cwd=str(BACKEND_ROOT),
                              env=dict(os.environ, FINANCE_MIGRATION_DSN=dsn),
                              capture_output=True, text=True)
    print("   exit code: %d" % finished.returncode)
    for line in finished.stderr.splitlines():
        if "Running upgrade" in line:
            print("   %s" % line.split("] ", 1)[-1][:100])
    if finished.returncode != 0:
        print(finished.stderr[-1500:])
        raise Refused("the migration failed. Restore from the backup if the database "
                      "is in an unexpected state.")

    print()
    print("### after ###")
    version_after, after, triggers_after = snapshot(dsn, arguments.database)
    print("   alembic  : %s" % version_after)
    print("   triggers : %d" % len(triggers_after))

    print()
    print("### every business table, before -> after ###")
    lost = []
    for table in sorted(before):
        now = after.get(table)
        flag = ""
        if now is None:
            flag, _ = "  TABLE GONE", lost.append(table)
        elif now < before[table]:
            flag, _ = "  ROWS LOST", lost.append(table)
        print("   %-32s %8d -> %-8s%s" % (table, before[table],
                                          "absent" if now is None else now, flag))

    missing = sorted(set(triggers_before) - set(triggers_after))
    print()
    print("   triggers before %d, after %d, missing: %s"
          % (len(triggers_before), len(triggers_after), ", ".join(missing) or "none"))

    if lost or missing:
        raise Refused("rows or triggers were lost: %s %s"
                      % (", ".join(lost), ", ".join(missing)))
    if version_after not in head:
        raise Refused("the database is at %r but head on disk is %s."
                      % (version_after, head))
    print()
    print("   NOTHING WAS REMOVED. Every business table is at or above its previous count,"
          " all %d triggers are present, and the database is at head." % len(triggers_after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
