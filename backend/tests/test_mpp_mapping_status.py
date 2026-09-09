# -*- coding: utf-8 -*-
"""What became of every row of the schedule, counted and not computed.

What these defend: the three states are exhaustive, so their counts sum to the total. A
status that does not add up is worse than none — it invites a reader to believe the rows
it quietly left out do not exist. And the status reads: it must never write, and must
never produce a financial figure.
"""

import asyncio
import re
import sys
import unittest
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint import finance_mpp_mapping
from coreint.finance_mpp_mapping import FinanceMppMappingService

ORG = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")


class Cursor:
    """Answers the statements the status asks, as the database would."""

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
        elif "source_assignment_uid AS assignment_uid" in text:
            self._rows = list(self._c.stray)
        else:
            self._rows = list(self._c.counted)

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class Connection:
    def __init__(self, counted=(), version=VERSION, stray=()):
        self.counted, self.version, self.stray = list(counted), version, list(stray)
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def cursor(self, **_kwargs):
        return Cursor(self)


def counted(status, rows, stage_labels=0, without_resource=0):
    return {"status": status, "rows": rows, "stage_labels": stage_labels,
            "assignments_without_resource": without_resource}


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class MappingStatusTests(unittest.TestCase):
    def service(self, connection):
        async def factory():
            return connection
        return FinanceMppMappingService(factory)

    def test_the_states_are_exhaustive_and_sum_to_the_total(self):
        connection = Connection([counted("assignment_mapped", 715),
                                 counted("activity_only", 74, 62, 12)])
        status = run(self.service(connection).mapping_status(ORG, "terrace"))
        self.assertEqual(789, status["total"])
        self.assertEqual(715 + 74 + 0,
                         status["assignmentMapped"] + status["activityOnly"] + status["unclassified"])
        self.assertEqual(status["total"],
                         status["assignmentMapped"] + status["activityOnly"] + status["unclassified"])

    def test_the_two_kinds_of_activity_only_are_told_apart(self):
        # A stage heading never had an assignment; a milestone has one that names nobody.
        connection = Connection([counted("activity_only", 74, 62, 12)])
        status = run(self.service(connection).mapping_status(ORG, "terrace"))
        self.assertEqual({"stageLabelRows": 62, "assignmentsWithoutResource": 12},
                         status["activityOnlyDetail"])

    def test_an_unexpected_state_is_named_and_listed(self):
        connection = Connection(
            [counted("assignment_mapped", 700), counted("unclassified", 2)],
            stray=[{"assignment_uid": 91, "resource_uid": 12, "task_wbs": "1.2",
                    "task_name": "کار", "resource_name": "سیمان"}])
        status = run(self.service(connection).mapping_status(ORG, "terrace"))
        self.assertEqual(2, status["unclassified"])
        self.assertEqual([{"sourceAssignmentUid": 91, "sourceResourceUid": 12,
                           "wbsCode": "1.2", "taskName": "کار", "resourceName": "سیمان"}],
                         status["unclassifiedRows"])

    def test_no_schedule_imported_reports_nothing_rather_than_failing(self):
        status = run(self.service(Connection(version=None)).mapping_status(ORG, "terrace"))
        self.assertEqual(0, status["total"])
        self.assertIsNone(status["sourceVersionId"])
        self.assertEqual([], status["unclassifiedRows"])

    def test_it_only_ever_reads(self):
        connection = Connection([counted("assignment_mapped", 1)])
        run(self.service(connection).mapping_status(ORG, "terrace"))
        for statement in connection.statements:
            # Starts with SELECT and contains no write verb. Matched on whole words so
            # that `deleted_at` -- which every one of these statements reads -- is not
            # mistaken for a DELETE.
            self.assertTrue(statement.upper().lstrip().startswith("SELECT"), statement)
            for write in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE"):
                self.assertNotIn(write, re.findall(r"[A-Z]+", statement.upper()))

    def test_it_never_reads_a_financial_figure(self):
        # It counts rows. A quantity, a price or a cost appearing here would be the first
        # step towards a status that quietly became a calculation.
        for sql in (finance_mpp_mapping._MAPPING_STATUS, finance_mpp_mapping._UNCLASSIFIED_ROWS):
            for column in ("original_quantity", "original_unit_price_irr", "source_cost",
                           "source_assignment_cost_irr", "source_assignment_units",
                           "unit_price", "price_versions"):
                self.assertNotIn(column, sql)

    def test_it_reads_only_the_version_in_force(self):
        for sql in (finance_mpp_mapping._MAPPING_STATUS, finance_mpp_mapping._UNCLASSIFIED_ROWS):
            self.assertIn("source_version_id = %(version_id)s", sql)


if __name__ == "__main__":
    unittest.main()
