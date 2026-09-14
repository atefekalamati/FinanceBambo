# -*- coding: utf-8 -*-
"""The pure helpers behind the operational scripts.

Everything here runs without a database and without a network, because everything here is
a decision made BEFORE either is touched: which database may be written to, which tool
matches the server, and which revisions are pending. Those are exactly the decisions that
are expensive to get wrong and cheap to test.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.ops._common import (CANONICAL_TEST, PROTECTED_DATABASES, Refused, database_of,
                                 refuse_protected, require_dsn)
from scripts.ops.migrate_canonical_test import BUSINESS_TABLES, chain, pending


class DsnReadingTests(unittest.TestCase):
    def test_both_dsn_spellings_are_read(self):
        for dsn, expected in (
                ("postgresql://u@127.0.0.1:5432/bambo_canonical_test", "bambo_canonical_test"),
                ("postgres://u:p@host:5432/somedb?sslmode=require", "somedb"),
                ("host=127.0.0.1 port=5432 dbname=other user=u", "other")):
            with self.subTest(dsn=dsn):
                self.assertEqual(expected, database_of(dsn))

    def test_a_dsn_naming_no_database_reads_as_none_rather_than_a_guess(self):
        for bad in ("", None, "not a dsn", "host=127.0.0.1 user=u"):
            with self.subTest(bad=repr(bad)):
                self.assertIsNone(database_of(bad))

    def test_a_missing_dsn_is_refused_and_names_the_variable_to_set(self):
        import os

        saved = os.environ.pop("FINANCE_OPS_DSN", None)
        try:
            with self.assertRaises(Refused) as caught:
                require_dsn(None, "FINANCE_OPS_DSN", "target DSN")
            self.assertIn("FINANCE_OPS_DSN", str(caught.exception))
        finally:
            if saved is not None:
                os.environ["FINANCE_OPS_DSN"] = saved

    def test_there_is_no_default_dsn_anywhere(self):
        """A default would be a hardcoded write target, which is how a script run in the
        wrong window becomes an incident."""
        import os

        saved = os.environ.pop("FINANCE_OPS_DSN", None)
        try:
            with self.assertRaises(Refused):
                require_dsn("", "FINANCE_OPS_DSN", "target DSN")
            with self.assertRaises(Refused):
                require_dsn("   ", "FINANCE_OPS_DSN", "target DSN")
        finally:
            if saved is not None:
                os.environ["FINANCE_OPS_DSN"] = saved


class ProtectedDatabaseTests(unittest.TestCase):
    def test_the_two_protected_names(self):
        self.assertEqual({"bambo", "bambo_canonical_local"}, set(PROTECTED_DATABASES))

    def test_a_protected_database_is_refused_on_any_host_and_in_any_spelling(self):
        for dsn in ("postgresql://u@127.0.0.1:5432/bambo_canonical_local",
                    "postgresql://u@192.168.100.200:5432/bambo_canonical_local",
                    "postgresql://u@127.0.0.1:5432/bambo",
                    "host=127.0.0.1 dbname=bambo user=u",
                    "host=192.168.100.200 dbname=bambo_canonical_local user=u"):
            with self.subTest(dsn=dsn):
                with self.assertRaises(Refused) as caught:
                    refuse_protected(dsn)
                self.assertIn("protected", str(caught.exception))

    def test_an_unreadable_dsn_is_refused_rather_than_allowed(self):
        """Unknown is not permission."""
        with self.assertRaises(Refused):
            refuse_protected("this names no database")

    def test_an_ordinary_local_database_is_allowed(self):
        """The guard must not be a blanket no, or somebody will work around it."""
        self.assertEqual(CANONICAL_TEST, refuse_protected(
            "postgresql://u@127.0.0.1:5432/" + CANONICAL_TEST))
        self.assertEqual("bambo_material_price_demo", refuse_protected(
            "postgresql://u@127.0.0.1:5432/bambo_material_price_demo"))


class RevisionChainTests(unittest.TestCase):
    """The bug this class exists for: the parser read only double quotes.

    The early revisions are written with single quotes, so their `down_revision` came back
    empty and four of them looked like heads. The "is the database at head" check at the
    end of a migration would then have accepted almost anything.
    """

    def test_every_revision_on_disk_is_read(self):
        revisions = chain()
        self.assertGreaterEqual(len(revisions), 22)
        for name in ("0001", "0002", "0016", "0021", "0022"):
            with self.subTest(revision=name):
                self.assertIn(name, revisions)

    def test_both_quote_styles_produce_a_parent(self):
        revisions = chain()
        self.assertEqual("0001", revisions["0002"][1], "0002 is written with single quotes")
        self.assertEqual("0021", revisions["0022"][1], "0022 with double")

    def test_the_first_revision_has_no_parent(self):
        self.assertIsNone(chain()["0001"][1])

    def test_there_is_exactly_one_head(self):
        revisions = chain()
        parents = {revisions[name][1] for name in revisions}
        head = sorted(name for name in revisions if name not in parents)
        self.assertEqual(1, len(head), "more than one head means the parser missed a parent")

    def test_pending_is_everything_after_the_current_revision(self):
        revisions = chain()
        self.assertEqual([], pending("0022", revisions), "at head, nothing is pending")
        self.assertEqual(["0021", "0022"], pending("0020", revisions))
        self.assertIn("0001", pending(None, revisions),
                      "an empty database runs the whole chain")

    def test_an_unknown_current_revision_reports_nothing_rather_than_everything(self):
        """A database at a revision this checkout does not have is not a database to
        migrate blindly."""
        self.assertEqual([], pending("9999", chain()))


class BusinessTableListTests(unittest.TestCase):
    def test_the_protected_tables_are_the_ones_holding_financial_records(self):
        for table in ("invoices", "invoice_lines", "price_versions", "estimate_lines",
                      "report_snapshots", "finance_audit_events", "price_observations"):
            with self.subTest(table=table):
                self.assertIn(table, BUSINESS_TABLES,
                              "%s holds records a migration must not lose" % table)

    def test_the_list_is_explicit_rather_than_discovered(self):
        """Discovery would silently stop protecting a table somebody renamed."""
        self.assertIsInstance(BUSINESS_TABLES, tuple)
        self.assertEqual(len(BUSINESS_TABLES), len(set(BUSINESS_TABLES)))


if __name__ == "__main__":
    unittest.main()
