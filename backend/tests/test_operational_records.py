# -*- coding: utf-8 -*-
"""Evidence that a person used an item, and the catalogue that keeps answering in full.

What these defend: `has_operational_records` says whether anybody has priced or invoiced
an item. A view uses it to keep a row it would otherwise withhold. It is evidence OF USE
and never evidence of origin, and asking the question must not change what the catalogue
returns -- every other consumer still needs the whole of it.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.repositories.resources import SEED_PRICE_REASON, PsycopgFinanceResourcesRepository
from app.finance.schemas.resources import ResourceResponse


class OperationalRecordsTests(unittest.TestCase):
    def test_the_seed_reason_is_quoted_from_the_seed_itself(self):
        # The seed stamps this on every price it invents. A price carrying it is the seed
        # talking to itself; anything else is a person. Quoted, so the two files cannot
        # drift into disagreeing about which prices count as use.
        seed = (BACKEND_ROOT / "scripts" / "test_only" / "seed_terrace_finance.py").read_text(encoding="utf-8")
        self.assertIn(SEED_PRICE_REASON, seed)

    def test_the_question_asked_is_use_and_not_origin(self):
        source = (BACKEND_ROOT / "app" / "finance" / "repositories" / "resources.py").read_text(encoding="utf-8")
        # Exactly the expression that answers the question, and nothing around it.
        statement = source[source.index("SELECT r.*,"):source.index(") has_operational_records")]
        # Use is an invoice line or a price somebody entered. Nothing about the row's code,
        # its name or where it came from may appear in this test.
        self.assertIn("invoice_lines", statement)
        self.assertIn("price_versions", statement)
        for origin in ("MSP-T", "source_resource_uid", "external_resource_id", "code"):
            self.assertNotIn(origin, statement,
                             "origin must not decide a question about use")

    def test_the_catalogue_still_returns_every_row(self):
        # The endpoint feeds six pages, four of which legitimately need the withheld rows:
        # price history titles, invoice line labels, the home price widget, and the items
        # page's own count of what it withheld. Filtering here would break all four.
        source = (BACKEND_ROOT / "app" / "finance" / "repositories" / "resources.py").read_text(encoding="utf-8")
        listing = source[source.index("async def list_resources"):]
        listing = listing[:listing.index("async def", 10)]
        self.assertIn("WHERE r.organization_id=%s AND r.project_id=%s AND r.deleted_at IS NULL", listing)
        self.assertNotIn("MSP-T", listing)
        self.assertNotIn("NOT EXISTS", listing)

    def test_the_flag_reaches_the_wire_and_defaults_to_untouched(self):
        self.assertIn("has_operational_records", ResourceResponse.model_fields)
        field = ResourceResponse.model_fields["has_operational_records"]
        self.assertIs(False, field.default, "silence must mean untouched, never used")
        self.assertEqual("hasOperationalRecords",
                         ResourceResponse.model_fields["has_operational_records"].alias)

    def test_a_row_maps_the_flag_it_was_given(self):
        row = {"id": "1", "organization_id": "2", "project_id": "terrace", "resource_type": "material",
               "code": "MSP-T915", "title": "نصب داربست", "base_unit": "unit", "dimension": "count",
               "external_resource_id": "915", "created_by": "3", "created_at": "2026-01-01",
               "source_resource_uid": None, "has_operational_records": True}
        resource = PsycopgFinanceResourcesRepository._resource(row)
        self.assertTrue(resource.has_operational_records)
        self.assertFalse(PsycopgFinanceResourcesRepository._resource({**row, "has_operational_records": None})
                         .has_operational_records)
        del row["has_operational_records"]
        self.assertFalse(PsycopgFinanceResourcesRepository._resource(row).has_operational_records,
                         "a row that does not answer has not said yes")


if __name__ == "__main__":
    unittest.main()
