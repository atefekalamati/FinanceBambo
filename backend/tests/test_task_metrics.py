# -*- coding: utf-8 -*-
"""The schedule's own per-task columns: read by alias, stored typed, fed to Finance.

These columns are what a finance rollup is actually built on -- the item quantity, the
weighting coefficients, the planner's own progress figure -- and every assertion here is
about not losing them, not renaming them, and not inventing them.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.mpp_reader import TASK_METRIC_ALIASES, TASK_METRIC_KEYS
from coreint.progress import TASK_METRIC_FIELDS, task_metrics, task_progress, task_row


def task(**overrides):
    """A joined task row shaped like the feed queries return."""
    row = {
        "id": 1, "uid": 1519, "guid": None, "task_id": 11, "name": "تخریب جداول",
        "wbs": "1.5.1.2", "outline_number": "1.5.1.2", "outline_level": 4,
        "start": "2025-08-19T08:00", "finish": "2025-09-17T17:00",
        "percent_complete": 100, "percent_work_complete": 100,
        "physical_percent_complete": 0, "text1": "1404/5/28",
        "item_quantity": None, "weight_rial": None, "weight_time": None,
        "weight_base": None, "actual_progress": None, "actual_progress_percent": None,
        "physical_progress": None, "planned_progress": None, "progress_variance": None,
        "task_cost": None, "jalali_start": None, "jalali_finish": None,
    }
    row.update(overrides)
    return row


class AliasContractTests(unittest.TestCase):
    """The alias is the contract, not the NumberN slot it happens to sit in."""

    def test_every_alias_maps_to_a_stable_key_and_a_known_kind(self):
        for alias, (key, kind) in TASK_METRIC_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertTrue(alias.strip(), "an empty alias matches everything")
                self.assertRegex(key, r"^[a-z][a-z_]*$", "keys stay machine-stable")
                self.assertIn(kind, ("number", "text"))

    def test_no_two_aliases_claim_the_same_key(self):
        keys = [key for key, _ in TASK_METRIC_ALIASES.values()]
        self.assertEqual(len(keys), len(set(keys)), "a collision would silently overwrite")

    def test_the_finance_columns_the_planners_named_are_all_mapped(self):
        # The four the finance rollup cannot be built without.
        for alias in ("آحجام هرآیتم", "ضریب وزنی ریالی", "ضریب وزنی زمانی",
                      "درصد پیشرفت واقعی"):
            self.assertIn(alias, TASK_METRIC_ALIASES)

    def test_cost_travels_with_the_metrics_and_is_not_an_alias(self):
        # Task cost is a standard MPXJ field, so it has no alias -- but it is a task
        # attribute finance reads, so it must still be in the stored key set.
        for key in ("task_cost", "task_actual_cost", "task_fixed_cost"):
            self.assertIn(key, TASK_METRIC_KEYS)
            self.assertNotIn(key, [k for k, _ in TASK_METRIC_ALIASES.values()])

    def test_the_key_order_is_fixed(self):
        # The importer builds its INSERT column list from this order; a reshuffle would
        # write every value into the wrong column without any error.
        self.assertEqual(TASK_METRIC_KEYS[0], "item_quantity")
        self.assertEqual(TASK_METRIC_KEYS[-3:], ["task_cost", "task_actual_cost",
                                                 "task_fixed_cost"])
        self.assertEqual(len(TASK_METRIC_KEYS), len(set(TASK_METRIC_KEYS)))


class FeedMetricsTests(unittest.TestCase):
    def test_a_snapshot_without_metrics_reports_none_not_a_dict_of_nulls(self):
        # "states nothing" and "states zero" are different claims about a schedule.
        bare = {key: value for key, value in task().items()
                if key not in dict(TASK_METRIC_FIELDS).values()
                and key not in ("jalali_start", "jalali_finish")}
        self.assertIsNone(task_metrics(bare))

    def test_all_null_metrics_are_reported_as_no_metrics(self):
        self.assertIsNone(task_metrics(task()))

    def test_stated_values_reach_the_feed_under_their_meaning(self):
        metrics = task_metrics(task(item_quantity=Decimal('3538.11'),
                                    weight_rial=Decimal('1.5549'),
                                    weight_time=Decimal('0.9621'),
                                    task_cost=Decimal('5660176000')))
        self.assertEqual("3538.11", metrics["itemQuantity"])
        self.assertEqual("1.5549", metrics["weightRial"])
        self.assertEqual("0.9621", metrics["weightTime"])
        self.assertEqual("5660176000", metrics["taskCost"])

    def test_numbers_travel_as_strings_not_floats(self):
        metrics = task_metrics(task(item_quantity=Decimal("1329121.22")))
        self.assertIsInstance(metrics["itemQuantity"], str)

    def test_a_float_cannot_smuggle_its_binary_expansion_into_a_report(self):
        # Decimal(3538.11) is 3538.110000000000127... -- 41 digits the schedule never
        # stated. psycopg hands back Decimal, so this is a guard, not the usual path.
        metrics = task_metrics(task(item_quantity=3538.11))
        self.assertEqual("3538.11", metrics["itemQuantity"])


class TaskProgressPrecedenceTests(unittest.TestCase):
    """Which of the three progress figures the feed reports, and why."""

    def test_the_planners_own_figure_wins_when_it_says_something(self):
        self.assertEqual(84, task_progress(task(actual_progress_percent=84,
                                                percent_complete=30,
                                                physical_percent_complete=0)))

    def test_a_stated_zero_yields_rather_than_reporting_a_live_project_as_unstarted(self):
        # MS Project leaves 0 in the column for untouched tasks, so a zero here is
        # silence -- the same rule physical progress already follows.
        self.assertEqual(30, task_progress(task(actual_progress_percent=0,
                                                percent_complete=30,
                                                physical_percent_complete=0)))

    def test_without_the_column_the_old_precedence_is_unchanged(self):
        row = task(percent_complete=30, physical_percent_complete=0)
        del row["actual_progress_percent"]
        self.assertEqual(30, task_progress(row))

    def test_physical_still_beats_duration_when_it_states_something(self):
        self.assertEqual(45, task_progress(task(percent_complete=30,
                                                physical_percent_complete=45)))


class TaskLevelQuantityTests(unittest.TestCase):
    """The task-level feed is the no-assignment path. It prices nothing."""

    def test_a_custom_planning_column_is_never_priced_as_the_planned_quantity(self):
        # "item quantity" is a planning volume the planners keep for their own rollups.
        # It is not a column they approved for pricing, and an earlier reading having
        # called it item_quantity does not make it one.
        row = task_row(task(item_quantity=Decimal('3538.11'), actual_progress_percent=100))
        self.assertIsNone(row["plannedQuantity"])

    def test_the_unit_is_never_guessed(self):
        # The file states no unit for this column, so the feed states none either.
        row = task_row(task(item_quantity=Decimal('3538.11')))
        self.assertIsNone(row["unit"])

    def test_a_task_with_no_stated_quantity_still_reports_null(self):
        self.assertIsNone(task_row(task())["plannedQuantity"])

    def test_no_resource_is_invented_on_a_task_row(self):
        row = task_row(task(item_quantity=Decimal('3538.11')))
        for field in ("resourceExternalId", "resourceName", "resourceType",
                      "assignmentExternalId"):
            self.assertIsNone(row[field], field)

    def test_the_metrics_ride_along_on_the_task_block(self):
        row = task_row(task(item_quantity=Decimal('3538.11'), weight_rial=Decimal('1.55')))
        self.assertEqual("1.55", row["task"]["metrics"]["weightRial"])


if __name__ == "__main__":
    unittest.main()
