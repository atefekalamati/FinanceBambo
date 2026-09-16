# -*- coding: utf-8 -*-
"""Say which schedule versions are no longer the one anybody reads.

WHAT MAKES A VERSION SUPERSEDED, AND WHAT DOES NOT

Two conditions, both required, and neither is "it is old":

    1. A NEWER version of the same file name exists for the same project.
    2. Nothing live points at this one -- no progress snapshot reference, and no estimate
       line completion citing it.

The second is the one that matters. A version can be old and still be what the estimate was
built from, and marking that superseded would say the estimate reads something nobody may
read. On the audited project exactly that is true of the OLDEST version: it is superseded
by two newer imports and is cited by 289 completions, so it stays live.

WHAT IT NEVER DOES

It does not delete a row, touch a hash, change a row count, or alter one `finance_mpp_rows`
record. A superseded version is still the evidence of what was imported that day; a report
issued against it has to stay explainable. All this writes is the three supersession
columns.

    python -m scripts.ops.mark_superseded_source_versions --dsn ... [--apply]

Without `--apply` it reports and writes nothing.
"""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

#: Everything needed to judge one version, in one query rather than one per row.
CANDIDATES = """
SELECT v.id, v.organization_id, v.project_id, v.source_file_name_safe, v.source_sha256,
       v.row_count, v.imported_at, v.superseded_at,
       (SELECT count(*) FROM finance_mpp_rows r WHERE r.source_version_id = v.id) AS rows,
       (SELECT count(*) FROM progress_snapshot_refs p
         WHERE p.source_file_version_id = v.id) AS refs,
       (SELECT count(*) FROM estimate_line_source_completions c
         WHERE c.source_version_id = v.id) AS completions,
       (SELECT w.id FROM finance_mpp_source_versions w
         WHERE w.organization_id = v.organization_id
           AND w.project_id = v.project_id
           AND w.source_file_name_safe = v.source_file_name_safe
           AND w.imported_at > v.imported_at
         ORDER BY w.imported_at DESC LIMIT 1) AS newer_id
  FROM finance_mpp_source_versions v
 ORDER BY v.project_id, v.imported_at
"""


def local_only(dsn):
    from psycopg.conninfo import conninfo_to_dict
    parts = conninfo_to_dict(dsn)
    host = (parts.get("host") or "").strip()
    if host not in ("127.0.0.1", "localhost", "::1", ""):
        raise SystemExit("STOP: refusing a non-loopback host %r" % host)
    name = parts.get("dbname") or ""
    if "local" in name or "prod" in name:
        raise SystemExit("STOP: refusing database %r" % name)
    return dsn


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    dsn = local_only(args.dsn)

    marked = kept = already = 0
    with psycopg.connect(dsn, row_factory=dict_row) as db:
        print("database:", db.execute("select current_database()").fetchone()["current_database"])
        rows = db.execute(CANDIDATES).fetchall()
        print("versions:", len(rows))
        print()
        for row in rows:
            gap = "" if row["rows"] == row["row_count"] else \
                "  ROWS %s vs DECLARED %s" % (row["rows"], row["row_count"])
            if row["superseded_at"] is not None:
                already += 1
                print("   already superseded  %s %s%s"
                      % (row["source_sha256"][:12], row["project_id"], gap))
                continue
            live = row["refs"] or row["completions"]
            if row["newer_id"] is None or live:
                kept += 1
                why = ("nothing newer" if row["newer_id"] is None
                       else "cited by %d reference(s) and %d completion(s)"
                            % (row["refs"], row["completions"]))
                print("   LIVE                %s %s -- %s%s"
                      % (row["source_sha256"][:12], row["project_id"], why, gap))
                continue
            marked += 1
            reason = ("a newer import of %s exists, and no snapshot reference or estimate "
                      "completion cites this version" % row["source_file_name_safe"])
            print("   supersede           %s %s -- %s%s"
                  % (row["source_sha256"][:12], row["project_id"], reason, gap))
            if args.apply:
                db.execute(
                    "UPDATE finance_mpp_source_versions"
                    "   SET superseded_at = now(), superseded_by = %s,"
                    "       superseded_reason = %s"
                    " WHERE organization_id = %s AND project_id = %s AND id = %s"
                    "   AND superseded_at IS NULL",
                    (row["newer_id"], reason, row["organization_id"], row["project_id"],
                     row["id"]))
        if args.apply:
            db.commit()

    print()
    print("   live: %d | superseded now: %d | already: %d" % (kept, marked, already))
    if not args.apply:
        print("   DRY RUN -- nothing was written. Pass --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
