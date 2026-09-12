import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.attachments import FILE_TRANSITIONS, require_file_transition
from app.finance.schemas.extractions import ExtractionDraftResponse


INVOICE_STATES = ("draft", "awaitingConfirmation", "confirmed", "voided", "corrected")
REVIEW_STATES = ("awaitingReview", "accepted", "rejected")
FILE_STATES = ("uploaded", "processing", "ready", "failed")


class ThreeLifecyclesStayApartTests(unittest.TestCase):
    """AT-27 / Integration Kit 05: three state machines, never one.

    The kit is explicit that a single generic `status` must not serve attachment
    processing, AI review and the invoice: «Do not use one generic `status` ... They are
    separate fields and separate state machines», and then names the failure it is guarding
    against -- «`processingStatus` never becomes `confirmed`, `voided`, or `corrected`.
    Those are invoice concepts.»

    The existing suite already proves the happy path stays independent: a ready file beside
    an `awaitingReview` draft beside a `draft` invoice with a financial effect of exactly
    zero. What it never asserted is the negative -- that the vocabularies cannot bleed into
    one another. That is what this adds, because the day someone adds a shared constant is
    the day a file going `ready` starts reading as money.
    """

    def test_file_vocabulary_never_borrows_an_invoice_word(self):
        words = set(FILE_TRANSITIONS) | {t for targets in FILE_TRANSITIONS.values() for t in targets}
        self.assertEqual(set(FILE_STATES), words)
        for invoice_word in ("confirmed", "voided", "corrected", "awaitingConfirmation"):
            self.assertNotIn(invoice_word, words,
                             "the file lifecycle accepts the invoice word %r" % invoice_word)

    def test_file_lifecycle_refuses_a_transition_named_after_an_invoice(self):
        for current in FILE_STATES:
            for invoice_word in ("confirmed", "voided", "corrected"):
                with self.assertRaises(ValueError):
                    require_file_transition(current, invoice_word)

    def test_review_vocabulary_never_borrows_an_invoice_or_file_word(self):
        overlap = set(REVIEW_STATES) & (set(INVOICE_STATES) | set(FILE_STATES))
        self.assertEqual(set(), overlap,
                         "the review lifecycle shares a word with another machine: %s" % overlap)

    def test_the_draft_carries_three_separate_fields_not_one_status(self):
        fields = ExtractionDraftResponse.model_fields
        for name in ("review_status", "invoice_status"):
            self.assertIn(name, fields, "the draft collapsed %s into something else" % name)
        self.assertNotIn("status", fields,
                         "a generic `status` reappeared on the extraction draft")

    def test_ready_is_terminal_so_a_file_cannot_walk_into_a_financial_state(self):
        self.assertEqual(set(), FILE_TRANSITIONS["ready"],
                         "a ready file can still transition; the next word added is the risk")


if __name__ == "__main__":
    unittest.main()
