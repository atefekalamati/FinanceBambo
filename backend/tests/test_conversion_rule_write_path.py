# -*- coding: utf-8 -*-
"""What gets written when a rule is created, against a real PostgreSQL.

Both claims here are about SQL, so a test double would only prove the double agreed with
the test:

  * the acknowledgement columns are in the INSERT. `create_rule` listed twenty-one columns
    and not these three, so every stored rule read as `product_dependent_acknowledged =
    false` with nobody named against it -- while the service went on refusing a broad
    product-dependent rule that arrived without one. The gate worked and kept no record.
  * a second rule for the same crossing in the same scope, written the other way round, is
    refused. Now that a rule is read from either direction, `branch->kg` and `kg->branch`
    at one scope are two live answers to one question, and the partial unique index cannot
    see it: to the database those are different unit pairs.

These skip by name when there is no disposable database to ask.
"""

import asyncio
import os
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.repositories.unit_conversion_rules import PsycopgUnitConversionRuleRepository
from app.finance.services.unit_conversion_rules import (UnitConversionRuleRefused,
                                                        UnitConversionRuleService)

DATABASE = "bambo_material_price_test"
DSN = os.environ.get("FINANCE_MATERIAL_PRICE_DSN",
                     "postgresql://postgres@127.0.0.1:5432/" + DATABASE)
PREPARE = "python -m scripts.test_only.prepare_material_price_test_db"

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")
#: Scoped to this run, so a re-run does not meet its own rows.
PROJECT = "rule_%s" % uuid4().hex[:8]
SETTINGS = "finance.manage_settings"


def _loop():
    return asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()


def run(coroutine):
    return asyncio.run(coroutine, loop_factory=_loop)


class Scope:
    organization_id = ORG
    project_id = PROJECT
    actor_user_id = ACTOR


class Payload:
    """Only what `create_rule` reads, so a field added there fails loudly here."""

    def __init__(self, *, from_unit, to_unit, factor_value, scope_type="organization",
                 acknowledged=False, supersedes_rule_id=None, provider_item_id=None,
                 provider_id=None, category=None, reason="اندازه‌گیری انبار"):
        self.scope_type = scope_type
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.factor_value = factor_value
        self.conversion_method = "factor"
        self.formula_definition = None
        self.formula_schema_version = None
        self.direction_definition = None
        self.effective_from = date(2026, 1, 1)
        self.supersedes_rule_id = supersedes_rule_id
        self.evidence_source = "برگهٔ تأمین‌کننده"
        self.reason = reason
        self.project_id = None
        self.provider_item_id = provider_item_id
        self.provider_id = provider_id
        self.category = category
        self.product_dependent_acknowledged = acknowledged


def disposable():
    try:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(DSN, row_factory=dict_row, connect_timeout=3,
                                     autocommit=True)
    except Exception as error:                                      # noqa: BLE001
        return None, str(error).splitlines()[0][:80]
    row = connection.execute("SELECT current_database() d").fetchone()
    if row["d"] != DATABASE:
        connection.close()
        return None, "refusing %r: not the disposable database" % row["d"]
    return connection, None


async def connect():
    import psycopg
    from psycopg.rows import dict_row
    return await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row,
                                                 connect_timeout=5, autocommit=True)


class WritePathTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection, cls.reason = disposable()
        if cls.connection is None:
            raise unittest.SkipTest(
                "no disposable database for conversion rules (%s). Create it with `%s`."
                % (cls.reason, PREPARE))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "connection", None) is not None:
            cls.connection.close()

    def setUp(self):
        # Rules are ordinary rows, so this run's are removed and nothing else is.
        self.connection.execute(
            "DELETE FROM finance_unit_conversion_rules"
            " WHERE organization_id=%s AND reason LIKE %s", (ORG, "%" + PROJECT + "%"))
        self.addCleanup(self.connection.execute,
                        "DELETE FROM finance_unit_conversion_rules"
                        " WHERE organization_id=%s AND reason LIKE %s",
                        (ORG, "%" + PROJECT + "%"))

    def create(self, payload):
        payload.reason = "%s / %s" % (payload.reason, PROJECT)

        async def go():
            db = await connect()
            try:
                service = UnitConversionRuleService(
                    PsycopgUnitConversionRuleRepository(db))
                return await service.create_rule(
                    Scope(), payload=payload, actor_id=ACTOR,
                    permissions=("finance.edit", SETTINGS))
            finally:
                await db.close()
        return run(go())

    def stored(self, rule_id):
        return self.connection.execute(
            "SELECT * FROM finance_unit_conversion_rules WHERE id=%s", (rule_id,)
        ).fetchone()


class AcknowledgementIsRecordedTests(WritePathTestCase):
    def test_an_acknowledged_rule_stores_the_admission_its_author_and_the_moment(self):
        """The record the gate exists to produce, and did not.

        «۱ شاخه = ۲۲ کیلوگرم» at organization scope crosses dimensions, so the service
        refuses it without an admission. With one, the row must say who made it.
        """
        rule = self.create(Payload(from_unit="branch", to_unit="kg",
                                   factor_value=Decimal("22"), acknowledged=True))
        row = self.stored(rule["id"])
        self.assertTrue(row["product_dependent_acknowledged"])
        self.assertEqual(ACTOR, row["product_dependent_acknowledged_by"],
                         "the acknowledger is the person who wrote the rule")
        self.assertIsNotNone(row["product_dependent_acknowledged_at"])

    def test_a_rule_that_needs_no_admission_stores_none(self):
        """Mass to mass is arithmetic. A flag here would later read as somebody having
        had doubts about `ton`->`kg`, and nobody did."""
        rule = self.create(Payload(from_unit="ton", to_unit="kg",
                                   factor_value=Decimal("1000")))
        row = self.stored(rule["id"])
        self.assertFalse(row["product_dependent_acknowledged"])
        self.assertIsNone(row["product_dependent_acknowledged_by"])
        self.assertIsNone(row["product_dependent_acknowledged_at"])

    def test_the_admission_is_refused_when_it_is_not_made(self):
        """Unchanged behaviour, kept here because this is what the record is FOR."""
        with self.assertRaises(UnitConversionRuleRefused) as refusal:
            self.create(Payload(from_unit="branch", to_unit="kg",
                                factor_value=Decimal("22"), acknowledged=False))
        self.assertIn("به خودِ محصول بستگی دارد", str(refusal.exception))


class OneCrossingOneRuleTests(WritePathTestCase):
    def test_the_opposite_direction_in_the_same_scope_is_refused_by_name(self):
        """22 and 0.05 are not each other's inverse, and both would be live.

        The message has to carry the existing rule, because "already exists" with no way
        forward is where a person gets stuck.
        """
        first = self.create(Payload(from_unit="branch", to_unit="kg",
                                    factor_value=Decimal("22"), acknowledged=True))
        with self.assertRaises(UnitConversionRuleRefused) as refusal:
            self.create(Payload(from_unit="kg", to_unit="branch",
                                factor_value=Decimal("0.05"), acknowledged=True))
        message = str(refusal.exception)
        self.assertIn("جهت معکوس", message)
        self.assertIn("22", message, "the message must show the number that is in the way")
        self.assertIn("supersedes_rule_id", message, "and how to move past it")
        self.assertEqual(1, self.connection.execute(
            "SELECT count(*) n FROM finance_unit_conversion_rules"
            " WHERE organization_id=%s AND reason LIKE %s",
            (ORG, "%" + PROJECT + "%")).fetchone()["n"])
        self.assertIsNotNone(first["id"])

    def test_replacing_it_is_allowed_because_that_is_the_supported_move(self):
        first = self.create(Payload(from_unit="branch", to_unit="kg",
                                    factor_value=Decimal("22"), acknowledged=True))
        replacement = self.create(Payload(from_unit="kg", to_unit="branch",
                                          factor_value=Decimal("0.05"), acknowledged=True,
                                          supersedes_rule_id=first["id"]))
        self.assertIsNotNone(replacement["id"])
        self.assertEqual(first["id"], self.stored(replacement["id"])["supersedes_rule_id"])

    def test_a_narrower_scope_may_still_state_the_other_direction(self):
        """Only the SAME scope conflicts. A listing-level rule beside a tenant-level one
        is the ladder working, not two answers to one question."""
        self.create(Payload(from_unit="branch", to_unit="kg",
                            factor_value=Decimal("22"), acknowledged=True))
        narrow = self.create(Payload(from_unit="kg", to_unit="branch",
                                     factor_value=Decimal("0.05"),
                                     scope_type="provider_item",
                                     provider_item_id=uuid4()))
        self.assertIsNotNone(narrow["id"])


class BothDirectionsAreFetchedTests(WritePathTestCase):
    def test_a_rule_stored_one_way_is_a_candidate_for_the_other(self):
        """The repository half of the change: the resolver can only invert what it is given."""
        self.create(Payload(from_unit="branch", to_unit="kg",
                            factor_value=Decimal("22"), acknowledged=True))
        # Approved the way the table requires -- the CHECK insists an approved rule names
        # its approver and the moment, which is the point of the column.
        self.connection.execute(
            "UPDATE finance_unit_conversion_rules"
            "   SET status='approved', approved_by=%s, approved_at=now()"
            " WHERE organization_id=%s AND reason LIKE %s",
            (ACTOR, ORG, "%" + PROJECT + "%"))

        async def go():
            db = await connect()
            try:
                repository = PsycopgUnitConversionRuleRepository(db)
                direct = await repository.candidates_for(Scope(), from_unit="branch",
                                                         to_unit="kg")
                reverse = await repository.candidates_for(Scope(), from_unit="kg",
                                                          to_unit="branch")
                pairs = await repository.candidates_for_pairs(Scope(), {("kg", "branch")})
                return direct, reverse, pairs
            finally:
                await db.close()

        direct, reverse, pairs = run(go())
        mine = [r for r in direct if PROJECT in (r["reason"] or "")]
        self.assertEqual(1, len(mine))
        self.assertEqual(1, len([r for r in reverse if PROJECT in (r["reason"] or "")]),
                         "asking for the crossing backwards must find the same rule")
        grouped = [r for r in pairs.get(("kg", "branch"), [])
                   if PROJECT in (r["reason"] or "")]
        self.assertEqual(1, len(grouped),
                         "and the batch lookup groups it under the pair that was asked for")


if __name__ == "__main__":
    unittest.main()
