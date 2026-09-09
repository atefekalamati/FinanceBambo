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
from coreint.finance_mpp_mapping import (CLASSIFIABLE_TYPES, RESOURCE_CODE_PREFIX,
                                         FinanceMppClassificationRefused,
                                         FinanceMppMappingService, _finance_type)

ORG = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")


def row(assignment, task, resource, *, name="بتن ۴۰۰", kind="MATERIAL",
        unit="مترمکعب", wbs="1.5.1", task_name="بتن ریزی"):
    return {"source_task_uid": task, "source_assignment_uid": assignment,
            "source_resource_uid": resource, "task_name": task_name, "task_wbs": wbs,
            "resource_name": name, "resource_type": kind, "resource_unit": unit}


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
        elif "FROM finance_mpp_rows" in text:
            self._rows = list(self._db.source_rows)
        elif "FROM finance_resources" in text and text.startswith("SELECT id"):
            # Two callers, two shapes: the mapping asks for `id`, `classify` asks for
            # `id, resource_type`. Both look the resource up by its source identity.
            found = self._db.resources.get(params[2])
            self._rows = [{"id": found, "resource_type": "equipment"}] if found else []
        elif text.startswith("SELECT id FROM estimate_lines"):
            found = self._db.lines.get(params[2])
            self._rows = [{"id": found}] if found else []
        elif "INSERT INTO finance_resources" in text:
            self._db.resources[params[8]] = params[0]      # source_resource_uid -> id
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
        # lookups here cannot see them and nothing updates or deletes them.
        _result, db = run([row(1, 100, 97)])
        lookups = [(t, p) for t, p in db.statements if t.startswith("SELECT id FROM")]
        for text, _params in lookups:
            self.assertIn("source_", text)
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


if __name__ == "__main__":
    unittest.main()
