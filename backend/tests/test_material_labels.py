# -*- coding: utf-8 -*-
"""What a person writes about a listing, against a real PostgreSQL.

The claims worth a database are the ones about time: that a correction supersedes rather
than replaces, that the superseded version stays readable, and that labelling a row does
not touch the imported observation it describes. A test double would only prove the double
agreed.

Skips, loudly and by name, when there is no disposable database to ask.
"""

import asyncio
import os
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository

DATABASE = "bambo_material_price_test"
DSN = os.environ.get("FINANCE_MATERIAL_PRICE_DSN",
                     "postgresql://postgres@127.0.0.1:5432/" + DATABASE)
PREPARE = "python -m scripts.test_only.prepare_material_price_test_db"

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
OTHER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1")
PROJECT_PREFIX = "lbl_%s_" % uuid4().hex[:8]


def _selector_loop():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def run(coroutine):
    return asyncio.run(coroutine, loop_factory=_selector_loop)


class Scope:
    def __init__(self, project_id):
        self.organization_id = ORG
        self.project_id = project_id
        self.actor_user_id = ACTOR


def open_disposable():
    try:
        connection = psycopg.connect(DSN, row_factory=dict_row, connect_timeout=3,
                                     autocommit=True)
    except psycopg.Error:
        return None
    name = connection.execute("SELECT current_database() AS d").fetchone()["d"]
    if name != DATABASE:
        connection.close()
        raise AssertionError("these tests only run against %r; reached %r" % (DATABASE, name))
    return connection


class LabelTests(unittest.TestCase):
    def setUp(self):
        self.sync = open_disposable()
        if self.sync is None:
            self.skipTest("no disposable database for material labels. Create it with `%s`."
                          % PREPARE)
        self.addCleanup(self.sync.close)
        self.db = run(psycopg.AsyncConnection.connect(DSN, row_factory=dict_row,
                                                      autocommit=True))
        self.addCleanup(lambda: run(self.db.close()))
        self.repo = PsycopgMaterialPriceRepository(self.db)
        # A project of this test's own: price_observations refuses DELETE by trigger, so
        # isolation is by scope and nothing is ever cleaned up.
        self.project_id = PROJECT_PREFIX + self.id().rsplit(".", 1)[-1][:40]
        self.scope = Scope(self.project_id)
        self.item = self._listing()

    def _listing(self, external_id="PIPE-LABEL-1", source_unit=None):
        """A provider and one listing, so a label has something real to attach to."""
        provider = run(self.repo.ensure_provider(
            self.scope, name="Sivanland", domain="docs/%s" % self.project_id))
        return run(self.repo.ensure_item(
            self.scope, provider_id=provider["id"], external_id=external_id,
            external_name="لوله پلی اتیلن ۱۱۰", category="pipe", url="https://example/x",
            source_unit=source_unit, worksheet="Pipe-table", active=True,
            inactive_reason=None, metadata={}))

    def label(self, **values):
        values.setdefault("reason", "مبنای قیمت از روی فاکتور تأمین‌کننده مشخص شد")
        return run(self.repo.append_label(self.scope, provider_item_id=self.item["id"],
                                          values=values, created_by=ACTOR))

    # ------------------------------------------------------------------ versioning

    def test_a_first_label_is_version_one_and_is_current(self):
        created = self.label(label="لوله", source_unit="m", target_unit="m")
        self.assertEqual(1, created["version"])
        self.assertIsNone(created["superseded_at"])
        current = run(self.repo.labels(self.scope, provider_item_id=self.item["id"]))
        self.assertEqual(1, len(current))
        self.assertEqual("m", current[0]["source_unit"])

    def test_a_correction_supersedes_and_the_earlier_version_stays_readable(self):
        first = self.label(label="لوله", source_unit="m", target_unit="m")
        second = self.label(label="لوله", source_unit="branch", target_unit="m",
                            reason="تأمین‌کننده اعلام کرد قیمت بابت شاخه است")
        self.assertEqual(2, second["version"])

        history = run(self.repo.label_history(self.scope, self.item["id"]))
        self.assertEqual([1, 2], [row["version"] for row in history])
        was = [row for row in history if row["id"] == first["id"]][0]
        self.assertIsNotNone(was["superseded_at"], "the old version is closed, not deleted")
        self.assertEqual(second["id"], was["superseded_by"])
        self.assertEqual("m", was["source_unit"], "and it still says what it used to say")

        current = run(self.repo.labels(self.scope, provider_item_id=self.item["id"]))
        self.assertEqual(1, len(current), "only one label is current")
        self.assertEqual("branch", current[0]["source_unit"])

    def test_every_version_records_who_and_why(self):
        created = self.label(label="لوله", reason="چون فاکتور فروشنده متری است")
        self.assertEqual(ACTOR, created["created_by"])
        self.assertIn("فاکتور", created["reason"])
        self.assertIsNotNone(created["created_at"])

    # -------------------------------------------------------------------- mapping

    def test_a_mapping_is_unapproved_until_somebody_approves_it(self):
        created = self.label(label="لوله", finance_resource_id=None)
        self.assertFalse(created["mapping_approved"])
        self.assertIsNone(created["mapping_approved_by"])

    def test_an_approval_without_an_approver_is_refused_by_the_database(self):
        """The constraint, not the service, is what makes this impossible."""
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.sync.execute(
                """INSERT INTO provider_item_labels
                       (id, organization_id, project_id, provider_item_id, version,
                        mapping_approved, reason, created_by)
                   VALUES (%s, %s, %s, %s, 99, true, 'x', %s)""",
                (uuid4(), ORG, self.project_id, self.item["id"], ACTOR))

    def test_an_approved_mapping_must_name_something_to_map_to(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.sync.execute(
                """INSERT INTO provider_item_labels
                       (id, organization_id, project_id, provider_item_id, version,
                        mapping_approved, mapping_approved_by, mapping_approved_at,
                        finance_resource_id, reason, created_by)
                   VALUES (%s, %s, %s, %s, 98, true, %s, now(), NULL, 'x', %s)""",
                (uuid4(), ORG, self.project_id, self.item["id"], ACTOR, ACTOR))

    # ------------------------------------------------------- the raw row is untouched

    def test_labelling_changes_nothing_about_the_imported_listing(self):
        before = self.sync.execute(
            "SELECT external_name, category, source_unit, metadata FROM provider_items"
            " WHERE id=%s", (self.item["id"],)).fetchone()
        self.label(label="چیز دیگری", display_name="نام تازه", category="pipe_fitting",
                   source_unit="branch", target_unit="m")
        after = self.sync.execute(
            "SELECT external_name, category, source_unit, metadata FROM provider_items"
            " WHERE id=%s", (self.item["id"],)).fetchone()
        self.assertEqual(dict(before), dict(after),
                         "a label describes the listing; it does not edit it")

    def test_labelling_writes_no_price_and_no_observation(self):
        self.label(label="لوله", source_unit="m", target_unit="m")
        for table in ("price_observations", "price_versions", "estimate_lines", "invoices"):
            with self.subTest(table=table):
                count = self.sync.execute(
                    "SELECT count(*) AS n FROM " + table
                    + (" WHERE project_id=%s" if table != "price_versions" else
                       " WHERE project_id=%s"), (self.project_id,)).fetchone()["n"]
                self.assertEqual(0, count, "a label is configuration, never a price")

    # ------------------------------------------------------------------- factors

    def test_a_factor_is_appended_and_supersedes_only_its_own_pair(self):
        weight = run(self.repo.append_item_factor(
            self.scope, provider_item_id=self.item["id"], from_unit="each", to_unit="kg",
            factor=Decimal("2.8"), factor_type="weight_per_piece", origin="manual",
            reason="وزن یک عدد آجر روی ترازو", created_by=ACTOR, approved_by=ACTOR))
        area = run(self.repo.append_item_factor(
            self.scope, provider_item_id=self.item["id"], from_unit="each", to_unit="m2",
            factor=Decimal("0.01"), factor_type="area_per_piece", origin="manual",
            reason="مساحت رویهٔ یک آجر", created_by=ACTOR, approved_by=ACTOR))
        self.assertEqual(1, weight["version"])
        self.assertEqual(1, area["version"], "a different pair starts its own version line")

        corrected = run(self.repo.append_item_factor(
            self.scope, provider_item_id=self.item["id"], from_unit="each", to_unit="kg",
            factor=Decimal("2.9"), factor_type="weight_per_piece", origin="manual",
            reason="ترازوی دقیق‌تر", created_by=ACTOR, approved_by=ACTOR))
        self.assertEqual(2, corrected["version"])

        rows = self.sync.execute(
            "SELECT from_unit, to_unit, version, factor, superseded_at"
            " FROM provider_item_unit_factors WHERE project_id=%s ORDER BY to_unit, version",
            (self.project_id,)).fetchall()
        by_pair = {(r["to_unit"], r["version"]): r for r in rows}
        self.assertIsNotNone(by_pair[("kg", 1)]["superseded_at"], "the old weight is closed")
        self.assertIsNone(by_pair[("kg", 2)]["superseded_at"])
        self.assertIsNone(by_pair[("m2", 1)]["superseded_at"],
                          "a new weight must not retire the area")

    def test_the_current_factor_is_the_newest_for_its_pair(self):
        for value in ("2.8", "2.9", "3.0"):
            run(self.repo.append_item_factor(
                self.scope, provider_item_id=self.item["id"], from_unit="each", to_unit="kg",
                factor=Decimal(value), factor_type="weight_per_piece", origin="manual",
                reason="اندازه‌گیری", created_by=ACTOR, approved_by=ACTOR))
        current = run(self.repo.item_unit_factors(self.scope, self.item["id"]))
        self.assertEqual(1, len(current))
        self.assertEqual(Decimal("3.00000000"), current[0]["factor"])

    # ------------------------------------------------------------- the work queue

    def test_a_listing_with_no_unit_and_no_label_is_in_the_unresolved_queue(self):
        items, total = run(self.repo.unresolved_items(self.scope))
        self.assertEqual(1, total)
        self.assertEqual(self.item["id"], items[0]["id"])

    def test_labelling_takes_it_out_of_the_queue(self):
        self.label(label="لوله", source_unit="m", target_unit="m")
        _items, total = run(self.repo.unresolved_items(self.scope))
        self.assertEqual(0, total, "somebody has said what this is; it is not waiting")

    def test_a_listing_whose_sheet_stated_a_unit_is_not_in_the_queue(self):
        self._listing(external_id="REBAR-STATED", source_unit="کیلو")
        items, _total = run(self.repo.unresolved_items(self.scope))
        self.assertNotIn("REBAR-STATED", [row["external_id"] for row in items])


if __name__ == "__main__":
    unittest.main()
