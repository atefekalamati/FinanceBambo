# -*- coding: utf-8 -*-
"""A price revision may be recorded without a sentence explaining it.

WHY THIS CHANGED

`reason` was required by the schema, by a CHECK and by `PriceCreate`. The row already
records `created_by` and `created_at`, neither of which can be omitted, and for an
ordinary equipment rate revision that is the evidence a reader needs.

Requiring more produced less. A client that MUST send something sends something: the UI
was generating a sentence purely to pass validation, so the history filled with text that
reads like a recorded reason and records nothing. A visible blank is more honest than a
placeholder nobody can tell from a real one.

What is still refused is a blank pretending to be a reason. Absent and empty are different
statements and only one of them is true, so `"   "` normalises to None at the boundary and
the database rejects it outright if anything gets past.
"""

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.schemas.prices import PriceCreate


def payload(**overrides):
    values = {"scopeKind": "project", "unitPriceIrr": "1500000",
              "effectiveFrom": "2026-09-22"}
    values.update(overrides)
    return values


class ReasonIsOptionalTests(unittest.TestCase):
    def test_a_price_may_be_created_with_no_reason_at_all(self):
        command = PriceCreate(**payload())
        self.assertIsNone(command.reason)
        self.assertEqual(Decimal("1500000"), command.unit_price_irr)
        self.assertEqual(date(2026, 9, 22), command.effective_from)

    def test_an_explicit_null_is_accepted(self):
        self.assertIsNone(PriceCreate(**payload(reason=None)).reason)

    def test_a_real_reason_is_kept_and_trimmed(self):
        command = PriceCreate(**payload(reason="  بازنگری نرخ ساعتی جرثقیل  "))
        self.assertEqual("بازنگری نرخ ساعتی جرثقیل", command.reason)

    def test_a_blank_reason_becomes_absent_rather_than_an_empty_string(self):
        """The placeholder problem, refused at the boundary.

        An empty string stored as a reason is indistinguishable from an attempt at one.
        Normalising it to None means the history says "nobody wrote a reason", which is
        what actually happened.
        """
        for blank in ("", "   ", "\t", "\n  "):
            with self.subTest(repr(blank)):
                self.assertIsNone(PriceCreate(**payload(reason=blank)).reason)

    def test_the_other_fields_are_still_required(self):
        """Relaxing one field must not relax the rest."""
        from pydantic import ValidationError

        for missing in ("scopeKind", "unitPriceIrr", "effectiveFrom"):
            with self.subTest(missing):
                values = payload()
                values.pop(missing)
                with self.assertRaises(ValidationError):
                    PriceCreate(**values)

    def test_a_negative_price_is_still_refused(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            PriceCreate(**payload(unitPriceIrr="-1"))


class DomainCarriesTheAbsenceTests(unittest.TestCase):
    def test_the_price_version_accepts_no_reason(self):
        from uuid import uuid4

        from app.finance.domain.prices import PriceVersion

        version = PriceVersion(uuid4(), uuid4(), "terrace", uuid4(), "project", 1,
                               Decimal("1500000"), date(2026, 9, 22), None, uuid4(),
                               date(2026, 9, 22))
        self.assertIsNone(version.reason)


if __name__ == "__main__":
    unittest.main()
