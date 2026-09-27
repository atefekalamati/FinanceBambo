# -*- coding: utf-8 -*-
"""The newer of two pricing decisions prices the item, and a revised quantity counts.

Decided 2026-09-27. «همیشه آخرین قیمتی که برای یک محصول ست می‌شود باید ارجحیت داشته
باشد»: type a rate, then link the item to the sheet, and the sheet prices it from that
moment; type a rate again and the rate does. Measured before the change on «بتن ۴۰۰»
(1.8.1.7.3): a rate typed at 10:10, a link made minutes later, and every surface still
showing the rate -- with no way back, because price versions are append-only.

The same day, two machines on that activity had a rate and a revised quantity and no
daily cost, because the quantity query read only the file's original.
"""
import asyncio
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.item_price_components import NEEDS_COMPONENTS, RESOURCE_PRICE_READY
from app.finance.domain.price_resolution import SOURCE_MANUAL_RESOURCE, SOURCE_SHEET
from app.finance.services.item_price_components import ItemPriceComponentService
from test_item_price_component_service import LINE, Repo, Scope, component

ITEM = UUID("77777777-7777-4777-8777-777777777777")


def service(resource_prices, components=(), prices=None):
    repo = Repo(components=list(components), quantities={LINE: Decimal("100")},
                prices=prices)
    repo._resource_prices = resource_prices
    return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 27))


def resolved(amount, source):
    return {"current_unit_price_irr": Decimal(amount), "current_price_unit": "kg",
            "current_price_source": source}


class TheStatusTableFollowsTheLadderTests(unittest.TestCase):
    """The ladder says which decision won; this table prices the row accordingly."""

    def test_the_typed_rate_prices_the_row_even_when_components_exist(self):
        row = asyncio.run(service({LINE: resolved("5000", SOURCE_MANUAL_RESOURCE)},
                                  [component()]).table_status(Scope()))[str(LINE)]
        self.assertEqual(RESOURCE_PRICE_READY, row["status"])
        self.assertEqual("500000", row["daily_item_cost_irr"], "100 × 5000")
        self.assertEqual(SOURCE_MANUAL_RESOURCE, row["price_source"])

    def test_a_newer_link_prices_the_row_through_its_components(self):
        """The ladder answered from the sheet, so the rate typed earlier is set aside and
        the component -- which knows the usage quantity and the crossing -- prices it."""
        row = asyncio.run(service({LINE: resolved("777", SOURCE_SHEET)},
                                  [component()]).table_status(Scope()))[str(LINE)]
        self.assertNotEqual(RESOURCE_PRICE_READY, row["status"])
        self.assertEqual(1, row["component_count"])

    def test_a_newer_link_with_no_components_here_prices_the_row_at_the_sheet_rate(self):
        """A schedule-level mapping: the ladder resolved it, this table holds nothing."""
        row = asyncio.run(service({LINE: resolved("777", SOURCE_SHEET)}).table_status(Scope()))[str(LINE)]
        self.assertEqual(RESOURCE_PRICE_READY, row["status"])
        self.assertEqual("77700", row["daily_item_cost_irr"])
        self.assertEqual(SOURCE_SHEET, row["price_source"])

    def test_nothing_resolved_and_nothing_linked_is_still_unresolved(self):
        row = asyncio.run(service({}).table_status(Scope()))[str(LINE)]
        self.assertEqual(NEEDS_COMPONENTS, row["status"])


class TheQuantityIsTheRevisedOneTests(unittest.TestCase):
    """Asserted on the SQL: the revision is read first, in both repositories."""

    def _source(self, path):
        return (BACKEND_ROOT / path).read_text(encoding="utf-8")

    def test_both_quantity_queries_read_the_newest_revision_first(self):
        for path in ("app/finance/repositories/item_price_components.py",
                     "app/finance/repositories/item_price_mappings.py"):
            with self.subTest(path):
                source = self._source(path)
                start = source.index("async def line_quantities")
                body = source[start:start + 2000]
                self.assertIn("FROM estimate_revisions er", body)
                self.assertIn("ORDER BY er.revision DESC LIMIT 1", body)
                self.assertLess(body.index("estimate_revisions"), body.index("l.original_quantity"),
                                "the revision is the first arm of the coalesce")
                self.assertIn("estimate_line_source_completions", body, "the file's completion is still the last resort")



class TheReportCrossesSheetUnitsLikeTheItemsTableTests(unittest.TestCase):
    """The link now reaches the report, so the report must read the listing's unit the
    way the items table does -- or refuse it the way the items table does."""

    def _report(self, base_unit, price_unit, current="100", source="sheet", conversions=()):
        from app.finance.domain.reports import calculate_live_report
        row = {"id": UUID(int=1), "resource_id": UUID(int=2), "resource_type": "material",
               "resource_code": "mat", "resource_title": "x", "original_quantity": "10",
               "revised_quantity": "10", "original_unit_price_irr": "100",
               "current_unit_price_irr": current, "current_price_unit": price_unit,
               "current_price_source": source, "base_unit": base_unit, "dimension": "mass",
               "assignment_external_id": "a-1", "activity_external_id": None,
               "progress_snapshot_id": UUID(int=3)}
        return calculate_live_report([row], [], [{"assignmentExternalId": "a-1",
                                                 "actualQuantity": "4", "task": {}}],
                                     list(conversions), "10")

    def codes(self, report):
        return {w["code"] for w in report.warnings}

    def test_a_listing_whose_unit_nobody_stated_does_not_price_the_line(self):
        report = self._report("مترمکعب", None)
        self.assertIn("PRICE_UNIT_NOT_CONVERTIBLE", self.codes(report))
        self.assertEqual(Decimal("0"), report.metrics["remainingPhysicalCostIrr"])
        self.assertEqual(0, report.required_line_count)

    def test_two_spellings_of_one_unit_are_one_unit(self):
        report = self._report("مترمکعب", "m3")
        self.assertNotIn("PRICE_UNIT_NOT_CONVERTIBLE", self.codes(report))
        self.assertEqual(Decimal("1000"), report.metrics["remainingPhysicalCostIrr"], "10 × 100")
        kilo = self._report("کیلوگرم", "کیلو")
        self.assertEqual(Decimal("1000"), kilo.metrics["remainingPhysicalCostIrr"])

    def test_a_registry_ratio_crosses_without_a_project_rule(self):
        # Priced per kg, measured in tonnes: one tonne is 1,000 kg -> 10 × (100 × 1000).
        report = self._report("ton", "kg")
        self.assertNotIn("PRICE_UNIT_NOT_CONVERTIBLE", self.codes(report))
        self.assertEqual(Decimal("1000000"), report.metrics["remainingPhysicalCostIrr"])

    def test_a_manual_price_still_reads_its_unit_literally(self):
        # By construction a manual price is per the base unit; a stated NULL is no mismatch.
        report = self._report("مترمکعب", None, source="manual_resource")
        self.assertNotIn("PRICE_UNIT_NOT_CONVERTIBLE", self.codes(report))
        self.assertEqual(Decimal("1000"), report.metrics["remainingPhysicalCostIrr"])

if __name__ == "__main__":
    unittest.main()
