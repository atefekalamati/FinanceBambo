# -*- coding: utf-8 -*-
"""What Finance keeps from a schedule, and what it deliberately does not.

Every column here exists because something reads it. These tests say which reader, so a
future change that drops one fails with the reason on screen -- and they pin the two
deliberate absences, work and outline, which are absences by decision rather than
oversight.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_mpp_sync import _COLUMNS, finance_rows
from coreint.finance_progress import _builder_row
from coreint.progress import assignment_row


class ParsedFile:
    def __init__(self, tasks, resources=(), assignments=()):
        self.tasks, self.resources, self.assignments = list(tasks), list(resources), list(assignments)
        self.warnings, self.parser_engine = [], "test"


def task(uid=1519, **raw):
    metrics = {"weight_rial": "1.55", "weight_time": "0.96", "weight_base": "2.1",
               "actual_progress": "0.5", "actual_progress_percent": "84",
               "physical_progress": "0.4", "planned_progress": "0.6",
               "progress_variance": "-0.2", "task_cost": "5660176000",
               "task_actual_cost": "0", "task_fixed_cost": "0"}
    return {"uid": uid, "name": "تخریب جداول", "wbs": "1.5.1.2",
            "start": "2025-08-19T08:00", "finish": "2025-09-17T17:00",
            "metrics": metrics, "raw_fields": dict(raw)}


def resource(uid=94, native="MATERIAL", unit="مترطول"):
    return {"uid": uid, "name": "آرماتور", "native_type": native,
            "quantity_unit": unit, "material_label": unit, "initials": unit}


def assignment(uid=1, task_uid=1519, resource_uid=94):
    return {"assignment_uid": uid, "task_uid": task_uid, "resource_uid": resource_uid}


def one_row(**raw):
    return finance_rows(ParsedFile([task(**raw)], [resource()], [assignment()]))[0]


class PersistedFieldTests(unittest.TestCase):
    def test_the_wbs_and_title_a_report_renders_are_kept(self):
        row = one_row()
        self.assertEqual("1.5.1.2", row["task_wbs"])
        self.assertEqual("تخریب جداول", row["task_name"])

    def test_the_three_source_identities_are_kept(self):
        row = one_row()
        self.assertEqual((1519, 1, 94), (row["source_task_uid"], row["source_assignment_uid"],
                                         row["source_resource_uid"]))

    def test_the_dates_the_progress_page_renders_are_kept_as_the_file_states_them(self):
        row = one_row()
        # Text, not a timestamp: the file names no timezone and none is invented.
        self.assertEqual("2025-08-19T08:00", row["task_start"])
        self.assertEqual("2025-09-17T17:00", row["task_finish"])

    def test_the_resource_facts_the_page_shows_are_kept(self):
        row = one_row()
        self.assertEqual("MATERIAL", row["resource_type"])
        self.assertEqual("مترطول", row["resource_unit"])
        self.assertEqual("آرماتور", row["resource_name"])

    def test_the_resource_unit_is_not_the_approved_quantitys_unit(self):
        # Two different claims about two different numbers. A row may state one and not
        # the other, and conflating them would put a unit on a quantity nobody stated.
        row = one_row()
        self.assertEqual("مترطول", row["resource_unit"])
        self.assertIsNone(row["quantity_unit"])
        self.assertIsNone(row["quantity"])

    def test_every_progress_measure_including_the_variance_is_kept(self):
        row = one_row()
        self.assertEqual(Decimal("84"), row["actual_progress_percent"])
        self.assertEqual(Decimal("0.5"), row["actual_progress"])
        self.assertEqual(Decimal("0.4"), row["physical_progress"])
        self.assertEqual(Decimal("0.6"), row["planned_progress"])
        self.assertEqual(Decimal("-0.2"), row["progress_variance"])

    def test_the_weights_are_kept(self):
        row = one_row()
        self.assertEqual((Decimal("1.55"), Decimal("0.96"), Decimal("2.1")),
                         (row["weight_rial"], row["weight_time"], row["weight_base"]))

    def test_schedule_cost_is_stored_under_a_name_that_says_whose_it_is(self):
        # Finance actual cost comes from confirmed invoices. A column called `actual_cost`
        # in a Finance table would invite exactly the confusion these names prevent.
        row = one_row()
        self.assertEqual(Decimal("5660176000"), row["source_cost"])
        self.assertIn("source_actual_cost", row)
        self.assertNotIn("actual_cost", row)
        self.assertNotIn("cost", row)

    def test_work_is_deliberately_not_persisted(self):
        # Persisting work would re-open `resolve_progress_quantity`'s work branch for a
        # labour or equipment resource, which moves money. That is a decision, not a
        # column, and it has not been taken.
        for forbidden in ("planned_work", "actual_work", "remaining_work",
                          "assignment_work_complete_percent"):
            self.assertNotIn(forbidden, _COLUMNS, forbidden)

    def test_outline_is_deliberately_not_persisted(self):
        # WBS parentage comes from the code string itself; no outline column is read.
        for forbidden in ("outline_number", "outline_level"):
            self.assertNotIn(forbidden, _COLUMNS, forbidden)

    def test_an_approved_quantity_still_persists_when_the_file_states_one(self):
        row = one_row(**{"مقدار": "250", "واحد مقدار": "m3"})
        self.assertEqual(Decimal("250"), row["quantity"])
        self.assertEqual("m3", row["quantity_unit"])

    def test_the_insert_column_list_matches_what_the_builder_produces(self):
        # The INSERT is built from _COLUMNS in order; a row missing one would bind None
        # into the wrong column without any error.
        row = one_row()
        for column in _COLUMNS:
            self.assertIn(column, row, column)


class SummaryLabelRowTests(unittest.TestCase):
    """A stage needs a name even when nobody is assigned to it.

    A summary task carries no resource assignment -- MS Project rolls its children up --
    so it produced no Finance row at all, and the WBS report showed the bare code "1.5"
    where "اجرای عملیات سیویل" belongs. These rows carry the name and nothing else.
    """

    def parsed(self):
        return ParsedFile(
            [task(uid=1),                       # a leaf: gets an assignment below
             dict(task(uid=2), name="اجرای عملیات سیویل", wbs="1.5"),   # summary
             dict(task(uid=3), name="تجهیز کارگاه", wbs="1.4")],        # summary
            [resource()], [assignment(uid=10, task_uid=1)])

    def rows(self):
        return finance_rows(self.parsed())

    def test_a_task_with_no_assignment_still_gets_a_row(self):
        by_uid = {r["source_task_uid"]: r for r in self.rows()}
        self.assertEqual({1, 2, 3}, set(by_uid), "every task is represented")
        self.assertEqual("اجرای عملیات سیویل", by_uid[2]["task_name"])
        self.assertEqual("1.5", by_uid[2]["task_wbs"])

    def test_a_label_row_names_no_assignment_and_no_resource(self):
        label = next(r for r in self.rows() if r["source_task_uid"] == 2)
        self.assertIsNone(label["source_assignment_uid"])
        self.assertIsNone(label["source_resource_uid"])
        self.assertIsNone(label["resource_name"])
        self.assertIsNone(label["resource_type"])
        self.assertIsNone(label["resource_unit"])

    def test_a_label_row_carries_no_quantity(self):
        label = next(r for r in self.rows() if r["source_task_uid"] == 2)
        self.assertIsNone(label["quantity"])
        self.assertIsNone(label["quantity_unit"])

    def test_an_assigned_task_gets_no_duplicate_label_row(self):
        # Task 1 has an assignment, so it is already represented. A second row for it
        # would violate the (version, task, assignment) unique index on the next sync.
        for_task_one = [r for r in self.rows() if r["source_task_uid"] == 1]
        self.assertEqual(1, len(for_task_one))
        self.assertEqual(10, for_task_one[0]["source_assignment_uid"])

    def test_label_rows_never_reach_the_feed(self):
        # This is what keeps a stage heading out of every sum: the provider builds feed
        # rows only from rows that name an assignment.
        label = next(r for r in self.rows() if r["source_task_uid"] == 2)
        self.assertIsNone(_builder_row(dict(label, task_start=None, task_finish=None,
                                            progress_variance=None, source_cost=None,
                                            source_actual_cost=None, source_fixed_cost=None,
                                            resource_type=None, resource_unit=None))
                          ["assignment_uid"])

    def test_a_file_with_no_assignments_at_all_still_yields_one_row_per_task(self):
        rows = finance_rows(ParsedFile([task(uid=1), task(uid=2)], [resource()], []))
        self.assertEqual(2, len(rows))
        self.assertTrue(all(r["source_assignment_uid"] is None for r in rows))


class FeedFromPersistedRowTests(unittest.TestCase):
    """The stored row, read back, must fill the feed fields the UI renders."""

    def stored(self, **over):
        row = {"source_task_uid": 1519, "source_assignment_uid": 1, "source_resource_uid": 94,
               "task_name": "تخریب جداول", "task_wbs": "1.5.1.2",
               "task_start": "2025-08-19T08:00", "task_finish": "2025-09-17T17:00",
               "resource_name": "آرماتور", "resource_type": "MATERIAL",
               "resource_unit": "مترطول", "normalized_unit": "m",
               "quantity": None, "quantity_unit": None,
               "weight_rial": Decimal("1.55"), "weight_time": None, "weight_base": None,
               "actual_progress": None, "actual_progress_percent": Decimal("84"),
               "physical_progress": None, "planned_progress": None,
               "progress_variance": Decimal("-0.2"), "source_cost": Decimal("5660176000"),
               "source_actual_cost": None, "source_fixed_cost": None}
        row.update(over)
        return assignment_row(_builder_row(row))

    def test_the_page_gets_its_dates_resource_type_and_unit(self):
        feed = self.stored()
        self.assertEqual("2025-08-19T08:00", feed["task"]["taskStart"])
        self.assertEqual("2025-09-17T17:00", feed["task"]["taskFinish"])
        self.assertEqual("material", feed["resourceType"])
        # The RESOLVED unit, not the file's text. The page maps this code to "متر".
        self.assertEqual("m", feed["unit"])

    def test_a_resource_initial_does_not_reach_the_page_as_a_unit(self):
        """MS Project's `initials` is not a unit, and must not be shown as one.

        On a real schedule this is the common case, not the edge one: 394 of 789 rows of
        `test_progress.mpp` carry a single Persian letter in the file's unit field, because
        that field is `initials` -- the first letter of the resource's name. The sync
        already decided about each of them and wrote NULL to `normalized_unit`. The feed
        used to fall back to the raw text, and the page prints any non-Latin string through
        unchanged, so the واحد column showed 'د'. NULL renders as "بدون واحد" instead.
        """
        feed = self.stored(resource_unit="د", normalized_unit=None)
        self.assertIsNone(feed["unit"])

    def test_an_unrecognised_unit_is_unresolved_rather_than_passed_through(self):
        # `دسیمترمکعب` is a real unit the registry does not carry, and two rows of the
        # schedule use it. Unresolved is the correct answer: inventing a conversion to m3
        # here would put a number in a report that nobody approved.
        self.assertIsNone(self.stored(resource_unit="دسیمترمکعب",
                                      normalized_unit=None)["unit"])

    def test_an_approved_quantity_unit_still_wins_over_the_resolved_one(self):
        # `quantity_unit` belongs to the APPROVED quantity, which a person entered. When
        # one exists it is the unit that quantity is in, and it outranks anything derived
        # from the file.
        self.assertEqual("kg", self.stored(quantity=Decimal("5"), quantity_unit="kg",
                                           normalized_unit="m")["unit"])

    def test_a_work_resource_is_not_classified_as_labour_or_equipment(self):
        self.assertIsNone(self.stored(resource_type="WORK")["resourceType"])

    def test_the_metrics_block_carries_the_variance_and_the_schedule_cost(self):
        metrics = self.stored()["task"]["metrics"]
        self.assertEqual("-0.2", metrics["progressVariance"])
        self.assertEqual("5660176000", metrics["taskCost"])

    def test_no_quantity_reaches_the_feed_when_none_was_approved(self):
        feed = self.stored()
        self.assertIsNone(feed["plannedQuantity"])
        self.assertIsNone(feed["actualQuantity"])

    def test_no_work_reaches_the_feed(self):
        feed = self.stored()
        for field in ("plannedWork", "actualWork", "remainingWork",
                      "assignmentWorkCompletePercent"):
            self.assertIsNone(feed[field], field)


if __name__ == "__main__":
    unittest.main()
