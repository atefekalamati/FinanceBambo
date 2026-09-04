# -*- coding: utf-8 -*-
"""A date must never become an activity code.

WHY THIS FILE EXISTS
`ACTIVITY_CODE_FIELDS` is `("text1", "outline_number", "wbs")` and its own docstring calls
the first entry a guess: Text1 holding an activity code is a planning convention, not a
schema fact. The docstring reasons that a wrong guess "shows up as unmapped lines, which is
visible, rather than as wrong pairings, which would not be".

That reasoning holds only while Text1 is empty. A real BAMBO schedule --
`Sources/زمان بندی پل.mpp`, 328 tasks -- fills Text1 on **every** task with a Jalali date
such as `1404/5/18`. The guess then does not fail visibly; it succeeds into the wrong value.
Measured against that file: the default order yields 128 distinct "activity codes" that are
dates, the worst shared by 27 assignments, while `("outline_number", "wbs")` yields 266
structural codes with a worst case of 7.

Pairing an estimate line to a date is not a near miss. Every task that happens to share a
status date becomes one activity, and a correction meant for one line reaches all of them.

WHAT IS AND IS NOT ASSERTED HERE
These tests change no behaviour and assert none into existence. They prove the guarantee
holds under the field order a host *can already* configure, and they pin the current default
so that changing it is a deliberate, visible act rather than a silent one. The default is
not asserted to be correct -- `test_the_default_order_still_admits_a_date` exists to fail
the day someone fixes it, which is exactly when this file should be re-read.
"""

import re
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint import activities as core_activities
from coreint import progress as core_progress

ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = "sample_site_01"

#: The order that reads the activity code from the schedule's structure rather than from a
#: free-text column. `outline_number` is what Core's own task query orders by and is present
#: on every task; `wbs` backs it up.
STRUCTURAL_FIELDS = ("outline_number", "wbs")

#: Date shapes seen in, or plausible for, a Text1 column: Jalali and Gregorian, both
#: separators, with or without zero padding. Deliberately a test-local rule -- production
#: code is not being taught to sniff dates here, and a matcher that lived in the adapter
#: would be a behaviour change this file is not allowed to make.
DATE_SHAPE = re.compile(r"^\s*\d{4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,2}\s*$")

#: Exactly what the reference file holds: one Jalali status date, repeated across tasks.
JALALI_DATES = ("1404/5/18", "1404/7/1", "1404/7/9", "1405-06-12", "1404.8.3")


def looks_like_a_date(value):
    return bool(value) and bool(DATE_SHAPE.match(str(value)))


SNAPSHOT_ROW = {
    "id": 9003, "project_id": PROJECT, "file_version_id": 1003, "snapshot_type": "ACTUAL",
    "previous_snapshot_id": None, "source_filename": "bridge.mpp",
    "status_date_jalali": "1405-05-11", "created_by": None,
    "created_at": datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc),
    "organization_id": ORG, "original_filename": "bridge.mpp",
    "version_number": 1, "superseded": False,
}


def task(uid, text1, outline):
    """One msp_tasks row shaped like the reference file: Text1 is a date, structure is not."""
    return {"id": uid, "uid": uid, "guid": None, "task_id": uid, "name": "کار %d" % uid,
            "wbs": outline, "outline_number": outline, "outline_level": outline.count(".") + 1,
            "start": "2026-06-01", "finish": "2026-08-30",
            "percent_complete": Decimal("0"), "percent_work_complete": Decimal("0"),
            "physical_percent_complete": None, "text1": text1}


#: A miniature of the real file: distinct structure, dates repeating across tasks.
BRIDGE_TASKS = tuple(
    task(index + 1, JALALI_DATES[index % len(JALALI_DATES)], "1.%d" % (index + 1))
    for index in range(12))


class FakeCursor:
    def __init__(self, answer, log):
        self._answer, self._log, self._rows = answer, log, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        self._log.append((str(sql), params))
        self._rows = self._answer(str(sql), params or {})

    async def fetchall(self):
        return list(self._rows)

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, answer):
        self._answer, self.log = answer, []

    def cursor(self, **_kwargs):
        return FakeCursor(self._answer, self.log)


def connection(tasks=BRIDGE_TASKS):
    """Answers the queries both adapters ask. No assignment tables, so the task feed is used.

    The task-level feed is the right shape for this question: the activity code is read from
    the task in either feed, and this keeps the test about one thing.
    """
    def answer(sql, _params):
        if "to_regclass" in sql or "information_schema" in sql:
            return [{"present": 0}]
        if "FROM msp_tasks" in sql:
            return [dict(row) for row in tasks]
        if "FROM msp_snapshots" in sql:
            return [dict(SNAPSHOT_ROW)]
        return []
    return FakeConnection(answer)


class ActivityCodeIsNotADateTests(unittest.IsolatedAsyncioTestCase):
    def test_the_reference_files_text1_values_are_all_dates(self):
        """The premise, asserted rather than assumed.

        If Text1 in the fixture were not date-shaped, every test below would pass for the
        wrong reason.
        """
        for value in JALALI_DATES:
            with self.subTest(value=value):
                self.assertTrue(looks_like_a_date(value))
        self.assertFalse(looks_like_a_date("ACT-102"))
        self.assertFalse(looks_like_a_date("1.4.2"))
        self.assertFalse(looks_like_a_date(None))

    def test_structural_fields_never_yield_a_date(self):
        """`activity_code` given the structural order returns structure, whatever Text1 says."""
        for row in BRIDGE_TASKS:
            with self.subTest(uid=row["uid"]):
                code = core_progress.activity_code(row, STRUCTURAL_FIELDS)
                self.assertFalse(looks_like_a_date(code),
                                 "activity code %r is a date" % code)
                self.assertEqual(row["outline_number"], code)

    async def test_the_progress_feed_emits_no_date_as_an_activity_code(self):
        """End to end through the provider, not just the helper."""
        provider = core_progress.CoreProgressSnapshotProvider(
            connection(), activity_code_fields=STRUCTURAL_FIELDS)
        feed = await provider.get_snapshot(str(ORG), PROJECT, "9003")
        codes = [row["task"]["activityCode"] for row in feed["assignments"]]
        self.assertEqual(len(BRIDGE_TASKS), len(codes))
        offenders = [code for code in codes if looks_like_a_date(code)]
        self.assertEqual([], offenders)

    async def test_the_activity_list_emits_no_date_either(self):
        """The two adapters have to agree, or a line is offered a code the feed never emits.

        `CoreProjectActivityProvider` keys its activities by the same `activity_code`, so a
        host that fixed one adapter and not the other would offer activities that can never
        be paired. Both are checked with the same wiring.
        """
        provider = core_activities.CoreProjectActivityProvider(
            connection(), activity_code_fields=STRUCTURAL_FIELDS)
        rows, _total = await provider.list_activities(str(ORG), PROJECT)
        self.assertTrue(rows)
        offenders = [row["activityExternalId"] for row in rows
                     if looks_like_a_date(row["activityExternalId"])]
        self.assertEqual([], offenders)

    async def test_dates_collapse_distinct_work_into_one_activity(self):
        """Why a date is not merely an odd-looking code: it destroys identity.

        Twelve tasks, twelve distinct structural codes, five distinct dates. Pairing on the
        date makes several unrelated tasks one activity, so a correction aimed at one lands
        on all of them.
        """
        by_date = core_progress.CoreProgressSnapshotProvider(
            connection(), activity_code_fields=("text1",))
        by_structure = core_progress.CoreProgressSnapshotProvider(
            connection(), activity_code_fields=STRUCTURAL_FIELDS)

        dated = {row["task"]["activityCode"]
                 for row in (await by_date.get_snapshot(str(ORG), PROJECT, "9003"))["assignments"]}
        structural = {
            row["task"]["activityCode"]
            for row in (await by_structure.get_snapshot(str(ORG), PROJECT, "9003"))["assignments"]}

        self.assertEqual(len(JALALI_DATES), len(dated))
        self.assertEqual(len(BRIDGE_TASKS), len(structural))
        self.assertLess(len(dated), len(structural))

    def test_both_adapters_share_one_default_so_they_cannot_drift(self):
        """One constant, imported by both. Two copies would eventually disagree."""
        self.assertIs(core_activities.ACTIVITY_CODE_FIELDS,
                      core_progress.ACTIVITY_CODE_FIELDS)

    def test_the_library_default_still_admits_a_date(self):
        """Why the host overrides it, asserted rather than described.

        The library default is deliberately unchanged: a host whose planners really do write
        codes in Text1 still needs it, and which field a planner uses is a deployment fact,
        not a library one. So the default remains capable of returning a date, and the
        protection lives in the host's wiring -- which `HostWiringTests` below pins.

        If this ever fails, the library default changed. That may well be right, but it is a
        decision about every host at once, and whoever makes it should confirm that
        `devhost.app.ACTIVITY_CODE_FIELDS` is still consistent with it.
        """
        row = task(1, "1404/5/18", "1.1")
        self.assertIn("text1", core_progress.ACTIVITY_CODE_FIELDS)
        self.assertEqual("1404/5/18",
                         core_progress.activity_code(row, core_progress.ACTIVITY_CODE_FIELDS))


class HostWiringTests(unittest.IsolatedAsyncioTestCase):
    """What the development host actually constructs.

    Asserted against the built objects rather than against the source text: a test that
    grepped `devhost/app.py` would pass on a commented-out line and fail on a rename, and
    would prove nothing about what a request reaches.
    """

    def wired(self, core):
        from fastapi import FastAPI
        from devhost.app import wire
        application = FastAPI()
        wire(application, connection(), BACKEND_ROOT / "build" / "storage", core)
        return application.state

    def core_wired(self):
        """`wire()` with the Core progress adapter switched on, restoring the environment."""
        import os
        previous = os.environ.get("FINANCE_CORE_PROGRESS")
        os.environ["FINANCE_CORE_PROGRESS"] = "on"
        try:
            return self.wired(connection())
        finally:
            os.environ.pop("FINANCE_CORE_PROGRESS", None)
            if previous is not None:
                os.environ["FINANCE_CORE_PROGRESS"] = previous

    def test_the_host_never_reads_an_activity_code_from_text1(self):
        from devhost.app import ACTIVITY_CODE_FIELDS as WIRED
        self.assertNotIn("text1", WIRED)
        self.assertEqual(("outline_number", "wbs"), WIRED)

    def test_both_adapters_are_wired_with_the_same_fields(self):
        """The property that matters most, because breaking it is silent.

        `CoreProjectActivityProvider` keys its activities by the same rule the progress feed
        uses. Rewiring one and not the other offers estimate lines activity codes the feed
        never emits -- every line unmapped, with nothing saying why.
        """
        from devhost.app import ACTIVITY_CODE_FIELDS as WIRED
        state = self.core_wired()
        progress = state.progress_service.provider
        activities = state.finance_resources_service._activity_provider

        self.assertIsInstance(progress, core_progress.CoreProgressSnapshotProvider)
        self.assertIsInstance(activities, core_activities.CoreProjectActivityProvider)
        self.assertEqual(tuple(WIRED), progress._activity_code_fields)
        self.assertEqual(tuple(WIRED), activities._activity_code_fields)
        self.assertEqual(progress._activity_code_fields, activities._activity_code_fields)

    async def test_the_wired_progress_feed_emits_no_date(self):
        """End to end through the provider the host actually installed."""
        provider = self.core_wired().progress_service.provider
        feed = await provider.get_snapshot(str(ORG), PROJECT, "9003")
        codes = [row["task"]["activityCode"] for row in feed["assignments"]]
        self.assertEqual(len(BRIDGE_TASKS), len(codes))
        self.assertEqual([], [code for code in codes if looks_like_a_date(code)])
        self.assertEqual(len(BRIDGE_TASKS), len(set(codes)))

    async def test_the_wired_activity_list_emits_no_date(self):
        provider = self.core_wired().finance_resources_service._activity_provider
        rows, _total = await provider.list_activities(str(ORG), PROJECT)
        self.assertTrue(rows)
        self.assertEqual([], [row["activityExternalId"] for row in rows
                              if looks_like_a_date(row["activityExternalId"])])

    async def test_the_two_wired_adapters_agree_on_every_code(self):
        """Not just the same configuration -- the same codes out of the same tasks."""
        state = self.core_wired()
        feed = await state.progress_service.provider.get_snapshot(str(ORG), PROJECT, "9003")
        rows, _total = await (state.finance_resources_service._activity_provider
                              .list_activities(str(ORG), PROJECT))
        self.assertEqual({row["task"]["activityCode"] for row in feed["assignments"]},
                         {row["activityExternalId"] for row in rows})


if __name__ == "__main__":
    unittest.main()
