# -*- coding: utf-8 -*-
"""One ladder, three readers, one answer.

The defect these exist for: a machine priced at 32,000,000 by a person showed that number
on the report and «بدون قیمت» on Items and Estimates, because the report resolved from
`price_versions` and the items page resolved from `price_observations` and neither knew
the other existed. Nothing failed. The two pages simply disagreed, and a reader had no way
to tell which was lying.

So the rungs are asserted here as an ORDER, not as four separate behaviours: the tests
that matter are the ones where two rungs both answer and only one may win.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.item_price_components import (NEEDS_COMPONENTS,
                                                      RESOURCE_PRICE_READY,
                                                      STATUS_LABELS, STATUS_REASONS,
                                                      aggregate_row, resource_priced_row)
from app.finance.domain.price_resolution import (MANUAL_SCOPES, RESOLVED_PRICE_COLUMNS,
                                                 SOURCE_MANUAL_RESOURCE, SOURCE_NONE,
                                                 SOURCE_SHEET, price_source_of,
                                                 resolved_price_columns,
                                                 resolved_price_joins)


class TheLadderTests(unittest.TestCase):
    """What the SQL says, asserted on the SQL rather than on a mock of it."""

    def test_project_outranks_organization_which_outranks_the_sheet(self):
        joins = resolved_price_joins("l")
        manual = joins.index("manual_price")
        sheet = joins.index("sheet_price")
        self.assertLess(manual, sheet, "the manual rung must be resolved first")
        # Project before organization is a sort, not a filter: both rows are candidates and
        # the ordering picks. A filter would have hidden an organization price whenever a
        # project price existed for a DIFFERENT date.
        self.assertIn("(pv.scope_kind='project') DESC", joins)
        self.assertIn("pv.effective_from DESC", joins)
        self.assertIn("pv.effective_from<=", joins)

    def test_the_amount_prefers_the_manual_rung(self):
        self.assertIn("COALESCE(manual_price.unit_price_irr, sheet_price.unit_price_irr)",
                      RESOLVED_PRICE_COLUMNS)

    def test_a_line_with_no_price_survives_the_joins(self):
        """LEFT, not INNER. An unpriced line must still be counted, not dropped."""
        joins = resolved_price_joins("l")
        self.assertEqual(2, joins.count("LEFT JOIN LATERAL"))
        self.assertEqual(0, joins.count("INNER JOIN"))

    def test_the_keys_can_come_from_different_tables(self):
        """Items and Estimates reads scope from the MPP row and identity from the resource.

        Its `estimate_lines` join is LEFT and may be absent; taking `resource_id` from a
        missing row would hand an unclassified assignment somebody else's price.
        """
        joins = resolved_price_joins("l", organization="m.organization_id",
                                     project="m.project_id", resource="r.id",
                                     assignment="m.source_assignment_uid")
        self.assertIn("pv.organization_id=m.organization_id", joins)
        self.assertIn("pv.resource_id=r.id", joins)
        self.assertIn("fm.source_assignment_uid=m.source_assignment_uid", joins)
        self.assertNotIn("l.resource_id", joins)


class ThePriceSourceTests(unittest.TestCase):
    def test_both_manual_scopes_read_as_one_source(self):
        """A reader asking "who set this" gets the same answer for either scope.

        The precise rung stays available in `current_price_scope`; this is the coarse
        answer a page shows, and collapsing the two is the point of it.
        """
        for scope in MANUAL_SCOPES:
            with self.subTest(scope):
                self.assertEqual(SOURCE_MANUAL_RESOURCE, price_source_of(scope))

    def test_the_sheet_and_the_absence_are_their_own_answers(self):
        self.assertEqual(SOURCE_SHEET, price_source_of("provider_sheet"))
        self.assertEqual(SOURCE_NONE, price_source_of(None))

    def test_none_is_a_statement_not_a_null(self):
        """`none` means the resolver looked. A null field means nobody asked."""
        self.assertIn("ELSE 'none'", RESOLVED_PRICE_COLUMNS)

    def test_the_python_and_sql_mappings_agree(self):
        """Two copies of one rule, kept honest against each other.

        A service that classified `organization` as a sheet price would disagree with the
        report about what the user is looking at, and nothing would fail.
        """
        self.assertIn("THEN 'manual_resource'", RESOLVED_PRICE_COLUMNS)
        self.assertIn("THEN 'sheet'", RESOLVED_PRICE_COLUMNS)
        self.assertEqual(SOURCE_MANUAL_RESOURCE, price_source_of("project"))


class ThePriceUnitTests(unittest.TestCase):
    """The two rungs quote per DIFFERENT units, and the amount alone hides that."""

    def test_a_manual_price_is_quoted_per_the_resource_base_unit(self):
        columns = resolved_price_columns("r.base_unit")
        self.assertIn("THEN r.base_unit", columns)
        self.assertIn("current_price_unit", columns)

    def test_a_sheet_price_is_quoted_per_the_worksheet_unit(self):
        self.assertIn("sheet_price.source_unit", resolved_price_columns("r.base_unit"))

    def test_a_caller_that_needs_no_unit_gets_the_columns_unchanged(self):
        self.assertEqual(RESOLVED_PRICE_COLUMNS, resolved_price_columns())


class ResourcePricedRowTests(unittest.TestCase):
    """A machine is hired at a rate. It is not assembled from materials."""

    def test_a_resource_price_replaces_the_demand_for_components(self):
        row = resource_priced_row(Decimal("32000000"), Decimal("100"), "hour",
                                  SOURCE_MANUAL_RESOURCE)
        self.assertEqual(RESOURCE_PRICE_READY, row["status"])
        self.assertNotEqual(NEEDS_COMPONENTS, row["status"])
        # A STRING. The schema types money as `str | None`: a Decimal serialises through
        # float, and 3,200,000,000 rial does not survive that intact.
        self.assertEqual("3200000000", row["daily_item_cost_irr"])
        self.assertEqual(("hour", SOURCE_MANUAL_RESOURCE),
                         (row["price_unit"], row["price_source"]))

    def test_it_reports_no_components_rather_than_zero_of_zero_ready(self):
        row = resource_priced_row(Decimal("1"), Decimal("1"), "hour", SOURCE_MANUAL_RESOURCE)
        self.assertEqual((0, 0, 0), (row["component_count"], row["ready_component_count"],
                                     row["unresolved_component_count"]))

    def test_a_line_with_no_quantity_has_a_price_and_no_total(self):
        """Null, never zero. "No total" is a question; "a total of 0" is a claim."""
        row = resource_priced_row(Decimal("32000000"), None, "hour", SOURCE_MANUAL_RESOURCE)
        self.assertIsNone(row["daily_item_cost_irr"], "None, never the string '0'")
        self.assertEqual("32000000", row["current_unit_price_irr"])

    def test_it_is_not_presented_as_something_to_fix(self):
        """Its reason is empty, like «آماده» and unlike every other status."""
        self.assertEqual("", STATUS_REASONS[RESOURCE_PRICE_READY])
        self.assertEqual("قیمت منبع ثبت شده است", STATUS_LABELS[RESOURCE_PRICE_READY])

    def test_a_line_with_neither_price_nor_components_is_unresolved_and_null(self):
        row = aggregate_row([])
        self.assertEqual(NEEDS_COMPONENTS, row["status"])
        self.assertIsNone(row["daily_item_cost_irr"], "null, not zero")


class OneLadderEverywhereTests(unittest.TestCase):
    """The readers must share the module, not merely agree today."""

    def _source(self, path):
        return (BACKEND_ROOT / path).read_text(encoding="utf-8")

    def test_every_pricing_reader_imports_the_shared_resolver(self):
        for path in ("app/finance/repositories/reports.py",
                     "app/finance/repositories/items_and_estimates.py",
                     "app/finance/repositories/item_price_components.py"):
            with self.subTest(path):
                self.assertIn("price_resolution", self._source(path))

    def test_no_reader_resolves_a_sheet_price_on_its_own(self):
        """The bespoke observation lookup Items and Estimates carried is gone.

        It was the second rule, and the one that ignored `price_versions` entirely.
        """
        items = self._source("app/finance/repositories/items_and_estimates.py")
        self.assertNotIn("obs.normalized_price_irr", items)
        self.assertNotIn("LIMIT 1) obs ON TRUE", items)


if __name__ == "__main__":
    unittest.main()
