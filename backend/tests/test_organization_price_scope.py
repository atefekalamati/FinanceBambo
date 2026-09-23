# -*- coding: utf-8 -*-
"""A market price belongs to the company. Proving it can be stored that way, once.

One Google Sheet was imported six times -- once per project, across two organizations,
14,258 rows from a single document. The price of rebar on a Tuesday is not a fact about
`terrace`, but there was nowhere else to put it: every table on that path is keyed
`(organization_id, project_id, ...)` with `project_id` NOT NULL inside seven composite
foreign keys.

These tests pin the two halves of the fix and, more importantly, the two things it must
NOT do: leak a company's price to another company, and let a general price quietly
outrank one somebody set for this specific project.
"""

import re
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.price_resolution import (RESOLVED_PRICE_COLUMNS,
                                                 resolved_price_columns,
                                                 resolved_price_joins)

from app.finance.domain.price_scope import (ORGANIZATION_SENTINEL_PROJECT,
                                            SCOPE_LEVELS, SCOPE_ORGANIZATION,
                                            SCOPE_PROJECT, is_organization_scope,
                                            price_scope_of, readable_scope_clause,
                                            storage_project_id)

def _migration():
    """The migration module, loaded from its path.

    Its SQL is assembled with `.format()` at import time, so reading the file as text sees
    `{table}` placeholders and proves nothing about what runs. Loading it asserts on the
    statements the database will actually receive.
    """
    import importlib.util
    path = (BACKEND_ROOT / "alembic" / "versions"
            / "0037_a_market_price_belongs_to_the_company.py")
    spec = importlib.util.spec_from_file_location("migration_0037", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_M = _migration()
UPGRADE = _M.UPGRADE_SQL
DOWNGRADE = _M.DOWNGRADE_SQL
MIGRATION = (BACKEND_ROOT / "alembic" / "versions"
             / "0037_a_market_price_belongs_to_the_company.py").read_text(encoding="utf-8")
SCOPED_TABLES = ("price_providers", "provider_items", "price_collection_runs",
                 "price_observations")


class TheSentinelTests(unittest.TestCase):
    """An organization row carries a real project_id that no project has."""

    def test_it_is_not_null(self):
        """A null would switch the foreign keys OFF.

        Under MATCH SIMPLE a composite foreign key with any null column is not enforced at
        all, so a null `project_id` would leave exactly these rows unchecked -- the ones
        the feature introduces.
        """
        self.assertIsNotNone(ORGANIZATION_SENTINEL_PROJECT)
        self.assertTrue(ORGANIZATION_SENTINEL_PROJECT.strip())

    def test_it_cannot_collide_with_a_real_project_id(self):
        self.assertTrue(ORGANIZATION_SENTINEL_PROJECT.startswith("__"))
        self.assertTrue(ORGANIZATION_SENTINEL_PROJECT.endswith("__"))

    def test_the_seed_project_was_not_borrowed_for_this(self):
        """`sample_site_01` is demo data, not a declared organization scope.

        Reusing it would make seeded rows indistinguishable from a company's real prices.
        """
        self.assertNotEqual("sample_site_01", ORGANIZATION_SENTINEL_PROJECT)

    def test_one_place_decides_where_a_row_is_stored(self):
        self.assertEqual(ORGANIZATION_SENTINEL_PROJECT,
                         storage_project_id(SCOPE_ORGANIZATION, "terrace"))
        self.assertEqual("terrace", storage_project_id(SCOPE_PROJECT, "terrace"))

    def test_a_stored_row_can_be_read_back_as_organization_scoped(self):
        self.assertTrue(is_organization_scope(ORGANIZATION_SENTINEL_PROJECT))
        self.assertFalse(is_organization_scope("terrace"))
        self.assertEqual(SCOPE_ORGANIZATION, price_scope_of(ORGANIZATION_SENTINEL_PROJECT))
        self.assertEqual(SCOPE_PROJECT, price_scope_of("terrace"))

    def test_the_migration_and_the_module_name_the_same_sentinel(self):
        """Two copies of one value, and the value is written into table CHECKs.

        If they drifted, the application would write rows the database refuses -- or worse,
        rows it accepts and no reader ever finds.
        """
        self.assertIn('ORGANIZATION_SENTINEL_PROJECT = "%s"' % ORGANIZATION_SENTINEL_PROJECT,
                      MIGRATION)


class TheMigrationTests(unittest.TestCase):
    def test_every_scoped_table_gets_the_column_with_a_project_default(self):
        for table in SCOPED_TABLES:
            with self.subTest(table):
                self.assertIn("ALTER TABLE %s\n    ADD COLUMN IF NOT EXISTS scope_level "
                              "text NOT NULL DEFAULT 'project'" % table, UPGRADE)

    def test_existing_rows_are_backfilled_and_never_rewritten(self):
        """The only UPDATE sets scope_level. Nothing else about a historical row moves."""
        updates = re.findall(r"UPDATE (\w+) SET (\w+)", UPGRADE)
        self.assertEqual({"scope_level"}, {column for _table, column in updates})
        self.assertEqual(set(SCOPED_TABLES), {table for table, _column in updates})
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, UPGRADE)

    def test_the_scope_and_the_sentinel_must_agree_in_both_directions(self):
        """Half the rule catches nothing, and both halves fail silently.

        An organization row with a real project_id is invisible to every reader; a project
        row parked on the sentinel is visible to every project in the company.
        """
        self.assertEqual(len(SCOPED_TABLES),
                         UPGRADE.count("(scope_level = 'organization') = (project_id = '%s')"
                                       % ORGANIZATION_SENTINEL_PROJECT))

    def test_the_vocabulary_is_constrained(self):
        self.assertEqual(len(SCOPED_TABLES),
                         UPGRADE.count("CHECK (scope_level IN ('project', 'organization'))"))
        self.assertEqual((SCOPE_PROJECT, SCOPE_ORGANIZATION), SCOPE_LEVELS)

    def test_downgrade_removes_exactly_what_upgrade_added(self):
        for table in SCOPED_TABLES:
            with self.subTest(table):
                self.assertIn("ALTER TABLE %s DROP COLUMN IF EXISTS scope_level" % table,
                              DOWNGRADE)

    def test_the_historical_duplicates_are_left_alone(self):
        """14,258 rows across six projects stay where they are.

        Collapsing them into one organization copy means choosing which of six imports is
        the truth and deleting five. That is a decision about data, not a schema change.
        """
        self.assertNotIn("INSERT INTO price_observations", UPGRADE)
        self.assertNotIn("DELETE", UPGRADE)


class TheResolverReachesTheCompanyTests(unittest.TestCase):
    def test_an_organization_price_version_no_longer_demands_a_project_match(self):
        """The bug this closes: «organization» that only worked inside one project."""
        joins = resolved_price_joins("l")
        self.assertIn("(pv.scope_kind='organization' OR pv.project_id=", joins)

    def test_an_organization_observation_is_readable_from_any_project(self):
        joins = resolved_price_joins("l")
        self.assertIn("(o.project_id=fm.project_id OR o.scope_level='organization')", joins)

    def test_a_project_price_still_outranks_the_companys(self):
        """Specificity wins -- the same reason project beats organization one rung up."""
        joins = resolved_price_joins("l")
        self.assertIn("(o.scope_level='project') DESC", joins)
        self.assertLess(joins.index("(o.scope_level='project') DESC"),
                        joins.index("o.workflow_date_gregorian DESC"),
                        "scope is the first sort key, ahead of the date")

    def test_the_date_and_not_the_fetch_time_picks_the_newest(self):
        joins = resolved_price_joins("l")
        self.assertLess(joins.index("o.workflow_date_gregorian DESC"),
                        joins.index("o.fetched_at DESC"))

    def test_a_rejected_observation_can_never_win(self):
        self.assertIn("o.validation_status='valid'", resolved_price_joins("l"))

    def test_nothing_widened_the_organization_boundary(self):
        """Every rung is still filtered by organization_id. That is the one wall."""
        joins = resolved_price_joins("l")
        self.assertIn("pv.organization_id=", joins)
        self.assertIn("fm.organization_id=", joins)
        self.assertIn("o.organization_id=fm.organization_id", joins)

    def test_the_scope_is_published_beside_the_source(self):
        """Additive: `priceSource` keeps its three values and `priceScope` says which."""
        self.assertIn("current_price_scope_level", RESOLVED_PRICE_COLUMNS)
        self.assertIn("THEN 'manual_resource'", RESOLVED_PRICE_COLUMNS)
        self.assertIn("current_price_unit", resolved_price_columns("r.base_unit"))


class TheReadableClauseTests(unittest.TestCase):
    def test_it_admits_this_project_and_the_company(self):
        clause = readable_scope_clause("o", project="%s")
        self.assertIn("o.project_id = %s", clause)
        self.assertIn("o.scope_level = 'organization'", clause)

    def test_it_does_not_pretend_to_enforce_the_tenant(self):
        """The organization filter lives in the query, not here.

        Repeating it would read as load-bearing when the real guarantee is upstream.
        """
        self.assertNotIn("organization_id", readable_scope_clause("o"))


if __name__ == "__main__":
    unittest.main()
