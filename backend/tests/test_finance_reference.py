# -*- coding: utf-8 -*-
"""A Finance source version is something Finance can pin a report to.

`progress_snapshot_refs` names a snapshot one of two ways: by a Core host id, or -- when
the snapshot is one of Finance's own persisted source versions and no MSP snapshot exists
-- by the version UUID itself. These tests pin that second identity end to end: the header
becomes a reference, the reference is stored under the right key, and an unpinned read
still resolves to the version.
"""

import asyncio
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.progress import (ProgressPairing, assignment_keys,
                                         finance_version_id, line_keys,
                                         reference_from_header)
from app.finance.repositories.progress import ensure_progress_reference
from app.finance.services.reports import FinanceLiveReportService
from coreint.finance_progress import SOURCE_TYPE_FINANCE_ROWS

ORG = UUID("c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
USER = UUID("53a1ac1b-d87f-4125-9ba9-a7d64166af88")
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")
SCOPE = SimpleNamespace(organization_id=ORG, project_id="terrace", actor_user_id=USER)
NOW = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)


def counter():
    n = [100]

    def new_id():
        n[0] += 1
        return UUID(int=n[0])
    return new_id


def finance_header(**over):
    header = {"organizationId": str(ORG), "projectId": "terrace",
              "progressSnapshotId": str(VERSION), "hostSnapshotId": None,
              "hostFileVersionId": None, "sourceFileVersionId": str(VERSION),
              "sourceFileNameSafe": "terrace.mpp", "reportingDate": "2026-09-05",
              "status": "ready", "snapshotType": "ACTUAL",
              "sourceType": SOURCE_TYPE_FINANCE_ROWS, "importedBy": None,
              "importedAt": "2026-09-05T09:00:00+00:00"}
    header.update(over)
    return header


def core_header(**over):
    return finance_header(progressSnapshotId="45", hostSnapshotId=45, hostFileVersionId=45,
                          sourceFileVersionId=None, **over)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class HeaderToReferenceTests(unittest.TestCase):
    def test_the_source_type_stays_inside_the_schemas_closed_vocabulary(self):
        # The provider must not invent a source_type: the response schema and the table's
        # CHECK both close that vocabulary, and a Project file read by Finance is still a
        # Project file. Identity is what distinguishes it, not this field.
        self.assertEqual("microsoft_project", SOURCE_TYPE_FINANCE_ROWS)

    def test_a_finance_version_is_recognised_by_identity_not_by_source_type(self):
        self.assertEqual(VERSION, finance_version_id(finance_header()))
        self.assertIsNone(finance_version_id(core_header()))
        # A header naming a source file version that is NOT its own snapshot id describes
        # something else; two different identifiers cannot both be this version.
        self.assertIsNone(finance_version_id(
            finance_header(sourceFileVersionId=str(UUID(int=3)))))

    def test_a_finance_version_header_is_its_own_identity(self):
        value = reference_from_header(finance_header(), SCOPE, counter(), lambda: NOW)
        self.assertIsNotNone(value)
        self.assertEqual(VERSION, value.progress_snapshot_id, "not a minted id: the version's own")
        self.assertIsNone(value.host_snapshot_id)
        self.assertIsNone(value.host_file_version_id)
        self.assertEqual(VERSION, value.source_file_version_id)
        self.assertEqual(date(2026, 9, 5), value.reporting_date)
        self.assertEqual(USER, value.imported_by)

    def test_the_stored_source_type_stays_inside_the_columns_vocabulary(self):
        # The CHECK constraint allows microsoft_project/primavera/manual/other. A Finance
        # version of a Project file is still a Project file; provenance is the null host id.
        value = reference_from_header(finance_header(), SCOPE, counter(), lambda: NOW)
        self.assertEqual("microsoft_project", value.source_type)

    def test_a_hostless_header_that_is_not_a_finance_version_is_still_nothing_to_pin_to(self):
        value = reference_from_header(finance_header(sourceFileVersionId=None),
                                      SCOPE, counter(), lambda: NOW)
        self.assertIsNone(value)

    def test_a_finance_header_with_a_malformed_version_id_is_refused_not_guessed(self):
        value = reference_from_header(finance_header(progressSnapshotId="not-a-uuid"),
                                      SCOPE, counter(), lambda: NOW)
        self.assertIsNone(value)

    def test_a_core_header_is_unchanged_a_minted_id_and_the_host_id(self):
        value = reference_from_header(core_header(), SCOPE, counter(), lambda: NOW)
        self.assertEqual(45, value.host_snapshot_id)
        self.assertNotEqual(VERSION, value.progress_snapshot_id)
        self.assertIsNone(value.source_file_version_id)
        self.assertEqual("microsoft_project", value.source_type)


class CorroboratedPairingTests(unittest.TestCase):
    """Against a Finance source version, "mapped" has to mean mapped.

    The estimate lines in this database carry identifiers from a different schedule and
    record no provenance, so a lone integer match against a new source is a collision as
    often as a mapping. Corroboration mode is what the report turns on for such a feed.
    """

    FEED = [{"assignmentExternalId": "9623", "actualQuantity": "4",
             "task": {"activityCode": "1.8.1.8.4"}},
            {"assignmentExternalId": "10708", "actualQuantity": "7",
             "task": {"activityCode": "1.6.3"}}]

    def line(self, assignment, activity):
        return {"assignment_external_id": assignment, "activity_external_id": activity}

    def pairing(self, corroborate):
        return ProgressPairing(self.FEED, assignment_keys, corroborate)

    def test_a_colliding_assignment_id_is_accepted_without_corroboration(self):
        # The legacy behaviour, unchanged for a Core snapshot: the assignment id wins.
        paired = self.pairing(False).match(*line_keys(self.line("9623", "1.9.2.9")))
        self.assertIsNotNone(paired)

    def test_the_same_collision_is_refused_with_corroboration(self):
        # Same id, an activity code that says it is a different piece of work.
        self.assertIsNone(self.pairing(True).match(*line_keys(self.line("9623", "1.9.2.9"))))

    def test_a_genuine_pair_agreeing_on_both_identifiers_is_kept(self):
        paired = self.pairing(True).match(*line_keys(self.line("9623", "1.8.1.8.4")))
        self.assertEqual("9623", paired["assignmentExternalId"])

    def test_a_lone_activity_match_is_not_promoted_under_corroboration(self):
        self.assertIsNone(self.pairing(True).match(*line_keys(self.line(None, "1.6.3"))))
        self.assertIsNotNone(self.pairing(False).match(*line_keys(self.line(None, "1.6.3"))))

    def test_a_line_stating_no_activity_still_pairs_on_its_assignment_id(self):
        # Nothing to contradict: corroboration rejects disagreement, it does not demand a
        # second identifier from a caller that never had one.
        paired = self.pairing(True).match(*line_keys(self.line("10708", None)))
        self.assertEqual("10708", paired["assignmentExternalId"])



# ------------------------------------------------------------------- the repository seam
class Cursor:
    def __init__(self, db):
        self._db, self._rows = db, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self._db.statements.append((text, params))
        if text.startswith("SELECT"):
            self._db.selects += 1
            self._rows = [self._db.row] if (self._db.selects > 1 and self._db.row) else []

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class Db:
    def __init__(self, row=None):
        self.row, self.statements, self.selects = row, [], 0

    def cursor(self, **_kwargs):
        return Cursor(self)


class EnsureReferenceTests(unittest.TestCase):
    def test_a_finance_version_is_keyed_by_its_progress_snapshot_id(self):
        value = reference_from_header(finance_header(), SCOPE, counter(), lambda: NOW)
        db = Db(row={"id": value.id, "progress_snapshot_id": VERSION, "host_snapshot_id": None})
        row = run(ensure_progress_reference(db, SCOPE, value))
        self.assertEqual(VERSION, row["progress_snapshot_id"])
        lookup, insert, readback = db.statements[0][0], db.statements[1][0], db.statements[2][0]
        self.assertIn("progress_snapshot_id=%s", lookup)
        self.assertNotIn("host_snapshot_id=%s", lookup)
        self.assertIn("ON CONFLICT (organization_id,project_id,progress_snapshot_id)", insert)
        self.assertIn("progress_snapshot_id=%s", readback)
        self.assertEqual(VERSION, db.statements[0][1][2], "the key is the version UUID")

    def test_a_core_snapshot_is_still_keyed_by_its_host_id(self):
        value = reference_from_header(core_header(), SCOPE, counter(), lambda: NOW)
        db = Db(row={"id": value.id, "progress_snapshot_id": value.progress_snapshot_id,
                     "host_snapshot_id": 45})
        run(ensure_progress_reference(db, SCOPE, value))
        lookup, insert = db.statements[0][0], db.statements[1][0]
        self.assertIn("host_snapshot_id=%s", lookup)
        self.assertIn("WHERE host_snapshot_id IS NOT NULL DO NOTHING", insert)
        self.assertEqual(45, db.statements[0][1][2])

    def test_an_existing_reference_is_returned_untouched_and_nothing_is_inserted(self):
        value = reference_from_header(finance_header(), SCOPE, counter(), lambda: NOW)
        db = Db(row={"id": UUID(int=7), "progress_snapshot_id": VERSION, "host_snapshot_id": None})
        db.selects = 1                       # make the FIRST lookup already find it
        row = run(ensure_progress_reference(db, SCOPE, value))
        self.assertEqual(UUID(int=7), row["id"])
        self.assertFalse(any(text.startswith("INSERT") for text, _ in db.statements))


# ------------------------------------------------------------------ the unpinned read
class Provider:
    async def current_snapshot(self, organization_id, project_id, as_of=None):
        return {"snapshot": finance_header(), "assignments": []}

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        return None


class Repo:
    def __init__(self):
        self.asked = []

    async def progress_reference_for_snapshot(self, scope, progress_snapshot_id):
        self.asked.append(progress_snapshot_id)
        return None


class UnpinnedReadTests(unittest.TestCase):
    def test_an_unpinned_read_resolves_to_the_finance_version_not_to_nothing(self):
        repo = Repo()
        service = FinanceLiveReportService(repo, Provider(), counter(), lambda: NOW)
        descriptor = run(service._read_current_snapshot(SCOPE, date(2026, 9, 5)))
        self.assertEqual({"progress_snapshot_ref_id": None,
                          "progress_snapshot_id": VERSION,
                          "host_snapshot_id": None,
                          "reporting_date": date(2026, 9, 5)}, descriptor)
        self.assertEqual([VERSION], repo.asked, "looked up by the version, never by a host id")


if __name__ == "__main__":
    unittest.main()
