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


class TheImportScopeTests(unittest.TestCase):
    """Which scope an import writes at, and the mistake a project-scoped URL invites.

    The route that triggers an import has a project in its path. Passing that project
    through while the config says `organization` would file the company's prices inside
    one project -- and it would not fail, it would just be wrong, silently, until somebody
    noticed the other projects still had no prices.
    """

    def _scope(self, **over):
        from app.finance.services.material_price_import import _Scope
        return _Scope(**dict({"organization_id": "org-1", "project_id": "terrace"}, **over))

    def test_an_unflagged_import_writes_exactly_what_it_always_wrote(self):
        scope = self._scope()
        self.assertEqual(SCOPE_PROJECT, scope.scope_level)
        self.assertEqual("terrace", scope.project_id)

    def test_an_organization_import_is_filed_under_the_sentinel(self):
        scope = self._scope(scope_level=SCOPE_ORGANIZATION)
        self.assertEqual(SCOPE_ORGANIZATION, scope.scope_level)
        self.assertEqual(ORGANIZATION_SENTINEL_PROJECT, scope.project_id)

    def test_the_project_in_the_url_cannot_capture_an_organization_import(self):
        """The whole point of resolving the destination in one place."""
        scope = self._scope(project_id="some-other-project",
                            scope_level=SCOPE_ORGANIZATION)
        self.assertEqual(ORGANIZATION_SENTINEL_PROJECT, scope.project_id)
        self.assertNotEqual("some-other-project", scope.project_id)

    def test_an_unknown_scope_is_refused(self):
        for bad in ("global", "ORGANIZATION", "", None, "org"):
            with self.subTest(repr(bad)):
                with self.assertRaises(ValueError):
                    self._scope(scope_level=bad)

    def test_an_import_without_an_organization_is_refused(self):
        """Organization scope with no organization is the one truly unsafe combination."""
        with self.assertRaises(ValueError):
            self._scope(organization_id=None, scope_level=SCOPE_ORGANIZATION)
        with self.assertRaises(ValueError):
            self._scope(organization_id="", scope_level=SCOPE_PROJECT)

    def test_the_project_id_is_never_null(self):
        for level in SCOPE_LEVELS:
            with self.subTest(level):
                self.assertIsNotNone(self._scope(scope_level=level).project_id)


class EveryWriteCarriesTheScopeTests(unittest.TestCase):
    """All four tables, or none of them.

    A repository that passed the scope to three writes out of four would commit a
    provider, an item and a run at one scope and have the observation rejected by 0037's
    CHECK -- after the first three were already in.
    """

    SOURCE = (BACKEND_ROOT / "app" / "finance" / "repositories"
              / "material_prices.py").read_text(encoding="utf-8")

    def test_every_insert_into_a_scoped_table_names_the_column(self):
        """Counted by parsing the statements, not by matching whitespace.

        The two indentation levels in this file differ, and a check keyed on one of them
        would pass while missing the other entirely.
        """
        for table in SCOPED_TABLES:
            with self.subTest(table):
                pattern = re.compile(r"INSERT INTO %s\s*\(([^)]*)" % table)
                columns = pattern.findall(self.SOURCE)
                self.assertTrue(columns, "no INSERT INTO %s found" % table)
                for column_list in columns:
                    self.assertIn("scope_level", column_list,
                                  "an INSERT INTO %s omits scope_level" % table)

    def test_the_value_comes_from_the_scope_and_not_a_parameter(self):
        """Read off the scope object, so three callers cannot supply three answers."""
        self.assertIn("def _scope_level(scope)", self.SOURCE)
        self.assertIn('getattr(scope, "scope_level", SCOPE_PROJECT)', self.SOURCE)

    def test_a_scope_that_predates_the_field_still_works(self):
        """The HTTP path's authorised scope has no `scope_level` and never needed one."""
        from app.finance.repositories.material_prices import _scope_level

        class OldScope:
            organization_id = "org-1"
            project_id = "terrace"

        self.assertEqual(SCOPE_PROJECT, _scope_level(OldScope()))


class TheProviderRowIsTheConfigurationTests(unittest.TestCase):
    """Activating the company's sheet must be one edit, on the thing being configured.

    The alternative was an environment variable or a document id in code, and both put the
    setting somewhere it can disagree with the row it describes. 0037 already gave
    `price_providers` a `scope_level`; the tick reads it, and that is the whole mechanism.
    """

    REPOSITORY = (BACKEND_ROOT / "app" / "finance" / "repositories"
                  / "material_prices.py").read_text(encoding="utf-8")
    SERVICE = (BACKEND_ROOT / "app" / "finance" / "services"
               / "material_price_import.py").read_text(encoding="utf-8")

    def test_discovery_reports_the_scope_each_provider_was_marked_with(self):
        self.assertIn("SELECT p.organization_id, p.project_id, p.scope_level",
                      self.REPOSITORY)
        self.assertIn("GROUP BY p.organization_id, p.project_id, p.scope_level",
                      self.REPOSITORY)

    def test_the_tick_obeys_it_rather_than_deciding(self):
        self.assertIn('row.get("scope_level") or SCOPE_PROJECT', self.SERVICE)

    def test_no_sheet_or_provider_is_named_in_code(self):
        """No hardcoded document id, no hardcoded provider, no borrowed seed project."""
        for forbidden in ("1RgjXoz", "sample_site_01", "docs.google.com/spreadsheets/d/1"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, self.SERVICE)
                self.assertNotIn(forbidden, self.REPOSITORY)


class ValidatingBeforeTheSheetExistsTests(unittest.TestCase):
    """Sign-off that does not wait for the production sheet to be finished."""

    @staticmethod
    def _validate(**over):
        from app.finance.services.material_price_import import validate_import
        return validate_import(**dict({"organization_id": "org-1",
                                       "project_id": "terrace",
                                       "scope_level": SCOPE_PROJECT}, **over))

    def test_it_writes_nothing_and_cannot(self):
        """No repository is passed to it at all.

        A stronger guarantee than a `dry_run` flag every downstream writer has to honour:
        a dry run that can reach the database is one edit away from not being one.
        """
        report = self._validate()
        self.assertFalse(report["written"])
        from app.finance.services import material_price_import as module
        import inspect
        self.assertNotIn("repository",
                         inspect.signature(module.validate_import).parameters)

    def test_a_good_project_configuration_passes(self):
        report = self._validate()
        self.assertTrue(report["ok"])
        self.assertEqual("terrace", report["storageProjectId"])

    def test_an_organization_configuration_says_where_rows_will_go(self):
        report = self._validate(scope_level=SCOPE_ORGANIZATION)
        self.assertTrue(report["ok"], "informational, not an error")
        self.assertEqual(ORGANIZATION_SENTINEL_PROJECT, report["storageProjectId"])
        codes = {problem["code"] for problem in report["problems"]}
        self.assertIn("SCOPE_ORGANIZATION_SENTINEL", codes)

    def test_an_unknown_scope_is_refused(self):
        report = self._validate(scope_level="global")
        self.assertFalse(report["ok"])
        self.assertIn("SCOPE_UNKNOWN", {p["code"] for p in report["problems"]})

    def test_a_missing_organization_is_refused(self):
        report = self._validate(organization_id=None)
        self.assertFalse(report["ok"])
        self.assertIn("ORGANIZATION_MISSING", {p["code"] for p in report["problems"]})

    def test_an_organization_import_needs_no_normal_project(self):
        report = self._validate(project_id=None, scope_level=SCOPE_ORGANIZATION)
        self.assertTrue(report["ok"])
        self.assertEqual(ORGANIZATION_SENTINEL_PROJECT, report["storageProjectId"])

    def test_a_project_import_still_needs_one(self):
        report = self._validate(project_id=None)
        self.assertFalse(report["ok"])
        self.assertIn("PROJECT_MISSING", {p["code"] for p in report["problems"]})

    def test_a_worksheet_refused_for_its_columns_is_reported_with_the_reason(self):
        """The answer to «will the new sheet's columns do» -- from a fixture, not the sheet."""
        from app.finance.services.material_price_sheet import WorkbookResult, WorksheetResult

        workbook = WorkbookResult(
            worksheets=(WorksheetResult(title="brick", read=False,
                                        reason="missing required header 'قیمت'"),),
            missing_titles=("steel -Rebar",))
        report = self._validate(workbook=workbook)
        self.assertFalse(report["ok"], "a worksheet the source does not state")
        self.assertIn("WORKSHEET_MISSING", {p["code"] for p in report["problems"]})
        self.assertEqual("missing required header 'قیمت'",
                         report["worksheets"][0]["reason"])

    def test_rejected_rows_are_counted_and_named_not_silently_dropped(self):
        from app.finance.domain.material_price_rows import RowStatus
        from app.finance.services.material_price_sheet import WorkbookResult, WorksheetResult

        class Row:
            status = RowStatus.REJECTED
            row_number = 7
            reasons = ("unknown unit",)

        workbook = WorkbookResult(
            worksheets=(WorksheetResult(title="brick", read=True, rows=(Row(),)),))
        report = self._validate(workbook=workbook)
        self.assertEqual(1, report["wouldReject"])
        self.assertEqual(0, report["wouldInsert"])
        self.assertIn((7, "unknown unit"), report["worksheets"][0]["rejections"])
        self.assertTrue(report["ok"], "bad ROWS do not condemn a whole sheet")
