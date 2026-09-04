# -*- coding: utf-8 -*-
"""The MPXJ reader against the real reference schedule, no doubles anywhere.

This test boots the actual JVM and parses ``Sources/test_progress.mpp`` -- 328 tasks,
81 resources, 727 assignments, measured once and pinned here. It runs in the canonical
interpreter (the one carrying mpxj + jpype) with ``MPP_JAVA_HOME`` pointing at a full
JRE; a machine without either FAILS loudly rather than skipping, because a suite that
silently stops parsing real files has lost exactly the coverage this file exists for.

What is pinned is what Finance depends on:

  * identity comes from UIDs, never names;
  * Work (hours) and Material quantity live in different keys and are never substituted;
  * numbers travel as Decimal-built strings, never floats;
  * what the file does not state is None;
  * assignments naming no resource are KEPT and counted in a warning, not dropped.
"""

import os
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.mpp_reader import MpxjMppReader

REFERENCE_FILE = BACKEND_ROOT.parent / "Sources" / "test_progress.mpp"


class RealFileTests(unittest.TestCase):
    """One parse, shared by every assertion: the JVM boots once per process."""

    @classmethod
    def setUpClass(cls):
        java_home = os.environ.get("MPP_JAVA_HOME") or os.environ.get("JAVA_HOME")
        cls.assertTrue(
            REFERENCE_FILE.is_file(),
            "the reference schedule Sources/test_progress.mpp must exist -- it is "
            "checked in; a missing copy is a broken checkout, not an optional case")
        reader = MpxjMppReader(java_home=java_home)
        cls.project = reader.read(REFERENCE_FILE)

    # ------------------------------------------------------------------------ the counts
    def test_the_reference_counts_are_exact(self):
        self.assertEqual(328, len(self.project.tasks))
        self.assertEqual(81, len(self.project.resources))
        self.assertEqual(727, len(self.project.assignments))

    def test_the_authoring_application_is_named(self):
        self.assertIn("Project", self.project.application)

    # ---------------------------------------------------------------------- identity
    def test_every_task_has_a_uid_and_uids_are_unique(self):
        uids = [task["uid"] for task in self.project.tasks]
        self.assertNotIn(None, uids)
        self.assertEqual(len(uids), len(set(uids)), "a duplicated task uid")

    def test_every_resource_has_a_uid_and_uids_are_unique(self):
        uids = [resource["uid"] for resource in self.project.resources]
        self.assertNotIn(None, uids)
        self.assertEqual(len(uids), len(set(uids)))

    def test_names_repeat_which_is_why_they_are_not_identity(self):
        # The reference file itself demonstrates the rule: task names collide freely.
        names = [task["name"] for task in self.project.tasks if task["name"]]
        self.assertLess(len(set(names)), len(names),
                        "if this ever fails the file changed, not the rule")

    # ----------------------------------------------------------- the rebar resource
    def test_the_rebar_resource_carries_its_material_facts(self):
        rebar = next(r for r in self.project.resources if r["uid"] == 94)
        self.assertEqual("آرماتور", rebar["name"])
        self.assertEqual("MATERIAL", rebar["native_type"])
        self.assertEqual("1329121.22", rebar["quantity"])
        self.assertEqual("کیلوگرم", rebar["quantity_unit"])
        # On the reference schedules the planners wrote units in Initials, not
        # MaterialLabel; the provenance key records that and must keep doing so.
        self.assertEqual("initials", rebar["quantity_unit_source"])
        # MPXJ's Rate.getAmount() is a Java double; the Decimal-string conversion is
        # faithful to it, trailing zero and all. Parsing it into numeric is lossless.
        self.assertEqual("66150.0", rebar["standard_rate"])

    # ----------------------------------------------- work is time, quantity is stuff
    def test_work_and_quantity_are_separate_and_never_substituted(self):
        material_uids = {r["uid"] for r in self.project.resources
                         if r["native_type"] == "MATERIAL"}
        with_quantity = [a for a in self.project.assignments
                         if a["planned_quantity"] is not None]
        self.assertTrue(with_quantity, "the file assigns real material quantities")
        for assignment in with_quantity:
            self.assertIn(assignment["resource_uid"], material_uids,
                          "a physical quantity on a non-material resource")
        work_only = [a for a in self.project.assignments
                     if a["planned_work"] is not None
                     and a["planned_quantity"] is None]
        self.assertTrue(work_only,
                        "labor/equipment hours exist and stay OUT of quantity")

    # ------------------------------------------------------------- value discipline
    def test_numbers_travel_as_decimal_strings_or_none_never_floats(self):
        numeric_keys = ("quantity", "max_units", "standard_rate", "work", "cost")
        for resource in self.project.resources:
            for key in numeric_keys:
                self.assertNotIsInstance(resource[key], float, key)
        for assignment in self.project.assignments:
            for key in ("units", "planned_work", "planned_quantity", "cost"):
                self.assertNotIsInstance(assignment[key], float, key)

    def test_what_the_file_does_not_state_is_none_not_zero(self):
        unstated = [r for r in self.project.resources if r["quantity"] is None]
        self.assertTrue(unstated, "labor resources state no material quantity")
        for resource in unstated:
            self.assertIsNone(resource["quantity_unit"],
                              "a unit beside an absent quantity is an invention")

    # ------------------------------------------------------------------- the warning
    def test_unlinked_assignments_are_kept_and_counted(self):
        unlinked = [a for a in self.project.assignments
                    if a["resource_uid"] is None]
        self.assertEqual(12, len(unlinked), "the reference file has exactly 12")
        self.assertTrue(any("12 assignment(s) name no resource" in warning
                            for warning in self.project.warnings),
                        self.project.warnings)

    def test_every_assignment_names_a_task_that_exists(self):
        task_uids = {task["uid"] for task in self.project.tasks}
        for assignment in self.project.assignments:
            self.assertIn(assignment["task_uid"], task_uids)


if __name__ == "__main__":
    unittest.main()
