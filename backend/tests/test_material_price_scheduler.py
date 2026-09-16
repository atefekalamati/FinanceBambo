# -*- coding: utf-8 -*-
"""The daily import that runs without anybody asking.

WHY THIS EXISTS

`price_observations` had one production writer and it was reachable only by running a
script by hand. Every provider row said `default_interval_minutes = 1440` and nothing read
that column, so "daily" was a stored intention. These tests pin the three decisions that
turn it into a behaviour:

    WHICH projects   those with an active spreadsheet provider, read from the database --
                     not a second list somebody has to keep in step with the first
    WHEN             when the newest SUCCESSFUL run started longer ago than the interval.
                     Successful, because a failed run left the prices untouched and must
                     be retried rather than counted as "we imported today"
    WHAT ON FAILURE  an outcome, never an exception. A loop that dies on one bad sheet
                     stops importing every other project, and the symptom is silence

The interval floor is here for the same reason: a mistyped `0` must not become "always
due", which is a tight loop against somebody else's servers.
"""

import sys
import unittest
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.services.material_price_import import (ImportOutcome,
                                                        MaterialPriceImportError,
                                                        MaterialPriceImportService,
                                                        MaterialPriceSheetNotConfigured)

ORG = UUID("11111111-1111-4111-8111-111111111111")


class Repo:
    """Just the one query the tick uses."""

    def __init__(self, projects):
        self.projects = list(projects)

    async def projects_with_active_providers(self):
        return self.projects


def project(project_id, minutes):
    return {"organization_id": ORG, "project_id": project_id,
            "minutes_since_last_success": minutes}


class Service(MaterialPriceImportService):
    """The real tick, with `run` replaced so no sheet is fetched."""

    def __init__(self, projects, behaviour=None):
        super().__init__(Repo(projects), sheet_link="configured")
        self.behaviour = behaviour or {}
        self.ran = []

    async def run(self, scope):
        self.ran.append(scope.project_id)
        outcome = self.behaviour.get(scope.project_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or ImportOutcome("succeeded", {"id": uuid4()}, 3, 1, 2, {})


class DueTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_project_that_ran_an_hour_ago_is_not_due_for_a_daily_import(self):
        service = Service([project("terrace", 60)])
        due = await service.due_projects(1440)
        self.assertEqual([], due)

    async def test_a_project_that_ran_yesterday_is_due(self):
        service = Service([project("terrace", 1500)])
        due = await service.due_projects(1440)
        self.assertEqual(["terrace"], [row["project_id"] for row, _ in due])

    async def test_a_project_that_has_never_succeeded_is_due(self):
        """A freshly configured project imports on the next tick, not a day later."""
        service = Service([project("new_site", None)])
        due = await service.due_projects(1440)
        self.assertEqual(["new_site"], [row["project_id"] for row, _ in due])

    async def test_force_ignores_the_due_check_and_nothing_else(self):
        service = Service([project("terrace", 1)])
        self.assertEqual([], await service.due_projects(1440))
        due = await service.due_projects(1440, force=True)
        self.assertEqual(["terrace"], [row["project_id"] for row, _ in due])


class TickTests(unittest.IsolatedAsyncioTestCase):
    async def test_it_imports_the_due_and_skips_the_rest(self):
        service = Service([project("due_one", 2000), project("fresh", 5)])
        outcomes = {o["projectId"]: o for o in await service.periodic_tick(1440)}
        self.assertEqual("imported", outcomes["due_one"]["status"])
        self.assertEqual("skipped", outcomes["fresh"]["status"])
        self.assertEqual(["due_one"], service.ran, "the skipped project read nothing")

    async def test_a_skipped_project_says_how_long_ago_it_succeeded(self):
        """A tick that did nothing and a tick that never ran must not look the same."""
        service = Service([project("fresh", 5)])
        outcome = (await service.periodic_tick(1440))[0]
        self.assertEqual("skipped", outcome["status"])
        self.assertEqual(5, outcome["minutesSinceLastSuccess"])

    async def test_the_counts_travel_with_the_outcome(self):
        service = Service([project("terrace", 2000)])
        outcome = (await service.periodic_tick(1440))[0]
        self.assertEqual((3, 1, 2), (outcome["inserted"], outcome["alreadyPresent"],
                                     outcome["rejected"]))

    async def test_one_project_failing_does_not_stop_the_next(self):
        service = Service(
            [project("broken", 2000), project("fine", 2000)],
            behaviour={"broken": MaterialPriceImportError("the sheet is missing a tab")})
        outcomes = {o["projectId"]: o for o in await service.periodic_tick(1440)}
        self.assertEqual("failed", outcomes["broken"]["status"])
        self.assertEqual("imported", outcomes["fine"]["status"])
        self.assertIn("missing a tab", outcomes["broken"]["reason"])
        self.assertEqual("MATERIAL_PRICE_IMPORT_REFUSED", outcomes["broken"]["code"])

    async def test_an_unexpected_error_is_an_outcome_not_an_exception(self):
        """The loop must survive anything, including what nobody anticipated."""
        service = Service([project("terrace", 2000)],
                          behaviour={"terrace": RuntimeError("the database went away")})
        outcomes = await service.periodic_tick(1440)
        self.assertEqual("failed", outcomes[0]["status"])
        self.assertEqual("UNEXPECTED", outcomes[0]["code"])

    async def test_an_import_already_in_flight_is_reported_not_raised(self):
        """Two ticks cannot interleave one price set: the database refuses the second."""
        service = Service(
            [project("terrace", 2000)],
            behaviour={"terrace": MaterialPriceImportError(
                "another import is already running for this provider")})
        outcomes = await service.periodic_tick(1440)
        self.assertEqual("failed", outcomes[0]["status"])
        self.assertIn("already running", outcomes[0]["reason"])

    async def test_no_configured_projects_is_an_empty_tick_not_a_failure(self):
        self.assertEqual([], await Service([]).periodic_tick(1440))


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        import os
        self.env = os.environ
        self.saved = {k: self.env.get(k) for k in
                      ("FINANCE_MATERIAL_PRICE_IMPORT_ENABLED",
                       "FINANCE_MATERIAL_PRICE_IMPORT_INTERVAL_MINUTES")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value

    def test_it_is_off_unless_explicitly_turned_on(self):
        from devhost.environment import material_price_import_enabled
        self.env.pop("FINANCE_MATERIAL_PRICE_IMPORT_ENABLED", None)
        self.assertFalse(material_price_import_enabled())
        for value in ("yes", "YES", "true", "1", "on"):
            with self.subTest(value):
                self.env["FINANCE_MATERIAL_PRICE_IMPORT_ENABLED"] = value
                self.assertTrue(material_price_import_enabled())
        for value in ("no", "false", "0", "", "maybe"):
            with self.subTest(value):
                self.env["FINANCE_MATERIAL_PRICE_IMPORT_ENABLED"] = value
                self.assertFalse(material_price_import_enabled())

    def test_the_interval_defaults_to_a_day(self):
        from devhost.environment import material_price_import_interval_minutes
        self.env.pop("FINANCE_MATERIAL_PRICE_IMPORT_INTERVAL_MINUTES", None)
        self.assertEqual(1440, material_price_import_interval_minutes())

    def test_a_useless_interval_falls_back_to_a_day_rather_than_to_zero(self):
        """Zero would mean always-due: a tight loop against somebody else's servers."""
        from devhost.environment import material_price_import_interval_minutes
        for value in ("0", "-5", "", "soon", "1440.5"):
            with self.subTest(value):
                self.env["FINANCE_MATERIAL_PRICE_IMPORT_INTERVAL_MINUTES"] = value
                self.assertEqual(1440, material_price_import_interval_minutes())

    def test_a_real_interval_is_honoured(self):
        from devhost.environment import material_price_import_interval_minutes
        self.env["FINANCE_MATERIAL_PRICE_IMPORT_INTERVAL_MINUTES"] = "360"
        self.assertEqual(360, material_price_import_interval_minutes())

    def test_the_tick_reads_the_project_list_from_the_database(self):
        """Not from configuration. A provider somebody adds tomorrow is picked up."""
        import inspect
        from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
        source = inspect.getsource(
            PsycopgMaterialPriceRepository.projects_with_active_providers)
        self.assertIn("FROM price_providers", source)
        self.assertIn("p.active AND p.crawl_method = 'google_sheet'", source)
        self.assertIn("r.status IN ('succeeded', 'partially_succeeded')", source)


if __name__ == "__main__":
    unittest.main()
