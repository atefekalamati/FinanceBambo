# -*- coding: utf-8 -*-
"""A stored id is not a name, and the one that reaches the page must not become one.

The module keeps actors as bare UUIDs on purpose. These tests pin the two halves of reading
them back: that the traversal finds every actor and touches nothing it should not, and that
the Core adapter answers with names, with nothing, or with nothing-and-no-exception.
"""

import asyncio
import unittest
from uuid import UUID, uuid4

from app.finance.adapters.ports import supports_actor_names
from app.finance.domain.actors import (ACTOR_FIELDS, apply_actor_names,
                                       collect_actor_ids)
from coreint.identity import CoreActorDirectory

ADMIN = "53a1ac1b-d87f-4125-9ba9-a7d64166af88"
OTHER = "7d324c1f-163a-4a23-88a9-476a933e3355"
NAMES = {ADMIN: "مدیر سیستم", OTHER: "محمود رضایی"}


class Model:
    """Stands in for a response model: attributes, and no dict behaviour."""

    def __init__(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)


#: Pairs the rule below finds that are NOT actors. Each is an id and a name that belong to
#: the same THING rather than to a person, so no directory lookup can fill them and they are
#: filled by their own query instead. Listed explicitly: the point of the rule is that a new
#: pair has to be classified by somebody, not that it has to be an actor.
NOT_ACTOR_PAIRS = {
    ("external_id", "external_name"),      # a supplier's own code for a product
    ("provider_id", "provider_name"),      # the supplier
    ("resource_id", "resource_name"),      # a Finance resource
}


def _declared_id_name_pairs():
    """Every `X` + `X_name` pair any response model declares, found by reading the schemas.

    The old version of this test pinned a hand-written list, which meant it could only fail
    when somebody EDITED the list -- and the failure it was written to catch is somebody
    adding a name field and not editing it. `labelledByName` was declared on the material
    price response and filled by nothing, shipped to the frontend, read there, and rendered
    empty on every row; this test passed throughout. So it now derives the pairs from the
    schemas and the pin is the classification, not the list.
    """
    import ast
    from pathlib import Path
    pairs = set()
    for path in sorted(Path("app/finance/schemas").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            fields = {n.target.id for n in node.body if isinstance(n, ast.AnnAssign)}
            for field in fields:
                if not field.endswith("_name"):
                    continue
                stem = field[: -len("_name")]
                for candidate in (stem, stem + "_id"):
                    if candidate in fields:
                        pairs.add((candidate, field))
    return pairs


class CollectTests(unittest.TestCase):
    def test_every_actor_column_the_api_exposes_is_covered(self):
        # The pairs are the contract. A name field added to a schema and classified neither
        # way is a field that silently never resolves -- which is exactly what happened.
        declared = _declared_id_name_pairs()
        unclassified = declared - set(ACTOR_FIELDS) - NOT_ACTOR_PAIRS
        self.assertEqual(set(), unclassified,
                         "a schema declares these id/name pairs and nothing says whether "
                         "they are actors; an actor pair must be added to ACTOR_FIELDS or "
                         "its name will always be null")
        # And nothing is claimed as an actor that no schema actually declares.
        self.assertEqual(set(), set(ACTOR_FIELDS) - declared,
                         "ACTOR_FIELDS names a pair no response model declares")

    def test_ids_are_found_in_rows_models_and_nested_containers(self):
        payload = {"items": [{"actor_user_id": ADMIN},
                             Model(submitted_by=UUID(OTHER), confirmed_by=None,
                                   lines=[Model(created_by=UUID(ADMIN))])],
                   "page": 1}
        self.assertEqual({ADMIN, OTHER}, collect_actor_ids(payload))

    def test_the_same_person_twice_is_asked_for_once(self):
        rows = [{"created_by": ADMIN} for _ in range(50)]
        self.assertEqual({ADMIN}, collect_actor_ids(rows),
                         "fifty rows by one person is one lookup, not fifty")

    def test_a_host_header_in_camel_case_is_found_too(self):
        # A progress feed's header is the HOST's JSON, not a psycopg row, so its keys are
        # camelCase -- and that header is exactly where the progress page reads its importer.
        # Matching only snake_case skipped it and the page kept printing the id.
        feed = {"snapshot": {"importedBy": ADMIN, "status": "ready"}, "assignments": []}
        self.assertEqual({ADMIN}, collect_actor_ids(feed))
        apply_actor_names(feed, NAMES)
        self.assertEqual("مدیر سیستم", feed["snapshot"]["importedByName"])
        self.assertEqual(ADMIN, feed["snapshot"]["importedBy"], "the id is never replaced")

    def test_a_nested_single_object_is_walked_not_only_a_list(self):
        feed = {"snapshot": {"importedBy": ADMIN}}
        self.assertEqual({ADMIN}, collect_actor_ids(feed))

    def test_recorded_audit_values_are_not_searched(self):
        # before_values/after_values are evidence written by whatever recorded the event.
        # An id in there names a subject, not the actor, and must not reach the lookup.
        event = {"actor_user_id": ADMIN,
                 "before_values": {"created_by": OTHER},
                 "after_values": {"items": [{"created_by": OTHER}]}}
        self.assertEqual({ADMIN}, collect_actor_ids(event))


class ApplyTests(unittest.TestCase):
    def test_a_row_gets_the_name_beside_the_id_it_keeps(self):
        row = {"imported_by": ADMIN, "status": "ready"}
        apply_actor_names(row, NAMES)
        self.assertEqual(ADMIN, row["imported_by"], "the id is never replaced")
        self.assertEqual("مدیر سیستم", row["imported_by_name"])

    def test_an_unknown_id_leaves_the_name_empty_rather_than_guessing(self):
        row = {"created_by": str(uuid4())}
        apply_actor_names(row, NAMES)
        self.assertIsNone(row["created_by_name"],
                          "an unnamed actor is None, never a placeholder string")

    def test_a_null_actor_gets_no_name_field_at_all(self):
        row = {"imported_by": None}
        apply_actor_names(row, NAMES)
        self.assertNotIn("imported_by_name", row,
                         "nobody imported it, so there is nobody to name")

    def test_a_model_that_declares_no_name_field_is_left_alone(self):
        # The response models forbid extras. Setting one that was never declared would turn
        # a decoration into a 500 on a page somebody needs.
        value = Model(created_by=UUID(ADMIN))
        apply_actor_names(value, NAMES)
        self.assertFalse(hasattr(value, "created_by_name"))

    def test_recorded_audit_values_are_not_rewritten(self):
        event = {"actor_user_id": ADMIN, "before_values": {"created_by": OTHER}}
        apply_actor_names(event, NAMES)
        self.assertEqual({"created_by": OTHER}, event["before_values"],
                         "decorating an audit event must not edit what it recorded")


class Cursor:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params):
        self.db.statements.append((sql, params))
        if self.db.raises:
            raise RuntimeError("the host is not answering")
        if "to_regclass" in sql:
            self.rows = [{"present": self.db.present}]
        else:
            wanted = set(params["ids"])
            self.rows = [{"id": UUID(key), "display_name": name}
                         for key, name in NAMES.items() if key in wanted]

    async def fetchall(self):
        return self.rows


class Db:
    def __init__(self, present=True, raises=False):
        self.present, self.raises, self.statements = present, raises, []

    def cursor(self, **_):
        return Cursor(self)


def names(db, ids):
    return asyncio.new_event_loop().run_until_complete(CoreActorDirectory(db).names(ids))


class CoreActorDirectoryTests(unittest.TestCase):
    def test_it_satisfies_the_port(self):
        self.assertTrue(supports_actor_names(CoreActorDirectory(Db())))

    def test_known_ids_come_back_named(self):
        self.assertEqual({ADMIN: "مدیر سیستم"}, names(Db(), [ADMIN]))

    def test_an_id_core_does_not_know_is_absent_rather_than_blank(self):
        stranger = str(uuid4())
        self.assertEqual({}, names(Db(), [stranger]),
                         "absent means 'no name'; a blank string would mean 'named nothing'")

    def test_a_database_without_users_answers_nothing_and_asks_once(self):
        db = Db(present=False)
        directory = CoreActorDirectory(db)
        loop = asyncio.new_event_loop()
        self.assertEqual({}, loop.run_until_complete(directory.names([ADMIN])))
        self.assertEqual({}, loop.run_until_complete(directory.names([OTHER])))
        self.assertEqual(1, len(db.statements),
                         "the probe is remembered; one missing table is not one failed "
                         "query per page load")

    def test_a_host_that_will_not_answer_costs_names_and_nothing_else(self):
        self.assertEqual({}, names(Db(raises=True), [ADMIN]))

    def test_a_value_that_is_not_an_id_cannot_spoil_the_page(self):
        # One malformed value in a fifty-row page would otherwise cost every row its name.
        db = Db()
        self.assertEqual({ADMIN: "مدیر سیستم"}, names(db, [ADMIN, "not-a-uuid", None]))

    def test_nothing_to_resolve_touches_the_database_at_all(self):
        db = Db()
        self.assertEqual({}, names(db, []))
        self.assertEqual([], db.statements)


if __name__ == "__main__":
    unittest.main()
