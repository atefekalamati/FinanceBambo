# -*- coding: utf-8 -*-
r"""TEST_ONLY -- LOCAL DEVELOPMENT. Record the estimate basis the mapper of the day dropped.

    ..\..\..\.venv312\Scripts\python -m scripts.test_only.complete_mpp_estimate_basis --dry-run

WHAT IT DOES

Two things, both for ONE source version and nothing else:

  1. Fills `finance_mpp_rows.source_material_quantity`, `source_resource_rate_irr` and
     `source_rate_basis` on rows imported before those columns existed. The values come from
     the file itself, through `finance_rows()` -- the same function the sync uses, so there
     is exactly one place where units, currency and the per-unit proof are decided.
  2. Writes `estimate_line_source_completions` for estimate lines whose own
     `original_quantity` is NULL and whose assignment the file gives a proven quantity and
     rate for.

WHAT IT REFUSES

  * to touch a line that HAS an original quantity or price. The completion is for lines that
    were created without one; a line that has one has it, whoever wrote it.
  * to touch `estimate_lines` at all. The immutability trigger stays on and is never
    circumvented -- the values are recorded beside the line, naming their source version.
  * to complete from a different file. The version's stored sha256 must equal the sha256 of
    the file on disk, or nothing is written: a newer schedule may state a different quantity,
    and that is a REVISION of the estimate, not the original it was created with.
  * to invent anything. A row the file gives no material quantity for, or whose rate its own
    arithmetic does not prove, is counted as skipped and left NULL.
  * to run twice. `estimate_line_source_completions` is unique per line and the insert is
    ON CONFLICT DO NOTHING; the row updates are idempotent by construction (they write the
    same computed values). A second run reports zero completed and changes nothing.
"""

import argparse
import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from coreint.finance_mpp_sync import MATERIAL_UNIT_RATE, finance_rows
from coreint.mpp_files import resolve_import_file
from coreint.mpp_reader import MpxjMppReader

DSN = "postgresql://postgres@127.0.0.1:5432/bambo_canonical_test"

#: Refused outright, whatever else is asked for.
FORBIDDEN_DATABASES = frozenset({"bambo", "bambo_canonical_local"})

_ROW_UPDATE = """
    UPDATE finance_mpp_rows
       SET source_material_quantity = %(quantity)s,
           source_resource_rate_irr = %(rate)s,
           source_rate_basis = %(basis)s
     WHERE organization_id = %(organization_id)s AND project_id = %(project_id)s
       AND source_version_id = %(version_id)s
       AND source_assignment_uid = %(assignment_uid)s
"""

#: The lines this may complete, with the file's own row beside each. The LEFT JOIN is what
#: makes the run idempotent: a line already completed comes back with `completion_id` set
#: and is counted, not rewritten.
_CANDIDATE_LINES = """
    SELECT l.id, l.source_assignment_uid, l.source_task_uid, l.original_quantity,
           l.original_unit_price_irr, l.created_by,
           m.source_material_quantity, m.source_resource_rate_irr, m.source_rate_basis,
           m.source_resource_uid, m.resource_unit,
           c.id AS completion_id
      FROM estimate_lines l
      JOIN finance_mpp_rows m
        ON m.organization_id = l.organization_id AND m.project_id = l.project_id
       AND m.source_version_id = %(version_id)s
       AND m.source_assignment_uid = l.source_assignment_uid
      LEFT JOIN estimate_line_source_completions c
        ON c.organization_id = l.organization_id AND c.project_id = l.project_id
       AND c.estimate_line_id = l.id
     WHERE l.organization_id = %(organization_id)s AND l.project_id = %(project_id)s
       AND l.deleted_at IS NULL
       AND l.source_assignment_uid IS NOT NULL
     ORDER BY l.source_assignment_uid
"""

_INSERT_COMPLETION = """
    INSERT INTO estimate_line_source_completions
        (id, organization_id, project_id, estimate_line_id, source_version_id,
         source_sha256, source_task_uid, source_assignment_uid, source_resource_uid,
         quantity, quantity_unit, unit_price_irr, currency, basis, completed_by)
    VALUES (%(id)s, %(organization_id)s, %(project_id)s, %(estimate_line_id)s,
            %(version_id)s, %(sha256)s, %(task_uid)s, %(assignment_uid)s,
            %(resource_uid)s, %(quantity)s, %(unit)s, %(unit_price_irr)s, 'IRR',
            %(basis)s, %(completed_by)s)
    ON CONFLICT ON CONSTRAINT estimate_line_source_completions_line_key DO NOTHING
"""


def _verify_local(connection):
    """Prove the target is the local development database before anything is written."""
    row = connection.execute(
        "SELECT current_database() AS database, host(inet_server_addr()) AS host, "
        "inet_server_port() AS port, current_user AS who").fetchone()
    print("  database                      %s @ %s:%s as %s"
          % (row["database"], row["host"], row["port"], row["who"]))
    if row["database"] in FORBIDDEN_DATABASES:
        raise SystemExit("STOP: %r is not a database this may write to." % row["database"])
    if row["host"] not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("STOP: %r is not a local server." % row["host"])
    return row


def _current_version(connection, organization_id, project_id):
    version = connection.execute("""
        SELECT id, source_file_name_safe, source_sha256, imported_by, row_count
          FROM finance_mpp_source_versions
         WHERE organization_id = %s AND project_id = %s AND status = 'ready'
         ORDER BY imported_at DESC, id DESC LIMIT 1
    """, (organization_id, project_id)).fetchone()
    if version is None:
        raise SystemExit("STOP: this project has no ready source version.")
    return version


def _read_file(version, import_root):
    """The file this version was made from, refused unless the bytes still match."""
    resolved = resolve_import_file(import_root, version["source_file_name_safe"])
    if resolved.sha256 != version["source_sha256"]:
        raise SystemExit(
            "STOP: %s on disk is sha256 %s but version %s was imported from %s. A different "
            "file states a different estimate, and that is a revision, not a completion."
            % (version["source_file_name_safe"], resolved.sha256[:16],
               str(version["id"])[:8], version["source_sha256"][:16]))
    print("  file                          %s  sha256 %s… (matches the version)"
          % (version["source_file_name_safe"], resolved.sha256[:16]))
    reader = MpxjMppReader(java_home=os.environ.get("MPP_JAVA_HOME")
                           or os.environ.get("JAVA_HOME"))
    parsed = reader.read(resolved.path)
    return finance_rows(parsed, source_sha256=resolved.sha256)


def run(arguments):
    print("\n  RECORDING THE ESTIMATE BASIS THE FILE STATES\n")
    with psycopg.connect(arguments.dsn, row_factory=dict_row, connect_timeout=10) as db:
        _verify_local(db)
        version = _current_version(db, arguments.organization, arguments.project)
        print("  source version                %s (%s rows recorded)"
              % (str(version["id"])[:8], version["row_count"]))
        rows = _read_file(version, arguments.import_root)
        by_assignment = {row["source_assignment_uid"]: row for row in rows
                         if row.get("source_assignment_uid") is not None}
        proven = sum(1 for row in by_assignment.values()
                     if row.get("source_rate_basis") == MATERIAL_UNIT_RATE)
        print("  assignments in the file       %d, of which the file proves a unit rate for %d"
              % (len(by_assignment), proven))

        counters = {"rows_updated": 0, "lines_checked": 0, "completed": 0,
                    "already_completed": 0, "has_own_original": 0, "no_basis": 0,
                    "no_file_row": 0}
        with db.transaction():
            for assignment_uid, row in by_assignment.items():
                cursor = db.execute(_ROW_UPDATE, {
                    "quantity": row.get("source_material_quantity"),
                    "rate": row.get("source_resource_rate_irr"),
                    "basis": row.get("source_rate_basis"),
                    "organization_id": arguments.organization,
                    "project_id": arguments.project,
                    "version_id": version["id"],
                    "assignment_uid": assignment_uid})
                counters["rows_updated"] += cursor.rowcount

            candidates = db.execute(_CANDIDATE_LINES, {
                "version_id": version["id"],
                "organization_id": arguments.organization,
                "project_id": arguments.project}).fetchall()
            for line in candidates:
                counters["lines_checked"] += 1
                if line["completion_id"] is not None:
                    counters["already_completed"] += 1
                    continue
                if (line["original_quantity"] is not None
                        or line["original_unit_price_irr"] is not None):
                    counters["has_own_original"] += 1
                    continue
                source = by_assignment.get(line["source_assignment_uid"])
                if source is None:
                    counters["no_file_row"] += 1
                    continue
                if (source.get("source_rate_basis") != MATERIAL_UNIT_RATE
                        or source.get("source_material_quantity") is None
                        or source.get("source_resource_rate_irr") is None):
                    counters["no_basis"] += 1
                    continue
                db.execute(_INSERT_COMPLETION, {
                    "id": str(uuid4()),
                    "organization_id": arguments.organization,
                    "project_id": arguments.project,
                    "estimate_line_id": line["id"],
                    "version_id": version["id"],
                    "sha256": version["source_sha256"],
                    "task_uid": line["source_task_uid"],
                    "assignment_uid": line["source_assignment_uid"],
                    "resource_uid": source.get("source_resource_uid"),
                    "quantity": source["source_material_quantity"],
                    "unit": source.get("resource_unit"),
                    "unit_price_irr": source["source_resource_rate_irr"],
                    "basis": MATERIAL_UNIT_RATE,
                    "completed_by": version["imported_by"] or arguments.actor})
                counters["completed"] += 1

            if arguments.dry_run:
                print("\n  --dry-run: rolling back everything above.")
                raise _Rollback(counters)
        _report(counters)
    return 0


class _Rollback(Exception):
    def __init__(self, counters):
        super().__init__("dry run")
        self.counters = counters


def _report(counters):
    print("\n  RESULT")
    print("    finance_mpp_rows updated      %d" % counters["rows_updated"])
    print("    estimate lines checked        %d" % counters["lines_checked"])
    print("    completions written           %d" % counters["completed"])
    print("    already completed             %d" % counters["already_completed"])
    print("    left alone (has its own)      %d" % counters["has_own_original"])
    print("    left alone (file proves none) %d" % counters["no_basis"])
    print("    left alone (no row this file) %d" % counters["no_file_row"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DSN)
    parser.add_argument("--organization", default="c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
    parser.add_argument("--project", default="terrace")
    parser.add_argument("--import-root",
                        default=os.environ.get("MPP_IMPORT_ROOT")
                        or str(BACKEND_ROOT.parent / "Sources"))
    parser.add_argument("--actor", default="53a1ac1b-d87f-4125-9ba9-a7d64166af88",
                        help="who to record as the completer when the version names nobody")
    parser.add_argument("--dry-run", action="store_true",
                        help="do everything, report it, then roll it back")
    arguments = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        return run(arguments)
    except _Rollback as rolled_back:
        _report(rolled_back.counters)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
