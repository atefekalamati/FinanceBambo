# -*- coding: utf-8 -*-
r"""TEST_ONLY -- LOCAL DEMO. Create the Finance reference for one Core snapshot.

    ..\..\..\.venv312\Scripts\python -m scripts.test_only.pin_terrace_snapshot --apply

WHY THIS EXISTS

`progress_snapshot_refs` is empty and that is not a bug. Reads never pin -- see
`FinanceLiveReportService._read_current_snapshot`: "Viewing a page must not insert a row,
and `/overview` is gated only by `finance.view` -- a read permission that must not imply a
write." Four tests enforce it, and `test_only_the_writing_operations_pin` asserts there is
exactly one `pin=True` call site.

Only two operations pin, and on a Core-backed host neither can succeed on a fresh project:

  * `issue()` needs `finance_report.issue`, a permission Core's catalogue does not contain,
    so nobody can ever hold it;
  * `override()` bootstraps a reference and then looks it up by the CLIENT's UUID, which can
    never match the one it just minted -- it writes the row and returns 404.

So the chain has no reachable first step. This script supplies that step for the local demo
and nothing else. It is not a fix; the fix belongs in `override()`'s bootstrap, which is
production code this script deliberately does not touch.

WHAT IT DOES NOT DO

No fake UUID is invented and no INSERT is hand-written. The Core adapter produces the real
feed header, `reference_from_header` turns it into the same `ProgressReference` value the
service would build, and `ensure_progress_reference` -- the one mechanism -- writes it.
Running twice reuses the existing row rather than adding a second.
"""

import argparse
import asyncio
import selectors
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

from app.finance.domain.progress import reference_from_header           # noqa: E402
from app.finance.repositories.progress import ensure_progress_reference  # noqa: E402
from app.finance.security.guards import FinanceScope                    # noqa: E402
from coreint.progress import CoreProgressSnapshotProvider               # noqa: E402
from devhost.app import ACTIVITY_CODE_FIELDS as WIRED_FIELDS            # noqa: E402

DSN = "postgresql://postgres@127.0.0.1:5432/bambo_canonical_test"
ORGANIZATION_ID = UUID("c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
PROJECT_ID = "terrace"
ACTOR_ID = UUID("53a1ac1b-d87f-4125-9ba9-a7d64166af88")
SNAPSHOT_ID = 38

#: Never written to by this script.
FORBIDDEN = frozenset({"bambo", "bambo_canonical_local"})


def say(label, detail=""):
    print("  %-38s %s" % (label, detail))


async def run(dsn, snapshot_id, apply_changes):
    scope = FinanceScope(organization_id=ORGANIZATION_ID, project_id=PROJECT_ID,
                         actor_user_id=ACTOR_ID)
    async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, row_factory=dict_row, connect_timeout=10) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT current_database() AS d")
            database = (await cursor.fetchone())["d"]
        if database in FORBIDDEN:
            raise SystemExit("STOP: %r is not a database this may write to." % database)
        say("database", database)

        # The real adapter, wired the way devhost wires it.
        provider = CoreProgressSnapshotProvider(connection,
                                                activity_code_fields=WIRED_FIELDS)
        feed = await provider.get_snapshot(str(scope.organization_id), scope.project_id,
                                           str(snapshot_id))
        if feed is None:
            raise SystemExit("STOP: Core has no snapshot %s for %s"
                             % (snapshot_id, PROJECT_ID))
        header = feed["snapshot"]
        say("host snapshot", "%s  %s" % (header["hostSnapshotId"],
                                         header["sourceFileNameSafe"]))
        say("snapshot type / status", "%s / %s" % (header["snapshotType"],
                                                   header["status"]))
        say("reporting date", header["reportingDate"])
        say("assignments in the feed", str(len(feed["assignments"])))

        # The same conversion the service uses. `importedBy` falls back to the scope actor
        # because msp_snapshots.created_by is null here, exactly as it would through a
        # request; nothing is invented.
        value = reference_from_header(header, scope, uuid4,
                                      lambda: datetime.now(timezone.utc))
        if value is None:
            raise SystemExit("STOP: reference_from_header refused this header.")
        say("ProgressReference built",
            "host_snapshot_id=%s host_file_version_id=%s"
            % (value.host_snapshot_id, value.host_file_version_id))

        if not apply_changes:
            print("\n  DRY RUN -- nothing written. Add --apply.")
            return 0

        row = await ensure_progress_reference(connection, scope, value)
        say("progress_snapshot_refs row", str(row["id"]) if row else "NONE")

        # Idempotency, proved rather than asserted: the table is immutable, so a second
        # reference for the same Core snapshot could never be removed.
        again = await ensure_progress_reference(
            connection, scope,
            reference_from_header(header, scope, uuid4,
                                  lambda: datetime.now(timezone.utc)))
        same = row and again and str(row["id"]) == str(again["id"])
        say("pinned twice", "same row" if same else "A SECOND ROW -- NOT IDEMPOTENT")

        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("""
                SELECT progress_snapshot_id, host_snapshot_id, host_file_version_id,
                       source_file_name_safe, reporting_date, snapshot_status, source_type
                  FROM progress_snapshot_refs
                 WHERE organization_id = %s AND project_id = %s
                 ORDER BY reporting_date
            """, (ORGANIZATION_ID, PROJECT_ID))
            rows = await cursor.fetchall()
        print()
        say("rows in progress_snapshot_refs", str(len(rows)))
        for item in rows:
            say("  host=%s" % item["host_snapshot_id"],
                "%s  %s  %s  %s" % (item["source_file_name_safe"], item["reporting_date"],
                                    item["snapshot_status"], item["source_type"]))
        return 0 if same else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DSN)
    parser.add_argument("--snapshot-id", type=int, default=SNAPSHOT_ID)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("\n  TEST_ONLY -- pin one Core snapshot, using the service's own mechanism\n")
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    try:
        return loop.run_until_complete(run(arguments.dsn, arguments.snapshot_id,
                                           arguments.apply))
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
