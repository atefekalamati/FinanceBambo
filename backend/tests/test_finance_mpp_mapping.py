# -*- coding: utf-8 -*-
"""Turning schedule rows into financial records, on identity and nothing else.

The mapping's whole job is to be boring and repeatable: the same file read twice must
recognise what it already made. These tests pin the identity rules that make that true,
and the refusals that keep a guess out of a financial record.
"""

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_mpp_sync import MATERIAL_UNIT_RATE
from coreint.finance_mpp_mapping import (CLASSIFIABLE_TYPES, FIXED_COST_RESIDUE_TASK_UID,
                                         FIXED_COST_RESOURCE_CODE,
                                         FIXED_COST_RESOURCE_TITLE, RESOURCE_CODE_PREFIX,
                                         FinanceMppClassificationRefused,
                                         FinanceMppMappingService, _FIXED_COST_TASKS,
                                         _finance_type)


def found_by_its_own_code(sql):
    """Whether a lookup is the fixed cost item's, found by code because it comes from
    no schedule resource at all -- and a code no legacy record carries is no more
    reachable than a source uid is."""
    return "AND code=%s" in sql and "finance_resources" in sql

ORG = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")


def row(assignment, task, resource, *, name="بتن ۴۰۰", kind="MATERIAL",
        unit="مترمکعب", wbs="1.5.1", task_name="بتن ریزی",
        fixed_cost=None, fixed_cost_irr=None):
    """One persisted schedule row. `fixed_cost` is the TASK's, repeated on every row it has,
    which is why the fixed-cost query de-duplicates and these tests can hand it in twice."""
    return {"source_task_uid": task, "source_assignment_uid": assignment,
            "source_resource_uid": resource, "task_name": task_name, "task_wbs": wbs,
            "resource_name": name, "resource_type": kind, "resource_unit": unit,
            "source_fixed_cost": fixed_cost, "source_fixed_cost_irr": fixed_cost_irr}


class Cursor:
    def __init__(self, db):
        self._db, self._rows = db, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self._db.statements.append((text, params))
        if "min(resource_name)" in text:
            # What the FILE says about one resource, which `classify` checks first.
            uid = params[2]
            named = [r for r in self._db.source_rows if r["source_resource_uid"] == uid]
            self._rows = [{"name": named[0]["resource_name"],
                           "native": named[0]["resource_type"]}] if named else [
                {"name": None, "native": None}]
        elif "source_fixed_cost_irr" in text and "FROM finance_mpp_rows" in text:
            # The task-level query, which the real one narrows and de-duplicates in SQL:
            # one row per task, and only where the file states a fixed cost at all.
            seen, stated = set(), []
            for source in self._db.source_rows:
                uid = source["source_task_uid"]
                if uid in seen or not source.get("source_fixed_cost"):
                    continue
                if source.get("source_fixed_cost_irr") is None:
                    continue
                seen.add(uid)
                stated.append(source)
            self._rows = stated
        elif "FROM finance_mpp_rows" in text:
            self._rows = list(self._db.source_rows)
        elif "AND code=%s" in text and "FROM finance_resources" in text:
            found = self._db.resources.get(params[2])   # the code names this one
            self._rows = [{"id": found}] if found else []
        elif "FROM finance_resources" in text and text.startswith("SELECT id"):
            # Two callers, two shapes: the mapping asks for `id`, `classify` asks for
            # `id, resource_type`. Both look the resource up by its source identity.
            found = self._db.resources.get(params[2])
            self._rows = [{"id": found, "resource_type": "equipment"}] if found else []
        elif text.startswith("SELECT id FROM estimate_lines") and "source_task_uid=%s" in text:
            found = self._db.fixed_cost_lines.get(params[2])   # keyed on the TASK
            self._rows = [{"id": found}] if found else []
        elif text.startswith("SELECT id FROM estimate_lines"):
            found = self._db.lines.get(params[2])
            self._rows = [{"id": found}] if found else []
        elif "INSERT INTO finance_resources" in text and "'general_cost'" in text:
            self._db.resources[params[3]] = params[0]      # code -> id
            self._rows = []
        elif "INSERT INTO finance_resources" in text:
            self._db.resources[params[8]] = params[0]      # source_resource_uid -> id
            self._rows = []
        elif "INSERT INTO estimate_lines" in text and "'progress_feed',NULL," in text:
            self._db.fixed_cost_lines[params[6]] = params[0]   # source_task_uid -> id
            self._rows = []
        elif "INSERT INTO estimate_lines" in text:
            self._db.lines[params[8]] = params[0]          # source_assignment_uid -> id
            self._rows = []
        else:
            self._rows = []

    async def fetchall(self):
        return list(self._rows)

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Db:
    def __init__(self, source_rows):
        self.source_rows = list(source_rows)
        self.statements, self.resources, self.lines = [], {}, {}
        #: Fixed cost lines live in their own book because they are keyed on the task, and
        #: a task uid and an assignment uid are different numbers that look alike.
        self.fixed_cost_lines = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return Transaction()

    def cursor(self, **_kwargs):
        return Cursor(self)


def run(rows, db=None, ids=None):
    db = db or Db(rows)
    counter = [0]

    def new_id():
        counter[0] += 1
        return UUID(int=counter[0])

    async def factory():
        return db

    service = FinanceMppMappingService(factory, id_factory=ids or new_id)
    result = asyncio.new_event_loop().run_until_complete(
        service.map_source_version(ORG, "terrace", VERSION, actor_user_id=UUID(int=1)))
    return result, db


class ResourceIdentityTests(unittest.TestCase):
    def test_a_resource_is_created_from_the_files_resource_uid(self):
        result, db = run([row(1, 100, 97)])
        self.assertEqual(1, result["resourcesCreated"])
        insert = next(p for text, p in db.statements if "INSERT INTO finance_resources" in text)
        self.assertEqual(97, insert[8], "keyed on the MPP resource uid")
        self.assertEqual("%s97" % RESOURCE_CODE_PREFIX, insert[4])
        self.assertEqual("بتن ۴۰۰", insert[5], "named from the RESOURCE, never the task")

    def test_the_files_padding_does_not_reach_the_stored_title(self):
        """A schedule's names carry trailing spaces, and the table must not.

        `ResourceResponse` inherits `ResourceCreate.nonblank`, which strips `title` -- so a
        resource created through the API is stored trimmed while one created here kept the
        file's padding. Nine of this project's 189 resources hold a trailing space for that
        reason, and because the response strips it AGAIN on the way out, the page and the
        table disagree silently: an export or a report payload reads one string while the
        UI shows another.
        """
        _result, db = run([row(1, 100, 97, name="آرماتوربندي ستون ها ")])
        insert = next(p for text, p in db.statements
                      if "INSERT INTO finance_resources" in text)
        self.assertEqual("آرماتوربندي ستون ها", insert[5])

    def test_leading_padding_goes_too(self):
        _result, db = run([row(1, 100, 97, name="  بتن ۴۰۰")])
        insert = next(p for text, p in db.statements
                      if "INSERT INTO finance_resources" in text)
        self.assertEqual("بتن ۴۰۰", insert[5])

    def test_a_name_of_nothing_but_spaces_is_a_name_the_file_did_not_give(self):
        # Trimming must not produce a blank title: the API refuses to render one, and a
        # financial item with no name is worse than one that says it has none.
        _result, db = run([row(1, 100, 97, name="   ")])
        insert = next(p for text, p in db.statements
                      if "INSERT INTO finance_resources" in text)
        self.assertEqual("منبع بدون نام", insert[5])

    def test_a_very_long_name_is_bounded_and_still_not_left_padded(self):
        # Cutting at 120 characters can itself land on a space, so the trim happens on both
        # sides of the bound.
        _result, db = run([row(1, 100, 97, name=("ب" * 119) + "  tail")])
        insert = next(p for text, p in db.statements
                      if "INSERT INTO finance_resources" in text)
        self.assertLessEqual(len(insert[5]), 120)
        self.assertEqual(insert[5], insert[5].strip())

    def test_the_task_never_becomes_a_resource(self):
        _result, db = run([row(1, 1244, 97, task_name="بتن فونداسیون")])
        insert = next(p for text, p in db.statements if "INSERT INTO finance_resources" in text)
        self.assertNotIn("بتن فونداسیون", insert, "the task name is not a resource title")
        self.assertNotEqual(1244, insert[8], "the task uid is not a resource identity")

    def test_one_resource_serving_many_activities_is_created_once(self):
        # «ترک میکسر» appears on sixty-four activities in the real file. One item, many lines.
        result, _db = run([row(1, 100, 97), row(2, 101, 97), row(3, 102, 97)])
        self.assertEqual(1, result["resourcesCreated"])
        self.assertEqual(3, result["linesCreated"])

    def test_one_activity_drawing_on_many_resources_gets_a_line_each(self):
        result, _db = run([row(1, 100, 97), row(2, 100, 98, name="آرماتور"),
                           row(3, 100, 99, name="قالب")])
        self.assertEqual(3, result["resourcesCreated"])
        self.assertEqual(3, result["linesCreated"])

    def test_an_already_classified_work_resource_is_matched_not_skipped(self):
        # The ordering that matters: the lookup runs BEFORE the kind rule. Asking the rule
        # first kept skipping a WORK resource somebody had since decided was equipment --
        # the decision was stored and ignored, and no line was ever built from it.
        db = Db([row(1, 100, 156, name="بیل مکانیکی", kind="WORK")])
        db.resources[156] = UUID(int=99)          # a person classified it earlier
        result, _ = run(db.source_rows, db=db)
        self.assertEqual(1, result["resourcesMatched"])
        self.assertEqual(1, result["linesCreated"])
        self.assertEqual([], result["unclassifiedResources"])

    def test_a_work_resource_is_left_for_a_person_to_classify(self):
        # MS Project says WORK; Finance separates labour from equipment and the file does
        # not. Guessing would put a claim in a financial record that nobody made.
        result, db = run([row(1, 100, 156, name="بیل مکانیکی", kind="WORK")])
        self.assertEqual(0, result["resourcesCreated"])
        self.assertEqual(0, result["linesCreated"])
        self.assertEqual(1, result["unmappedRows"])
        self.assertEqual([{"sourceResourceUid": 156, "name": "بیل مکانیکی",
                           "nativeType": "WORK"}], result["unclassifiedResources"])
        self.assertFalse(any("INSERT" in text for text, _p in db.statements))

    def test_the_kinds_the_file_states_unambiguously_are_mapped(self):
        self.assertEqual("material", _finance_type("MATERIAL"))
        self.assertEqual("general_cost", _finance_type("COST"))
        self.assertIsNone(_finance_type("WORK"))
        self.assertIsNone(_finance_type(None))

    def test_a_general_cost_carries_no_unit(self):
        _result, db = run([row(1, 100, 97, kind="COST", name="بیمه", unit="مترمکعب")])
        insert = next(p for text, p in db.statements if "INSERT INTO finance_resources" in text)
        self.assertEqual("general_cost", insert[3])
        self.assertIsNone(insert[6], "an amount is not measured in metres")
        self.assertIsNone(insert[7])


class EstimateLineIdentityTests(unittest.TestCase):
    def test_a_line_is_keyed_on_the_assignment_uid(self):
        _result, db = run([row(55, 1244, 97)])
        insert = next(p for text, p in db.statements if "INSERT INTO estimate_lines" in text)
        self.assertEqual(55, insert[8], "source_assignment_uid is the identity")
        self.assertEqual(1244, insert[9], "the task uid is carried for corroboration")

    def test_a_row_the_file_proves_nothing_for_carries_no_quantity_and_no_price(self):
        # No material quantity, no proven unit rate: both columns stay NULL rather than
        # being derived from work, units, duration or the assignment's total cost.
        _result, db = run([row(1, 100, 97)])
        insert = next(p for text, p in db.statements if "INSERT INTO estimate_lines" in text)
        self.assertIsNone(insert[6], "no quantity was stated, so none is written")
        self.assertIsNone(insert[7], "no unit rate was proven, so none is written")

    def test_a_row_the_file_proves_carries_the_file_s_own_quantity_and_rate(self):
        # The Material field and the resource's standard rate, whose product the file's own
        # cost reproduces. This is the estimate's basis; it is not a price of the day.
        proven = row(9703, 1212, 155)
        proven.update({"source_material_quantity": Decimal("1"),
                       "source_resource_rate_irr": Decimal("125651153910"),
                       "source_rate_basis": MATERIAL_UNIT_RATE})
        result, db = run([proven])
        insert = next(p for text, p in db.statements if "INSERT INTO estimate_lines" in text)
        self.assertEqual(Decimal("1"), insert[6])
        self.assertEqual(Decimal("125651153910"), insert[7])
        self.assertEqual(1, result["linesWithEstimate"])

    def test_an_unproven_rate_is_refused_even_when_both_numbers_are_present(self):
        # A rate whose product does not reproduce the file's cost proves nothing, and half
        # a basis is not half an estimate: the line is created without either number.
        unproven = row(9704, 1212, 156)
        unproven.update({"source_material_quantity": Decimal("2"),
                         "source_resource_rate_irr": Decimal("10000000"),
                         "source_rate_basis": None})
        result, db = run([unproven])
        insert = next(p for text, p in db.statements if "INSERT INTO estimate_lines" in text)
        self.assertEqual((None, None), (insert[6], insert[7]))
        self.assertEqual(0, result["linesWithEstimate"])

    def test_the_pairing_identifiers_come_from_the_file(self):
        _result, db = run([row(55, 1244, 97, wbs="1.8.1.12")])
        insert = next(p for text, p in db.statements if "INSERT INTO estimate_lines" in text)
        self.assertEqual("1.8.1.12", insert[4], "activity code is the file's WBS")
        self.assertEqual("55", insert[5], "assignment id is the file's assignment uid")

    def test_a_row_naming_no_resource_produces_nothing(self):
        # The query already excludes them; this pins that such a row could not become a
        # line even if it arrived, because there is no resource to name.
        result, _db = run([row(1, 100, 156, kind="WORK")])
        self.assertEqual(0, result["linesCreated"])
        self.assertEqual(1, result["unmappedRows"])


class ClassificationTests(unittest.TestCase):
    """The one decision the file cannot make, made once and stored as the resource."""

    def service(self, db):
        async def factory():
            return db
        return FinanceMppMappingService(factory, id_factory=lambda: UUID(int=7))

    def classify(self, db, uid=156, kind="equipment", unit="hour"):
        return asyncio.new_event_loop().run_until_complete(
            self.service(db).classify(ORG, "terrace", uid, kind, unit, actor_user_id=UUID(int=1)))

    def work_db(self, uid=156, native="WORK"):
        return Db([row(1, 100, uid, name="بیل مکانیکی", kind=native)])

    def test_work_becomes_equipment_when_a_person_says_so(self):
        db = self.work_db()
        decision = self.classify(db, kind="equipment")
        self.assertEqual("classified", decision["status"])
        self.assertEqual("equipment", decision["resourceType"])
        insert = next(p for t, p in db.statements if "INSERT INTO finance_resources" in t)
        self.assertEqual("equipment", insert[3])
        self.assertEqual(("hour", "time"), (insert[6], insert[7]), "unit and its dimension")
        self.assertEqual(156, insert[8], "stored against the source identity")

    def test_the_decision_is_recorded_as_an_event_not_only_as_a_row(self):
        """The resource says who and when. Only the event says what was chosen.

        `created_by` and `created_at` are on every resource the mapper writes too, so a
        column cannot tell a judgement apart from an import. A WORK resource is the one
        kind Finance refuses to type on its own, and that refusal is only honest if the
        answer a person gave is written down as an answer.
        """
        db = self.work_db()
        self.classify(db, kind="equipment")
        event = next((p for t, p in db.statements
                      if "INSERT INTO finance_audit_events" in t
                      and "finance_resource.classified" in t), None)
        self.assertIsNotNone(event, "a person's classification left no audit event")
        self.assertEqual(ORG, event[1])
        self.assertEqual("terrace", event[2])
        self.assertEqual(UUID(int=1), event[3], "the event names who decided")
        before, after = event[5].obj, event[6].obj
        self.assertEqual("WORK", before["nativeType"], "before states what the file said")
        self.assertIsNone(before["resourceType"], "the file typed it as nothing")
        self.assertEqual("equipment", after["resourceType"], "after states what was chosen")
        self.assertEqual(156, after["sourceResourceUid"])

    def test_an_unchanged_decision_records_no_second_event(self):
        """Repeating the request is not a new decision, so it is not a new event."""
        db = self.work_db()
        db.resources[156] = UUID(int=99)          # a person classified it earlier
        decision = self.classify(db)
        self.assertEqual("unchanged", decision["status"])
        self.assertFalse(any("finance_resource.classified" in t for t, _p in db.statements))

    def test_work_becomes_labor_when_a_person_says_so(self):
        decision = self.classify(self.work_db(), kind="labor")
        self.assertEqual("labor", decision["resourceType"])

    def test_only_labour_and_equipment_may_be_chosen(self):
        self.assertEqual(("labor", "equipment"), CLASSIFIABLE_TYPES)
        for refused in ("material", "general_cost", "", None, "Equipment"):
            with self.assertRaises(FinanceMppClassificationRefused) as caught:
                self.classify(self.work_db(), kind=refused)
            self.assertEqual("FINANCE_MPP_TYPE_NOT_CLASSIFIABLE", caught.exception.code)

    def test_a_unit_the_registry_does_not_define_is_refused(self):
        # The file's own "unit" for a WORK resource is MS Project's initials -- the first
        # letter of the name. Accepting it would put "ت" in a unit column.
        with self.assertRaises(FinanceMppClassificationRefused) as caught:
            self.classify(self.work_db(), unit="ت")
        self.assertEqual("FINANCE_MPP_UNIT_UNKNOWN", caught.exception.code)

    def test_a_resource_the_file_already_typed_needs_no_decision(self):
        with self.assertRaises(FinanceMppClassificationRefused) as caught:
            self.classify(self.work_db(native="MATERIAL"))
        self.assertEqual("FINANCE_MPP_NOT_A_WORK_RESOURCE", caught.exception.code)

    def test_an_unknown_resource_is_refused_rather_than_created(self):
        db = Db([])
        with self.assertRaises(FinanceMppClassificationRefused) as caught:
            self.classify(db)
        self.assertEqual("FINANCE_MPP_RESOURCE_NOT_FOUND", caught.exception.code)

    def test_repeating_a_decision_changes_nothing(self):
        db = self.work_db()
        self.classify(db)
        before = len([t for t, _p in db.statements if t.startswith("INSERT")])
        again = self.classify(db)
        self.assertEqual("unchanged", again["status"])
        after = len([t for t, _p in db.statements if t.startswith("INSERT")])
        self.assertEqual(before, after, "a repeat inserts nothing")

    def test_classification_never_touches_a_legacy_record(self):
        db = self.work_db()
        self.classify(db)
        for text, _params in db.statements:
            self.assertNotIn("external_resource_id", text)
            self.assertFalse(text.startswith("UPDATE"), text[:60])
            self.assertFalse(text.startswith("DELETE"), text[:60])

    def test_mapping_refuses_to_create_records_nobody_asked_for(self):
        # estimate_lines.created_by is NOT NULL and a financial record names its author.
        async def factory():
            return self.work_db()
        with self.assertRaises(FinanceMppClassificationRefused) as caught:
            asyncio.new_event_loop().run_until_complete(
                FinanceMppMappingService(factory).map_source_version(ORG, "terrace", VERSION))
        self.assertEqual("FINANCE_MPP_ACTOR_REQUIRED", caught.exception.code)


class IdempotenceTests(unittest.TestCase):
    def test_reading_the_same_source_twice_creates_nothing_the_second_time(self):
        rows = [row(1, 100, 97), row(2, 101, 98, name="آرماتور")]
        db = Db(rows)
        first, _ = run(rows, db=db)
        second, _ = run(rows, db=db)
        self.assertEqual((2, 2), (first["resourcesCreated"], first["linesCreated"]))
        self.assertEqual((0, 0), (second["resourcesCreated"], second["linesCreated"]))
        self.assertEqual((2, 2), (second["resourcesMatched"], second["linesMatched"]))

    def test_a_legacy_record_can_never_be_matched(self):
        # Legacy rows carry no source_resource_uid and no source_assignment_uid, so the
        # lookups here cannot see them and nothing updates or deletes them. A fixed cost
        # row is in the data on purpose: that pass has lookups of its own and is held to
        # the same rule.
        _result, db = run([row(1, 100, 97),
                           row(2, 101, 98, fixed_cost="500", fixed_cost_irr="5000")])
        lookups = [(t, p) for t, p in db.statements if t.startswith("SELECT id FROM")]
        for text, _params in lookups:
            self.assertTrue("source_" in text or found_by_its_own_code(text), text)
            self.assertNotIn("external_resource_id", text)
            self.assertNotIn("assignment_external_id", text)

    def test_nothing_is_ever_updated_or_deleted(self):
        _result, db = run([row(1, 100, 97), row(2, 101, 98)])
        for text, _params in db.statements:
            self.assertFalse(text.startswith("UPDATE"), text[:60])
            self.assertFalse(text.startswith("DELETE"), text[:60])

    def test_every_write_tolerates_an_existing_row(self):
        _result, db = run([row(1, 100, 97)])
        for text, _params in db.statements:
            if text.startswith("INSERT"):
                self.assertIn("ON CONFLICT DO NOTHING", text)


class TaskFixedCostTests(unittest.TestCase):
    """The money MS Project puts on the task rather than on anyone working on it.

    It was read from the file and stored from the day 0012 landed, and no financial
    calculation ever opened the column. These tests pin what it becomes and, as
    importantly, what it does not: it is never attributed to a resource on the task,
    because every equipment assignment in this project shares its task with a material one
    and the money moved would be the material's, counted a second time.
    """

    def lines(self, db):
        return [p for text, p in db.statements
                if "INSERT INTO estimate_lines" in text and "'progress_feed',NULL," in text]

    def test_a_task_fixed_cost_becomes_one_general_cost_line(self):
        result, db = run([row(1, 100, 97, wbs="1.5.1.2",
                              fixed_cost="2829688000.0", fixed_cost_irr="28296880000.0")])
        self.assertEqual(1, result["fixedCostLinesCreated"])
        self.assertEqual("28296880000", result["fixedCostIrr"])
        params, = self.lines(db)
        self.assertEqual("1.5.1.2", params[4], "the activity is the task's own WBS code")
        self.assertEqual(Decimal("28296880000"), params[5], "the amount is the whole line")
        self.assertEqual(100, params[6], "keyed on the task, because that is whose it is")

    def test_the_line_states_no_quantity_and_no_assignment(self):
        # A general cost has nothing to measure, and a fixed cost has no assignment to
        # measure it on. Both absences are in the statement itself rather than in a value,
        # so no caller can pass a number into either.
        _result, db = run([row(1, 100, 97, fixed_cost="500", fixed_cost_irr="5000")])
        statement, = [t for t, _p in db.statements
                      if "INSERT INTO estimate_lines" in t and "'progress_feed',NULL," in t]
        self.assertIn("VALUES (%s,%s,%s,%s,%s,NULL,NULL,%s,'progress_feed',NULL,%s,%s)",
                      statement)

    def test_the_amount_is_the_rial_column_and_never_the_files_own_number(self):
        # The file is denominated in toman, and the column that has been through that
        # decision is `source_fixed_cost_irr`. Reading the raw column instead would be
        # wrong by a factor of ten in the direction nobody notices.
        _result, db = run([row(1, 100, 97,
                               fixed_cost="2829688000.0", fixed_cost_irr="28296880000.0")])
        params, = self.lines(db)
        self.assertEqual(Decimal("28296880000"), params[5])

    def test_an_amount_with_a_fraction_of_a_rial_is_rounded_to_whole_rials(self):
        _result, db = run([row(1, 100, 97,
                               fixed_cost="5290960000.5", fixed_cost_irr="52909600004.6")])
        params, = self.lines(db)
        self.assertEqual(Decimal("52909600005"), params[5])

    def test_a_negative_fixed_cost_is_carried_as_the_file_states_it(self):
        # This project's file states -2,972,160,000 on one activity and +5,290,960,000.5
        # on the next: one correction across two related activities. Dropping the negative
        # would publish a total the schedule does not have.
        result, db = run([row(1, 100, 97, fixed_cost="-2972160000.0",
                              fixed_cost_irr="-29721600000.0")])
        params, = self.lines(db)
        self.assertEqual(Decimal("-29721600000"), params[5])
        self.assertEqual("-29721600000", result["fixedCostIrr"])

    def test_residue_below_one_unit_is_not_its_own_line_but_is_not_lost_either(self):
        # MS Project holds Task.Cost = its assignments + Fixed Cost, in doubles, so a task
        # nobody entered a fixed cost on still carries what is left of that arithmetic.
        # This project shows both kinds and they are not close: twenty-one tasks between
        # -0.25 and 0.5 of a toman, and three holding the whole of it.
        #
        # Neither extreme is right. Twenty-one lines of a fraction of a rial would be
        # noise in the estimate; dropping them makes the project total disagree with the
        # file by an amount nobody can account for. So they are summed into one line.
        result, db = run([row(1, 100, 97, fixed_cost="0.5", fixed_cost_irr="5"),
                          row(2, 101, 98, fixed_cost="-0.25", fixed_cost_irr="-2.5"),
                          row(3, 102, 99, fixed_cost="2829688000.0",
                              fixed_cost_irr="28296880000.0")])
        self.assertEqual(2, result["fixedCostLinesCreated"], "the task's own, plus one aggregate")
        self.assertEqual(2, result["fixedCostResidueRows"], "counted, never quietly dropped")
        self.assertEqual("0.25", result["fixedCostResidueFileUnits"])
        stated, aggregate = sorted(self.lines(db), key=lambda p: p[6], reverse=True)
        self.assertEqual(Decimal("28296880000"), stated[5])
        self.assertEqual(FIXED_COST_RESIDUE_TASK_UID, aggregate[6])
        self.assertEqual(Decimal("3"), aggregate[5], "5 + -2.5 = 2.5, rounded half up")
        self.assertIsNone(aggregate[4], "it belongs to no one activity, so it names none")
        self.assertEqual("28296880003", result["fixedCostIrr"],
                         "the reported total is what was written, aggregate included")

    def test_the_aggregate_is_keyed_on_a_task_the_file_can_never_use(self):
        # The residue line needs a key of its own, and the match-or-insert rule keys fixed
        # costs on the task. Task 0 is MS Project's project summary: it is not a costed
        # task and never appears in the rows. The query excludes it OUTRIGHT so that a
        # future file stating a fixed cost there could not be silently matched by -- or
        # collide with -- this aggregate.
        self.assertEqual(0, FIXED_COST_RESIDUE_TASK_UID)
        self.assertIn("source_task_uid <> 0", " ".join(_FIXED_COST_TASKS.split()))

    def test_a_residue_that_rounds_to_nothing_writes_no_line(self):
        # A general cost of zero would sit in the estimate forever stating nothing.
        result, db = run([row(1, 100, 97, fixed_cost="0.02", fixed_cost_irr="0.2"),
                          row(2, 101, 98, fixed_cost="-0.02", fixed_cost_irr="-0.2")])
        self.assertEqual(2, result["fixedCostResidueRows"])
        self.assertEqual(0, result["fixedCostLinesCreated"])
        self.assertEqual([], self.lines(db))

    def test_a_project_whose_only_fixed_cost_is_residue_still_gets_the_aggregate(self):
        # The resource the lines hang on has to be created for the aggregate alone, so the
        # early return cannot be "nothing was priced".
        result, db = run([row(1, 100, 97, fixed_cost="0.5", fixed_cost_irr="5"),
                          row(2, 101, 98, fixed_cost="0.5", fixed_cost_irr="5")])
        self.assertEqual(1, result["fixedCostLinesCreated"])
        self.assertEqual(2, result["fixedCostResidueRows"])
        params, = self.lines(db)
        self.assertEqual(Decimal("10"), params[5])
        self.assertEqual(FIXED_COST_RESIDUE_TASK_UID, params[6])

    def test_a_negative_residue_sum_stays_negative(self):
        # Same rule as a stated negative fixed cost: the file's evidence travels as it is.
        result, db = run([row(1, 100, 97, fixed_cost="-0.5", fixed_cost_irr="-5"),
                          row(2, 101, 98, fixed_cost="-0.4", fixed_cost_irr="-4")])
        params, = self.lines(db)
        self.assertEqual(Decimal("-9"), params[5])
        self.assertEqual("-9", result["fixedCostIrr"])

    def test_a_second_pass_matches_the_aggregate_instead_of_adding_another(self):
        # Idempotency covers the synthetic line exactly as it covers the file's own.
        rows = [row(1, 100, 97, fixed_cost="0.5", fixed_cost_irr="5"),
                row(2, 101, 98, fixed_cost="-0.25", fixed_cost_irr="-2.5"),
                row(3, 102, 99, fixed_cost="2829688000.0", fixed_cost_irr="28296880000.0")]
        db = Db(rows)
        first, _ = run(rows, db=db)
        self.assertEqual(2, first["fixedCostLinesCreated"])
        second, _ = run(rows, db=db)
        self.assertEqual(0, second["fixedCostLinesCreated"])
        self.assertEqual(2, second["fixedCostLinesMatched"])
        self.assertEqual(2, len(self.lines(db)), "no second write of either line")

    def test_a_task_fixed_cost_repeated_on_every_row_of_the_task_makes_one_line(self):
        # The column holds the TASK's figure on each of the task's rows, exactly as
        # `source_cost` does. Summing it across rows is how a project's cost comes out
        # several times too large.
        result, _db = run([row(1, 100, 97, fixed_cost="500", fixed_cost_irr="5000"),
                           row(2, 100, 98, fixed_cost="500", fixed_cost_irr="5000"),
                           row(3, 100, 99, fixed_cost="500", fixed_cost_irr="5000")])
        self.assertEqual(1, result["fixedCostLinesCreated"])
        self.assertEqual("5000", result["fixedCostIrr"])

    def test_a_currency_nobody_decided_produces_no_fixed_cost_line(self):
        # `source_fixed_cost_irr` is NULL when the reader refused to call the file's
        # amounts rials. A line built from the raw column would be a currency guess.
        result, db = run([row(1, 100, 97, fixed_cost="2829688000.0", fixed_cost_irr=None)])
        self.assertEqual(0, result["fixedCostLinesCreated"])
        self.assertEqual([], self.lines(db))

    def test_the_item_the_lines_hang_on_is_one_general_cost_with_no_unit(self):
        _result, db = run([row(1, 100, 97, fixed_cost="500", fixed_cost_irr="5000"),
                           row(2, 101, 98, fixed_cost="700", fixed_cost_irr="7000")])
        inserts = [p for text, p in db.statements
                   if "INSERT INTO finance_resources" in text and "'general_cost'" in text]
        self.assertEqual(1, len(inserts), "one item per project, not one per task")
        self.assertEqual(FIXED_COST_RESOURCE_CODE, inserts[0][3])
        self.assertEqual(FIXED_COST_RESOURCE_TITLE, inserts[0][4])
        statement, = [t for t, _p in db.statements
                      if "INSERT INTO finance_resources" in t and "'general_cost'" in t]
        self.assertIn("'general_cost',%s,%s,NULL,NULL,%s", statement)

    def test_reading_the_same_source_twice_creates_no_second_fixed_cost_line(self):
        rows = [row(1, 100, 97, fixed_cost="500", fixed_cost_irr="5000")]
        db = Db(rows)
        first, _ = run(rows, db=db)
        second, _ = run(rows, db=db)
        self.assertEqual(1, first["fixedCostLinesCreated"])
        self.assertEqual(0, second["fixedCostLinesCreated"])
        self.assertEqual(1, second["fixedCostLinesMatched"])

    def test_the_fixed_cost_write_tolerates_an_existing_row(self):
        _result, db = run([row(1, 100, 97, fixed_cost="500", fixed_cost_irr="5000")])
        for text, _params in db.statements:
            if text.startswith("INSERT"):
                self.assertIn("ON CONFLICT DO NOTHING", text)


if __name__ == "__main__":
    unittest.main()


class TerraceFixedCostAcceptanceTests(unittest.TestCase):
    """The whole fixed-cost reading of this project's schedule, in one pass.

    The numbers are the file's own: three activities carry a fixed cost somebody entered,
    twenty-one carry what is left of MS Project's `Task.Cost = assignments + Fixed Cost`
    reconciliation, and the three real ones do not agree in sign -- one activity was
    corrected by a negative against its neighbour's positive.

    Kept together as one case because the interesting property is the TOTAL: three stated
    amounts plus an aggregated residue that reconciles the project to the file. Any one of
    them tested alone would still pass while the sum was wrong.
    """

    #: What the file states on the three activities that carry a real fixed cost, in the
    #: file's own units and through the currency decision. 5,290,960,000.5 toman is not a
    #: whole rial and is the reason the rounding policy is stated once and shared.
    STATED = ((1227, "2829688000.0", "28296880000.0"),
              (1229, "-2972160000.0", "-29721600000.0"),
              (1231, "5290960000.5", "52909600004.6"))

    def fixture(self):
        rows = [row(uid, uid, 900 + index, wbs="1.%d" % uid,
                    fixed_cost=stated, fixed_cost_irr=rials)
                for index, (uid, stated, rials) in enumerate(self.STATED)]
        # Twenty-one tasks below one toman: twenty at +0.3 and one at -0.1, which is
        # +59 rials once. Each on its own rounds to 3 or -1 rials; none of them is an
        # amount anybody entered, and together they are the difference from the file.
        for index in range(20):
            rows.append(row(2000 + index, 2000 + index, 800 + index,
                            fixed_cost="0.3", fixed_cost_irr="3"))
        rows.append(row(2100, 2100, 899, fixed_cost="-0.1", fixed_cost_irr="-1"))
        return rows

    def lines(self, db):
        return [p for text, p in db.statements
                if "INSERT INTO estimate_lines" in text and "'progress_feed',NULL," in text]

    def test_the_first_pass_creates_four_lines_totalling_the_files_fixed_cost(self):
        result, db = run(self.fixture())
        self.assertEqual(4, result["fixedCostLinesCreated"], "three stated, one aggregate")
        self.assertEqual(0, result["fixedCostLinesMatched"])
        self.assertEqual("51484880064", result["fixedCostIrr"])
        self.assertEqual(21, result["fixedCostResidueRows"])
        self.assertEqual("5.9", result["fixedCostResidueFileUnits"])
        self.assertEqual(4, len(self.lines(db)))

    def test_the_second_pass_matches_all_four_and_writes_none(self):
        rows = self.fixture()
        db = Db(rows)
        run(rows, db=db)
        second, _ = run(rows, db=db)
        self.assertEqual(0, second["fixedCostLinesCreated"])
        self.assertEqual(4, second["fixedCostLinesMatched"])
        self.assertEqual(4, len(self.lines(db)), "still four, not eight")

    def test_the_corrected_activity_keeps_its_negative(self):
        # 1229 is the activity this project's planner corrected downwards. Clamping it to
        # zero would publish an initial estimate the schedule does not have, and would do
        # it in the direction that looks more plausible.
        _result, db = run(self.fixture())
        by_task = {params[6]: params[5] for params in self.lines(db)}
        self.assertEqual(Decimal("-29721600000"), by_task[1229])

    def test_the_half_rial_is_rounded_once_and_kept(self):
        _result, db = run(self.fixture())
        by_task = {params[6]: params[5] for params in self.lines(db)}
        self.assertEqual(Decimal("52909600005"), by_task[1231])

    def test_the_residue_arrives_as_one_line_on_task_zero(self):
        _result, db = run(self.fixture())
        by_task = {params[6]: params for params in self.lines(db)}
        aggregate = by_task[FIXED_COST_RESIDUE_TASK_UID]
        self.assertEqual(Decimal("59"), aggregate[5])
        self.assertIsNone(aggregate[4], "no activity: it is the residue of twenty-one")

    def test_the_lines_hang_on_one_general_cost_item(self):
        _result, db = run(self.fixture())
        created = [p for text, p in db.statements
                   if "INSERT INTO finance_resources" in text and "'general_cost'" in text]
        self.assertEqual(1, len(created), "one MPP-FIXEDCOST resource for the project")
        self.assertEqual(FIXED_COST_RESOURCE_CODE, created[0][3])

    def test_the_pass_never_touches_a_line_it_did_not_create(self):
        # The 715 estimate lines this project already carries are not addressable from
        # here at all: every statement is an INSERT that tolerates an existing row, or a
        # SELECT keyed on the file's own identifiers.
        _result, db = run(self.fixture())
        for text, _params in db.statements:
            self.assertFalse(text.startswith("UPDATE"), text[:60])
            self.assertFalse(text.startswith("DELETE"), text[:60])
            if text.startswith("INSERT"):
                self.assertIn("ON CONFLICT DO NOTHING", text)
