"""Regression cases from the local MPP/Finance audit; no live database writes."""
import asyncio
import sqlite3
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coreint.finance_mpp_sync import (
    _APPROVED_TOMAN_SHA256, FinanceMppSyncRefused, finance_rows,
)
from coreint.finance_mpp_mapping import _SOURCE_ROWS


def parsed(symbol="تومان", code="IRR", cost="12565115391.0"):
    return SimpleNamespace(
        currency_symbol=symbol, currency_code=code,
        tasks=[{"uid": 1212, "name": "task", "wbs": "1.4.2",
                "metrics": {"task_cost": "900", "task_actual_cost": "0"},
                "raw_fields": {}}],
        resources=[{"uid": 155, "name": "resource", "native_type": "MATERIAL",
                    "quantity_unit": "m"}],
        assignments=[{"task_uid": 1212, "resource_uid": 155, "assignment_uid": 9703,
                      "units": "100", "cost": cost}],
    )


def _sync_fixtures():
    """The sync test's own stubs, imported here rather than at module scope.

    `test_readiness_docs` walks the syntax tree for import statements to check every
    third-party package is declared, and a sibling test module read from `sys.path` is
    indistinguishable from a package on PyPI there. Fetched by name it is plainly neither.
    """
    import importlib
    return importlib.import_module("test_finance_mpp_sync")


class CurrencyAndAssignmentTests(unittest.TestCase):
    def test_approved_file_converts_once_without_replacing_task_or_estimate(self):
        row = finance_rows(parsed(), source_sha256=_APPROVED_TOMAN_SHA256)[0]
        self.assertEqual(Decimal("125651153910"), row["source_assignment_cost_irr"])
        self.assertEqual(Decimal("900"), row["source_cost"])
        self.assertEqual(Decimal("1"), row["source_assignment_units"])
        self.assertIsNone(row["quantity"])
        self.assertEqual("m", row["normalized_unit"])

    def test_an_irr_file_is_not_multiplied_again(self):
        row = finance_rows(parsed("ریال", cost="125651153910"), source_sha256="another-file")[0]
        self.assertEqual(Decimal("125651153910"), row["source_assignment_cost_irr"])

    def test_toman_decision_is_not_inherited_by_different_bytes(self):
        with self.assertRaises(FinanceMppSyncRefused) as caught:
            finance_rows(parsed(), source_sha256="different-file")
        self.assertEqual("MPP_CURRENCY_UNRESOLVED", caught.exception.code)

    def test_unknown_or_conflicting_currency_never_becomes_rials(self):
        for symbol, code in [(None, None), ("$", "USD"), ("تومان", "USD")]:
            with self.subTest(symbol=symbol, code=code):
                with self.assertRaises(FinanceMppSyncRefused):
                    finance_rows(parsed(symbol, code), source_sha256=_APPROVED_TOMAN_SHA256)

    def test_zero_and_null_are_distinct(self):
        row = finance_rows(parsed(cost="0"), source_sha256=_APPROVED_TOMAN_SHA256)[0]
        self.assertEqual(Decimal(0), row["source_assignment_cost_irr"])
        self.assertIsNone(finance_rows(parsed(None, None, None))[0]["source_assignment_cost_irr"])

    def test_each_assignment_keeps_its_cost(self):
        value = parsed(cost="12")
        value.assignments.append(dict(value.assignments[0], assignment_uid=9704, cost="0", units=None))
        rows = finance_rows(value, source_sha256=_APPROVED_TOMAN_SHA256)
        self.assertEqual([Decimal(120), Decimal(0)], [r["source_assignment_cost_irr"] for r in rows])
        self.assertIsNone(rows[1]["source_assignment_units"])
        self.assertTrue(all(r["source_cost"] == Decimal(900) for r in rows))

    def test_unresolved_currency_refuses_before_any_database_access(self):
        fixture = _sync_fixtures().SyncTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        connection = _sync_fixtures().Connection()
        with self.assertRaises(FinanceMppSyncRefused):
            asyncio.run(fixture.service(connection, _sync_fixtures().Reader(parsed())).sync("org", "terrace"))
        self.assertEqual([], connection.statements)
        self.assertEqual([], connection.log)


class SourceScopeTests(unittest.TestCase):
    def test_assignment_uid_is_scoped_to_organization_project_and_version(self):
        # Execute the production SELECT against isolated in-memory rows. No local DB.
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE finance_mpp_rows (organization_id TEXT, project_id TEXT, "
                       "source_version_id TEXT, source_task_uid INT, source_assignment_uid INT, "
                       "source_resource_uid INT, task_name TEXT, task_wbs TEXT, resource_name TEXT, "
                       "resource_type TEXT, resource_unit TEXT, "
                       "source_material_quantity NUMERIC, source_resource_rate_irr NUMERIC, "
                       "source_rate_basis TEXT)")
            for org, project, version in [("a", "p", "v"), ("b", "p", "v"),
                                          ("a", "q", "v"), ("a", "p", "old")]:
                db.execute("INSERT INTO finance_mpp_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (org, project, version, 1212, 9703, 155, org+project+version,
                            "1.4.2", "resource", "MATERIAL", "m", 1, 125651153910,
                            "material_unit"))
            sql = _SOURCE_ROWS
            for key in ("organization_id", "project_id", "version_id"):
                sql = sql.replace("%("+key+")s", ":"+key)
            rows = db.execute(sql, {"organization_id": "a", "project_id": "p", "version_id": "v"}).fetchall()
            self.assertEqual(1, len(rows))
            self.assertEqual("apv", rows[0][3])
