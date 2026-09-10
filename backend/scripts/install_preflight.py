# -*- coding: utf-8 -*-
"""Answer "can Finance be installed here?" before anything is applied.

THE PROBLEM

Finance owns its own schema and Alembic owns Finance's revisions -- but revision 0009
declares a real foreign key into a table Core owns:

    finance_task_resource_map.task_id  ->  msp_tasks (id)  ON DELETE CASCADE

0009 checks for that table itself and raises a clear error when it is missing. The check is
right; its TIMING is the problem for an operator. `alembic upgrade head` runs 0001 through
0008 first, so the missing prerequisite is discovered eight revisions in, after several
minutes of DDL on a production-sized database. The whole upgrade is one transaction and
rolls back cleanly -- nothing is left half-migrated -- but the operator still learns about a
five-second precondition the slow way, and a rollback of a large upgrade is not free.

So this asks the same questions first, reads nothing but the catalogue, and says what to do.

WHAT IT IS NOT

It is not an installer for Core. This repository contains no authoritative Core migration:
`scripts/demo/core_mirror.sql` is a GENERATED DEMO MIRROR whose own header says it is never
applied to the Core database, and using it to create production tables would put Finance in
charge of a schema another team owns and versions. When `msp_tasks` is missing, the answer
is to ask the host team for Core's own migration -- not to create it from here.

READ ONLY

Every statement runs inside a read-only transaction, so this is safe to point at any
database, including a live one. It changes nothing and never writes a migration ledger.

Run:
    python -m scripts.install_preflight --dsn postgresql://.../<database>
Exit codes:
    0  every prerequisite is present -- `alembic upgrade head` may run
    1  something is missing; the report names it and the next step
    2  the database could not be reached or inspected
"""

import argparse
import re
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

BACKEND_ROOT = Path(__file__).resolve().parent.parent
VERSIONS = BACKEND_ROOT / "alembic" / "versions"

#: The Core objects a Finance migration genuinely depends on, and what depends on them.
#: Taken from the DDL, not from prose: 0007 creates `msp_resources` and
#: `msp_resource_assignments` itself, so those are Finance's own and are not listed here.
CORE_REQUIREMENTS = (
    ("msp_tasks", "0009 declares FOREIGN KEY (task_id) REFERENCES msp_tasks (id)"),
    ("msp_snapshots", "0009's scope trigger joins msp_snapshots to find a task's project"),
)

#: `finance_task_resource_map.task_id` is `bigint`, so the referenced column must be a type
#: a bigint key can point at. A mismatch fails at CREATE TABLE with a less obvious message.
TASK_ID_TYPES = ("bigint", "integer", "smallint")


def repository_head():
    """The head revision this checkout would migrate to, read from the files themselves."""
    revisions, downs = {}, set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(?:None|["\']([^"\']+))', text, re.M)
        if found:
            revisions[found.group(1)] = path.name
            if down and down.group(1):
                downs.add(down.group(1))
    heads = sorted(set(revisions) - downs)
    return heads, len(revisions)


class Report:
    def __init__(self):
        self.lines = []
        self.blockers = []

    def ok(self, label, detail=""):
        self.lines.append(("  OK      ", label, detail))

    def note(self, label, detail=""):
        self.lines.append(("  --      ", label, detail))

    def missing(self, label, detail, next_step):
        self.lines.append(("  MISSING ", label, detail))
        self.blockers.append((label, next_step))

    def render(self):
        for mark, label, detail in self.lines:
            print("%s%-34s %s" % (mark, label, detail))
        if not self.blockers:
            print("\n  Every prerequisite is present. `alembic upgrade head` may run.")
            return 0
        print("\n  NOT READY -- %d prerequisite(s) missing:" % len(self.blockers))
        for label, next_step in self.blockers:
            print("    * %s" % label)
            print("      next step: %s" % next_step)
        return 1


def inspect(connection, report):
    row = connection.execute(
        "SELECT current_database() AS name, current_user AS role, version() AS server"
    ).fetchone()
    report.note("database", row["name"])
    report.note("connected as", row["role"])
    report.note("server", row["server"].split(",")[0])

    heads, count = repository_head()
    report.note("finance revisions on disk", "%d, head %s" % (count, ", ".join(heads) or "none"))
    if len(heads) != 1:
        report.missing(
            "a single migration head",
            "found %d: %s" % (len(heads), ", ".join(heads)),
            "resolve the branch in alembic/versions before installing")

    ledger = connection.execute(
        "SELECT to_regclass('finance_alembic_version') AS present").fetchone()["present"]
    if ledger is None:
        report.note("finance ledger", "absent -- this would be a fresh installation")
    else:
        current = connection.execute(
            "SELECT version_num FROM finance_alembic_version").fetchall()
        stamped = ", ".join(entry["version_num"] for entry in current) or "empty"
        report.note("finance ledger", stamped)
        if heads and stamped == heads[0]:
            report.note("finance schema", "already at head -- upgrade would be a no-op")

    for table, why in CORE_REQUIREMENTS:
        present = connection.execute(
            "SELECT to_regclass(%s) AS present", (table,)).fetchone()["present"]
        if present is None:
            report.missing(
                "Core table %s" % table, why,
                "install Core's own schema into this database first -- Finance has no "
                "migration for it and must not create one. Ask the host team for the Core "
                "migration package (or point Finance at the shared BAMBO database where "
                "Core already maintains it).")
            continue
        report.ok("Core table %s" % table, why)

        if table == "msp_tasks":
            column = connection.execute("""
                SELECT format_type(a.atttypid, a.atttypmod) AS type
                  FROM pg_attribute a
                 WHERE a.attrelid = 'msp_tasks'::regclass
                   AND a.attname = 'id' AND a.attnum > 0 AND NOT a.attisdropped
            """).fetchone()
            if column is None:
                report.missing(
                    "msp_tasks.id", "the column the foreign key points at does not exist",
                    "the Core schema in this database is not the one Finance expects; "
                    "confirm the Core revision with the host team")
            elif column["type"] not in TASK_ID_TYPES:
                report.missing(
                    "msp_tasks.id type", "is %s; finance_task_resource_map.task_id is bigint"
                    % column["type"],
                    "confirm the Core revision -- a foreign key cannot span these types")
            else:
                report.ok("msp_tasks.id type", column["type"])

            granted = connection.execute(
                "SELECT has_table_privilege(current_user, 'msp_tasks', 'REFERENCES') AS may"
            ).fetchone()["may"]
            if granted:
                report.ok("REFERENCES on msp_tasks", "granted to %s" % row["role"])
            else:
                report.missing(
                    "REFERENCES on msp_tasks",
                    "%s may not create a foreign key into it" % row["role"],
                    "GRANT REFERENCES ON msp_tasks TO %s;  (an operator step 0009 "
                    "cannot perform for itself)" % row["role"])

    # 0009 also refuses to run against data it would have to merge. Checked here so the
    # operator can clean it up beforehand rather than mid-upgrade.
    resources = connection.execute(
        "SELECT to_regclass('finance_resources') AS present").fetchone()["present"]
    if resources is not None:
        duplicated = connection.execute("""
            SELECT count(*) AS n FROM (
                SELECT 1 FROM finance_resources
                 WHERE external_resource_id IS NOT NULL AND deleted_at IS NULL
                 GROUP BY organization_id, project_id, external_resource_id
                HAVING count(*) > 1) AS duplicated
        """).fetchone()["n"]
        if duplicated:
            report.missing(
                "duplicated finance_resources identities",
                "%d group(s) share (organization_id, project_id, external_resource_id)"
                % duplicated,
                "resolve them first -- 0009 refuses to merge or delete rows itself")
        else:
            report.ok("finance_resources identities", "no duplicates among live rows")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", required=True,
                        help="target database; inspected read-only, never modified")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parts = conninfo_to_dict(arguments.dsn)
    print("\n  FINANCE INSTALLATION PREFLIGHT -- read only, nothing is applied\n")
    print("  %-34s %s/%s" % ("target", parts.get("host") or "local socket",
                             parts.get("dbname") or "?"))

    report = Report()
    try:
        with psycopg.connect(arguments.dsn, row_factory=dict_row, connect_timeout=10) as db:
            db.execute("SET TRANSACTION READ ONLY")
            inspect(db, report)
    except psycopg.Error as error:
        print("\n  could not inspect the database: %s" % str(error).strip().splitlines()[0])
        return 2
    return report.render()


if __name__ == "__main__":
    sys.exit(main())
