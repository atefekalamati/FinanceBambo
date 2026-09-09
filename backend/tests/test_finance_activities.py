# -*- coding: utf-8 -*-
"""The activity catalogue, and the schedule cost it carries.

What these defend: the cost the page shows beside an activity is the schedule's figure for
that activity, read once -- not summed over the activity's assignments, which would
multiply it by however many items the activity has, and not attributed to any one item,
which the file does not say.
"""

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint import finance_activities
from coreint.finance_activities import FinanceRowsActivityProvider

ORG = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")


class Cursor:
    """Answers the three statements the provider issues, as the database would."""

    def __init__(self, connection):
        self._c = connection
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self._c.statements.append(text)
        if "FROM finance_mpp_source_versions" in text:
            self._rows = [] if self._c.version is None else [{"id": self._c.version}]
        elif "source_assignment_units" in text:
            self._rows = list(self._c.assignments)
        else:
            self._rows = list(self._c.catalogue)

    async def fetchall(self):
        return self._rows


class Connection:
    def __init__(self, catalogue=(), version=VERSION, assignments=()):
        self.catalogue, self.version = list(catalogue), version
        self.assignments = list(assignments)
        self.statements = []

    def cursor(self, **_kwargs):
        return Cursor(self)


def row(code, title, task_uid, task_cost):
    return {"code": code, "title": title, "task_uid": task_uid, "task_cost": task_cost}


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class ActivityCatalogueTests(unittest.TestCase):
    def catalogue(self, rows, version=VERSION, assignments=()):
        connection = Connection(rows, version, assignments)
        return connection, FinanceRowsActivityProvider(connection)

    def test_an_activity_carries_the_schedules_cost_for_it(self):
        _, provider = self.catalogue([row("1.5.2.9", "اجرای بتن پیش ساخته دال", 252,
                                          Decimal("11838737372"))])
        rows, total = run(provider.list_activities(ORG, "terrace"))
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["mppTaskCostIrr"], Decimal("11838737372"))
        self.assertEqual(rows[0]["wbsCode"], "1.5.2.9")
        self.assertEqual(rows[0]["title"], "اجرای بتن پیش ساخته دال")

    def test_a_cost_the_query_could_not_resolve_is_none_and_not_zero(self):
        _, provider = self.catalogue([row("1.6", "اصلاح هندسی بلوار شاهنامه", 300, None)])
        rows, _total = run(provider.list_activities(ORG, "terrace"))
        self.assertIsNone(rows[0]["mppTaskCostIrr"])
        self.assertNotEqual(rows[0]["mppTaskCostIrr"], 0)

    def test_a_cost_the_schedule_states_as_zero_stays_zero(self):
        # Zero is a figure the file gives, unlike absence. The two must not merge.
        _, provider = self.catalogue([row("1.7", "تحویل زمین", 301, Decimal("0"))])
        rows, _total = run(provider.list_activities(ORG, "terrace"))
        self.assertEqual(rows[0]["mppTaskCostIrr"], Decimal("0"))
        self.assertIsNotNone(rows[0]["mppTaskCostIrr"])

    def test_the_activity_total_sums_its_own_assignments_and_never_the_task_column(self):
        # `source_cost` holds the TASK's figure repeated on every one of its rows, so
        # adding it up counts it once per assignment -- and on a summary task it is a
        # rollup of children that none of the visible rows accounts for. The assignment
        # column is per assignment, so summing THAT is what the header means.
        statement = " ".join(finance_activities._ACTIVITIES.split())
        self.assertIn("sum(source_assignment_cost_irr)", statement)
        self.assertNotIn("sum(source_cost)", statement)
        self.assertNotIn("min(source_cost)", statement)

    def test_no_imported_schedule_means_an_empty_catalogue_not_a_failure(self):
        _, provider = self.catalogue([row("1.1", "هر چیزی", 1, Decimal("5"))], version=None)
        rows, total = run(provider.list_activities(ORG, "terrace"))
        self.assertEqual((rows, total), ([], 0))

    def test_the_catalogue_never_reports_a_price(self):
        # A Finance price lives in price_versions and a person enters it. Nothing the
        # activity catalogue answers may be mistaken for one.
        _, provider = self.catalogue([row("1.5.2.9", "اجرای بتن پیش ساخته دال", 252,
                                          Decimal("11838737372"))])
        rows, _total = run(provider.list_activities(ORG, "terrace"))
        self.assertEqual([key for key in rows[0] if "rice" in key], [])


if __name__ == "__main__":
    unittest.main()
