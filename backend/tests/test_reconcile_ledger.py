# -*- coding: utf-8 -*-
"""What the ledger reconciliation must refuse, asserted where it is decided.

The database half of this was exercised on a copy restored from the working database: the
dry-run proved equivalence, the apply moved 0013 to 0016 with an identical business-table
fingerprint, a rerun reported "already in step", and `alembic current` then agreed the copy
was at head. What those runs cannot pin down is the reasoning that decides WHEN to refuse,
because a passing run never visits it. These do.

The dangerous failure is not a crash. It is a tool that says "proven" about a revision range
containing a backfill it never looked at, or about a column that exists with the wrong type.
"""

import re
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.reconcile_ledger import (DATA_VERBS, DDL_TABLE, LEDGER, chain, head,
                                      objects_touched, revisions, upgrade_sql)

SOURCE = (BACKEND_ROOT / "scripts" / "reconcile_ledger.py").read_text(encoding="utf-8")


class DataMigrationTests(unittest.TestCase):
    """A revision that moves rows cannot be vouched for by comparing schemas."""

    def test_the_range_this_procedure_was_written_for_is_pure_ddl(self):
        """0014 to 0019 add columns, indexes and a table, and touch no row.

        That is the whole justification for reconciling this particular ledger: there is no
        backfill that could have been skipped. The range is named explicitly rather than
        running to head, because head has since moved past it -- see the test below.
        """
        found = revisions()
        self.assertEqual(1, len(head(found)), "a branched chain has no single intended revision")
        _tables, data = objects_touched(found, chain(found, "0013", "0019"))
        self.assertEqual([], data, "a revision in 0013..0019 moves data: %s" % data)

    def test_the_invoice_numbering_revision_is_seen_as_the_data_migration_it_is(self):
        """0020 backfills every invoice with a number, and the tool must say so.

        This is the case the test above was written to anticipate: "if a later revision
        changes that, the tool must refuse rather than inherit today's answer." It has, and
        it does -- a range containing 0020 is reported as a data migration, and
        `reconcile_ledger` answers `refused-data-migration` rather than vouching for a
        backfill it never looked at.
        """
        found = revisions()
        _tables, data = objects_touched(found, chain(found, "0013", head(found)[0]))
        self.assertEqual(["0020"], [revision for revision, _name, _moved in data])
        _revision, _name, moved = data[0]
        self.assertEqual(["INSERT INTO", "UPDATE INVOICES AS TARGET SET"], moved)
        self.assertIn("refused-data-migration", SOURCE)

    def test_a_revision_that_writes_rows_is_reported_as_a_data_migration(self):
        # The aliased forms are the ones 0020 exposed: a backfill that joins to a subquery
        # names the target with an alias, and the pattern used to require SET immediately
        # after the table -- so the statement that does the most work was the one missed.
        for statement in ("INSERT INTO finance_resources (id) SELECT id FROM msp_tasks;",
                          "UPDATE estimate_lines SET original_quantity = 0;",
                          "UPDATE invoices AS target SET invoice_seq = n.row_number"
                          " FROM (SELECT 1 AS row_number) n;",
                          "UPDATE invoices target SET invoice_seq = 1;",
                          "UPDATE ONLY invoices SET invoice_seq = 1;",
                          "DELETE FROM price_versions WHERE version = 1;",
                          "COPY estimate_lines FROM STDIN;"):
            with self.subTest(statement=statement[:40]):
                self.assertTrue(DATA_VERBS.search(statement),
                                "a data migration would have been read as pure DDL")

    def test_ordinary_ddl_is_not_mistaken_for_a_data_migration(self):
        """A false positive here refuses a reconciliation that was safe, every time.

        Only executable DDL is claimed. The detector reads the revision as text, so a
        sentence inside a comment or a string literal that happens to read like a
        statement will match -- and that is the direction to be wrong in: a false positive
        refuses a reconciliation somebody then does by hand, while a false negative vouches
        for a backfill nobody looked at.
        """
        for statement in ("ALTER TABLE finance_mpp_rows ADD COLUMN source_rate_basis text;",
                          "CREATE INDEX IF NOT EXISTS ix_rows ON finance_mpp_rows (id);",
                          "CREATE TABLE estimate_line_source_completions (id uuid);",
                          "ALTER TABLE invoices DISABLE TRIGGER confirmed_invoice_immutable;",
                          "ALTER TABLE finance_mpp_source_versions ADD COLUMN reporting_date date;"):
            with self.subTest(statement=statement[:40]):
                self.assertIsNone(DATA_VERBS.search(statement))

    def test_only_the_upgrade_half_of_a_revision_is_examined(self):
        """A downgrade's DML is not applied by an upgrade, and must not refuse one."""
        text = ('UPGRADE_SQL = """ALTER TABLE t ADD COLUMN c text; """\n'
                'DOWNGRADE_SQL = """DELETE FROM t WHERE c IS NULL; """')
        self.assertIsNone(DATA_VERBS.search(upgrade_sql(text)))
        self.assertTrue(DATA_VERBS.search(text), "the fixture has no DML to be fooled by")


class ObjectDiscoveryTests(unittest.TestCase):
    def test_the_tables_compared_are_the_tables_the_revisions_touch(self):
        found = revisions()
        walk = chain(found, "0013", head(found)[0])
        tables, _data = objects_touched(found, walk)
        # `estimate_lines` and `finance_resources` are here because 0019 adds an index to
        # each: a revision that only indexes still changes the object the reconciler must
        # compare, and an index is exactly the kind of difference an environment drifts on.
        # `invoices` and `finance_invoice_counters` arrive with 0020. The six price names
        # arrive with 0021: four tables it alters and two it creates, and
        # `provider_item_labels` with 0022. That the discovery
        # found them without being told is the property this test is really about.
        self.assertEqual(
            ["estimate_line_source_completions", "estimate_lines",
             "finance_invoice_counters", "finance_mpp_rows",
             "finance_mpp_source_versions", "finance_resources", "invoices",
             "material_unit_settings", "price_collection_runs", "price_observations",
             "price_providers", "progress_snapshot_refs", "provider_item_labels",
             "provider_item_unit_factors", "provider_items"], tables)

    def test_each_ddl_shape_the_revisions_use_is_recognised(self):
        """A shape the pattern misses is a table altered and never compared."""
        for statement, expected in (
                ("ALTER TABLE finance_mpp_rows ADD COLUMN x text", "finance_mpp_rows"),
                ("ALTER TABLE IF EXISTS finance_mpp_rows DROP COLUMN x", "finance_mpp_rows"),
                ("CREATE TABLE IF NOT EXISTS estimate_line_source_completions (id uuid)",
                 "estimate_line_source_completions"),
                ("CREATE UNIQUE INDEX ux_a ON finance_mpp_source_versions (id)",
                 "finance_mpp_source_versions"),
                ("CREATE INDEX IF NOT EXISTS ix_a ON ONLY finance_mpp_rows (id)",
                 "finance_mpp_rows"),
        ):
            with self.subTest(statement=statement[:46]):
                self.assertIn(expected, [m.lower() for m in DDL_TABLE.findall(statement)])

    def test_a_revision_off_the_chain_is_refused_rather_than_guessed(self):
        found = revisions()
        with self.assertRaises(SystemExit):
            chain(found, "0016", "0014")  # 0016 is not an ancestor of 0014


class SafetyShapeTests(unittest.TestCase):
    """Properties of the procedure that must not be edited away."""

    def test_it_never_runs_ddl_and_writes_only_the_ledger(self):
        """Every statement it can execute, including the ones built by %-formatting.

        Reading only `ast.Constant` arguments would have skipped
        `"SELECT ... FROM %s FOR UPDATE" % LEDGER` and reported a smaller, tidier set than
        the tool actually runs.
        """
        import ast
        executed = []
        for node in ast.walk(ast.parse(SOURCE)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute" and node.args):
                continue
            first = node.args[0]
            if isinstance(first, ast.BinOp) and isinstance(first.op, ast.Mod):
                first = first.left
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                executed.append(" ".join(first.value.split()))
            else:
                # Two statements here are not literals, and both are accounted for: the
                # LOCK, built from psycopg.sql identifiers, and `query`, which is one of
                # the borrowed catalogue SELECTs asserted below.
                rendered = ast.unparse(node.args[0])
                allowed = "LOCK TABLE" in rendered or rendered == "query"
                self.assertTrue(allowed, "an unreadable statement: %s" % rendered[:70])
        from scripts.reconcile_release_schema import QUERIES
        for kind, statement in QUERIES.items():
            with self.subTest(borrowed=kind):
                self.assertTrue(" ".join(statement.split()).upper().startswith("SELECT"),
                                "a borrowed catalogue query is not a read")
        self.assertGreaterEqual(len(executed), 6, "almost no statements were examined")
        writes = [s for s in executed if not s.upper().startswith(("SELECT", "SET "))]
        # Exactly one write. Asserted against the template, because that is what the
        # source holds: the table name arrives by %-formatting from LEDGER.
        self.assertEqual(1, len(writes), "more than one write: %s" % writes)
        self.assertEqual("UPDATE %s SET version_num=%%s WHERE version_num=%%s", writes[0])
        self.assertEqual("finance_alembic_version", LEDGER,
                         "the one table this may write is no longer the ledger")
        for verb in ("ALTER TABLE", "CREATE TABLE", "DROP ", "TRUNCATE", "INSERT INTO",
                     "DELETE FROM"):
            with self.subTest(verb=verb.strip()):
                self.assertEqual([], [s for s in executed if verb in s.upper()])

    def test_the_release_only_restriction_of_the_other_tool_is_left_alone(self):
        """This procedure exists BECAUSE that one refuses the working database.

        Widening it there instead would have made the casual release-rehearsal tool able to
        write to production, which is the opposite of the trade being made here.
        """
        other = (BACKEND_ROOT / "scripts" / "reconcile_release_schema.py").read_text(
            encoding="utf-8")
        self.assertIn('startswith("bambo_release_")', other)
        self.assertIn("only isolated bambo_release_* databases are allowed", other)
        self.assertIn("this recovery tool is local-only", other)
        # And this file borrows that tool's comparison logic without borrowing -- or
        # softening -- its target guard. Naming it in prose is fine; calling it is not.
        self.assertNotIn("local_dsn", SOURCE)
        import ast
        imported = {name.name for node in ast.walk(ast.parse(SOURCE))
                    if isinstance(node, ast.ImportFrom)
                    and node.module == "scripts.reconcile_release_schema"
                    for name in node.names}
        self.assertEqual({"QUERIES", "fingerprints"}, imported)

    def test_it_reuses_the_existing_comparison_logic_rather_than_restating_it(self):
        self.assertIn("from scripts.reconcile_release_schema import QUERIES, fingerprints",
                      SOURCE)
        from scripts.reconcile_release_schema import QUERIES
        self.assertEqual({"columns", "constraints", "indexes", "triggers"}, set(QUERIES))
        # Column existence alone is not equivalence: the column query carries the type,
        # nullability, default, identity and generated-ness.
        for fragment in ("format_type", "attnotnull", "pg_get_expr", "attidentity",
                         "attgenerated"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, QUERIES["columns"])
        # And a trigger is compared by its function body, not only its name.
        self.assertIn("pg_get_functiondef", QUERIES["triggers"])

    def test_writing_requires_the_target_name_to_be_echoed_back(self):
        self.assertIn("--confirm-database", SOURCE)
        self.assertIn("if confirm_database != identity[0]", SOURCE)
        self.assertIn('REFUSED: --apply needs --confirm-database', SOURCE)

    def test_it_takes_the_locks_the_repository_already_uses(self):
        self.assertIn("FOR UPDATE", SOURCE, "the ledger row is not locked")
        self.assertIn("SHARE ROW EXCLUSIVE MODE", SOURCE, "the tables are not locked")

    def test_it_refuses_rather_than_reports_when_contents_change(self):
        self.assertIn("refused-contents-changed", SOURCE)
        self.assertRegex(SOURCE, r"if fingerprints\(target\) != before:")


if __name__ == "__main__":
    unittest.main()
