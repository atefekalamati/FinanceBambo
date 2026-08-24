"""One rule for pairing an estimate line with the progress that reports it.

The rule was written three times: in `domain/reports.py` to find a line's assignment, in
`services/progress.py` to find the same thing when recording an override, and in
`apply_progress_overrides` to go the other way, from a feed row to the override stored
against a line.

They did not merely repeat each other -- two of them disagreed. The report consulted the
assignment index first, so the assignment id always won. The override service scanned the
feed and took the first row satisfying either test, so row order won instead. A line
naming ASG-2 on activity ACT-1 paired with ASG-9 in one place and ASG-2 in the other
whenever ASG-9 shared the activity and came first, which meant an override's baseline
could be computed from a different assignment than the report had used for that line.

These tests pin the shared rule and, more importantly, pin that the three consumers give
the same answer for the same input. That second property is the one duplication broke, and
it is not visible from any single call site.
"""

import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.progress import (ProgressPairing, apply_progress_overrides,
                                         assignment_keys, line_keys)
from app.finance.domain.reports import calculate_live_report
from app.finance.services.progress import ProgressService
from app.finance.schemas.progress import ProgressOverrideCreate

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")
REF = UUID("30000000-0000-4000-8000-0000000001ff")
LINE = UUID("10000000-0000-4000-8000-000000000001")
RESOURCE = UUID("20000000-0000-4000-8000-000000000001")
SCOPE = SimpleNamespace(organization_id=ORG, project_id="p1", actor_user_id=ACTOR)

#: The line names both identifiers, and the feed carries a different assignment that
#: shares its activity and comes first. Both are ordinary: dev data has lines with both
#: ids, and a feed's row order is whatever the schedule source emitted.
LINE_MAPPING = {"id": LINE, "assignment_external_id": "ASG-2", "activity_external_id": "ACT-1"}
FEED_ROWS = [
    {"assignmentExternalId": "ASG-9", "actualQuantity": "9", "manualOverride": None,
     "task": {"activityCode": "ACT-1"}},
    {"assignmentExternalId": "ASG-2", "actualQuantity": "2", "manualOverride": None,
     "task": {"activityCode": "ACT-7"}},
]


def estimate_line(assignment, activity):
    return {"id": LINE, "resource_id": RESOURCE, "resource_type": "material",
            "resource_code": "mat", "resource_title": "material",
            "original_quantity": "10", "revised_quantity": "10",
            "original_unit_price_irr": "100", "current_unit_price_irr": "100",
            "assignment_external_id": assignment, "activity_external_id": activity,
            "progress_snapshot_id": SNAPSHOT}


class PairingRuleTests(unittest.TestCase):
    def index(self, rows=FEED_ROWS):
        return ProgressPairing(rows, assignment_keys)

    def test_the_assignment_id_wins_over_a_shared_activity_whatever_the_row_order(self):
        # The case the two copies answered differently. ASG-9 matches the line's activity
        # and comes first; ASG-2 is the line's own assignment.
        for order in (FEED_ROWS, list(reversed(FEED_ROWS))):
            with self.subTest(order=[row["assignmentExternalId"] for row in order]):
                paired = ProgressPairing(order, assignment_keys).match(*line_keys(LINE_MAPPING))
                self.assertEqual("ASG-2", paired["assignmentExternalId"])

    def test_the_activity_is_used_when_the_line_names_no_assignment(self):
        paired = self.index().match(*line_keys(
            {"assignment_external_id": None, "activity_external_id": "ACT-1"}))
        self.assertEqual("ASG-9", paired["assignmentExternalId"])

    def test_the_activity_is_used_when_the_named_assignment_matches_nothing(self):
        # A broken assignment reference still leaves the activity route open, which is the
        # behaviour both previous versions had.
        paired = self.index().match(*line_keys(
            {"assignment_external_id": "ASG-absent", "activity_external_id": "ACT-1"}))
        self.assertEqual("ASG-9", paired["assignmentExternalId"])

    def test_a_line_naming_nothing_matches_nothing(self):
        self.assertIsNone(self.index().match(None, None))
        # Blank strings are absent claims, not keys: looking one up could otherwise pair a
        # line with a feed row that also has a blank identifier.
        self.assertIsNone(self.index().match("", ""))

    def test_a_feed_row_with_no_identifiers_is_never_paired(self):
        blank = ProgressPairing([{"task": {}}, {"assignmentExternalId": None, "task": None},
                                 {"assignmentExternalId": "", "task": {"activityCode": ""}}],
                                assignment_keys)
        self.assertIsNone(blank.match("ASG-2", "ACT-1"))
        # A blank identifier is not indexed either, so two rows that both say nothing about
        # themselves cannot be paired with each other through the empty string.
        self.assertIsNone(blank.match("", ""))

    def test_the_last_row_wins_a_tie_as_it_always_did(self):
        # Both previous versions built plain dicts, so a repeated identifier resolved to the
        # last row. Preserved deliberately: changing it would move quantities.
        duplicated = [{"assignmentExternalId": "ASG-2", "actualQuantity": "1", "task": {}},
                      {"assignmentExternalId": "ASG-2", "actualQuantity": "2", "task": {}}]
        paired = ProgressPairing(duplicated, assignment_keys).match("ASG-2", None)
        self.assertEqual("2", paired["actualQuantity"])

    def test_the_same_object_runs_the_rule_backwards(self):
        # From a feed row to the override recorded against a line: the roles swap, the rule
        # does not. `keys` is what says which vocabulary the indexed rows speak.
        overrides = [{"assignment_external_id": "ASG-2", "activity_external_id": None, "tag": "own"},
                     {"assignment_external_id": None, "activity_external_id": "ACT-1", "tag": "shared"}]
        pairing = ProgressPairing(overrides, line_keys)
        self.assertEqual("own", pairing.match(*assignment_keys(FEED_ROWS[1]))["tag"])
        self.assertEqual("shared", pairing.match(*assignment_keys(FEED_ROWS[0]))["tag"])

    def test_the_two_key_readers_describe_the_same_pair_in_two_vocabularies(self):
        self.assertEqual(("ASG-2", "ACT-7"), assignment_keys(FEED_ROWS[1]))
        self.assertEqual(("ASG-2", "ACT-1"), line_keys(LINE_MAPPING))


class Repository:
    async def get_snapshot(self, _scope, _snapshot_id):
        return {"id": REF, "progress_snapshot_id": SNAPSHOT}

    async def get_line_mapping(self, _scope, _line_id):
        return dict(LINE_MAPPING)

    async def latest_overrides(self, _scope, _ref_id):
        return []

    async def append_override(self, _scope, value, _audit_id):
        return value


class Provider:
    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        return {"snapshot": {"organizationId": organization_id, "projectId": project_id,
                             "progressSnapshotId": snapshot_id},
                "assignments": [dict(row) for row in FEED_ROWS]}


class ConsumersAgreeTests(unittest.IsolatedAsyncioTestCase):
    """The property duplication broke: one line, one feed, one answer everywhere.

    Each consumer is asked which assignment it paired the line with, and each reports it in
    its own currency -- an executed quantity, an override baseline, a feed row carrying the
    override. The fixture gives the two candidate assignments different quantities so the
    answer is readable from any of them.
    """

    async def test_the_report_and_the_override_service_pair_the_line_the_same_way(self):
        report = calculate_live_report([estimate_line("ASG-2", "ACT-1")], [],
                                       [dict(row) for row in FEED_ROWS], [], "10")
        service = ProgressService(Repository(), Provider(), id_factory=uuid4,
                                  clock=lambda: datetime(2026, 8, 2, tzinfo=timezone.utc))
        override = await service.override(
            SCOPE, LINE, ProgressOverrideCreate(progressSnapshotId=SNAPSHOT,
                                                overrideValue="5", reason="اصلاح معتبر"))
        # 2 is ASG-2's quantity, 9 is ASG-9's. Before the consolidation this was (2, 9).
        self.assertEqual(Decimal("2"), report.quantity_variances[0]["executedQuantity"])
        self.assertEqual(Decimal("2"), override.computed_value)

    async def test_an_override_is_applied_to_the_row_the_report_read(self):
        stored = [{"estimate_line_id": LINE, "computed_value": Decimal("2"),
                   "override_value": Decimal("5"), "reason": "اصلاح معتبر",
                   "created_by": ACTOR, "created_at": datetime(2026, 8, 2, tzinfo=timezone.utc),
                   "assignment_external_id": "ASG-2", "activity_external_id": "ACT-1"}]
        applied = apply_progress_overrides([dict(row) for row in FEED_ROWS], stored, SNAPSHOT)
        carrying = [row["assignmentExternalId"] for row in applied if row.get("manualOverride")]
        # KNOWN DEFECT, pinned rather than fixed. The override names both identifiers, so
        # it lands on ASG-2 by assignment id AND on ASG-9 by shared activity: one override,
        # two feed rows. A second estimate line pairing with ASG-9 would then read a
        # quantity that was corrected for a different line.
        #
        # This is not a regression -- the previous code matched each feed row the same way,
        # and a before/after capture of the development database returned byte-identical
        # responses. Narrowing it moves executed quantities, which is a financial decision
        # and out of scope for consolidating the rule. The assertion states what the system
        # does today so the behaviour cannot change unnoticed.
        self.assertEqual(["ASG-9", "ASG-2"], carrying)

    async def test_all_three_consumers_change_together_when_the_line_moves(self):
        # Point the line at the activity only. Every consumer must follow to ASG-9.
        line = dict(LINE_MAPPING, assignment_external_id=None)

        class ActivityOnlyRepository(Repository):
            async def get_line_mapping(self, _scope, _line_id):
                return dict(line)

        report = calculate_live_report([estimate_line(None, "ACT-1")], [],
                                       [dict(row) for row in FEED_ROWS], [], "10")
        service = ProgressService(ActivityOnlyRepository(), Provider(), id_factory=uuid4,
                                  clock=lambda: datetime(2026, 8, 2, tzinfo=timezone.utc))
        override = await service.override(
            SCOPE, LINE, ProgressOverrideCreate(progressSnapshotId=SNAPSHOT,
                                                overrideValue="5", reason="اصلاح معتبر"))
        stored = [{"estimate_line_id": LINE, "computed_value": Decimal("9"),
                   "override_value": Decimal("5"), "reason": "اصلاح معتبر",
                   "created_by": ACTOR, "created_at": datetime(2026, 8, 2, tzinfo=timezone.utc),
                   "assignment_external_id": None, "activity_external_id": "ACT-1"}]
        applied = apply_progress_overrides([dict(row) for row in FEED_ROWS], stored, SNAPSHOT)
        self.assertEqual(Decimal("9"), report.quantity_variances[0]["executedQuantity"])
        self.assertEqual(Decimal("9"), override.computed_value)
        self.assertEqual(["ASG-9"], [row["assignmentExternalId"] for row in applied
                                     if row.get("manualOverride")])


class NoSecondCopyTests(unittest.TestCase):
    """The rule may not be written a fourth time.

    A grep, deliberately: the point of consolidating is that a new call site cannot quietly
    re-derive the pairing, and only reading the source can tell whether one has.
    """

    SOURCES = ("app/finance/domain/reports.py", "app/finance/services/progress.py",
               "app/finance/services/reports.py")

    def test_no_consumer_reads_the_feed_identifiers_for_itself(self):
        for name in self.SOURCES:
            with self.subTest(name):
                source = (BACKEND_ROOT / name).read_text(encoding="utf-8")
                self.assertNotIn('get("assignmentExternalId")', source)
                self.assertNotIn('get("activityCode")', source)

    def test_the_rule_lives_in_exactly_one_place(self):
        domain = (BACKEND_ROOT / "app/finance/domain/progress.py").read_text(encoding="utf-8")
        # assignment_keys is the only reader of the feed's vocabulary, and ProgressPairing
        # the only place the precedence between the two identifiers is decided.
        self.assertEqual(1, domain.count('get("assignmentExternalId")'))
        self.assertEqual(1, domain.count('get("activityCode")'))
        self.assertEqual(1, domain.count("class ProgressPairing"))


if __name__ == "__main__":
    unittest.main()
