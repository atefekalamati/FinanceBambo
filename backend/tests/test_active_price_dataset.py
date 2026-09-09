# -*- coding: utf-8 -*-
"""Which items the price module offers today, and everything it must not disturb.

What these defend: `finance_resources` is a reference entity — invoices point at it,
issued reports pin it, the audit trail names it — so nothing is deleted, hidden from
lookup, or rewritten. The operational question is narrower and belongs to the price
module alone: of those rows, which is a person meant to be pricing now.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.active_prices import ACTIVE_PRICE_RESOURCE, active_price_resource


class ActivePriceRuleTests(unittest.TestCase):
    def test_the_rule_admits_a_schedule_item(self):
        self.assertIn("source_resource_uid IS NOT NULL", active_price_resource("r"))

    def test_the_rule_admits_anything_not_seed_shaped(self):
        # The negated fingerprint: a hand-made item passes because it fails at least one
        # of the three marks, whatever it is coded.
        rule = active_price_resource("r")
        self.assertIn("NOT (r.source_resource_uid IS NULL", rule)
        self.assertIn("r.code LIKE 'MSP-T%%'", rule)
        self.assertIn("r.external_resource_id IS NOT NULL", rule)

    def test_the_rule_admits_a_seed_row_an_invoice_names(self):
        self.assertIn("FROM invoice_lines il", active_price_resource("r"))

    def test_the_fingerprint_needs_all_three_marks(self):
        # Any one alone would take real data with it: a typed code, a hand-made item, or
        # anything ever linked to an external system.
        rule = " ".join(active_price_resource("r").split())
        self.assertIn("AND r.code LIKE", rule)
        self.assertIn("AND r.external_resource_id IS NOT NULL", rule)

    def test_the_rule_never_keys_on_a_price(self):
        # "Show everything with a price" would show 120 seeded rows and hide every real
        # schedule item, which has none.
        self.assertNotIn("price_versions", active_price_resource("r"))

    def test_the_rule_travels_with_its_alias(self):
        self.assertIn("x.source_resource_uid", active_price_resource("x"))
        self.assertNotIn("r.source_resource_uid", active_price_resource("x"))
        self.assertIn("{r}", ACTIVE_PRICE_RESOURCE, "the template keeps its placeholder")


class BlastRadiusTests(unittest.TestCase):
    """What the rule must NOT reach."""

    def source(self, *parts):
        return (BACKEND_ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_the_resource_catalogue_is_not_filtered(self):
        # Four other consumers read it: price history titles, invoice line labels, the
        # home price widget, and the items page's count of what it withheld.
        listing = self.source("app", "finance", "repositories", "resources.py")
        listing = listing[listing.index("async def list_resources"):]
        listing = listing[:listing.index("async def", 10)]
        self.assertNotIn("MSP-T", listing)
        self.assertNotIn("active_price_resource", listing)

    def test_resolving_one_price_by_id_is_never_scoped(self):
        # An invoice or a report resolving a historical item must keep working for ever.
        prices = self.source("app", "finance", "repositories", "prices.py")
        current = prices[prices.index("async def current"):]
        current = current[:current.index("async def", 10)]
        self.assertNotIn("active_price_resource", current)

    def test_appending_a_price_is_never_scoped(self):
        prices = self.source("app", "finance", "repositories", "prices.py")
        append = prices[prices.index("async def append"):]
        self.assertNotIn("active_price_resource", append)

    def test_the_operational_listings_are_scoped(self):
        prices = self.source("app", "finance", "repositories", "prices.py")
        for method in ("async def history", "async def trend_history"):
            body = prices[prices.index(method):]
            body = body[:body.index("async def", 10)] if "async def" in body[10:] else body
            self.assertIn("active_price_resource", body, method)

    def test_the_price_calculation_itself_is_untouched(self):
        # The selection rule: project scope first, then the latest effective date.
        prices = self.source("app", "finance", "repositories", "prices.py")
        self.assertIn("ORDER BY (scope_kind='project') DESC,effective_from DESC,version DESC", prices)

    def test_the_rule_is_defined_once(self):
        domain = self.source("app", "finance", "domain", "active_prices.py")
        self.assertIn("ACTIVE_PRICE_RESOURCE", domain)
        for path in (("app", "finance", "repositories", "resources.py"),
                     ("app", "finance", "services", "prices.py"),
                     ("app", "finance", "router.py")):
            self.assertNotIn("MSP-T", self.source(*path),
                             "the fingerprint belongs in one place")


if __name__ == "__main__":
    unittest.main()
