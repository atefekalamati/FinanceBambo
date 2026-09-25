# -*- coding: utf-8 -*-
"""Which currency a schedule's amounts are in, and who is allowed to answer.

The file cannot answer it. `test_progress.mpp` states `currencySymbol = تومان` and
`currencyCode = IRR`, and those two disagree: believing the symbol stores toman as rial
and every cost is a tenth of the truth, believing the code does the reverse. So the answer
comes from a person, recorded against exact bytes -- first in a frozenset in code, and
since 0023 also in `finance_mpp_currency_decisions`, which can record WHO decided, WHEN,
and on what evidence.

These tests pin the precedence and, more importantly, pin the refusal: a file nobody has
decided about is refused outright, with the code `MPP_CURRENCY_UNRESOLVED`. That is
stronger than storing nulls, and deliberately so -- a half-stored version whose costs
happen to be null is something a report will read and average, while a version that was
never written is something an operator has to look at.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_mpp_sync import (APPROVED_TOMAN_SHA256, FinanceMppSyncRefused,
                                      finance_rows)

#: The bytes the toman decision was already taken for, in code, before 0023 existed.
APPROVED_SHA = "b86b63738f592bfd90286ab08daedcea4374d815c02a7503adc18182cec6e908"

#: The file staged on disk today. MS Project re-saved the schedule -- same figures, new
#: container, new digest -- so the frozenset does not cover it and never will without a
#: deploy. This is exactly the case 0023 exists for.
RESAVED_SHA = "55cfe5dc6881813387851c4ae15eaeecf7bfa465dbf41113749d48e2f15fa289"

#: One assignment costing 1,000 toman. Small enough to read the arithmetic off the page.
COST_TOMAN = "1000.0"


class ParsedFile:
    def __init__(self, currency_symbol="تومان", currency_code="IRR"):
        self.tasks = [{"uid": 1212, "name": "تجهیز کارگاه", "wbs": "1.4.2",
                       "raw_fields": {}, "metrics": dict.fromkeys(
                           ("weight_rial", "weight_time", "weight_base",
                            "actual_progress", "actual_progress_percent",
                            "physical_progress", "planned_progress", "task_cost",
                            "task_actual_cost", "task_fixed_cost"))}]
        self.resources = [{"uid": 155, "name": "تجهیز مستمر", "native_type": "MATERIAL",
                           "initials": "واحد", "material_label": None, "quantity": "1.0",
                           "quantity_unit": "واحد", "quantity_unit_source": "initials",
                           "standard_rate": COST_TOMAN}]
        self.assignments = [{"assignment_uid": 9703, "task_uid": 1212, "resource_uid": 155,
                             "units": "100.0", "planned_quantity": "1.0",
                             "cost": COST_TOMAN, "planned_work": "1.0"}]
        self.warnings, self.parser_engine = [], "test-engine"
        self.currency_symbol, self.currency_code = currency_symbol, currency_code


def row(sha=APPROVED_SHA, decision=None, **file_currency):
    rows = finance_rows(ParsedFile(**file_currency), source_sha256=sha,
                        recorded_decision=decision)
    return next(r for r in rows if r["source_assignment_uid"] is not None)


class TheApprovalAlreadyInCodeTests(unittest.TestCase):
    """0023 widens the question. It must not change the answer already given."""

    def test_the_approved_file_still_converts_toman_to_rials_with_no_decision_row(self):
        # The deployment that has not run 0023 yet, and every existing test.
        self.assertEqual(Decimal("10000"), row()["source_assignment_cost_irr"])

    def test_the_approved_sha_is_still_in_the_frozenset(self):
        self.assertIn(APPROVED_SHA, APPROVED_TOMAN_SHA256)

    def test_the_resaved_file_is_deliberately_not_in_the_frozenset(self):
        # If somebody adds it here instead of recording a decision, this fails and says
        # why: the point of 0023 is that approvals stop needing a deploy.
        self.assertNotIn(RESAVED_SHA, APPROVED_TOMAN_SHA256)


class NobodyHasDecidedTests(unittest.TestCase):
    def test_a_resaved_file_with_no_decision_is_refused_rather_than_stored(self):
        # Not "stored with null costs". The whole sync stops, no version row is written,
        # and the reason is a code an operator can act on.
        with self.assertRaises(FinanceMppSyncRefused) as refusal:
            row(sha=RESAVED_SHA)
        self.assertEqual("MPP_CURRENCY_UNRESOLVED", refusal.exception.code)

    def test_the_refusal_names_the_file_rather_than_the_amount(self):
        # An operator reading this has to know the fix is a decision about the file, not a
        # correction to one row.
        with self.assertRaises(FinanceMppSyncRefused) as refusal:
            row(sha=RESAVED_SHA)
        self.assertIn("source file", str(refusal.exception))

    def test_a_currency_nobody_recognises_is_refused_even_for_approved_bytes(self):
        # Approval is per-file, and it is approval of what the amounts ARE. It cannot make
        # euros readable.
        with self.assertRaises(FinanceMppSyncRefused):
            row(currency_symbol="€", currency_code="EUR")


class ARecordedDecisionTests(unittest.TestCase):
    def test_toman_multiplies_by_exactly_ten_once(self):
        decided = row(sha=RESAVED_SHA, decision="toman")
        self.assertEqual(Decimal("10000"), decided["source_assignment_cost_irr"])
        self.assertEqual(Decimal("10000"), decided["source_resource_rate_irr"])

    def test_rial_multiplies_by_nothing(self):
        decided = row(sha=RESAVED_SHA, decision="rial")
        self.assertEqual(Decimal("1000"), decided["source_assignment_cost_irr"])

    def test_unknown_is_a_finding_and_refuses_exactly_as_silence_does(self):
        # "Somebody looked and could not tell" is worth recording, and it must not be
        # weaker than never having looked.
        with self.assertRaises(FinanceMppSyncRefused) as refusal:
            row(sha=RESAVED_SHA, decision="unknown")
        self.assertEqual("MPP_CURRENCY_UNRESOLVED", refusal.exception.code)

    def test_a_decision_outranks_a_file_that_plainly_states_rials(self):
        # A file can say IRR and still hold toman -- that is how this whole problem
        # started. A person who read the amounts beats the file's own label.
        decided = row(sha=RESAVED_SHA, decision="toman",
                      currency_symbol="ریال", currency_code="IRR")
        self.assertEqual(Decimal("10000"), decided["source_assignment_cost_irr"])

    def test_unknown_outranks_a_file_that_plainly_states_rials(self):
        # The plain-rial branch would otherwise guess, and a recorded "we could not tell"
        # is precisely the evidence that the guess is not safe here.
        with self.assertRaises(FinanceMppSyncRefused):
            row(sha=RESAVED_SHA, decision="unknown",
                currency_symbol="ریال", currency_code="IRR")

    def test_a_decision_never_multiplies_twice(self):
        # The conversion happens once, on the way in. A rate and a cost from the same row
        # must scale identically rather than one of them compounding.
        decided = row(sha=RESAVED_SHA, decision="toman")
        self.assertEqual(decided["source_assignment_cost_irr"],
                         decided["source_resource_rate_irr"])


class TheMigrationTests(unittest.TestCase):
    """The table the decision is read from has to exist, and stay append-only."""

    def setUp(self):
        self.source = (BACKEND_ROOT / "alembic" / "versions"
                       / "0023_mpp_currency_decisions.py").read_text(encoding="utf-8")

    def test_the_evidence_column_may_not_be_blank(self):
        # A decision nobody explained is one nobody can review.
        self.assertIn("evidence text NOT NULL", self.source)
        self.assertIn("length(btrim(evidence)) > 0", self.source)

    def test_only_the_three_answers_are_storable(self):
        self.assertIn("amounts_are IN ('toman', 'rial', 'unknown')", self.source)

    def test_a_decision_cannot_be_edited_or_deleted_after_the_fact(self):
        self.assertIn("finance_reject_mutation", self.source)
        self.assertIn("BEFORE UPDATE OR DELETE", self.source)

    def test_the_sha_is_pinned_to_a_full_digest(self):
        self.assertIn("length(source_sha256) = 64", self.source)


if __name__ == "__main__":
    unittest.main()
