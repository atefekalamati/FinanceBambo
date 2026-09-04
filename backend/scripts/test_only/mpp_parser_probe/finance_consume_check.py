# -*- coding: utf-8 -*-
r"""TEST_ONLY -- DISPOSABLE. Can Finance actually consume the imported MSP snapshot?

Drives the REAL integration end to end against the scratch database:

    msp_snapshots + msp_tasks + msp_resources + msp_resource_assignments
        -> coreint.progress.CoreProgressSnapshotProvider   (the real adapter)
        -> domain.progress.snapshot_metadata               (the real header check)
        -> domain.progress.reference_from_header           (the real ProgressReference)
        -> repositories.progress.ensure_progress_reference (the real Finance ref row)
        -> domain.progress.resolve_progress_quantity       (the real calculation)
        -> domain.progress.ProgressPairing                 (the real matching rule)

No import logic is duplicated here and no validation is relaxed. Every step calls the
module Finance itself calls; this file only supplies a connection, a scope, and a report.
If a step refuses, that refusal is the finding -- it is printed, not worked around.

    ..\..\..\..\.venv312\Scripts\python -m scripts.test_only.mpp_parser_probe.finance_consume_check
"""

import argparse
import asyncio
import selectors
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

from app.finance.domain.progress import (ProgressPairing, assignment_keys,   # noqa: E402
                                         reference_from_header,
                                         resolve_progress_quantity,
                                         snapshot_assignments, snapshot_metadata)
from app.finance.repositories.progress import ensure_progress_reference  # noqa: E402
from app.finance.security.guards import FinanceScope                     # noqa: E402
from coreint.progress import (ACTIVITY_CODE_FIELDS,                      # noqa: E402
                              PROGRESS_SNAPSHOT_TYPES,
                              CoreProgressSnapshotProvider)
# The host's own choice of activity-code field, imported rather than restated so this
# reports what devhost actually installs instead of what this file hopes it installs.
from devhost.app import ACTIVITY_CODE_FIELDS as WIRED_FIELDS              # noqa: E402
from scripts.test_only.mpp_parser_probe.load_scratch import (ORGANIZATION_ID,  # noqa: E402
                                                             PROJECT_ID)
from scripts.test_only.mpp_parser_probe.scratch_target import (          # noqa: E402
    SCRATCH_DATABASE, SCRATCH_HOST, SCRATCH_PORT, UnsafeTarget,
    assert_dsn_targets_scratch)

DEFAULT_DSN = "postgresql://postgres@%s:%s/%s" % (SCRATCH_HOST, SCRATCH_PORT,
                                                  SCRATCH_DATABASE)

#: A stand-in actor. `progress_snapshot_refs.imported_by` is NOT NULL and this snapshot's
#: `created_by` is NULL, so without a scope actor `reference_from_header` correctly returns
#: None. Through the router an actor is always present; this supplies the same thing a
#: request would, rather than relaxing the rule that refuses to invent one.
ACTOR_ID = UUID("00000000-0000-4000-8000-00000000fa01")

findings = []


def say(label, detail=""):
    print("  %-46s %s" % (label, detail))


def finding(severity, text):
    findings.append((severity, text))
    say("  %s" % severity, text)


async def check_discovery(provider, scope, snapshot_id):
    """Does Finance find this snapshot on its own, and can it fetch it by id?

    Two different questions with two different answers, which is the point of asking both.
    """
    print("\n  --- 1. discovery ---")
    current = await provider.current_snapshot(str(scope.organization_id), scope.project_id)
    say("current_snapshot()", "None" if current is None else "returned a feed")
    if current is None:
        say("  reason", "snapshot_type=TARGET is not in %s" % (PROGRESS_SNAPSHOT_TYPES,))
        say("  verdict", "correct -- a baseline is not a progress report")

    feed = await provider.get_snapshot(str(scope.organization_id), scope.project_id,
                                       str(snapshot_id))
    say("get_snapshot(%s)" % snapshot_id, "None" if feed is None else "returned a feed")
    if feed is not None and current is None:
        finding("CONTRACT",
                "get_snapshot() applies no snapshot_type filter, so the TARGET baseline "
                "current_snapshot() refuses is still fetchable by id and is then consumed "
                "as executed progress. The two entry points disagree.")
    return feed


def check_header(feed, scope, snapshot_id):
    """The header, through Finance's own validator."""
    print("\n  --- 2. header ---")
    snapshot_metadata(feed, scope.organization_id, scope.project_id, snapshot_id)
    header = feed["snapshot"]
    for key in ("progressSnapshotId", "hostSnapshotId", "hostFileVersionId",
                "sourceFileVersionId", "sourceFileNameSafe", "reportingDate", "status",
                "snapshotType", "sourceType", "importedBy", "importedAt"):
        say(key, repr(header.get(key)))
    if header.get("importedBy") is None:
        finding("CONTRACT",
                "msp_snapshots.created_by is NULL, so the header carries importedBy=None "
                "while progress_snapshot_refs.imported_by is NOT NULL. Finance falls back "
                "to the request actor; a caller with no actor gets no reference at all.")
    return header


async def check_reference(connection, header, scope):
    """The Finance-side ProgressSnapshotRef, built and stored by the real code."""
    print("\n  --- 3. Finance snapshot reference ---")
    value = reference_from_header(header, scope, uuid4,
                                  lambda: datetime.now(timezone.utc))
    if value is None:
        finding("BLOCKER", "reference_from_header() returned None: Finance cannot pin a "
                           "reference to this snapshot. Nothing below can run.")
        return None
    say("ProgressReference built", "host_snapshot_id=%s host_file_version_id=%s"
        % (value.host_snapshot_id, value.host_file_version_id))
    say("source_file_version_id", repr(value.source_file_version_id))

    stored = await ensure_progress_reference(connection, scope, value)
    say("progress_snapshot_refs row", "id=%s" % (stored["id"] if stored else None))

    # Idempotency is the property that matters: the same Core snapshot must never produce a
    # second Finance reference, or two reports of the same data would cite different ids.
    again = reference_from_header(header, scope, uuid4,
                                  lambda: datetime.now(timezone.utc))
    repeated = await ensure_progress_reference(connection, scope, again)
    same = stored and repeated and str(stored["id"]) == str(repeated["id"])
    say("re-pinning the same snapshot", "same row" if same else "A SECOND ROW")
    if not same:
        finding("BLOCKER", "ensure_progress_reference() is not idempotent for a Core "
                           "snapshot: pinning twice produced two references.")
    return stored


def check_calculations(feed):
    """`resolve_progress_quantity` over every assignment -- the real Finance calculation."""
    print("\n  --- 4. Finance calculations ---")
    rows = snapshot_assignments(feed)
    say("assignments in the feed", str(len(rows)))

    methods, kinds, statuses, warnings = Counter(), Counter(), Counter(), Counter()
    refused = 0
    executed_total = Decimal(0)
    qualities = []
    for row in rows:
        try:
            resolved = resolve_progress_quantity(row)
        except ValueError:
            refused += 1
            continue
        methods[resolved["source_method"]] += 1
        kinds[resolved["measurement_type"]] += 1
        statuses[resolved["progress_status"]] += 1
        qualities.append(resolved["quality"])
        executed_total += resolved["effective_quantity"]
        for item in resolved["warnings"]:
            warnings[item["code"]] += 1

    for title, counter in (("source method", methods), ("measurement type", kinds),
                           ("progress status", statuses)):
        say(title, ", ".join("%s=%d" % kv for kv in sorted(counter.items())) or "none")
    say("no computable source (needs an override)", str(refused))
    say("total executed quantity", format(executed_total, "f"))
    if qualities:
        say("quality min/max", "%s / %s" % (format(min(qualities), "f"),
                                            format(max(qualities), "f")))
    say("warnings raised", ", ".join("%s=%d" % kv for kv in sorted(warnings.items()))
        or "none")

    if executed_total == 0 and refused == 0:
        finding("DATA",
                "Every assignment resolved and the total executed quantity is exactly 0. "
                "This file records no progress, so the calculation path is exercised but "
                "no non-zero result is proven by it.")
    if methods.get("assignment_actual") and warnings.get("PROGRESS_WORK_NOT_QUANTITY"):
        say("note", "both quantity and work-effort paths were taken; they are distinguished "
                    "by measurement_type, not merged")
    return rows


def check_pairing(rows):
    """The matching rule Finance uses to attach an estimate line to an assignment."""
    print("\n  --- 5. pairing keys ---")
    pairs = [assignment_keys(row) for row in rows]
    activity_codes = [pair[1] for pair in pairs]
    missing_activity = sum(1 for code in activity_codes if not code)
    say("assignments with an activity code", str(len(activity_codes) - missing_activity))
    say("assignments with no activity code", str(missing_activity))
    say("distinct activity codes", str(len({code for code in activity_codes if code})))

    # A shared activity code is not an error, but it is the condition under which one
    # correction lands on several assignments at once, so it is reported rather than
    # summarised away.
    shared = Counter(code for code in activity_codes if code)
    fanned = {code: count for code, count in shared.items() if count > 1}
    say("activity codes used by >1 assignment", str(len(fanned)))
    if fanned:
        worst = sorted(fanned.items(), key=lambda kv: -kv[1])[:3]
        say("  largest fan-out", ", ".join("%s x%d" % kv for kv in worst))
        finding("KNOWN",
                "%d activity codes are shared by more than one assignment. ProgressPairing "
                "matches on (assignment_external_id, activity_external_id); an estimate "
                "line keyed on the activity alone reaches every assignment sharing it."
                % len(fanned))

    if missing_activity == len(activity_codes):
        finding("BLOCKER", "No assignment carries an activity code, so no estimate line "
                           "can ever be paired with this snapshot.")

    # Prove the real matcher resolves a real key rather than asserting that it would.
    sample = next((pair for pair in pairs if pair[0] and pair[1]), None)
    if sample:
        matched = ProgressPairing(rows, assignment_keys).match(*sample)
        say("ProgressPairing.match on a real key", "matched" if matched else "NO MATCH")
        if matched is None:
            finding("BLOCKER", "ProgressPairing could not match a key it produced itself.")
    return pairs


async def check_activity_field_choice(connection, scope, snapshot_id, default_pairs):
    """Which MSP field the activity code is read from, and what the default choice costs.

    `ACTIVITY_CODE_FIELDS` tries `text1` first because a planner writing an activity code
    there is a common convention. Its own docstring says a wrong guess "shows up as unmapped
    lines, which is visible, rather than as wrong pairings, which would not be". That holds
    only when the field is empty. This file fills `text1` on every task with a Jalali date,
    so the guess does not fail visibly -- it succeeds into the wrong value.

    The provider takes the field order as a constructor argument, so this is settled by host
    wiring. Running it both ways turns the claim into a measurement.
    """
    print("\n  --- 6. activity code field ---")

    async def codes_for(fields):
        provider = CoreProgressSnapshotProvider(connection, activity_code_fields=fields)
        feed = await provider.get_snapshot(str(scope.organization_id), scope.project_id,
                                           str(snapshot_id))
        pairs = [assignment_keys(row) for row in snapshot_assignments(feed)]
        codes = [pair[1] for pair in pairs if pair[1]]
        counts = Counter(codes)
        return pairs, len(counts), (max(counts.values()) if counts else 0)

    library_pairs, library_distinct, library_worst = await codes_for(ACTIVITY_CODE_FIELDS)
    wired_pairs, wired_distinct, wired_worst = await codes_for(WIRED_FIELDS)

    say("library default %s" % (ACTIVITY_CODE_FIELDS,),
        "%d distinct codes, largest fan-out %d" % (library_distinct, library_worst))
    say("host wiring     %s" % (WIRED_FIELDS,),
        "%d distinct codes, largest fan-out %d" % (wired_distinct, wired_worst))
    say("sample library code", repr(next((p[1] for p in library_pairs if p[1]), None)))
    say("sample wired code", repr(next((p[1] for p in wired_pairs if p[1]), None)))

    if "text1" in WIRED_FIELDS:
        finding("BLOCKER",
                "The host is wired with %s, which reads Text1 first. Every task in this "
                "file fills Text1 with a Jalali date, so the activity code resolves to a "
                "DATE: %d distinct codes with a fan-out of %d, against %d structural codes "
                "with a fan-out of %d."
                % (WIRED_FIELDS, library_distinct, library_worst, wired_distinct,
                   wired_worst))
    elif wired_distinct > library_distinct:
        say("verdict", "RESOLVED -- the host reads structure, not Text1")
        finding("RESOLVED",
                "Every task in this file fills Text1 with a Jalali date, so the LIBRARY "
                "default would resolve each activity code to a date (%d codes, fan-out "
                "%d). devhost wires both adapters with %s instead: %d structural codes, "
                "fan-out %d. The library default is left unchanged on purpose -- a host "
                "whose planners really do write codes in Text1 still needs it."
                % (library_distinct, library_worst, WIRED_FIELDS, wired_distinct,
                   wired_worst))
    return wired_pairs


async def run(dsn, snapshot_id):
    scope = FinanceScope(organization_id=ORGANIZATION_ID, project_id=PROJECT_ID,
                         actor_user_id=ACTOR_ID)
    async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, row_factory=dict_row, connect_timeout=10) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT current_database() d, host(inet_server_addr()) h")
            server = await cursor.fetchone()
        if server["d"] != SCRATCH_DATABASE or server["h"] != SCRATCH_HOST:
            raise SystemExit("STOP: the server answering is %s/%s"
                             % (server["h"], server["d"]))
        say("target", "%s/%s" % (server["h"], server["d"]))

        # Wired exactly as devhost wires it, so sections 1-5 report what the host does
        # rather than what the library would do unconfigured. Section 6 compares the two.
        provider = CoreProgressSnapshotProvider(connection,
                                                activity_code_fields=WIRED_FIELDS)
        say("activity code fields", "%s (from devhost.app)" % (WIRED_FIELDS,))
        feed = await check_discovery(provider, scope, snapshot_id)
        if feed is None:
            finding("BLOCKER", "get_snapshot() returned None; Finance cannot see this "
                               "snapshot at all.")
            return
        header = check_header(feed, scope, snapshot_id)
        await check_reference(connection, header, scope)
        rows = check_calculations(feed)
        pairs = check_pairing(rows)
        await check_activity_field_choice(connection, scope, snapshot_id, pairs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--snapshot-id", type=int, default=9001)
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        assert_dsn_targets_scratch(arguments.dsn)
    except UnsafeTarget as refusal:
        raise SystemExit("STOP: %s" % refusal)

    print("\n  TEST_ONLY / DISPOSABLE -- Finance consuming imported MSP data")
    print("  every step calls the module Finance itself calls\n")

    # psycopg's async connection needs a selector loop on Windows; the default proactor
    # loop has no add_reader and the connection fails with NotImplementedError.
    asyncio.set_event_loop_policy(None)
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    try:
        loop.run_until_complete(run(arguments.dsn, arguments.snapshot_id))
    finally:
        loop.close()

    print("\n  --- findings ---")
    if not findings:
        print("  none: Finance consumed the imported snapshot with no gap found.")
    for severity, text in findings:
        print("  [%s] %s" % (severity, text))
    blockers = [item for item in findings if item[0] == "BLOCKER"]
    print("\n  %s" % ("BLOCKED: %d" % len(blockers) if blockers
                      else "Finance can consume this snapshot."))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
