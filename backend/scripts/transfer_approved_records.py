# -*- coding: utf-8 -*-
"""Move a NAMED list of finance records from a validated copy into another database.

WHY THIS IS NOT A MERGE TOOL

A `pg_dump` restore replaces a database. That is the right shape for a backup and for a
fresh install, and the wrong shape entirely for a shared database that already holds Core's
tables and the site's real rows. This is the other shape: the schema arrives by migration,
and then a SHORT, EXPLICIT list of records is carried across by id.

NOTHING IS APPROVED YET

`APPROVED` below is deliberately empty. Filling it is a business decision about which rows
may leave a test database, and nobody has made it -- so this script transfers nothing until
somebody names records and records why. An empty list is a refusal, not a bug, and the
script says so rather than quietly succeeding.

WHAT IT REFUSES BY CONSTRUCTION

  * a target that is not on loopback. A tool that can be pointed at the central server by
    a typo is a tool that will be.
  * writing at all, unless `--apply` is given AND the target is loopback AND `APPROVED` is
    non-empty. Dry run is the default and prints exactly what would happen.
  * any row belonging to a synthetic identity, a demo role, or a probe resource. The
    exclusion is by pattern AND by explicit id, because a name is easy to change.
  * crossing a tenant. Every statement carries (organization_id, project_id) from the
    MAPPING, so a record cannot arrive in a project nobody named.

REPEATABILITY

Every write is `ON CONFLICT DO NOTHING` against the table's own scoped identity, so running
this twice transfers nothing the second time and reports what it matched. That is the same
rule the MPP mapper uses, for the same reason: a transfer that cannot be repeated safely is
a transfer nobody dares repeat.
"""
import argparse
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

#: The records a person has approved for transfer, with the reason recorded beside each.
#:
#: Shape: {"table": <finance table>, "id": <uuid>, "reason": <why this row may travel>}
#:
#: EMPTY ON PURPOSE. See the module docstring: naming a row here is a business decision.
APPROVED = ()

#: Tenant identity on the SOURCE mapped to tenant identity on the TARGET. A transfer
#: without this would carry the test database's organization and project ids into a
#: database where they mean something else, or nothing.
MAPPING = {
    # ("<source organization_id>", "<source project_id>"):
    #     ("<target organization_id>", "<target project_id>"),
}

#: Never transferred, whatever else is asked for. Patterns first, because a synthetic row
#: renamed by hand is still synthetic.
EXCLUDED_TITLE_PATTERNS = ("آزمون%", "TEST%", "T-PROBE%", "%DEMO%", "%demo%")
EXCLUDED_RESOURCE_CODES = ("T-PROBE-EDITOR", "T-PROBE-VIEWER", "T-PROBE-INVOICE_MGR",
                           "T-PROBE-BADUNIT", "T-PROBE-X1")

#: The tables this tool knows how to carry, and the scoped identity each conflicts on.
#: A table absent from here cannot be transferred, which is the point: `invoices` and
#: `report_snapshots` are NOT here, because a financial document created in a test database
#: has no business appearing in a real ledger.
TRANSFERABLE = {
    "finance_resources": "(organization_id, project_id, id)",
    "unit_conversions": "(organization_id, project_id, id)",
}


def loopback_only(value):
    host = conninfo_to_dict(value).get("host")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise argparse.ArgumentTypeError(
            "this tool writes financial records and is loopback-only; got host %r. "
            "Transferring to a remote target is a separate, approved, rehearsed "
            "operation and not something this script may do." % host)
    return value


def excluded(connection, table, identifier):
    """Is this row synthetic? Asked of the row itself, never of the request."""
    if table != "finance_resources":
        return None
    row = connection.execute(
        "SELECT code, title FROM finance_resources WHERE id = %s", (identifier,)
    ).fetchone()
    if row is None:
        return "no such row"
    if row["code"] in EXCLUDED_RESOURCE_CODES:
        return "code %r is a probe record" % row["code"]
    for pattern in EXCLUDED_TITLE_PATTERNS:
        hit = connection.execute(
            "SELECT 1 WHERE %s LIKE %s", (row["title"], pattern)).fetchone()
        if hit:
            return "title matches the synthetic pattern %r" % pattern
    return None


def plan(source, target, apply_changes):
    """What would be carried, and what refuses to be. Reads only unless apply_changes."""
    findings = []
    if not APPROVED:
        return [("REFUSED", "-", "-",
                 "APPROVED is empty: no record has been approved for transfer")], 0

    with psycopg.connect(source, row_factory=dict_row) as src:
        src.execute("SET TRANSACTION READ ONLY")
        for entry in APPROVED:
            table, identifier = entry["table"], entry["id"]
            if table not in TRANSFERABLE:
                findings.append(("REFUSED", table, identifier,
                                 "this table is not transferable by this tool"))
                continue
            reason = excluded(src, table, identifier)
            if reason:
                findings.append(("EXCLUDED", table, identifier, reason))
                continue
            row = src.execute(
                "SELECT * FROM %s WHERE id = %%s" % table, (identifier,)).fetchone()
            scope = (str(row["organization_id"]), row["project_id"])
            if scope not in MAPPING:
                findings.append(("REFUSED", table, identifier,
                                 "no target tenant is mapped for %s" % (scope,)))
                continue
            findings.append(("WOULD TRANSFER", table, identifier, entry["reason"]))

    if not apply_changes:
        return findings, 0

    carried = 0
    with psycopg.connect(source, row_factory=dict_row) as src, \
            psycopg.connect(target, row_factory=dict_row) as dst:
        src.execute("SET TRANSACTION READ ONLY")
        with dst.transaction():
            for status, table, identifier, _reason in findings:
                if status != "WOULD TRANSFER":
                    continue
                row = src.execute(
                    "SELECT * FROM %s WHERE id = %%s" % table, (identifier,)).fetchone()
                scope = (str(row["organization_id"]), row["project_id"])
                row["organization_id"], row["project_id"] = MAPPING[scope]
                columns = list(row)
                dst.execute(
                    "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT DO NOTHING"
                    % (table, ", ".join(columns),
                       ", ".join(["%s"] * len(columns))),
                    [row[column] for column in columns])
                carried += 1
    return findings, carried


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=loopback_only,
                        help="the validated candidate database to read from")
    parser.add_argument("--target", required=True, type=loopback_only,
                        help="the database to write to; loopback only")
    parser.add_argument("--apply", action="store_true",
                        help="actually write. Without this, nothing is written.")
    options = parser.parse_args(argv)

    if conninfo_to_dict(options.source) == conninfo_to_dict(options.target):
        parser.error("source and target must be different databases")

    findings, carried = plan(options.source, options.target, options.apply)
    print("  %-15s %-22s %-38s %s" % ("STATUS", "TABLE", "ID", "WHY"))
    for status, table, identifier, reason in findings:
        print("  %-15s %-22s %-38s %s" % (status, table, identifier, reason))
    print()
    if not options.apply:
        print("  DRY RUN -- nothing was written. Add --apply to carry the rows above.")
    else:
        print("  %d row(s) carried." % carried)
    refused = sum(1 for status, *_ in findings if status in ("REFUSED", "EXCLUDED"))
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
