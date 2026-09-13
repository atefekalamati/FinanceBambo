# -*- coding: utf-8 -*-
"""Bring a migration ledger back in step with a schema somebody already applied.

WHEN THIS IS THE RIGHT TOOL, AND WHEN IT IS NOT

`finance_alembic_version` records which revision a database is at. Occasionally the schema
moves without it: a revision's DDL is applied by hand during an incident, a restore brings
back a newer dump under an older ledger row, an operator runs the SQL and not the migration.
The database is then correct and unmigratable -- `alembic upgrade` replays revisions whose
objects already exist and fails.

`alembic stamp` fixes the symptom by asserting the answer. That is exactly what must not
happen to a database holding financial records: a stamp is a claim that the schema matches,
made without looking.

This looks. It compares the objects the intervening revisions touch against a reference
installation that reached the head the honest way, refuses on any difference, and changes
one row of metadata only when equivalence is proven. It never runs DDL and never touches a
business table.

WHY IT IS SEPARATE FROM `reconcile_release_schema`

That script deliberately refuses anything but an isolated `bambo_release_*` database, and
that restriction is not widened here or anywhere else -- it is what makes it safe to run
casually during release rehearsals. This one is the reviewed maintenance procedure for a
database that matters, and it earns that by asking for more: an explicit echo of the target
database's name before it will write, a scan for data migrations it cannot verify, and a
receipt of what it did.

WHAT IT REFUSES

  * a revision in the range that transforms DATA. Comparing schemas proves nothing about a
    backfill that was skipped, and there is no honest way to infer one after the fact;
  * a reference that is not at the intended head;
  * a target whose recorded revision is not what the operator said it was;
  * any difference at all in a column, constraint, index, trigger or trigger function body
    of any table those revisions touch;
  * a business table whose contents changed while it held the lock.

Run:
    python -m scripts.reconcile_ledger --reference-dsn ... --target-dsn ...
    python -m scripts.reconcile_ledger --reference-dsn ... --target-dsn ... \
        --apply --confirm-database <exact database name>

Exit codes: 0 proven (and applied if asked), 1 refused, 2 could not inspect.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# The catalogue queries this reuses rather than restates. One definition of "the same
# column" for both tools, so a difference one of them would catch cannot slip past the
# other.
from scripts.reconcile_release_schema import QUERIES, fingerprints  # noqa: E402

VERSIONS = BACKEND_ROOT / "alembic" / "versions"
LEDGER = "finance_alembic_version"

#: Anything that moves rows. A revision containing one of these did work no schema
#: comparison can vouch for.
#:
#: The obvious spelling of this -- `\b(INSERT\s+INTO|UPDATE\s+[a-z_]|...)\b` -- silently
#: missed `UPDATE estimate_lines SET ...`, because the trailing `\b` has to fall between a
#: word character and a non-word one and the table name continues past it. A detector that
#: misses an UPDATE is the one bug this tool cannot afford, so each verb now carries the
#: shape of the statement it belongs to and stops before the identifier.
#: The UPDATE arm also allows an alias between the table and SET. `UPDATE invoices AS
#: target SET ...` is how a backfill that joins to a subquery is written, which is how
#: nearly every backfill is written, and without the optional group it did not match at
#: all -- a revision whose only data statement took that shape read as pure DDL. The
#: negative lookahead keeps SET itself from being taken for the alias.
DATA_VERBS = re.compile(
    r"\bINSERT\s+INTO\b"
    r"|\bUPDATE\s+(?:ONLY\s+)?[a-z_][\w.\"]*(?:\s+(?:AS\s+)?(?!SET\b)[a-z_]\w*)?\s+SET\b"
    r"|\bDELETE\s+FROM\b"
    r"|\bCOPY\s+[a-z_][\w.\"]*\s+FROM\b", re.I)

#: Objects a revision names in DDL. Deliberately generous: comparing a table the revision
#: merely mentions costs a query, missing one it altered costs correctness.
DDL_TABLE = re.compile(
    r"\b(?:ALTER\s+TABLE(?:\s+IF\s+EXISTS)?|CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?|"
    r"CREATE\s+(?:UNIQUE\s+)?INDEX(?:\s+CONCURRENTLY)?(?:\s+IF\s+NOT\s+EXISTS)?\s+\w+\s+ON|"
    r"CREATE\s+(?:CONSTRAINT\s+)?TRIGGER\s+\w+\s+(?:AFTER|BEFORE|INSTEAD\s+OF)[^O]*ON)\s+"
    r"(?:ONLY\s+)?([a-z_][a-z0-9_]*)", re.I)


def revisions():
    """Every revision on disk as {revision: (down_revision, filename, source)}."""
    found = {}
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        this = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(?:None|["\']([^"\']+))', text, re.M)
        if this:
            found[this.group(1)] = (down.group(1) if down else None, path.name, text)
    return found


def head(found):
    downs = {down for down, _name, _text in found.values() if down}
    heads = sorted(set(found) - downs)
    return heads


def chain(found, start, target):
    """The revisions strictly after `start` up to and including `target`, in order."""
    walk, node = [], target
    while node is not None and node != start:
        if node not in found:
            raise SystemExit("revision %s is not on disk" % node)
        walk.append(node)
        node = found[node][0]
    if node != start:
        raise SystemExit("%s is not an ancestor of %s" % (start, target))
    return list(reversed(walk))


def upgrade_sql(text):
    """Only the upgrade half: a downgrade's DML is not applied by an upgrade."""
    if "UPGRADE_SQL" in text and "DOWNGRADE_SQL" in text:
        return text.split("UPGRADE_SQL", 1)[1].split("DOWNGRADE_SQL", 1)[0]
    return text


def objects_touched(found, walk):
    """Tables the revisions in `walk` create or alter, and any data migrations in them."""
    tables, data = set(), []
    for revision in walk:
        _down, name, text = found[revision]
        body = upgrade_sql(text)
        tables.update(match.lower() for match in DDL_TABLE.findall(body))
        moved = sorted({" ".join(m.split()).upper() for m in DATA_VERBS.findall(body)})
        if moved:
            data.append((revision, name, moved))
    return sorted(tables), data


def manifest(connection, tables):
    return {table: {kind: connection.execute(query, ("public." + table,)).fetchall()
                    for kind, query in QUERIES.items()} for table in tables}


def ledger_of(connection):
    rows = connection.execute("SELECT version_num FROM %s" % LEDGER).fetchall()
    return [row[0] for row in rows]


def reconcile(reference_dsn, target_dsn, apply, confirm_database, expect_from):
    found = revisions()
    heads = head(found)
    if len(heads) != 1:
        print("REFUSED: the repository has %d heads (%s); there is no single intended "
              "revision to reconcile to." % (len(heads), ", ".join(heads)))
        return 1
    intended = heads[0]

    receipt = {"tool": "reconcile_ledger", "intendedRevision": intended,
               "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

    with psycopg.connect(reference_dsn) as reference, psycopg.connect(target_dsn) as target:
        reference.execute("SET TRANSACTION READ ONLY")
        identity = target.execute(
            "SELECT current_database(), current_schema(), current_user").fetchone()
        receipt["target"] = {"database": identity[0], "schema": identity[1],
                             "role": identity[2],
                             "host": conninfo_to_dict(target_dsn).get("host") or "local socket"}
        receipt["reference"] = {
            "database": reference.execute("SELECT current_database()").fetchone()[0]}
        print("  target      %s / schema %s as %s"
              % (identity[0], identity[1], identity[2]))
        print("  reference   %s" % receipt["reference"]["database"])

        if conninfo_to_dict(reference_dsn) == conninfo_to_dict(target_dsn):
            print("REFUSED: the reference and the target are the same database.")
            return 1

        reference_at = ledger_of(reference)
        if reference_at != [intended]:
            print("REFUSED: the reference is at %s, not the intended head %s. A reference "
                  "that did not reach head the ordinary way proves nothing."
                  % (", ".join(reference_at) or "nothing", intended))
            return 1

        # FOR UPDATE is the lock on the ledger row: a second reconciliation or a migration
        # holding it will wait here rather than race this one.
        recorded = [row[0] for row in
                    target.execute("SELECT version_num FROM %s FOR UPDATE" % LEDGER).fetchall()]
        receipt["recordedRevision"] = recorded
        print("  recorded    %s" % (", ".join(recorded) or "nothing"))
        print("  intended    %s" % intended)

        if recorded == [intended]:
            receipt["outcome"] = "already-in-step"
            print("\n  Already in step. Nothing to reconcile; running this again is safe.")
            print(json.dumps(receipt, ensure_ascii=False))
            return 0
        if len(recorded) != 1:
            print("REFUSED: the ledger holds %d rows; a branched or empty ledger is not "
                  "something this can resolve." % len(recorded))
            return 1
        if expect_from and recorded[0] != expect_from:
            print("REFUSED: the ledger says %s, and --expect-from said %s."
                  % (recorded[0], expect_from))
            return 1

        walk = chain(found, recorded[0], intended)
        tables, data = objects_touched(found, walk)
        receipt["revisions"] = [{"revision": r, "file": found[r][1]} for r in walk]
        receipt["tablesCompared"] = tables
        print("\n  revisions between them: %s" % ", ".join(walk))
        for revision in walk:
            print("      %s  %s" % (revision, found[revision][1]))
        print("  tables those revisions touch: %s" % ", ".join(tables))

        if data:
            receipt["outcome"] = "refused-data-migration"
            print("\nREFUSED: a revision in this range moves data, and comparing schemas "
                  "says nothing about whether that ran:")
            for revision, name, verbs in data:
                print("      %s (%s): %s" % (revision, name, ", ".join(verbs)))
            print("  Reconcile these by hand, with evidence about the rows, or replay the "
                  "revision on a copy and compare the DATA as well.")
            print(json.dumps(receipt, ensure_ascii=False))
            return 1
        print("  data migrations in that range: none -- every revision is pure DDL")

        missing = [t for t in tables
                   if target.execute("SELECT to_regclass(%s)", ("public." + t,)).fetchone()[0]
                   is None]
        if missing:
            receipt["outcome"] = "refused-missing-table"
            print("\nREFUSED: the target does not have %s. The schema is not ahead of its "
                  "ledger; it is behind, and `alembic upgrade head` is the right tool."
                  % ", ".join(missing))
            print(json.dumps(receipt, ensure_ascii=False))
            return 1

        # Held until COMMIT so nothing alters these tables between the comparison and the
        # metadata write. The same mode revision 0009 uses.
        target.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
            sql.SQL(",").join(sql.Identifier("public", name) for name in tables)))

        expected, actual = manifest(reference, tables), manifest(target, tables)
        differences = {table: {kind: {"expected": expected[table][kind],
                                      "actual": actual[table][kind]}
                               for kind in QUERIES if expected[table][kind] != actual[table][kind]}
                       for table in tables if expected[table] != actual[table]}
        if differences:
            receipt["outcome"] = "refused-schema-difference"
            receipt["differingTables"] = sorted(differences)
            print("\nREFUSED: the schema is not equivalent. Differences in %s:"
                  % ", ".join(sorted(differences)))
            print(json.dumps(differences, default=str, ensure_ascii=True))
            print(json.dumps(receipt, ensure_ascii=False))
            return 1
        checks = sorted(QUERIES)
        print("  compared per table: %s -- all identical" % ", ".join(checks))
        receipt["compared"] = checks

        before = fingerprints(target)
        receipt["businessTablesFingerprinted"] = len(before)
        print("  business tables fingerprinted: %d" % len(before))

        if not apply:
            receipt["outcome"] = "dry-run-proven"
            print("\n  DRY RUN. Equivalence is proven; nothing was changed.")
            print("  To apply, add:  --apply --confirm-database %s" % identity[0])
            print("  The metadata change would be exactly:")
            print("      UPDATE %s SET version_num='%s' WHERE version_num='%s';"
                  % (LEDGER, intended, recorded[0]))
            print(json.dumps(receipt, ensure_ascii=False))
            return 0

        if confirm_database != identity[0]:
            receipt["outcome"] = "refused-unconfirmed-target"
            print("\nREFUSED: --confirm-database said %r and the connection is to %r. The "
                  "echo exists so a maintenance write cannot land on the wrong database."
                  % (confirm_database, identity[0]))
            print(json.dumps(receipt, ensure_ascii=False))
            return 1

        target.execute("UPDATE %s SET version_num=%%s WHERE version_num=%%s" % LEDGER,
                       (intended, recorded[0]))
        if fingerprints(target) != before:
            receipt["outcome"] = "refused-contents-changed"
            print("\nREFUSED: a business table changed during the run; rolling back.")
            print(json.dumps(receipt, ensure_ascii=False))
            raise SystemExit(1)
        receipt["outcome"] = "applied"
        receipt["metadataChange"] = {"table": LEDGER, "from": recorded[0], "to": intended}
        print("\n  APPLIED. %s: %s -> %s. No DDL ran and no business row was touched."
              % (LEDGER, recorded[0], intended))
        print(json.dumps(receipt, ensure_ascii=False))
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference-dsn", required=True,
                        help="a database that reached the intended head by migrating")
    parser.add_argument("--target-dsn", required=True, help="the database whose ledger lags")
    parser.add_argument("--expect-from", default=None,
                        help="the revision the operator believes is recorded; refuses if not")
    parser.add_argument("--apply", action="store_true",
                        help="write the metadata change (requires --confirm-database)")
    parser.add_argument("--confirm-database", default=None,
                        help="the target database's exact name, echoed back")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("\n  MIGRATION LEDGER RECONCILIATION -- read only unless --apply is given\n")
    if arguments.apply and not arguments.confirm_database:
        print("REFUSED: --apply needs --confirm-database <name>.")
        return 1
    try:
        return reconcile(arguments.reference_dsn, arguments.target_dsn, arguments.apply,
                         arguments.confirm_database, arguments.expect_from)
    except psycopg.Error as error:
        print("\n  could not inspect: %s" % str(error).strip().splitlines()[0])
        return 2


if __name__ == "__main__":
    sys.exit(main())
