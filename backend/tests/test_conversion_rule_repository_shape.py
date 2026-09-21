# -*- coding: utf-8 -*-
"""A conversion rule shaped the way the repository really returns it.

THE BUG THIS EXISTS TO STOP COMING BACK

`finance_unit_conversion_rules` has a column called `factor_value`. It has no column
called `factor`. `provider_item_unit_factors` is a different table and its column IS
called `factor`. The domain read `factor` off both, so a stored rule:

  * resolved correctly and then priced nothing, because `choose_conversion` asked a rule
    for a key it never carries; and
  * was skipped outright when read backwards, because `invert_factor(None)` is None and
    the candidate was dropped rather than returned.

Every test in the sibling file passed throughout, because its fixture carried `factor`
AND `factor_value`. So the rule here is simple and absolute: a rule dict in this file
carries `factor_value` and never `factor`, exactly as `PsycopgUnitConversionRuleRepository`
returns it. If a change makes these fail, the change is reading the wrong column.
"""

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.conversion_rules import (CONVERSION_RULE_FACTOR,
                                                 DIRECTION_DIRECT, DIRECTION_REVERSE,
                                                 PROVIDER_ITEM_FACTOR, choose_conversion,
                                                 resolve_rule)
from app.finance.repositories.unit_conversion_rules import _RULE_COLUMNS

ITEM = UUID(int=11)
PROVIDER = UUID(int=12)

#: Parsed from the repository's OWN select list rather than copied from it. A hand-kept
#: copy is the thing that failed here once already: the fixture said what somebody
#: believed the row contained, the row said something else, and the tests agreed with the
#: fixture. Bound this way, a column added, dropped or renamed in the repository shows up
#: in these tests on the next run instead of the next incident.
REPOSITORY_COLUMNS = tuple(name.strip() for name in _RULE_COLUMNS.split(",")
                           if name.strip())


def rule(**overrides):
    """One row as the repository hands it over: `factor_value`, no `factor`."""
    row = {name: None for name in REPOSITORY_COLUMNS}
    row.update({"id": UUID(int=99), "scope_type": "organization",
                "conversion_method": "factor", "status": "approved",
                "direction_definition": "one_from_unit_equals_factor_to_unit",
                "effective_from": date(2026, 1, 1)})
    row.update(overrides)
    assert "factor" not in row, "the rules table has no `factor` column"
    return row


class RepositoryShapeTests(unittest.TestCase):
    """Test 1 -- the real shape, resolved and then priced."""

    def test_the_fixture_matches_what_the_repository_selects(self):
        row = rule(from_unit="kg", to_unit="branch", factor_value=Decimal("1.2"))
        self.assertEqual(set(REPOSITORY_COLUMNS), set(row))
        self.assertIn("factor_value", row)
        self.assertNotIn("factor", row)

    def test_the_repository_selects_no_column_called_factor(self):
        """The premise every other test here rests on, asserted against the real query.

        If somebody ever adds `factor_value AS factor` to the select list, this is where
        that decision surfaces -- rather than in a row that prices differently from the
        estimate beneath it.
        """
        self.assertIn("factor_value", REPOSITORY_COLUMNS)
        self.assertNotIn("factor", REPOSITORY_COLUMNS)

    def test_a_row_with_only_factor_value_resolves_and_prices(self):
        rows = [rule(from_unit="kg", to_unit="branch", factor_value=Decimal("1.2"))]
        resolved = resolve_rule(rows, from_unit="kg", to_unit="branch")
        self.assertIsNotNone(resolved, "a stored rule must resolve")
        factor, source = choose_conversion(None, resolved)
        self.assertEqual(Decimal("1.2"), factor,
                         "resolving is not enough -- it has to price")
        self.assertEqual(CONVERSION_RULE_FACTOR, source)


class DirectConversionTests(unittest.TestCase):
    """Test 3 -- a provider_item rule, kg to branch, factor_value 1.2."""

    def test_a_provider_item_rule_answers_its_own_listing(self):
        rows = [rule(scope_type="provider_item", provider_item_id=ITEM,
                     from_unit="kg", to_unit="branch", factor_value=Decimal("1.2"))]
        resolved = resolve_rule(rows, from_unit="kg", to_unit="branch",
                                provider_item_id=ITEM)
        self.assertEqual(DIRECTION_DIRECT, resolved["applied_direction"])
        factor, source = choose_conversion(None, resolved)
        self.assertEqual(Decimal("1.2"), factor)
        self.assertEqual(CONVERSION_RULE_FACTOR, source)

    def test_it_does_not_answer_a_different_listing(self):
        rows = [rule(scope_type="provider_item", provider_item_id=ITEM,
                     from_unit="kg", to_unit="branch", factor_value=Decimal("1.2"))]
        self.assertIsNone(resolve_rule(rows, from_unit="kg", to_unit="branch",
                                       provider_item_id=UUID(int=404)))


class InverseConversionTests(unittest.TestCase):
    """Test 4 -- an organization rule branch to kg, asked for kg to branch."""

    ORGANIZATION_RULE = None

    def setUp(self):
        self.rows = [rule(scope_type="organization", from_unit="branch", to_unit="kg",
                          factor_value=Decimal("22"))]

    def test_the_inverse_is_one_over_the_stated_factor(self):
        resolved = resolve_rule(self.rows, from_unit="kg", to_unit="branch")
        self.assertIsNotNone(resolved, "reading backwards must not drop the rule")
        self.assertEqual(DIRECTION_REVERSE, resolved["applied_direction"])
        factor, source = choose_conversion(None, resolved)
        self.assertEqual(Decimal(1) / Decimal(22), factor)
        self.assertEqual(CONVERSION_RULE_FACTOR, source)

    def test_the_inverse_carries_no_rounding(self):
        """0.0454545 typed by hand is not the same number, which is why it is computed."""
        factor, _source = choose_conversion(
            None, resolve_rule(self.rows, from_unit="kg", to_unit="branch"))
        self.assertEqual(Decimal("22"), Decimal(1) / factor)

    def test_what_the_person_wrote_is_still_readable(self):
        resolved = resolve_rule(self.rows, from_unit="kg", to_unit="branch")
        self.assertEqual(Decimal("22"), resolved["stated_factor_value"])
        self.assertEqual("branch", resolved["stated_from_unit"])
        self.assertEqual("kg", resolved["stated_to_unit"])

    def test_the_stored_row_is_untouched(self):
        resolve_rule(self.rows, from_unit="kg", to_unit="branch")
        self.assertEqual(Decimal("22"), self.rows[0]["factor_value"])
        self.assertNotIn("factor", self.rows[0])


class ListingMeasurementTests(unittest.TestCase):
    """Test 5 -- a listing already weighed keeps pricing from its own measurement.

    `provider_item_unit_factors` really is keyed `factor`. The fix must not reach across
    and rename this one, and a rule must not displace it.
    """

    def test_a_weighed_listing_prices_from_its_own_column(self):
        listing = {"id": UUID(int=7), "factor": Decimal("20")}
        factor, source = choose_conversion(listing, None)
        self.assertEqual(Decimal("20"), factor)
        self.assertEqual(PROVIDER_ITEM_FACTOR, source)

    def test_a_rule_does_not_displace_a_weighing_of_this_product(self):
        listing = {"id": UUID(int=7), "factor": Decimal("20")}
        rows = [rule(from_unit="branch", to_unit="kg", factor_value=Decimal("22"))]
        resolved = resolve_rule(rows, from_unit="branch", to_unit="kg")
        factor, source = choose_conversion(listing, resolved)
        self.assertEqual(Decimal("20"), factor,
                         "the narrow evidence wins; 22 is the broader statement")
        self.assertEqual(PROVIDER_ITEM_FACTOR, source)


class NoUsableFactorTests(unittest.TestCase):
    def test_a_rule_stating_no_factor_is_absent_rather_than_zero(self):
        rows = [rule(from_unit="kg", to_unit="branch", factor_value=None)]
        factor, source = choose_conversion(
            None, resolve_rule(rows, from_unit="kg", to_unit="branch"))
        self.assertIsNone(factor)
        self.assertIsNone(source)

    def test_a_zero_factor_is_not_a_price_of_nothing(self):
        rows = [rule(from_unit="kg", to_unit="branch", factor_value=Decimal("0"))]
        factor, _source = choose_conversion(
            None, resolve_rule(rows, from_unit="kg", to_unit="branch"))
        self.assertIsNone(factor)

    def test_an_unapproved_rule_never_prices(self):
        rows = [rule(from_unit="kg", to_unit="branch", factor_value=Decimal("1.2"),
                     status="draft")]
        self.assertIsNone(resolve_rule(rows, from_unit="kg", to_unit="branch"))


if __name__ == "__main__":
    unittest.main()
