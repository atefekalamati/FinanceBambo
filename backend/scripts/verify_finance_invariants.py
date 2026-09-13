# -*- coding: utf-8 -*-
"""Every financial invariant this schema cannot express as a constraint, checked on data.

WHY THIS EXISTS
A matching migration ledger proves the shape of the database. It proves nothing about what
is in it. The audit that found `source_fixed_cost` stored and never read had a green ledger
the whole time, and so did the report that published an estimate built from 120 of its 835
lines. The gap between "the schema is right" and "the data is right" is what this closes,
and it closes it the same way every time so two runs can be compared.

WHAT IT IS NOT
It is not a repair tool. Nothing here writes: every connection is opened with
`SET TRANSACTION READ ONLY`, so a check cannot become a fix by accident, and a failing
check is a finding for a person rather than something this script may decide about.

It is not a substitute for the constraints either. A rule that CAN be a constraint belongs
in a migration; what is here is the set that cannot -- cross-table arithmetic, a currency
factor that lives in the reader, and counts that must agree between a header and its rows.

LOCAL ONLY
The DSN must name a loopback host. This reads financial data, and a tool that can be
pointed at the central server by a typo is a tool that will be.
"""
import argparse
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

#: The toman-to-rial factor `coreint.finance_mpp_sync` applies to this project's files.
#: Named here so the check compares against the reader's own decision rather than a
#: number retyped from a report. A file whose currency was never decided stores NULL in
#: the `_irr` columns and is excluded from the comparison, not assumed to be 1.
TOMAN_TO_RIAL = 10

#: Each entry: a name, the question in SQL, and how many rows a healthy database returns.
#: The SQL selects the OFFENDING rows, so an empty result is a pass and the rows themselves
#: are the evidence when it is not.
CHECKS = (
    (
        "source rows match the count their version states",
        """
        SELECT v.id, v.row_count AS stated,
               (SELECT count(*) FROM finance_mpp_rows r
                 WHERE r.source_version_id = v.id) AS actual
          FROM finance_mpp_source_versions v
         WHERE v.row_count <> (SELECT count(*) FROM finance_mpp_rows r
                                WHERE r.source_version_id = v.id)
        """,
    ),
    (
        "every source row belongs to a version that exists",
        """
        SELECT r.id, r.source_version_id
          FROM finance_mpp_rows r
         WHERE NOT EXISTS (SELECT 1 FROM finance_mpp_source_versions v
                            WHERE v.id = r.source_version_id)
        """,
    ),
    (
        "every estimate line points at a live resource in its own tenant",
        """
        SELECT l.id, l.resource_id
          FROM estimate_lines l
         WHERE l.deleted_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM finance_resources r
                            WHERE r.id = l.resource_id
                              AND r.organization_id = l.organization_id
                              AND r.project_id = l.project_id
                              AND r.deleted_at IS NULL)
        """,
    ),
    (
        "every invoice line that names an estimate line names a live one",
        """
        SELECT il.id, il.estimate_line_id
          FROM invoice_lines il
         WHERE il.estimate_line_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM estimate_lines l
                            WHERE l.id = il.estimate_line_id AND l.deleted_at IS NULL)
        """,
    ),
    (
        "every completion belongs to a line that exists",
        """
        SELECT c.id, c.estimate_line_id
          FROM estimate_line_source_completions c
         WHERE NOT EXISTS (SELECT 1 FROM estimate_lines l WHERE l.id = c.estimate_line_id)
        """,
    ),
    (
        "one estimate line per MPP assignment, per tenant",
        """
        SELECT organization_id, project_id, source_assignment_uid, count(*) AS lines
          FROM estimate_lines
         WHERE source_assignment_uid IS NOT NULL AND deleted_at IS NULL
         GROUP BY 1, 2, 3 HAVING count(*) > 1
        """,
    ),
    (
        "one estimate line per MPP task among the lines that name no assignment",
        """
        SELECT organization_id, project_id, source_task_uid, count(*) AS lines
          FROM estimate_lines
         WHERE source_task_uid IS NOT NULL AND source_assignment_uid IS NULL
           AND deleted_at IS NULL
         GROUP BY 1, 2, 3 HAVING count(*) > 1
        """,
    ),
    (
        "one financial item per MPP resource, per tenant",
        """
        SELECT organization_id, project_id, source_resource_uid, count(*) AS items
          FROM finance_resources
         WHERE source_resource_uid IS NOT NULL AND deleted_at IS NULL
         GROUP BY 1, 2, 3 HAVING count(*) > 1
        """,
    ),
    (
        "one resource per code, per tenant",
        """
        SELECT organization_id, project_id, code, count(*) AS items
          FROM finance_resources
         WHERE deleted_at IS NULL
         GROUP BY 1, 2, 3 HAVING count(*) > 1
        """,
    ),
    (
        "the rial fixed cost is the file's own figure through the currency factor",
        """
        SELECT source_version_id, source_task_uid, source_fixed_cost, source_fixed_cost_irr
          FROM finance_mpp_rows
         WHERE source_fixed_cost_irr IS NOT NULL
           AND source_fixed_cost_irr <> source_fixed_cost * %(factor)s
        """,
    ),
    (
        "a row with a fixed cost in rials states the file's figure too",
        """
        SELECT id FROM finance_mpp_rows
         WHERE source_fixed_cost_irr IS NOT NULL AND source_fixed_cost IS NULL
        """,
    ),
    (
        "no estimate amount carries a fraction of a rial",
        """
        SELECT id, original_unit_price_irr FROM estimate_lines
         WHERE original_unit_price_irr IS NOT NULL
           AND original_unit_price_irr <> trunc(original_unit_price_irr)
        """,
    ),
    (
        "a general cost states an amount and no quantity",
        """
        SELECT l.id, l.original_quantity
          FROM estimate_lines l JOIN finance_resources r ON r.id = l.resource_id
         WHERE r.resource_type = 'general_cost' AND l.deleted_at IS NULL
           AND l.original_quantity IS NOT NULL
        """,
    ),
    (
        "a general cost item carries no unit and no dimension",
        """
        SELECT id, code, base_unit, dimension FROM finance_resources
         WHERE resource_type = 'general_cost' AND deleted_at IS NULL
           AND (base_unit IS NOT NULL OR dimension IS NOT NULL)
        """,
    ),
    (
        # The vocabulary is read from the database's own CHECK rather than retyped here.
        # Retyped, it was wrong in three ways at once -- no `awaitingConfirmation`, `void`
        # for `voided`, `corrective` for `corrected` -- and it passed for as long as no
        # invoice had ever been voided or corrected on the database it was asked about.
        # `chr(39)` is a single quote, so the state is matched as it appears in the
        # constraint text without a second layer of quoting to get wrong.
        "every invoice is in a state the workflow defines",
        """
        SELECT id, status FROM invoices
         WHERE status IS NULL
            OR position(chr(39) || status || chr(39) IN
                        (SELECT pg_get_constraintdef(oid) FROM pg_constraint
                          WHERE conrelid = 'invoices'::regclass
                            AND conname = 'invoices_status_check')) = 0
        """,
    ),
    (
        "a confirmed invoice records when it was confirmed",
        """
        SELECT id FROM invoices WHERE status = 'confirmed' AND confirmed_at IS NULL
        """,
    ),
    (
        "an issued report froze its own payload",
        """
        SELECT id FROM report_snapshots
         WHERE snapshot_payload IS NULL OR snapshot_payload = 'null'::jsonb
        """,
    ),
    (
        "an issued report names the progress reference it was calculated from",
        """
        SELECT id FROM report_snapshots WHERE progress_snapshot_ref_id IS NULL
        """,
    ),
    (
        # `source_file_version_id`, not `source_version_id`: the reference names the FILE
        # version it was taken from, and a Finance source version carries the same id when
        # the feed came from a file this module read. A reference whose id resolves to
        # nothing is a report that can no longer say what it was calculated from.
        "every pinned progress reference that names a Finance source version resolves",
        """
        SELECT p.id, p.source_file_version_id
          FROM progress_snapshot_refs p
         WHERE p.source_type = 'finance_mpp'
           AND p.source_file_version_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM finance_mpp_source_versions v
                            WHERE v.id = p.source_file_version_id)
        """,
    ),
    (
        "every pinned reference states a status its own vocabulary allows",
        """
        SELECT id, snapshot_status FROM progress_snapshot_refs
         WHERE snapshot_status NOT IN ('ready', 'superseded')
        """,
    ),
    (
        "a price version states a whole number of rials",
        """
        SELECT id, unit_price_irr FROM price_versions
         WHERE unit_price_irr <> trunc(unit_price_irr)
        """,
    ),
)

#: Counted rather than judged. Each of these is a legitimate state whose SIZE is the thing
#: worth watching between two runs -- an estimate line with no baseline is correct when the
#: file states none, and alarming if the number changes without an import.
COUNTS = (
    ("source versions", "SELECT count(*) FROM finance_mpp_source_versions"),
    ("source rows", "SELECT count(*) FROM finance_mpp_rows"),
    ("rows stating a fixed cost",
     "SELECT count(*) FROM finance_mpp_rows WHERE source_fixed_cost <> 0"),
    ("rows with a rial fixed cost",
     "SELECT count(*) FROM finance_mpp_rows WHERE source_fixed_cost_irr IS NOT NULL"),
    ("financial items", "SELECT count(*) FROM finance_resources WHERE deleted_at IS NULL"),
    ("estimate lines", "SELECT count(*) FROM estimate_lines WHERE deleted_at IS NULL"),
    ("  of them keyed on an assignment",
     "SELECT count(*) FROM estimate_lines"
     " WHERE deleted_at IS NULL AND source_assignment_uid IS NOT NULL"),
    ("  of them keyed on a task alone",
     "SELECT count(*) FROM estimate_lines"
     " WHERE deleted_at IS NULL AND source_assignment_uid IS NULL"
     " AND source_task_uid IS NOT NULL"),
    ("  of them stating no baseline at all",
     "SELECT count(*) FROM estimate_lines l"
     " WHERE l.deleted_at IS NULL AND l.original_quantity IS NULL"
     " AND l.original_unit_price_irr IS NULL"
     " AND NOT EXISTS (SELECT 1 FROM estimate_line_source_completions c"
     "                  WHERE c.estimate_line_id = l.id)"),
    ("source completions", "SELECT count(*) FROM estimate_line_source_completions"),
    ("invoices", "SELECT count(*) FROM invoices"),
    ("issued reports", "SELECT count(*) FROM report_snapshots"),
    ("pinned progress references", "SELECT count(*) FROM progress_snapshot_refs"),
    ("audit events", "SELECT count(*) FROM finance_audit_events"),
)


def local_only(value):
    host = conninfo_to_dict(value).get("host")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise argparse.ArgumentTypeError(
            "this tool reads financial data and is loopback-only; got host %r" % host)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True, type=local_only)
    parser.add_argument("--rows", type=int, default=5,
                        help="how many offending rows to print per failing check")
    options = parser.parse_args(argv)

    failures = skipped = 0
    with psycopg.connect(options.dsn, row_factory=dict_row) as db:
        db.execute("SET TRANSACTION READ ONLY")
        ledger = [r["version_num"] for r in
                  db.execute("SELECT version_num FROM finance_alembic_version")]
        print("  migration ledger: %s" % ledger)
        print()
        print("  COUNTS")
        for label, query in COUNTS:
            try:
                value = list(db.execute(query).fetchone().values())[0]
            except psycopg.Error as error:
                db.rollback()
                value = "(unavailable: %s)" % str(error).splitlines()[0][:60]
            print("    %-38s %s" % (label, value))
        print()
        print("  INVARIANTS")
        for label, query in CHECKS:
            # A check whose column or table this ledger has not reached yet is SKIPPED and
            # said to be skipped. Reporting it as a pass would turn "we did not ask" into
            # "the answer was yes", which is the whole failure mode this script exists to
            # avoid. The rollback is needed because one failed statement aborts the
            # read-only transaction and every later check would report the same error.
            try:
                rows = db.execute(query, {"factor": TOMAN_TO_RIAL}).fetchall()
            except psycopg.Error as error:
                db.rollback()
                db.execute("SET TRANSACTION READ ONLY")
                skipped += 1
                print("    SKIP  %s" % label)
                print("            %s" % str(error).splitlines()[0][:100])
                continue
            if not rows:
                print("    PASS  %s" % label)
                continue
            failures += 1
            print("    FAIL  %s  (%d row(s))" % (label, len(rows)))
            for row in rows[:options.rows]:
                print("            %s" % dict(row))
            if len(rows) > options.rows:
                print("            ... and %d more" % (len(rows) - options.rows))

    print()
    print("  %d failed, %d skipped, %d passed, of %d invariants"
          % (failures, skipped, len(CHECKS) - failures - skipped, len(CHECKS)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
