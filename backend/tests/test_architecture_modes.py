# -*- coding: utf-8 -*-
"""The three deployment modes, and the rule that keeps hours out of kilograms.

The architecture this file defends: the schedule FILE is the source of MPP data, one
reader parses it, and each consumer keeps its own persistence. Finance must be able to
compute from the file alone -- no `msp_tasks`, no `msp_snapshots`, no `msp_task_metrics`,
no bridge row. The bridge links an MSP task to a Finance resource when both exist and
means nothing when they do not.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.progress import (TIME_BASED_RESOURCE_TYPES,
                                         resolve_progress_quantity)
from coreint.finance_mpp_sync import finance_rows
from coreint.finance_quantity import approved_quantity
from coreint.mpp_progress_shape import file_rows


class ParsedFile:
    """What the shared reader returns. No database identity anywhere in it."""

    def __init__(self, tasks, resources=(), assignments=(), warnings=()):
        self.application = "Microsoft.Project 16.0"
        self.tasks = list(tasks)
        self.resources = list(resources)
        self.assignments = list(assignments)
        self.warnings = list(warnings)
        self.parser_engine = "test"


def task(uid=1519, percent="100", **metrics):
    base = {"item_quantity": None, "weight_rial": None, "weight_time": None,
            "weight_base": None, "actual_progress": None,
            "actual_progress_percent": None, "physical_progress": None,
            "planned_progress": None, "progress_variance": None, "task_cost": None,
            "jalali_start": None, "jalali_finish": None}
    base.update(metrics)
    return {"uid": uid, "guid": None, "task_id": 11, "name": "تخریب جداول",
            "wbs": "1.5.1.2", "outline_number": "1.5.1.2", "outline_level": 4,
            "summary": False, "start": "2025-08-19T08:00", "finish": "2025-09-17T17:00",
            "baseline_start": None, "baseline_finish": None, "duration": "240",
            "percent_complete": percent, "percent_work_complete": percent,
            "physical_percent_complete": "0", "text1": "1404/5/28",
            "metrics": base, "raw_fields": {}}


def resource(uid=94, native="MATERIAL", quantity="1329121.22", unit="کیلوگرم"):
    return {"uid": uid, "guid": None, "name": "آرماتور", "native_type": native,
            "initials": unit, "material_label": unit, "quantity": quantity,
            "quantity_unit": unit, "quantity_unit_source": "material_label",
            "group": None, "code": None, "max_units": None, "standard_rate": "66150",
            "overtime_rate": None, "cost_per_use": None, "work": None,
            "actual_work": None, "remaining_work": None, "cost": None,
            "actual_cost": None, "remaining_cost": None}


def assignment(task_uid=1519, resource_uid=94, **over):
    row = {"assignment_uid": 1, "task_uid": task_uid, "resource_uid": resource_uid,
           "units": "1", "planned_work": "240", "actual_work": "240",
           "remaining_work": "0", "planned_quantity": None, "actual_quantity": None,
           "remaining_quantity": None, "work_complete_percent": "100",
           "cost": None, "actual_cost": None, "remaining_cost": None}
    row.update(over)
    return row


class SharedNormalizedModelTests(unittest.TestCase):
    """One reader, one normalized shape, no consumer identity inside it."""

    def test_the_normalized_rows_carry_no_database_identity(self):
        rows = file_rows(ParsedFile([task()], [resource()], [assignment()]))
        for row in rows["tasks"] + rows["assignments"]:
            self.assertIsNone(row["id"], "no msp_tasks.id exists for a parsed file")
            self.assertNotIn("snapshot_id", row)
            self.assertNotIn("finance_resource_id", row)
            self.assertNotIn("bridge_id", row)

    def test_the_stable_source_identity_is_the_msp_uid(self):
        rows = file_rows(ParsedFile([task(uid=1519)], [resource()], [assignment()]))
        self.assertEqual(1519, rows["assignments"][0]["uid"])

    def test_numbers_arrive_as_decimals_so_both_sources_agree(self):
        # The reader states decimal strings; the database states Decimal. The shared
        # builders must not have to know which source they are reading.
        rows = file_rows(ParsedFile([task(item_quantity="3538.11")], [resource()],
                                    [assignment()]))
        self.assertEqual(Decimal("3538.11"), rows["tasks"][0]["item_quantity"])
        self.assertIsInstance(rows["assignments"][0]["planned_work"], Decimal)

    def test_a_material_resource_is_classified_and_a_work_one_is_not_guessed(self):
        material = file_rows(ParsedFile([task()], [resource(native="MATERIAL")],
                                        [assignment()]))["assignments"][0]
        self.assertEqual("material", material["bambo_resource_type"])
        work = file_rows(ParsedFile([task()], [resource(uid=95, native="WORK")],
                                    [assignment(resource_uid=95)]))["assignments"][0]
        self.assertIsNone(work["bambo_resource_type"],
                          "MS Project does not say labour or equipment, so nor do we")

    def test_an_assignment_whose_task_is_absent_is_dropped_not_invented(self):
        rows = file_rows(ParsedFile([task(uid=1)], [resource()],
                                    [assignment(task_uid=999)]))
        self.assertEqual([], rows["assignments"])


class FinanceOnlyModeTests(unittest.TestCase):
    """MODE A: the file alone. No MSP tables, no bridge."""

    def test_finance_gets_metrics_with_no_msp_row_anywhere(self):
        parsed = ParsedFile(
            [task(item_quantity="3538.11", weight_rial="1.55",
                  actual_progress_percent="100")],
            [resource()],
            [assignment(planned_quantity="3538.11", actual_quantity="3538.11")])
        row = file_rows(parsed)["assignments"][0]
        self.assertEqual(Decimal("1.55"), row["weight_rial"])
        self.assertEqual(Decimal("100"), row["actual_progress_percent"])
        # The planning volume travels as a METRIC under its own name. It is not priced.
        self.assertEqual(Decimal("3538.11"), row["item_quantity"])

    def test_a_material_amount_is_not_an_approved_quantity(self):
        # MPXJ's Material field is real, and it is still not the column the planners
        # approved for pricing. The persisted rows say NULL for this file; the feed must
        # say the same, or a report can be computed from a number one table denies.
        parsed = ParsedFile([task()], [resource()],
                            [assignment(planned_quantity="3538.11",
                                        actual_quantity="3538.11")])
        row = file_rows(parsed)["assignments"][0]
        self.assertIsNone(row["planned_quantity"])
        self.assertIsNone(row["actual_quantity"])
        self.assertIsNone(row["remaining_quantity"])


class ApprovedQuantityTests(unittest.TestCase):
    """The one rule for what Finance may call a quantity, shared by feed and persistence."""

    def with_columns(self, **raw):
        t = task()
        t["raw_fields"] = raw
        return t

    def test_the_current_file_states_no_approved_quantity(self):
        # Every custom column the real file has, by its planner-given name. None is one.
        t = self.with_columns(**{"آحجام هرآیتم": "3538.11", "احجام کاری": "10",
                                 "حجم اولیه": "5", "ضریب وزنی ریالی": "1.55",
                                 "درصد پیشرفت واقعی": "100"})
        self.assertEqual((None, None), approved_quantity(t))

    def test_an_approved_column_is_read_with_its_unit(self):
        t = self.with_columns(**{"مقدار": "250", "واحد مقدار": "m3"})
        self.assertEqual((Decimal("250"), "m3"), approved_quantity(t))

    def test_the_english_spelling_is_approved_too(self):
        t = self.with_columns(Quantity="12.5")
        self.assertEqual((Decimal("12.5"), None), approved_quantity(t))

    def test_a_numbered_slot_never_becomes_a_quantity(self):
        # A number in Number16 is a number in Number16. The slot proves nothing.
        t = self.with_columns(Number16="3538.11", Number2="10")
        self.assertEqual((None, None), approved_quantity(t))

    def test_an_approved_quantity_reaches_the_feed_as_planned_only(self):
        t = self.with_columns(**{"مقدار": "250", "واحد مقدار": "m3"})
        row = file_rows(ParsedFile([t], [resource()], [assignment()]))["assignments"][0]
        self.assertEqual(Decimal("250"), row["planned_quantity"])
        self.assertEqual("m3", row["quantity_unit"])
        # A planned quantity says nothing about what was executed; nothing derives one.
        self.assertIsNone(row["actual_quantity"])

    def test_an_approved_quantity_is_persisted_and_its_absence_is_null(self):
        stated = self.with_columns(**{"مقدار": "250", "واحد مقدار": "m3"})
        rows = finance_rows(ParsedFile([stated], [resource()], [assignment()]))
        self.assertEqual((Decimal("250"), "m3"), (rows[0]["quantity"], rows[0]["quantity_unit"]))
        rows = finance_rows(ParsedFile([task()], [resource()], [assignment()]))
        self.assertEqual((None, None), (rows[0]["quantity"], rows[0]["quantity_unit"]))

    def test_persisted_rows_carry_the_files_own_identifiers_only(self):
        rows = finance_rows(ParsedFile([task(uid=1519)], [resource(uid=94)],
                                       [assignment(task_uid=1519, resource_uid=94)]))
        row = rows[0]
        self.assertEqual((1519, 1, 94), (row["source_task_uid"], row["source_assignment_uid"],
                                         row["source_resource_uid"]))
        for forbidden in ("id", "snapshot_id", "msp_task_id", "resource_id"):
            self.assertNotIn(forbidden, row)

    def test_the_file_states_whether_it_is_progress_or_a_baseline(self):
        live = file_rows(ParsedFile([task(percent="30")]))
        self.assertEqual("ACTUAL", live["snapshot_type"])
        baseline = file_rows(ParsedFile([task(percent="0")]))
        self.assertEqual("TARGET", baseline["snapshot_type"])


class QuantityRuleTests(unittest.TestCase):
    """Hours are not kilograms. This is the rule the report's credibility rests on."""

    BASE = {"plannedQuantity": None, "actualQuantity": None,
            "assignmentWorkCompletePercent": None, "task": {}, "manualOverride": None}

    def test_work_is_never_a_material_quantity(self):
        row = {**self.BASE, "actualWork": "48", "resourceType": "material"}
        with self.assertRaises(ValueError):
            resolve_progress_quantity(row)

    def test_work_is_not_a_quantity_for_an_unclassified_resource_either(self):
        # "we do not know what this is" is not "it is measured in hours".
        row = {**self.BASE, "actualWork": "48", "resourceType": None}
        with self.assertRaises(ValueError):
            resolve_progress_quantity(row)

    def test_work_is_a_quantity_for_a_resource_whose_unit_is_time(self):
        for kind in TIME_BASED_RESOURCE_TYPES:
            with self.subTest(kind=kind):
                resolved = resolve_progress_quantity(
                    {**self.BASE, "actualWork": "48", "resourceType": kind})
                self.assertEqual(Decimal("48"), resolved["effective_quantity"])
                self.assertEqual("work_effort", resolved["measurement_type"])
                self.assertEqual("PROGRESS_WORK_NOT_QUANTITY",
                                 resolved["warnings"][0]["code"])

    def test_a_material_with_a_real_quantity_is_unaffected(self):
        resolved = resolve_progress_quantity(
            {**self.BASE, "actualQuantity": "3538.11", "actualWork": "48",
             "resourceType": "material"})
        self.assertEqual(Decimal("3538.11"), resolved["effective_quantity"])
        self.assertEqual("measured_quantity", resolved["measurement_type"])

    def test_a_material_without_a_quantity_falls_to_percent_not_to_hours(self):
        resolved = resolve_progress_quantity(
            {**self.BASE, "plannedQuantity": "100", "actualWork": "48",
             "assignmentWorkCompletePercent": "25", "resourceType": "material"})
        self.assertEqual(Decimal("25"), resolved["effective_quantity"])
        self.assertEqual("derived_from_percent", resolved["measurement_type"])

    def test_missing_quantity_is_refused_rather_than_reported_as_zero(self):
        with self.assertRaises(ValueError):
            resolve_progress_quantity({**self.BASE, "resourceType": "material"})


if __name__ == "__main__":
    unittest.main()
