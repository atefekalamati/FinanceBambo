# -*- coding: utf-8 -*-
"""Which column the importer will call a daily quantity, and which it will not.

The rule this pins is the one that costs money if it is wrong. MS Project writes 0.0 into
every Number column nobody filled, and MPXJ hands that back indistinguishably from a
deliberate zero. Reading those zeros as "this line uses none today" would take every daily
estimate on the project to zero on the strength of an empty column -- a change that looks
like data rather than like a bug.

Measured on this project's own schedule, which is why the rule exists:

    «حجم اولیه»      initial volume    328 tasks state it, 0 non-zero
    «احجام کاری»      working volumes   328 state it, 0 non-zero
    «حجم انجام شده»   completed volume  328 state it, 0 non-zero
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_quantity import (APPROVED_DAILY_QUANTITY_ALIASES,
                                      APPROVED_QUANTITY_ALIASES, approved_daily_quantity,
                                      approved_quantity)


def task(**raw):
    return {"uid": 1, "name": "t", "raw_fields": raw}


class DailyQuantityReaderTests(unittest.TestCase):
    def test_7_a_stated_daily_quantity_is_read_with_the_column_it_came_from(self):
        value, field = approved_daily_quantity(task(**{"حجم انجام شده": "80"}))
        self.assertEqual(Decimal("80"), value)
        self.assertEqual("حجم انجام شده", field)

    def test_8_a_column_ms_project_left_empty_stays_null(self):
        # 0.0 is what an untouched Number column contains. Treating it as a stated zero is
        # the expensive mistake this rule exists to refuse.
        self.assertEqual((None, None), approved_daily_quantity(task(**{"حجم انجام شده": "0.0"})))
        self.assertEqual((None, None), approved_daily_quantity(task(**{"حجم انجام شده": "0"})))

    def test_8b_a_file_stating_no_such_column_yields_null(self):
        self.assertEqual((None, None), approved_daily_quantity(task(**{"ضریب وزنی ریالی": "5"})))
        self.assertEqual((None, None), approved_daily_quantity(task()))

    def test_the_alias_list_is_matched_case_insensitively(self):
        value, field = approved_daily_quantity(task(**{"Daily Quantity": "12.5"}))
        self.assertEqual(Decimal("12.5"), value)
        self.assertEqual("Daily Quantity", field)

    def test_5_a_percentage_column_is_not_a_daily_quantity(self):
        # Assignment Units of 100 means 100%, and no aliased percentage column is on the
        # list. Nothing here can promote one by accident.
        self.assertNotIn("درصد احجام کاری", APPROVED_DAILY_QUANTITY_ALIASES)
        self.assertNotIn("درصد پیشرفت واقعی", APPROVED_DAILY_QUANTITY_ALIASES)
        self.assertEqual((None, None),
                         approved_daily_quantity(task(**{"درصد احجام کاری": "100"})))

    def test_6_the_baseline_and_the_daily_lists_are_separate_decisions(self):
        # Adding a spelling to either is a reviewable act; sharing one list would make a
        # baseline column start being read as today's figure the moment somebody added it.
        self.assertEqual((), tuple(set(APPROVED_QUANTITY_ALIASES)
                                   & set(APPROVED_DAILY_QUANTITY_ALIASES)))

    def test_the_daily_reader_never_falls_back_to_the_baseline_column(self):
        # 4.2: "do not copy quantity into daily_quantity during import".
        row = task(**{"مقدار": "500"})
        self.assertEqual((Decimal("500"), None), approved_quantity(row))
        self.assertEqual((None, None), approved_daily_quantity(row))


class ImporterWiringTests(unittest.TestCase):
    """That the reader is actually used, and its value actually stored."""

    def test_the_row_builder_reads_the_daily_column(self):
        source = (BACKEND_ROOT / "coreint" / "finance_mpp_sync.py").read_text(encoding="utf-8")
        self.assertIn("approved_daily_quantity(task)", source)
        self.assertIn('"source_daily_quantity": daily_quantity', source)
        self.assertIn('"source_daily_quantity_field": daily_quantity_field', source)

    def test_the_columns_are_in_the_insert(self):
        from coreint.finance_mpp_sync import _COLUMNS
        self.assertIn("source_daily_quantity", _COLUMNS)
        self.assertIn("source_daily_quantity_field", _COLUMNS)

    def test_9_the_same_file_read_twice_yields_the_same_values(self):
        # Idempotence at the reader: the same task gives the same answer every time, so a
        # re-sync of unchanged bytes cannot drift.
        row = task(**{"حجم انجام شده": "80"})
        self.assertEqual(approved_daily_quantity(row), approved_daily_quantity(row))


if __name__ == "__main__":
    unittest.main()
