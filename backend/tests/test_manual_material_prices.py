# -*- coding: utf-8 -*-
"""A price somebody typed, against a real PostgreSQL.

Everything claimed here is a property of the DATABASE -- that the importer's upsert cannot
reach a manual listing, that recording a second price appends rather than replaces, that a
manual observation is allowed to have no run and no url while an imported one is not. A
test double would only prove the double agreed with the test, so these skip by name when
there is no disposable database to ask.

The database is created and owned by `scripts/test_only/prepare_material_price_test_db.py`.
Its name is checked after connecting, so no environment variable can aim these at a
database that matters.
"""

import asyncio
import os
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import app.finance.services.material_price_import as import_module
from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
from app.finance.schemas.material_prices import ManualPriceCreate, MaterialCategoryCreate
from app.finance.services.material_price_import import MaterialPriceImportService
from app.finance.services.material_price_sheet import WORKSHEET_ALLOWLIST
from app.finance.services.material_prices import (MaterialCategoryRefused,
                                                  MaterialPriceService,
                                                  TENANT_WIDE_CATEGORY_PERMISSION)

DATABASE = "bambo_material_price_test"
DSN = os.environ.get("FINANCE_MATERIAL_PRICE_DSN",
                     "postgresql://postgres@127.0.0.1:5432/" + DATABASE)
PREPARE = "python -m scripts.test_only.prepare_material_price_test_db"

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")

TEST_SHEET_LINK = ("https://docs.google.com/spreadsheets/d/"
                   "1TESTDOCUMENTIDENTIFIER0000000000000000000/edit")
HEADER = ("source", "محصول", "واحد - وزن", "قیمت", "تاریخ آپدیت ورک فلو", "productId")

#: Scoped to this run: `price_observations` refuses DELETE by trigger, so isolation is by
#: project id and nothing is ever cleaned up.
PROJECT_PREFIX = "man_%s_" % uuid4().hex[:8]

#: A category declared for the ORGANIZATION is visible to every project in it, so it cannot
#: be isolated by project id. The name carries the run instead.
WIDE_PREFIX = "wide_%s_" % uuid4().hex[:8]


def _selector_loop():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def run(coroutine):
    return asyncio.run(coroutine, loop_factory=_selector_loop)


class Scope:
    """What the repositories read off a scope, plus the permissions a service asks for."""

    def __init__(self, project_id, permission_codes=()):
        self.organization_id = ORG
        self.project_id = project_id
        self.actor_user_id = ACTOR
        self.permission_codes = tuple(permission_codes)


def open_disposable():
    """A connection to the disposable database, or None. Never to anything else."""
    try:
        connection = psycopg.connect(DSN, row_factory=dict_row, connect_timeout=3,
                                     autocommit=True)
    except psycopg.Error:
        return None
    row = connection.execute("SELECT current_database() AS d").fetchone()
    if row["d"] != DATABASE:
        connection.close()
        raise AssertionError(
            "these tests only ever run against %r; the DSN reached %r" % (DATABASE, row["d"]))
    return connection


class ManualPriceTestCase(unittest.TestCase):
    def setUp(self):
        self.sync = open_disposable()
        if self.sync is None:
            self.skipTest("no disposable database for manual material prices. "
                          "Create it with `%s`." % PREPARE)
        self.addCleanup(self.sync.close)
        self.db = run(psycopg.AsyncConnection.connect(DSN, row_factory=dict_row,
                                                      autocommit=True))
        self.addCleanup(lambda: run(self.db.close()))
        self.repo = PsycopgMaterialPriceRepository(self.db)
        self.project_id = PROJECT_PREFIX + self.id().rsplit(".", 1)[-1][:40]
        self.scope = Scope(self.project_id)
        self.service = MaterialPriceService(self.repo)
        # `finance_price_categories` is the one table here that is NOT append-only, and an
        # ORGANIZATION category is visible to every project in the organization -- which is
        # the whole point of it and is exactly why it cannot be isolated by project id the
        # way everything else in this file is. So the rows this test writes are removed
        # when it ends, and nothing else is: the append-only tables keep theirs.
        self.addCleanup(self._forget_declared_categories)

    # ------------------------------------------------------------------ small helpers

    def declare(self, category, *, scope_level="project", label=None, scope=None,
                permissions=None):
        target = self.scope if scope is None else scope
        return run(self.service.declare_category(
            target,
            MaterialCategoryCreate(category=category, label=label,
                                   scope_level=scope_level),
            ACTOR,
            permissions=(target.permission_codes if permissions is None else permissions)))

    def enter(self, *, product_name="داربست فلزی ۴ متری", category="داربست",
              source_unit="kg", price_irr="1250000", observed_at=date(2026, 9, 14),
              reason="استعلام تلفنی از تأمین‌کننده"):
        return run(self.service.record_manual_price(
            self.scope,
            ManualPriceCreate(product_name=product_name, category=category,
                              source_unit=source_unit, price_irr=Decimal(price_irr),
                              observed_at=observed_at, reason=reason),
            ACTOR))

    def categories(self):
        return {row["category"]: row for row in run(self.service.categories(self.scope))}

    def count(self, sql, *args):
        return self.sync.execute(sql, args).fetchone()["n"]

    def _forget_declared_categories(self):
        self.sync.execute(
            """DELETE FROM finance_price_categories
                WHERE project_id=%s OR (organization_id=%s AND category LIKE %s)""",
            (self.project_id, ORG, WIDE_PREFIX + "%"))


class ManualEntryTests(ManualPriceTestCase):
    def test_a_hand_entered_price_appears_among_the_current_prices_marked_manual(self):
        """The whole point: it reaches the same table the imported prices are read from.

        Not a separate list and not a separate endpoint -- a reader comparing what things
        cost should not have to consult two places and merge them.
        """
        self.declare("داربست")
        answer = self.enter()
        self.assertFalse(answer["already_recorded"])

        rows, total = run(self.service.current(self.scope))
        self.assertEqual(1, total)
        row = rows[0]
        self.assertEqual("داربست فلزی ۴ متری", row["external_name"])
        self.assertEqual(Decimal("1250000"), row["current_price_irr"])
        self.assertEqual("manual", row["origin"],
                         "the reader must be able to see it was typed")
        self.assertEqual(ACTOR, row["entered_by"])
        self.assertEqual(date(2026, 9, 14), row["workflow_date_gregorian"],
                         "the day the price was obtained, not the moment it was typed")

        # And the database agrees about what a manual observation may not claim.
        stored = self.sync.execute(
            """SELECT origin, collection_run_id, source_url, reason
                 FROM price_observations WHERE project_id=%s""",
            (self.project_id,)).fetchone()
        self.assertEqual("manual", stored["origin"])
        self.assertIsNone(stored["collection_run_id"], "no run read this")
        self.assertIsNone(stored["source_url"], "and it came from no address")
        self.assertEqual("استعلام تلفنی از تأمین‌کننده", stored["reason"])

    def test_a_declared_category_appears_in_the_list_before_anything_is_priced_in_it(self):
        """The state between naming a category and recording the first price in it.

        `GROUP BY category` cannot see this -- there is nothing to group -- which is the
        entire reason the category table exists beside the column.
        """
        self.assertNotIn("داربست", self.categories())
        self.declare("داربست", label="داربست و قالب‌بندی")

        listed = self.categories()
        self.assertIn("داربست", listed)
        self.assertTrue(listed["داربست"]["declared"])
        self.assertEqual("project", listed["داربست"]["scope_level"])
        self.assertEqual(0, listed["داربست"]["item_count"],
                         "nothing has been recorded in it yet, and it says so")

        # And once a price lands in it, the counts move and the declaration stays.
        self.enter()
        listed = self.categories()
        self.assertTrue(listed["داربست"]["declared"])
        self.assertEqual(1, listed["داربست"]["item_count"])

    def test_declaring_a_category_that_already_exists_is_refused(self):
        """Two chips with the same name would be two chips for one thing."""
        self.declare("داربست")
        with self.assertRaises(MaterialCategoryRefused) as refusal:
            self.declare("داربست")
        self.assertEqual(409, refusal.exception.status)
        self.assertEqual("FINANCE_MATERIAL_CATEGORY_REFUSED", refusal.exception.code)
        self.assertEqual(
            1, self.count("SELECT count(*) AS n FROM finance_price_categories"
                          " WHERE project_id=%s", self.project_id))

    def test_a_price_in_a_category_nobody_declared_is_refused(self):
        """A category invented at the moment a price is saved is a typo with a chip."""
        with self.assertRaises(MaterialCategoryRefused) as refusal:
            self.enter(category="دارربست")
        self.assertEqual(409, refusal.exception.status)
        self.assertEqual(
            0, self.count("SELECT count(*) AS n FROM price_observations WHERE project_id=%s",
                          self.project_id),
            "a refused entry writes nothing at all")

    def test_a_unit_the_registry_cannot_name_is_refused(self):
        """A price per something nobody can name cannot be converted.

        It would enter an estimate as a number with no denominator, which is the one thing
        the conversion work exists to prevent.
        """
        self.declare("داربست")
        with self.assertRaises(MaterialCategoryRefused):
            self.enter(source_unit="حلقه")
        self.assertEqual(
            0, self.count("SELECT count(*) AS n FROM price_observations WHERE project_id=%s",
                          self.project_id))

    def test_entering_a_new_price_for_the_same_product_appends_to_its_history(self):
        """Correcting a price means STATING the new one. The old one stays readable.

        `price_observations` refuses UPDATE by trigger, and should: a price that can be
        rewritten is not a record of what anything cost.
        """
        self.declare("داربست")
        first = self.enter(price_irr="1250000", observed_at=date(2026, 9, 14))
        second = self.enter(price_irr="1310000", observed_at=date(2026, 9, 16))
        self.assertEqual(first["provider_item_id"], second["provider_item_id"],
                         "the same product, not a second listing with the same name")

        history, total = run(self.service.history(
            self.scope, first["provider_item_id"], page=1, page_size=50))
        self.assertEqual(2, total)
        self.assertEqual([Decimal("1310000"), Decimal("1250000")],
                         [row["normalized_price_irr"] for row in history],
                         "newest first, and the earlier one still there")

        rows, _total = run(self.service.current(self.scope))
        self.assertEqual(Decimal("1310000"), rows[0]["current_price_irr"],
                         "the current price is the newest one stated")

    def test_recording_the_identical_price_twice_is_recognised_rather_than_stored_twice(self):
        """Somebody pressing save twice has not obtained a second quote."""
        self.declare("داربست")
        self.enter()
        again = self.enter()
        self.assertTrue(again["already_recorded"])
        self.assertEqual(
            1, self.count("SELECT count(*) AS n FROM price_observations WHERE project_id=%s",
                          self.project_id))


class ImportLeavesManualRowsAloneTests(ManualPriceTestCase):
    def _workbook(self, product_name, product_id):
        """A COMPLETE workbook: the importer refuses a partial one, and should.

        An empty worksheet is indistinguishable from a worksheet that failed to download,
        so a book with six of the seven filled is one the importer will not write at all --
        which would make this test pass for the wrong reason.
        """
        book = {}
        for index, title in enumerate(WORKSHEET_ALLOWLIST):
            book[title] = [HEADER, ("Mashhad Foolad", "میلگرد آجدار 8 A3", "کیلو", 95500.0,
                                    "1405-06-22", "OTHER-%d" % index)]
        book["steel -Rebar"] = [HEADER, ("Mashhad Foolad", product_name, "کیلو", 95500.0,
                                         "1405-06-22", product_id)]
        return book

    def _import(self, book):
        async def fetch(_link):
            return b"PK"

        original = import_module.workbook_from_xlsx
        import_module.workbook_from_xlsx = lambda _content: book
        self.addCleanup(setattr, import_module, "workbook_from_xlsx", original)
        return run(MaterialPriceImportService(
            self.repo, sheet_link=TEST_SHEET_LINK, fetch=fetch).run(self.scope))

    def test_an_import_cannot_overwrite_or_deactivate_a_hand_entered_listing(self):
        """The guarantee that makes manual entry safe to use at all.

        The importer's upsert is scoped to `origin = 'sheet'`, so a sheet that happens to
        name the same product cannot rewrite its unit, its category or its active flag --
        and the sweep that deactivates listings the sheet stopped carrying cannot reach it
        either, which is what would otherwise happen to EVERY manual row on EVERY import.
        """
        self.declare("داربست")
        entered = self.enter(source_unit="kg", price_irr="1250000")
        before = self.sync.execute(
            "SELECT * FROM provider_items WHERE id=%s", (entered["provider_item_id"],)
        ).fetchone()
        self.assertEqual("manual", before["origin"])

        outcome = self._import(self._workbook("میلگرد آجدار 8 A3", "REBAR-1"))
        self.assertEqual("succeeded", outcome.status)

        after = self.sync.execute(
            "SELECT * FROM provider_items WHERE id=%s", (entered["provider_item_id"],)
        ).fetchone()
        self.assertEqual(before, after,
                         "the import changed nothing about the manual listing")
        self.assertTrue(after["active"],
                        "and the absent-from-the-sheet sweep did not deactivate it")

        rows = {row["external_name"]: row
                for row in run(self.service.current(self.scope))[0]}
        self.assertEqual(Decimal("1250000"), rows["داربست فلزی ۴ متری"]["current_price_irr"])
        self.assertEqual("manual", rows["داربست فلزی ۴ متری"]["origin"])
        self.assertEqual("sheet", rows["میلگرد آجدار 8 A3"]["origin"],
                         "and the imported row beside it is still an imported one")


class WideScopeTests(ManualPriceTestCase):
    def test_a_category_above_this_project_needs_the_settings_permission(self):
        """A word that lands in every project's list is a decision about the tenant.

        Checked in the SERVICE against the scope's permissions rather than at the route,
        because `finance.manage_settings` is not one of the permissions a route may be
        gated on -- the same place, and the same permission, the conversion rules use for
        their own tenant-wide scopes.
        """
        editor = Scope(self.project_id, permission_codes=("finance.view", "finance.edit"))
        with self.assertRaises(MaterialCategoryRefused) as refusal:
            self.declare(WIDE_PREFIX + "داربست", scope_level="organization", scope=editor)
        self.assertIn(TENANT_WIDE_CATEGORY_PERMISSION, str(refusal.exception))
        self.assertEqual(
            0, self.count("SELECT count(*) AS n FROM finance_price_categories"
                          " WHERE organization_id=%s AND category=%s"
                          "   AND scope_level='organization'",
                          ORG, WIDE_PREFIX + "داربست"),
            "nothing was written at the level the caller was not allowed to write at")

        settings_holder = Scope(
            self.project_id,
            permission_codes=("finance.view", "finance.edit",
                              TENANT_WIDE_CATEGORY_PERMISSION))
        row = self.declare(WIDE_PREFIX + "داربست", scope_level="organization",
                           scope=settings_holder)
        self.assertEqual("organization", row["scope_level"])
        self.assertIsNone(row["project_id"],
                          "an organization category belongs to no project")

    def test_a_project_category_needs_nothing_beyond_editing_this_project(self):
        editor = Scope(self.project_id, permission_codes=("finance.view", "finance.edit"))
        row = self.declare("قالب‌بندی", scope_level="project", scope=editor)
        self.assertEqual("project", row["scope_level"])
        self.assertEqual(self.project_id, row["project_id"])


if __name__ == "__main__":
    unittest.main()
