# -*- coding: utf-8 -*-
"""The rules that make the numbers trustworthy, proved where they are enforced.

TWO LAYERS, TESTED SEPARATELY
Most financial rules live in the domain and are covered by the service tests. A smaller set
lives in the database, as triggers, and those had no test at all -- they were only ever
exercised by hand against a running server. That is the wrong place for the strongest
guarantee in the system to be unverified: application code can be bypassed by anyone with a
connection string, and the triggers are what makes "immutable" mean immutable.

So this module checks both:

  * **structure**, always: the migration declares every guard, on the right table, for the
    right events. Runs anywhere, needs nothing.
  * **enforcement**, when a local database is reachable: the guard actually refuses. Skipped
    with a stated reason otherwise, never silently.

The structural half is not a consolation prize. A trigger that is declared for UPDATE but
not DELETE looks correct in review and leaves a hole, and that is exactly what it catches.
"""

import os
import sys
import unittest
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

REVISION = BACKEND_ROOT / "alembic" / "versions" / "0001_finance_core.py"

#: Tables whose rows may never be changed or removed once written. Each is a record of
#: something that happened; editing one would rewrite the past.
APPEND_ONLY = (
    "finance_project_settings", "estimate_revisions", "price_versions",
    "unit_conversions", "progress_snapshot_refs", "progress_overrides",
    "report_snapshots", "finance_audit_events",
)

#: Two tables that are partly mutable, and therefore need a guard that inspects the row
#: rather than refusing outright.
GUARDED = {
    "estimate_lines": "finance_guard_estimate_original",
    "invoices": "finance_guard_confirmed_invoice",
}

DEMO_DSN = os.environ.get(
    "FINANCE_DEMO_DSN",
    "postgresql://postgres@127.0.0.1:5432/bambo_finance_integration_demo")


def live_connection():
    """A connection to the local demo database, or None with the reason recorded.

    Never falls back to any other target: the module-level constant is the only DSN this
    file will use, and it names a disposable local database.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(DEMO_DSN, row_factory=dict_row, connect_timeout=3)
    except Exception as error:                                    # noqa: BLE001
        return None, str(error).splitlines()[0][:80]
    row = connection.execute(
        "SELECT current_database() d, host(inet_server_addr()) h, inet_server_port() p"
    ).fetchone()
    if (row["d"], row["h"], int(row["p"])) != ("bambo_finance_integration_demo",
                                               "127.0.0.1", 5432):
        connection.close()
        return None, f'refusing {row["h"]}/{row["d"]}: not the local demo database'
    return connection, None


class DeclaredGuardTests(unittest.TestCase):
    """What the migration says. Runs everywhere, needs no database."""

    SQL = REVISION.read_text(encoding="utf-8")

    def test_the_rejecting_function_exists_and_raises(self):
        self.assertIn("CREATE OR REPLACE FUNCTION finance_reject_mutation()", self.SQL)
        self.assertIn("RAISE EXCEPTION 'immutable finance history cannot be updated or deleted'",
                      self.SQL)

    def test_every_append_only_table_refuses_both_update_and_delete(self):
        """`BEFORE UPDATE` alone is the mistake this catches.

        It reads as a complete guard and leaves DELETE open, which is the more destructive
        of the two: an edited row can at least still be seen.
        """
        for table in APPEND_ONLY:
            with self.subTest(table=table):
                self.assertIn(
                    f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                    f"FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();", self.SQL)

    def test_the_partly_mutable_tables_have_their_own_inspecting_guard(self):
        """An estimate line may be revised and an invoice may move through its lifecycle.

        Neither can use the blanket refusal, so each has a function that looks at what
        changed -- and those are the two places a mistake would be silent.
        """
        for table, function in GUARDED.items():
            with self.subTest(table=table):
                self.assertIn(f"EXECUTE FUNCTION {function}();", self.SQL)
                self.assertIn(f"CREATE OR REPLACE FUNCTION {function}()", self.SQL)

    def test_the_original_estimate_fields_are_the_ones_protected(self):
        """A revision changes the revised quantity. The original never moves.

        Without this the estimate's own history would be editable, and the variance between
        original and revised -- the number the whole report is about -- could be made to say
        anything.
        """
        guard = self.SQL[self.SQL.index("finance_guard_estimate_original"):]
        guard = guard[:guard.index("$$", guard.index("$$") + 2)]
        for column in ("original_quantity", "original_unit_price_irr"):
            with self.subTest(column=column):
                self.assertIn(column, guard)

    def test_the_guard_count_matches_the_number_of_protected_tables(self):
        declared = self.SQL.count("CREATE TRIGGER ")
        self.assertEqual(len(APPEND_ONLY) + len(GUARDED), declared,
                         "a table gained or lost a guard without this list being updated")


class EnforcedGuardTests(unittest.TestCase):
    """What the database does. Skipped, with a reason, when there is nothing to ask."""

    @classmethod
    def setUpClass(cls):
        cls.connection, cls.reason = live_connection()
        if cls.connection is None:
            raise unittest.SkipTest(
                f"no local demo database to verify against ({cls.reason}). "
                "Structure is still checked by DeclaredGuardTests; enforcement is not. "
                "Run scripts.demo.prepare --recreate to close this gap.")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "connection", None) is not None:
            cls.connection.close()

    def refused(self, statement):
        """True when the database rejected the statement. The transaction is rolled back."""
        try:
            with self.connection.transaction():
                self.connection.execute(statement)
            return False
        except Exception:                                          # noqa: BLE001
            return True

    def rows_in(self, table):
        return self.connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]

    def test_no_append_only_row_can_be_updated_or_deleted(self):
        """A row-level trigger only fires when there is a row.

        An UPDATE that matches nothing succeeds, so running these statements against an
        empty table proves nothing and would report a pass. Empty tables are therefore
        collected and reported rather than counted as verified -- and the report is checked
        against what the fixture is known to populate, so a table quietly becoming empty
        cannot turn this test into a no-op.
        """
        unprovable = []
        for table in APPEND_ONLY:
            if not self.rows_in(table):
                unprovable.append(table)
                continue
            for statement in (f"UPDATE {table} SET organization_id = organization_id",
                              f"DELETE FROM {table}"):
                with self.subTest(statement=statement):
                    self.assertTrue(self.refused(statement),
                                    "the database allowed a change to immutable history")
        # `report_snapshots` is empty because no report has been issued -- which is itself
        # correct: `finance_report.issue` does not exist in Core, so issuing fails closed.
        self.assertEqual(["report_snapshots"], sorted(unprovable),
                         "a table that used to carry fixture rows is now empty")

    def test_a_confirmed_invoice_cannot_be_changed(self):
        self.assertTrue(self.refused(
            "UPDATE invoices SET final_amount_irr = final_amount_irr + 1 "
            "WHERE status = 'confirmed'"))
        self.assertTrue(self.refused("DELETE FROM invoices WHERE status = 'confirmed'"))

    def test_an_original_estimate_quantity_cannot_be_rewritten(self):
        self.assertTrue(self.refused(
            "UPDATE estimate_lines SET original_quantity = original_quantity + 1 "
            "WHERE original_quantity IS NOT NULL"))

    def test_appending_is_still_possible(self):
        """The guards must refuse change, not writing.

        A trigger that blocked INSERT as well would make the tables read-only and every
        one of the tests above would pass for the wrong reason.
        """
        rows = self.rows_in("price_versions")
        self.assertGreater(rows, 0, "the fixture has no price history to reason about")
        appended = None
        try:
            with self.connection.transaction():
                self.connection.execute("""
                    INSERT INTO price_versions
                        (id, organization_id, project_id, resource_id, scope_kind, version,
                         unit_price_irr, effective_from, reason, created_by, created_at)
                    SELECT gen_random_uuid(), organization_id, project_id, resource_id,
                           scope_kind, version + 1000, unit_price_irr, effective_from,
                           'invariant test', created_by, now()
                    FROM price_versions LIMIT 1
                """)
                appended = self.rows_in("price_versions")
                # Ends the transaction without leaving the row behind. Caught below, so
                # the rollback is part of the test rather than a failure of it.
                raise _Rollback()
        except _Rollback:
            pass
        self.assertEqual(rows + 1, appended)
        self.assertEqual(rows, self.rows_in("price_versions"), "the test left a row behind")

    def test_money_is_stored_as_whole_rial(self):
        """`numeric(18,0)`. A fractional rial is not a real amount, and a float would make
        the same total depend on the order rows were added.
        """
        types = self.connection.execute("""
            SELECT table_name, column_name, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name LIKE '%_irr'
        """).fetchall()
        self.assertGreater(len(types), 10)
        for row in types:
            with self.subTest(column=f'{row["table_name"]}.{row["column_name"]}'):
                self.assertEqual(0, row["numeric_scale"])


class _Rollback(Exception):
    """Ends the transaction above without leaving the appended row behind."""


class RoundingTests(unittest.TestCase):
    """Half-up, and only at the boundary where a number becomes money."""

    def test_money_rounds_half_away_from_zero(self):
        from app.finance.domain.reports import money
        cases = {"0.5": "1", "1.5": "2", "2.5": "3", "-0.5": "-1", "-1.5": "-2",
                 "0.4": "0", "0.6": "1"}
        for given, expected in cases.items():
            with self.subTest(given=given):
                self.assertEqual(Decimal(expected), money(Decimal(given)))

    def test_it_is_not_bankers_rounding(self):
        """Python's default rounds 2.5 to 2. Accounting does not, and a default that
        disagrees with the accountant is the kind of difference nobody finds.
        """
        from app.finance.domain.reports import money
        self.assertEqual(Decimal("3"), money(Decimal("2.5")))
        self.assertNotEqual(round(Decimal("2.5")), money(Decimal("2.5")))

    def test_the_domain_names_the_rounding_mode_explicitly(self):
        source = (BACKEND_ROOT / "app" / "finance" / "domain" / "reports.py").read_text(
            encoding="utf-8")
        self.assertIn("ROUND_HALF_UP", source)
        self.assertNotIn("ROUND_HALF_EVEN", source)
        self.assertIs(ROUND_HALF_UP, ROUND_HALF_UP)


if __name__ == "__main__":
    unittest.main()
