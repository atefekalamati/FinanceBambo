# -*- coding: utf-8 -*-
"""The estimate the file states: a material quantity, a unit rate, and the proof of both.

MS Project keeps a material assignment's physical quantity in its own field, and the price
of one such unit on the resource. What these defend is that Finance takes those two and
nothing else: not Units (the same quantity scaled by a hundred), not Work (hours), not the
assignment's Cost (a total, not a rate) — and that it takes them only where the file's own
arithmetic proves the rate is per unit of that quantity.

They also defend the shape of the completion: a line created without an original is
completed BESIDE itself, never inside itself, so the immutability trigger never has to be
argued with and the original columns keep saying exactly what they always said.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.estimate_basis import (effective_original_price,
                                               effective_original_quantity,
                                               original_value_source)
from coreint.finance_mpp_mapping import MATERIAL_UNIT_RATE, estimate_basis
from coreint.finance_mpp_sync import finance_rows

#: The bytes the toman decision was taken for. `finance_rows` refuses to convert the
#: currency of any other file, so the tests that want rials must present this one.
APPROVED_SHA = "b86b63738f592bfd90286ab08daedcea4374d815c02a7503adc18182cec6e908"


class ParsedFile:
    def __init__(self, tasks, resources, assignments,
                 currency_symbol="تومان", currency_code="IRR"):
        self.tasks, self.resources, self.assignments = list(tasks), list(resources), list(assignments)
        self.warnings, self.parser_engine = [], "test-engine"
        self.currency_symbol, self.currency_code = currency_symbol, currency_code


def task(uid=1212, name="تجهیز کارگاه مستمر"):
    metrics = dict.fromkeys(
        ("weight_rial", "weight_time", "weight_base", "actual_progress",
         "actual_progress_percent", "physical_progress", "planned_progress",
         "task_cost", "task_actual_cost", "task_fixed_cost"))
    return {"uid": uid, "name": name, "wbs": "1.4.2", "metrics": metrics, "raw_fields": {}}


def resource(uid=155, native_type="MATERIAL", rate="12565115391.0", unit="واحد"):
    return {"uid": uid, "name": "تجهیز مستمر", "native_type": native_type,
            "initials": unit, "material_label": None, "quantity": "1.0",
            "quantity_unit": unit, "quantity_unit_source": "initials",
            "standard_rate": rate}


def assignment(uid=9703, task_uid=1212, resource_uid=155,
               material="1.0", units="100.0", cost="12565115391.0"):
    return {"assignment_uid": uid, "task_uid": task_uid, "resource_uid": resource_uid,
            "units": units, "planned_quantity": material, "cost": cost,
            "planned_work": "1.0"}


def one_row(**overrides):
    """The single assignment row `finance_rows` produces for the sample above."""
    parsed = ParsedFile([task()],
                        [resource(**overrides.pop("resource", {}))],
                        [assignment(**overrides.pop("assignment", {}))],
                        **overrides)
    rows = finance_rows(parsed, source_sha256=overrides.pop("sha", APPROVED_SHA))
    return next(row for row in rows if row["source_assignment_uid"] is not None)


class WhatTheFileStatesTests(unittest.TestCase):
    def test_the_material_field_becomes_the_quantity_and_the_rate_becomes_the_price(self):
        row = one_row()
        self.assertEqual(row["source_material_quantity"], Decimal("1"))
        # 12,565,115,391 toman x 10. Converted once, on the way in, and never again.
        self.assertEqual(row["source_resource_rate_irr"], Decimal("125651153910"))
        self.assertEqual(row["source_rate_basis"], MATERIAL_UNIT_RATE)

    def test_the_quantity_is_not_the_units_and_the_price_is_not_the_cost(self):
        row = one_row()
        # Units is the same quantity scaled by a hundred; both are stored, and they are
        # different columns because they are different numbers.
        self.assertEqual(row["source_assignment_units"], Decimal("1"))
        self.assertEqual(row["source_material_quantity"], Decimal("1"))
        # The assignment's cost is a total. It is not the rate, even when they coincide
        # for a quantity of one -- what makes the rate the rate is the resource stating it.
        self.assertEqual(row["source_assignment_cost_irr"], Decimal("125651153910.0"))
        self.assertIsNot(row["source_resource_rate_irr"], row["source_assignment_cost_irr"])

    def test_the_double_s_rounding_tail_is_dropped_and_nothing_else_is(self):
        # MPXJ hands back 3538.1100000000006 for a quantity a planner typed as 3538.11.
        row = one_row(assignment={"material": "3538.1100000000006", "cost": "2830488000.0000005",
                                  "units": "353811.00000000006"},
                      resource={"rate": "800000.0", "unit": "مترطول"})
        self.assertEqual(row["source_material_quantity"], Decimal("3538.11"))
        self.assertEqual(row["source_resource_rate_irr"], Decimal("8000000"))
        self.assertEqual(row["source_rate_basis"], MATERIAL_UNIT_RATE)

    def test_a_work_resource_states_no_quantity_and_its_rate_is_not_a_unit_price(self):
        row = one_row(resource={"native_type": "WORK", "rate": "0.0"},
                      assignment={"material": None, "cost": "500000.0"})
        self.assertIsNone(row["source_material_quantity"])
        # The rate the file states is still recorded -- a real zero, distinguishable from
        # nothing being stated -- but nothing proves it prices a unit of anything.
        self.assertEqual(row["source_resource_rate_irr"], Decimal("0"))
        self.assertIsNone(row["source_rate_basis"])

    def test_a_rate_the_file_s_own_arithmetic_contradicts_is_not_a_basis(self):
        # Quantity x rate = 2,000,000 but the file says the assignment cost 999,999.
        row = one_row(assignment={"material": "2.0", "cost": "999999.0"},
                      resource={"rate": "1000000.0"})
        self.assertEqual(row["source_material_quantity"], Decimal("2"))
        self.assertEqual(row["source_resource_rate_irr"], Decimal("10000000"))
        self.assertIsNone(row["source_rate_basis"])

    def test_the_stage_heading_row_states_none_of_the_three(self):
        parsed = ParsedFile([task(), task(uid=1300, name="اجرای عملیات سیویل")],
                            [resource()], [assignment()])
        heading = next(row for row in finance_rows(parsed, source_sha256=APPROVED_SHA)
                       if row["source_assignment_uid"] is None)
        self.assertIsNone(heading["source_material_quantity"])
        self.assertIsNone(heading["source_resource_rate_irr"])
        self.assertIsNone(heading["source_rate_basis"])

    def test_an_unresolved_currency_stops_the_rate_rather_than_guessing_at_it(self):
        with self.assertRaises(Exception) as refusal:
            one_row(currency_symbol="€", currency_code="EUR")
        self.assertIn("currency", str(refusal.exception).lower())


class TheGateTests(unittest.TestCase):
    def test_a_proven_row_hands_over_both_numbers(self):
        self.assertEqual(
            estimate_basis({"source_rate_basis": MATERIAL_UNIT_RATE,
                            "source_material_quantity": Decimal("3538.11"),
                            "source_resource_rate_irr": Decimal("8000000")}),
            (Decimal("3538.11"), Decimal("8000000")))

    def test_an_unproven_row_hands_over_neither(self):
        self.assertEqual(
            estimate_basis({"source_rate_basis": None,
                            "source_material_quantity": Decimal("3538.11"),
                            "source_resource_rate_irr": Decimal("8000000")}),
            (None, None))

    def test_half_a_row_is_not_half_an_estimate(self):
        for half in ({"source_material_quantity": None,
                      "source_resource_rate_irr": Decimal("8000000")},
                     {"source_material_quantity": Decimal("3538.11"),
                      "source_resource_rate_irr": None}):
            self.assertEqual(
                estimate_basis({"source_rate_basis": MATERIAL_UNIT_RATE, **half}),
                (None, None))


class TheEffectiveOriginalTests(unittest.TestCase):
    """The SQL that decides which of the two numbers a reader sees.

    Checked as text rather than against a database, because what matters is the SHAPE: the
    line's own column first, the completion only as a fallback, and the completion looked up
    inside the tenant. The statements themselves are exercised against a real database by
    `scripts/test_only/complete_mpp_estimate_basis.py`, which is run on a restored copy
    before it is run locally.
    """

    def test_the_line_s_own_column_is_preferred(self):
        for expression in (effective_original_quantity("l"), effective_original_price("l")):
            self.assertTrue(expression.startswith("COALESCE(l.original_"))
            self.assertIn("estimate_line_source_completions", expression)
            self.assertLess(expression.index("l.original_"),
                            expression.index("estimate_line_source_completions"))

    def test_the_completion_is_looked_up_inside_the_tenant(self):
        for expression in (effective_original_quantity("l"), effective_original_price("l"),
                           original_value_source("l")):
            self.assertIn("c.organization_id = l.organization_id", expression)
            self.assertIn("c.project_id = l.project_id", expression)
            self.assertIn("c.estimate_line_id = l.id", expression)

    def test_the_provenance_names_the_three_states_and_no_others(self):
        expression = original_value_source("l")
        self.assertIn("'recorded'", expression)
        self.assertIn("'source_completion'", expression)
        self.assertIn("ELSE NULL", expression)

    def test_neither_expression_reads_a_schedule_cost_or_a_price_version(self):
        # The estimate's basis comes from the estimate's own record. A schedule total and
        # the price of the day are different facts and live in different columns.
        for expression in (effective_original_quantity("l"), effective_original_price("l")):
            self.assertNotIn("price_versions", expression)
            self.assertNotIn("source_cost", expression)
            self.assertNotIn("source_assignment_cost_irr", expression)


if __name__ == "__main__":
    unittest.main()
