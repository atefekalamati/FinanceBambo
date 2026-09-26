"""The Core adapter's two modes, and the line between them.

`CoreProgressSnapshotProvider` answers from `msp_resource_assignments` when Core carries
that table and from `msp_tasks` when it does not. The interesting case is neither of those:
exactly one of the two tables present means somebody is midway through a migration, and an
adapter that quietly fell back would make a half-migrated Core look identical to one nobody
had touched. That case raises, and the test for it is the reason this file exists.

The rest guards the distinction the whole integration rests on: quantity is physical and
comes from MPXJ's Material field; work is hours. They travel in separate fields, and an
absent quantity stays None rather than becoming zero.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.progress import (ASSIGNMENT_TABLES, SOURCE_TYPE, CoreSchemaMismatch,
                              assignment_row, task_row)


ORGANIZATION = UUID("c4ee6a23-b2a8-4afe-94c8-63baba552ca4")


def joined(**overrides):
    """A row shaped like the assignment/resource/task join the adapter reads."""
    row = {
        "assignment_uid": 9449, "task_uid": 1221, "resource_uid": 94,
        "units": Decimal("100"),
        "planned_work": Decimal("98935.41"), "actual_work": None,
        "remaining_work": Decimal("98935.41"),
        "planned_quantity": Decimal("98935.41"), "actual_quantity": None,
        "remaining_quantity": Decimal("98935.41"),
        "quantity_unit": None, "assignment_work_complete_percent": None,
        "resource_name": "آرماتور", "native_type": "MATERIAL",
        "bambo_resource_type": "material", "resource_quantity_unit": "کیلوگرم",
        "task_row_id": 5501, "uid": 1221, "guid": None, "task_id": 1221,
        "name": "آرماتور بندی فونداسیون", "wbs": "1.5.2.3",
        "outline_number": "1.5.2.3", "outline_level": 4,
        "start": "2025-09-08T08:00", "finish": "2025-10-20T17:00",
        "percent_complete": Decimal("0"), "percent_work_complete": Decimal("0"),
        "physical_percent_complete": None, "text1": None,
    }
    row.update(overrides)
    return row


class AssignmentRowTests(unittest.TestCase):
    def test_a_material_assignment_carries_resource_unit_and_quantity(self):
        row = assignment_row(joined())
        self.assertEqual("9449", row["assignmentExternalId"])
        self.assertEqual("94", row["resourceExternalId"])
        self.assertEqual("آرماتور", row["resourceName"])
        self.assertEqual("material", row["resourceType"])
        self.assertEqual("کیلوگرم", row["unit"])
        self.assertEqual("98935.41", row["plannedQuantity"])
        self.assertEqual("98935.41", row["remainingQuantity"])

    def test_quantity_and_work_stay_in_separate_fields(self):
        # Both read 98935.41 here because MSP stores a material assignment's consumption in
        # Work. They must still arrive as two fields: Finance's progress precedence prefers
        # quantity and treats work as a weaker fallback, which only works if it can tell
        # them apart.
        row = assignment_row(joined(planned_work=Decimal("120"),
                                    planned_quantity=Decimal("98935.41")))
        self.assertEqual("98935.41", row["plannedQuantity"])
        self.assertEqual("120", row["plannedWork"])

    def test_an_unreported_actual_quantity_stays_null(self):
        row = assignment_row(joined(actual_quantity=None, actual_work=None))
        self.assertIsNone(row["actualQuantity"])
        self.assertIsNone(row["actualWork"])

    def test_a_measured_zero_is_not_the_same_as_an_absent_measurement(self):
        row = assignment_row(joined(actual_quantity=Decimal("0")))
        self.assertEqual("0", row["actualQuantity"])
        self.assertIsNotNone(row["actualQuantity"])

    def test_the_assignment_unit_wins_over_the_resource_unit(self):
        row = assignment_row(joined(quantity_unit="تن", resource_quantity_unit="کیلوگرم"))
        self.assertEqual("تن", row["unit"])

    def test_an_unlinked_assignment_is_reported_rather_than_dropped(self):
        # 12 of 727 in the reference file. It reaches no resource, so a line naming it fails
        # to pair visibly instead of the row disappearing.
        row = assignment_row(joined(resource_uid=None, resource_name=None,
                                    bambo_resource_type=None, resource_quantity_unit=None,
                                    quantity_unit=None, planned_quantity=None,
                                    actual_quantity=None, remaining_quantity=None))
        self.assertEqual("9449", row["assignmentExternalId"])
        self.assertIsNone(row["resourceExternalId"])
        self.assertIsNone(row["plannedQuantity"])

    def test_a_work_resource_stored_without_a_classification_is_typed_from_the_file(self):
        # Rows written before 0038 carry null here for every WORK resource, because
        # Finance then separated labour from equipment and the file does not. It no
        # longer does: WORK is `work`, so the file's own kind types the row. Nothing about
        # the crane's NAME is read -- guessing from a name is how a crane becomes a
        # bricklayer -- and the quantity stays as absent as it was.
        row = assignment_row(joined(native_type="WORK", bambo_resource_type=None,
                                    resource_name="جرثقیل ۳۰ تن",
                                    planned_quantity=None, remaining_quantity=None,
                                    quantity_unit=None, resource_quantity_unit=None))
        self.assertEqual("work", row["resourceType"])
        self.assertIsNone(row["plannedQuantity"])

    def test_a_stored_labor_or_equipment_classification_is_read_as_work(self):
        for old in ("labor", "equipment"):
            row = assignment_row(joined(native_type="WORK", bambo_resource_type=old))
            self.assertEqual("work", row["resourceType"], old)

    def test_the_task_block_matches_the_task_level_feed(self):
        row = joined()
        self.assertEqual(task_row(row)["task"], assignment_row(row)["task"])
        self.assertEqual("1.5.2.3", row["wbs"])

    def test_quantities_are_decimal_strings_never_floats(self):
        row = assignment_row(joined(planned_quantity=Decimal("0.000001")))
        self.assertEqual("0.000001", row["plannedQuantity"])
        self.assertNotIn("e", row["plannedQuantity"].lower())

    def test_no_quantity_is_invented_from_work_or_percentage(self):
        row = assignment_row(joined(planned_quantity=None, remaining_quantity=None,
                                    actual_quantity=None, quantity_unit=None,
                                    resource_quantity_unit=None,
                                    planned_work=Decimal("500"),
                                    assignment_work_complete_percent=Decimal("40")))
        self.assertIsNone(row["plannedQuantity"])
        self.assertIsNone(row["actualQuantity"])
        self.assertEqual("500", row["plannedWork"])


class SourceTypeTests(unittest.TestCase):
    def test_the_source_type_is_one_the_finance_reference_accepts(self):
        # Revision 0005 constrains progress_snapshot_refs.source_type. The previous value,
        # "mpp", was refused by that CHECK the moment a reference was pinned from Core.
        from app.finance.schemas.progress import ProgressSnapshotResponse  # noqa: F401
        import re
        source = (BACKEND_ROOT / "alembic" / "versions"
                  / "0005_progress_snapshot_source_type.py").read_text(encoding="utf-8")
        permitted = set(re.findall(r"'([a-z_]+)'", source.split("source_type IN (")[1]
                                   .split(")")[0]))
        self.assertIn(SOURCE_TYPE, permitted)
        self.assertNotIn("mpp", permitted)

    def test_the_schedule_vocabulary_is_a_different_one_and_stays_separate(self):
        from app.finance.domain.schedule import SOURCE_TYPES
        self.assertIn("mpp", SOURCE_TYPES)
        self.assertNotIn(SOURCE_TYPE, SOURCE_TYPES)


class CapabilityDetectionTests(unittest.IsolatedAsyncioTestCase):
    """Which mode the adapter picks, driven only by which tables exist."""

    class Provider:
        """The capability check in isolation, with the row source faked."""

        def __init__(self, present):
            self.present = present

        async def _rows(self, sql, params):
            return [{"present": self.present}]

    def provider(self, present):
        from coreint.progress import CoreProgressSnapshotProvider
        instance = CoreProgressSnapshotProvider.__new__(CoreProgressSnapshotProvider)
        instance._rows = self.Provider(present)._rows
        return instance

    async def test_both_tables_present_enables_the_assignment_feed(self):
        self.assertTrue(await self.provider(len(ASSIGNMENT_TABLES))._assignments_available())

    async def test_neither_table_present_falls_back_to_tasks(self):
        self.assertFalse(await self.provider(0)._assignments_available())

    async def test_exactly_one_table_present_fails_loudly(self):
        with self.assertRaises(CoreSchemaMismatch) as caught:
            await self.provider(1)._assignments_available()
        self.assertIn("half migrated", str(caught.exception))

    async def test_the_capability_is_not_cached_between_requests(self):
        # A migration can land between two requests. A provider that remembered "absent"
        # would keep answering from task percentages long after the real data arrived.
        calls = []

        async def counting(sql, params):
            calls.append(sql)
            return [{"present": 0}]

        instance = self.provider(0)
        instance._rows = counting
        await instance._assignments_available()
        await instance._assignments_available()
        self.assertEqual(2, len(calls))


if __name__ == "__main__":
    unittest.main()


class FeedModeSelectionTests(unittest.IsolatedAsyncioTestCase):
    """Which feed a snapshot gets, when the tables exist but hold nothing for it.

    Revision 0007 creates both tables for the whole database at once, so every historical
    snapshot suddenly has an assignment table -- with no rows in it. If the adapter chose its
    mode on table existence alone, all of them would flip to assignment mode and return an
    empty feed: every activity would vanish from the report, and no error would be raised.

    The guard is one `if rows:` in `_feed`. These tests are what keep it there.
    """

    SNAPSHOT = {"id": 40, "project_id": "terrace", "organization_id": ORGANIZATION,
                "file_version_id": 900, "snapshot_type": "ACTUAL",
                "previous_snapshot_id": None, "source_filename": "bridge.mpp",
                "status_date_jalali": "1405-06-01", "created_by": None,
                "created_at": __import__("datetime").datetime(2026, 8, 20),
                "original_filename": "bridge.mpp", "version_number": 1,
                "superseded": False}

    TASK = {"id": 5501, "uid": 1221, "guid": None, "task_id": 1221,
            "name": "آرماتور بندی فونداسیون", "wbs": "1.5.2.3",
            "outline_number": "1.5.2.3", "outline_level": 4,
            "start": "2025-09-08T08:00", "finish": "2025-10-20T17:00",
            "percent_complete": Decimal("40"), "percent_work_complete": Decimal("55"),
            "physical_percent_complete": None, "text1": None}

    def provider(self, tables_present, assignment_rows, task_rows=None):
        from coreint.progress import CoreProgressSnapshotProvider
        task_rows = [self.TASK] if task_rows is None else task_rows

        async def rows(sql, params):
            if "information_schema.tables" in sql:
                return [{"present": tables_present}]
            if "FROM msp_resource_assignments" in sql:
                return list(assignment_rows)
            if "FROM msp_tasks" in sql:
                return list(task_rows)
            return [dict(self.SNAPSHOT)]

        instance = CoreProgressSnapshotProvider.__new__(CoreProgressSnapshotProvider)
        instance._rows = rows
        instance._activity_code_fields = ("text1", "outline_number", "wbs")
        instance._progress_types = ("ACTUAL", "RESCHEDULED")
        return instance

    async def test_tables_absent_gives_the_task_level_feed(self):
        feed = await self.provider(0, [])._feed(dict(self.SNAPSHOT))
        self.assertEqual(1, len(feed["assignments"]))
        self.assertIsNone(feed["assignments"][0]["assignmentExternalId"])

    async def test_tables_present_but_empty_for_this_snapshot_still_gives_tasks(self):
        # The regression 0007 could have introduced across every historical snapshot.
        feed = await self.provider(2, [])._feed(dict(self.SNAPSHOT))
        self.assertEqual(1, len(feed["assignments"]),
                         "an empty assignment table must not empty the feed")
        row = feed["assignments"][0]
        self.assertIsNone(row["assignmentExternalId"])
        self.assertEqual("1.5.2.3", row["task"]["wbsCode"])

    async def test_tables_present_with_rows_gives_the_assignment_feed(self):
        feed = await self.provider(2, [joined()])._feed(dict(self.SNAPSHOT))
        self.assertEqual(1, len(feed["assignments"]))
        self.assertEqual("9449", feed["assignments"][0]["assignmentExternalId"])
        self.assertEqual("98935.41", feed["assignments"][0]["plannedQuantity"])

    async def test_one_snapshot_having_rows_does_not_change_another(self):
        # The assignment query is filtered by snapshot_id, so a newly imported snapshot
        # cannot pull a historical one into assignment mode.
        historical = await self.provider(2, [])._feed(dict(self.SNAPSHOT))
        current = await self.provider(2, [joined()])._feed(dict(self.SNAPSHOT))
        self.assertIsNone(historical["assignments"][0]["assignmentExternalId"])
        self.assertEqual("9449", current["assignments"][0]["assignmentExternalId"])

    async def test_the_legacy_feed_leaves_every_resource_field_null(self):
        feed = await self.provider(2, [])._feed(dict(self.SNAPSHOT))
        row = feed["assignments"][0]
        for field in ("assignmentExternalId", "resourceExternalId", "resourceName",
                      "resourceType", "unit", "plannedQuantity", "actualQuantity",
                      "remainingQuantity", "plannedWork", "actualWork", "remainingWork",
                      "assignmentWorkCompletePercent"):
            self.assertIsNone(row[field], field)
        self.assertEqual("1221", row["task"]["taskExternalId"])
        self.assertEqual("آرماتور بندی فونداسیون", row["task"]["taskName"])

    async def test_task_progress_prefers_physical_then_duration_and_never_work(self):
        # percent_work_complete measures effort. Effort is not a proportion of a physical
        # quantity, and using it here is the conflation this integration exists to avoid.
        measured = dict(self.TASK, physical_percent_complete=Decimal("30"))
        feed = await self.provider(2, [], [measured])._feed(dict(self.SNAPSHOT))
        self.assertEqual("30", feed["assignments"][0]["task"]["taskProgressPercent"])

        feed = await self.provider(2, [], [self.TASK])._feed(dict(self.SNAPSHOT))
        self.assertEqual("40", feed["assignments"][0]["task"]["taskProgressPercent"])
        self.assertNotEqual("55", feed["assignments"][0]["task"]["taskProgressPercent"])

    async def test_no_numbered_custom_field_reaches_the_feed(self):
        from coreint import progress
        for name in ("number1", "number3", "number4", "number13", "number14", "number18"):
            self.assertNotIn(name, progress.TASKS)
            self.assertNotIn(name, progress.ASSIGNMENTS)


class TaskProgressSelectionTests(unittest.TestCase):
    """Which percentage a task reports, and why a physical zero yields.

    Microsoft Project writes 0.0000 into physical_percent_complete whether or not anyone
    entered physical progress. Central snapshot 40 has all 1248 tasks at physical 0.0000
    while percent_complete carries values up to 100 -- so preferring the zero reported the
    whole project as unstarted, silently.

    percent_work_complete stays out of it entirely: it measures effort, and effort is not a
    proportion of a physical quantity.
    """

    def progress(self, physical, percent, work=None):
        from coreint.progress import task_progress
        return task_progress({"physical_percent_complete": physical,
                              "percent_complete": percent,
                              "percent_work_complete": work})

    def test_physical_progress_wins_when_it_states_something(self):
        self.assertEqual(Decimal("30"), self.progress(Decimal("30"), Decimal("40")))

    def test_absent_physical_falls_back_to_duration(self):
        self.assertEqual(Decimal("40"), self.progress(None, Decimal("40")))

    def test_a_physical_zero_yields_to_a_real_duration_figure(self):
        # Snapshot 40's case, on all 1248 rows.
        self.assertEqual(Decimal("40"), self.progress(Decimal("0"), Decimal("40")))

    def test_both_zero_stays_zero(self):
        self.assertEqual(Decimal("0"), self.progress(Decimal("0"), Decimal("0")))

    def test_physical_progress_survives_a_zero_duration(self):
        # Built but not yet scheduled as advanced. The physical figure is the real one.
        self.assertEqual(Decimal("30"), self.progress(Decimal("30"), Decimal("0")))

    def test_a_physical_zero_with_no_duration_at_all_stays_zero(self):
        self.assertEqual(Decimal("0"), self.progress(Decimal("0"), None))

    def test_work_complete_never_overrides_either_field(self):
        self.assertEqual(Decimal("0"), self.progress(Decimal("0"), Decimal("0"),
                                                     work=Decimal("80")))
        self.assertEqual(Decimal("40"), self.progress(None, Decimal("40"),
                                                      work=Decimal("80")))
        self.assertEqual(Decimal("30"), self.progress(Decimal("30"), Decimal("40"),
                                                      work=Decimal("80")))

    def test_the_feed_row_uses_the_same_rule(self):
        row = task_row({**FeedModeSelectionTests.TASK,
                        "physical_percent_complete": Decimal("0"),
                        "percent_complete": Decimal("40"),
                        "percent_work_complete": Decimal("55")})
        self.assertEqual("40", row["task"]["taskProgressPercent"])

    def test_no_numbered_field_participates(self):
        from coreint import progress
        import inspect
        source = inspect.getsource(progress.task_progress)
        for name in ("number1", "number3", "number4", "number13", "number14", "number18"):
            self.assertNotIn(name, source)
