# -*- coding: utf-8 -*-
"""The import, against a real PostgreSQL.

Most of what this claims is a property of the DATABASE -- a second import inserting
nothing, two imports refusing to overlap, a failed import leaving yesterday's prices where
they were -- so a test double would only prove the double agreed with the test. Those cases
skip, loudly and by name, when there is no disposable database to ask.

The database is created and owned by `scripts/test_only/prepare_material_price_test_db.py`.
Its name is checked after connecting, so no environment variable can aim these at a
database that matters.
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import app.finance.services.material_price_import as import_module
from app.finance.repositories.material_prices import (PsycopgMaterialPriceRepository,
                                                      RunAlreadyRunning, row_fingerprint)
from app.finance.services.material_price_import import (MaterialPriceImportError,
                                                        MaterialPriceImportService)
from app.finance.services.material_price_sheet import WORKSHEET_ALLOWLIST

DATABASE = "bambo_material_price_test"
DSN = os.environ.get("FINANCE_MATERIAL_PRICE_DSN",
                     "postgresql://postgres@127.0.0.1:5432/" + DATABASE)
PREPARE = "python -m scripts.test_only.prepare_material_price_test_db"

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")

#: A link the real parser accepts: its document id is the 20+ characters
#: `parse_sheet_link` requires, so these tests exercise the production parser
#: rather than a relaxed one.
TEST_SHEET_LINK = ("https://docs.google.com/spreadsheets/d/1TESTDOCUMENTIDENTIFIER0000000000000000000/edit")

HEADER = ("source", "محصول", "واحد - وزن", "قیمت", "تاریخ آپدیت ورک فلو", "productId")
REBAR_ROW = ("Mashhad Foolad", "میلگرد آجدار 8 A3", "کیلو", 95500.0, "1405-06-22", "REBAR-1")

#: `price_observations` carries an immutability trigger that refuses UPDATE and DELETE --
#: which is correct, and is the reason these tests never clean up. Each test gets a project
#: id of its own instead, so isolation costs nothing and nothing is ever deleted. The
#: project id is scoped to this file and to this run; no other project can collide with it.
#: ...and a suffix unique to this RUN, because the project id alone is stable across runs
#: and the second run would find the first run's rows already present. The disposable
#: database simply accumulates; `prepare_material_price_test_db` recreates it.
PROJECT_PREFIX = "mpt_%s_" % uuid4().hex[:8]


def _selector_loop():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop.

    The same choice `tests/test_invoice_numbering.py` makes, and made per call rather than
    by setting the policy: a global change would reach every other test in the run.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def run(coroutine):
    return asyncio.run(coroutine, loop_factory=_selector_loop)


class Scope:
    """What the repositories read off a scope. Three attributes, and no more."""

    def __init__(self, project_id):
        self.organization_id = ORG
        self.project_id = project_id
        self.actor_user_id = ACTOR


def open_disposable():
    """A connection to the disposable database, or None. Never to anything else."""
    try:
        connection = psycopg.connect(DSN, row_factory=dict_row, connect_timeout=3,
                                     autocommit=True)
    except psycopg.Error:
        return None
    row = connection.execute(
        "SELECT current_database() AS d, inet_server_addr() AS h").fetchone()
    if row["d"] != DATABASE:
        connection.close()
        raise AssertionError(
            "these tests only ever run against %r; the DSN reached %r" % (DATABASE, row["d"]))
    return connection


def sheet(rows):
    return [HEADER, *rows]


#: One productId prefix per worksheet, as the real sheet has. The first version of this
#: fixture put the SAME row in all seven worksheets and then expected seven observations --
#: but one product at one price on one date IS one observation however many worksheets
#: repeat it, and the importer said so. The fixture was wrong, not the rule.
WORKSHEET_PREFIX = {
    "steel - I-beam": "IBEAM",
    "Angle iron-table": "ANGLE",
    "Channel_table": "CHANNEL",
    "Hollow structural section_table": "PROFILE",
    "Pipe-table": "PIPE",
    "steel -Rebar": "REBAR",
    "brick": "BRICK",
}


#: Every row a test builds by hand carries the pricing unit, because the importer requires
#: one. `واحد - وزن` is the Rebar spelling and HEADER above uses it; six of the seven real
#: worksheets spell the same column `واحد`, which `test_material_price_sheet` covers.
def full_workbook(rebar_rows=None):
    """Every allowlisted worksheet present, so a complete workbook is the default."""
    book = {}
    for title in WORKSHEET_ALLOWLIST:
        prefix = WORKSHEET_PREFIX[title]
        name = "لوله پلی اتیلن" if prefix == "PIPE" else "میلگرد آجدار 8 A3"
        book[title] = sheet([("Mashhad Foolad", name, "کیلو", 95500.0, "1405-06-22",
                              "%s-1" % prefix)])
    if rebar_rows is not None:
        book["steel -Rebar"] = sheet(rebar_rows)
    return book


class FingerprintTests(unittest.TestCase):
    """No database needed: this is a hash of three strings, and what it must separate."""

    def test_the_same_row_fingerprints_the_same(self):
        self.assertEqual(row_fingerprint("REBAR-1", "1405-06-22", "95500"),
                         row_fingerprint("REBAR-1", "1405-06-22", "95500"))

    def test_one_product_on_two_dates_stays_two_observations(self):
        """The real duplicate productIds differ only in the workflow date."""
        self.assertNotEqual(row_fingerprint("PIPE-0TORAEC02QSN76", "۱۴۰۵/۶/۲۱", "339400.0"),
                            row_fingerprint("PIPE-0TORAEC02QSN76", "۱۴۰۵/۶/۱۹", "339400.0"))

    def test_a_changed_price_on_the_same_date_is_a_different_observation(self):
        self.assertNotEqual(row_fingerprint("BRICK-1", "۱۴۰۵/۶/۲۱", "4300.0"),
                            row_fingerprint("BRICK-1", "۱۴۰۵/۶/۲۱", "11700.0"))


class RealDatabaseTestCase(unittest.TestCase):
    """Shared gate: skip with a reason rather than fail when there is nothing to ask."""

    def setUp(self):
        self.sync = open_disposable()
        if self.sync is None:
            self.skipTest("no disposable database for the material price import. "
                          "Create it with `%s`." % PREPARE)
        self.addCleanup(self.sync.close)
        self.db = run(psycopg.AsyncConnection.connect(DSN, row_factory=dict_row,
                                                      autocommit=True))
        self.addCleanup(lambda: run(self.db.close()))
        self.repo = PsycopgMaterialPriceRepository(self.db)
        # A project of this test's own. `price_observations` refuses DELETE by trigger and
        # should, so isolation is by scope rather than by cleanup -- which also means these
        # tests prove the scope filter works, because a leak from another test would show up
        # as a count that is too high.
        self.project_id = PROJECT_PREFIX + self.id().rsplit(".", 1)[-1][:40]
        self.scope = Scope(self.project_id)

    def count(self, sql, *args):
        return self.sync.execute(sql, args).fetchone()["n"]

    def service(self, book):
        """An import whose workbook this test supplies. No network, real workbook layer.

        Only the bytes-to-worksheets step is replaced: building a genuine xlsx would be a
        test of openpyxl, and everything downstream of it -- the header contract, the
        completeness rule, the row decisions -- runs exactly as it does in production.
        """
        async def fetch(_link):
            return b"PK"

        original = import_module.workbook_from_xlsx
        import_module.workbook_from_xlsx = lambda _content: book
        self.addCleanup(setattr, import_module, "workbook_from_xlsx", original)
        return MaterialPriceImportService(
            self.repo, sheet_link=TEST_SHEET_LINK,
            fetch=fetch)


class ImportTests(RealDatabaseTestCase):
    def test_an_import_writes_providers_items_and_observations(self):
        outcome = run(self.service(full_workbook()).run(self.scope))
        self.assertEqual("succeeded", outcome.status)
        self.assertEqual(7, outcome.inserted, "one accepted row per worksheet")
        self.assertEqual(0, outcome.rejected)

        rows = self.sync.execute(
            "SELECT normalized_price_irr, source_currency, observed_at_source"
            " FROM price_observations WHERE organization_id=%s AND project_id=%s",
            (ORG, self.project_id)).fetchall()
        self.assertEqual(7, len(rows))
        self.assertTrue(all(r["source_currency"] == "TOMAN" for r in rows))
        self.assertTrue(all(r["normalized_price_irr"] == Decimal("955000") for r in rows),
                        "95500 Toman is 955000 rial, multiplied once")
        self.assertTrue(all(r["observed_at_source"] == "workflow_date" for r in rows),
                        "observed_at must say where it came from, never imply a provider")

    def test_running_the_same_import_twice_inserts_nothing_the_second_time(self):
        book = full_workbook()
        first = run(self.service(book).run(self.scope))
        second = run(self.service(book).run(self.scope))
        self.assertEqual(7, first.inserted)
        self.assertEqual(0, second.inserted, "a re-import must not double the rows")
        self.assertEqual(7, second.already_present)
        self.assertEqual(7, self.count(
            "SELECT count(*) AS n FROM price_observations WHERE organization_id=%s"
            " AND project_id=%s", ORG, self.project_id))

    def test_one_product_on_two_workflow_dates_is_kept_as_two_observations(self):
        book = full_workbook([
            ("Sivanland", "لوله پلی اتیلن 110", "عدد", 339400.0, "۱۴۰۵/۶/۲۱", "PIPE-DUP"),
            ("Sivanland", "لوله پلی اتیلن 110", "عدد", 339400.0, "۱۴۰۵/۶/۱۹", "PIPE-DUP"),
        ])
        outcome = run(self.service(book).run(self.scope))
        self.assertEqual(8, outcome.inserted)
        self.assertEqual(2, self.count(
            """SELECT count(*) AS n FROM price_observations o JOIN provider_items i
                 ON i.id = o.provider_item_id
                WHERE o.organization_id=%s AND o.project_id=%s
                  AND i.external_id='PIPE-DUP'""", ORG, self.project_id),
            "the owner asked for duplicate rows to be kept, not merged")

    def test_a_non_pipe_row_is_stored_and_marked_inactive_with_a_reason(self):
        book = full_workbook([
            ("Sivanland", "لوله پلی اتیلن 110", "عدد", 100000.0, "۱۴۰۵/۶/۲۱", "PIPE-REAL"),
            ("Sivanland", "تفلون صورتی خمیری آسیا", "عدد", 24000.0, "۱۴۰۵/۶/۲۱", "PIPE-TAPE"),
        ])
        run(self.service(book).run(self.scope))
        rows = self.sync.execute(
            """SELECT external_id, category, active, inactive_reason FROM provider_items
                WHERE organization_id=%s AND project_id=%s AND external_id LIKE 'PIPE-%%'""",
            (ORG, self.project_id)).fetchall()
        by_id = {r["external_id"]: r for r in rows}
        self.assertEqual("pipe", by_id["PIPE-REAL"]["category"])
        self.assertTrue(by_id["PIPE-REAL"]["active"])
        self.assertEqual("pipe_fitting", by_id["PIPE-TAPE"]["category"])
        self.assertFalse(by_id["PIPE-TAPE"]["active"])
        self.assertIn("not a pipe", by_id["PIPE-TAPE"]["inactive_reason"])
        # Scoped to this test's project. Without the project filter this counted every
        # PIPE row every other test had ever written into the disposable database, which is
        # a number that says nothing about this test.
        self.assertEqual(3, self.count(
            """SELECT count(*) AS n FROM price_observations o JOIN provider_items i
                 ON i.id=o.provider_item_id AND i.project_id=o.project_id
                WHERE o.organization_id=%s AND o.project_id=%s
                  AND i.external_id LIKE 'PIPE-%%'""", ORG, self.project_id),
            "the fitting is excluded from the active list and kept as imported history")

    def test_a_blank_price_is_stored_as_rejected_and_never_as_zero(self):
        book = full_workbook([
            ("Mashhad Foolad", "میلگرد", "کیلو", "عدد", "1405-06-22", "REBAR-BLANK"),
        ])
        outcome = run(self.service(book).run(self.scope))
        self.assertEqual(1, outcome.rejected)
        row = self.sync.execute(
            """SELECT o.normalized_price_irr, o.validation_status, o.validation_reasons
                 FROM price_observations o JOIN provider_items i ON i.id=o.provider_item_id
                WHERE o.organization_id=%s AND i.external_id='REBAR-BLANK'""",
            (ORG,)).fetchone()
        self.assertIsNotNone(row, "a rejected row is stored, not dropped")
        self.assertIsNone(row["normalized_price_irr"],
                          "and it carries no price at all, not a zero")
        self.assertEqual("rejected", row["validation_status"])
        self.assertTrue(row["validation_reasons"], "with the reason attached")

    def test_a_refused_workbook_writes_nothing_and_keeps_the_previous_prices(self):
        run(self.service(full_workbook()).run(self.scope))
        before = self.count("SELECT count(*) AS n FROM price_observations"
                            " WHERE organization_id=%s AND project_id=%s", ORG, self.project_id)

        damaged = full_workbook()
        damaged["brick"] = [HEADER]          # a header with nothing under it
        with self.assertRaises(MaterialPriceImportError) as caught:
            run(self.service(damaged).run(self.scope))
        self.assertIn("unchanged", str(caught.exception))

        self.assertEqual(before, self.count(
            "SELECT count(*) AS n FROM price_observations WHERE organization_id=%s"
            " AND project_id=%s", ORG, self.project_id),
            "a failed import must not erase the current prices")
        self.assertEqual(1, self.count(
            "SELECT count(*) AS n FROM price_collection_runs WHERE organization_id=%s"
            " AND project_id=%s", ORG, self.project_id),
            "the refused import never even started a run")

    def test_a_renamed_price_column_refuses_the_whole_import(self):
        damaged = full_workbook()
        damaged["Pipe-table"] = [tuple(h for h in HEADER if h != "قیمت"),
                                 ("Sivanland", "لوله", "کیلو", "۱۴۰۵/۶/۲۱", "PIPE-1")]
        with self.assertRaises(MaterialPriceImportError) as caught:
            run(self.service(damaged).run(self.scope))
        self.assertIn("قیمت", str(caught.exception))
        self.assertEqual(0, self.count(
            "SELECT count(*) AS n FROM price_observations WHERE organization_id=%s"
            " AND project_id=%s", ORG, self.project_id))

    def test_two_imports_cannot_overlap(self):
        provider = run(self.repo.ensure_provider(self.scope, name="X", domain="docs/x"))
        run(self.repo.start_run(self.scope, provider_id=provider["id"], document_id="D",
                                started_at=datetime.now(timezone.utc)))
        with self.assertRaises(RunAlreadyRunning):
            run(self.repo.start_run(self.scope, provider_id=provider["id"], document_id="D",
                                    started_at=datetime.now(timezone.utc)))

    def test_a_listing_that_left_the_sheet_is_not_deleted(self):
        run(self.service(full_workbook([
            ("Mashhad Foolad", "میلگرد الف", "کیلو", 95500.0, "1405-06-22", "REBAR-GONE"),
        ])).run(self.scope))
        run(self.service(full_workbook([
            ("Mashhad Foolad", "میلگرد ب", "کیلو", 96000.0, "1405-06-23", "REBAR-STAYS"),
        ])).run(self.scope))
        survivors = [r["external_id"] for r in self.sync.execute(
            """SELECT external_id FROM provider_items WHERE organization_id=%s
                AND project_id=%s AND external_id LIKE 'REBAR-%%'""",
            (ORG, self.project_id)).fetchall()]
        self.assertIn("REBAR-GONE", survivors,
                      "a row that stopped appearing must not delete the listing")
        self.assertIn("REBAR-STAYS", survivors)

    def test_the_import_writes_to_no_financial_table(self):
        run(self.service(full_workbook()).run(self.scope))
        for table in ("price_versions", "estimate_lines", "invoices", "report_snapshots"):
            with self.subTest(table=table):
                self.assertEqual(0, self.count("SELECT count(*) AS n FROM " + table),
                                 "the import must not write to %s: an observation is "
                                 "evidence, not a Finance price" % table)

    def test_the_latest_observation_is_the_newest_the_sheet_states(self):
        run(self.service(full_workbook([
            ("Mashhad Foolad", "میلگرد", "کیلو", 90000.0, "1405-06-19", "REBAR-T"),
            ("Mashhad Foolad", "میلگرد", "کیلو", 95500.0, "1405-06-22", "REBAR-T"),
        ])).run(self.scope))
        latest = run(self.repo.latest_observations(self.scope, category="rebar"))
        rebar = [r for r in latest if r["external_id"] == "REBAR-T"]
        self.assertEqual(1, len(rebar), "one row per listing")
        self.assertEqual(Decimal("955000"), rebar[0]["normalized_price_irr"],
                         "the newest workflow date wins, not the last row read")


class UnitSettingTests(RealDatabaseTestCase):
    def test_a_unit_decision_is_appended_and_the_previous_one_stays_readable(self):
        first = run(self.repo.append_unit_setting(
            self.scope, category="rebar", resource_id=None, display_unit="kg",
            reason="rebar is quantified in kilograms", created_by=ACTOR))
        second = run(self.repo.append_unit_setting(
            self.scope, category="rebar", resource_id=None, display_unit="ton",
            reason="the team reports rebar in tons", created_by=ACTOR))
        self.assertEqual(1, first["version"])
        self.assertEqual(2, second["version"])

        rows = self.sync.execute(
            "SELECT version, display_unit FROM material_unit_settings"
            " WHERE organization_id=%s AND project_id=%s ORDER BY version",
            (ORG, self.project_id)).fetchall()
        self.assertEqual([(1, "kg"), (2, "ton")],
                         [(r["version"], r["display_unit"]) for r in rows],
                         "the earlier decision is still there; nothing was updated")

        current = run(self.repo.unit_settings(self.scope, category="rebar"))
        self.assertEqual(1, len(current))
        self.assertEqual("ton", current[0]["display_unit"])

    def test_a_category_setting_and_a_resource_setting_are_separate_decisions(self):
        run(self.repo.append_unit_setting(self.scope, category="brick", resource_id=None,
                                          display_unit="piece", reason="default",
                                          created_by=ACTOR))
        settings = run(self.repo.unit_settings(self.scope, category="brick"))
        self.assertEqual(1, len(settings))
        self.assertIsNone(settings[0]["resource_id"])


if __name__ == "__main__":
    unittest.main()
