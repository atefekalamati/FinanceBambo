# -*- coding: utf-8 -*-
"""Which rule wins, and which rule may not be written.

The precedence order is stated in one place and tested here, because a precedence that is
only implied by a query's ORDER BY is a decision nobody can find.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.conversion_rules import (SCOPE_PRECEDENCE, ConversionRuleRefused,
                                                 crosses_dimensions, resolve_rule,
                                                 validate_scope)

ITEM = "11111111-1111-4111-8111-111111111111"
PROVIDER = "22222222-2222-4222-8222-222222222222"


def rule(scope, **over):
    return dict({"id": "rule-" + scope, "scope_type": scope, "status": "approved",
                 "from_unit": "branch", "to_unit": "kg", "factor_value": "22",
                 "conversion_method": "factor", "version": 1,
                 "effective_from": date(2026, 1, 1), "effective_to": None,
                 "project_id": None, "provider_id": None, "provider_item_id": None,
                 "category": None}, **over)


class ScopeSafetyTests(unittest.TestCase):
    def test_31_a_global_branch_to_kilogram_rule_is_refused(self):
        # A branch weight is a property of one product. Written once and believed
        # everywhere, it is right for one size of angle and wrong for the next.
        for scope in ("global", "organization", "project", "category", "provider"):
            with self.assertRaises(ConversionRuleRefused) as caught:
                validate_scope(scope_type=scope, from_unit="branch", to_unit="kg",
                               project_id="terrace", provider_id=PROVIDER, category="angle")
            self.assertEqual("FINANCE_CONVERSION_SCOPE_TOO_BROAD", caught.exception.code)
            self.assertIn("محصول", caught.exception.message_fa)

    def test_31b_the_same_rule_is_allowed_against_one_listing(self):
        self.assertTrue(validate_scope(scope_type="provider_item", from_unit="branch",
                                       to_unit="kg", provider_item_id=ITEM))

    def test_32_a_global_kilogram_to_tonne_rule_is_allowed_and_reusable(self):
        # A fact about units, true on every project that will ever run.
        self.assertTrue(validate_scope(scope_type="global", from_unit="kg", to_unit="ton"))
        self.assertTrue(validate_scope(scope_type="organization", from_unit="ton", to_unit="kg"))

    def test_which_crossings_count_as_product_dependent(self):
        self.assertFalse(crosses_dimensions("kg", "ton"))
        self.assertFalse(crosses_dimensions("mm", "m"))
        self.assertFalse(crosses_dimensions("liter", "m3"))
        self.assertTrue(crosses_dimensions("branch", "kg"))
        self.assertTrue(crosses_dimensions("each", "m2"))
        self.assertTrue(crosses_dimensions("bag", "kg"))

    def test_a_unit_outside_the_registry_is_refused(self):
        with self.assertRaises(ConversionRuleRefused) as caught:
            validate_scope(scope_type="global", from_unit="گونی", to_unit="kg")
        self.assertEqual("FINANCE_CONVERSION_UNIT_UNKNOWN", caught.exception.code)

    def test_a_rule_that_crosses_nothing_is_refused(self):
        with self.assertRaises(ConversionRuleRefused) as caught:
            validate_scope(scope_type="global", from_unit="kg", to_unit="kg")
        self.assertEqual("FINANCE_CONVERSION_UNITS_EQUAL", caught.exception.code)

    def test_a_scope_that_names_nothing_is_refused(self):
        for scope, kwargs in (("project", {}), ("provider", {}), ("category", {}),
                              ("provider_item", {})):
            with self.assertRaises(ConversionRuleRefused) as caught:
                validate_scope(scope_type=scope, from_unit="kg", to_unit="ton", **kwargs)
            self.assertEqual("FINANCE_CONVERSION_SCOPE_INCOMPLETE", caught.exception.code)


class PrecedenceTests(unittest.TestCase):
    def test_the_documented_order_is_most_specific_first(self):
        self.assertEqual(("provider_item", "provider_category", "category", "provider",
                          "project", "organization", "global"), SCOPE_PRECEDENCE)

    def test_30_a_more_specific_rule_overrides_a_broader_one(self):
        rules = [rule("global", from_unit="kg", to_unit="ton", factor_value="1000"),
                 rule("project", from_unit="kg", to_unit="ton", project_id="terrace",
                      factor_value="999"),
                 rule("provider_item", from_unit="kg", to_unit="ton",
                      provider_item_id=ITEM, factor_value="1")]
        chosen = resolve_rule(rules, from_unit="kg", to_unit="ton", provider_item_id=ITEM)
        self.assertEqual("rule-provider_item", chosen["id"])

    def test_a_broader_rule_is_used_when_no_narrow_one_applies(self):
        rules = [rule("global", from_unit="kg", to_unit="ton", factor_value="1000"),
                 rule("provider_item", from_unit="kg", to_unit="ton",
                      provider_item_id="another-listing")]
        chosen = resolve_rule(rules, from_unit="kg", to_unit="ton", provider_item_id=ITEM)
        self.assertEqual("rule-global", chosen["id"])

    def test_a_provider_rule_naming_a_category_outranks_the_category_alone(self):
        rules = [rule("category", from_unit="kg", to_unit="ton", category="angle"),
                 rule("provider", from_unit="kg", to_unit="ton", provider_id=PROVIDER,
                      category="angle")]
        chosen = resolve_rule(rules, from_unit="kg", to_unit="ton",
                              provider_id=PROVIDER, category="angle")
        self.assertEqual("rule-provider", chosen["id"])

    def test_26_a_draft_rule_is_never_applied(self):
        rules = [rule("provider_item", provider_item_id=ITEM, status="draft")]
        self.assertIsNone(resolve_rule(rules, from_unit="branch", to_unit="kg",
                                       provider_item_id=ITEM))

    def test_a_rejected_rule_is_never_applied(self):
        rules = [rule("provider_item", provider_item_id=ITEM, status="rejected")]
        self.assertIsNone(resolve_rule(rules, from_unit="branch", to_unit="kg",
                                       provider_item_id=ITEM))

    def test_27_an_approved_active_rule_is_applied(self):
        rules = [rule("provider_item", provider_item_id=ITEM)]
        self.assertIsNotNone(resolve_rule(rules, from_unit="branch", to_unit="kg",
                                          provider_item_id=ITEM))

    def test_28_a_superseded_rule_is_not_chosen_for_a_new_calculation(self):
        rules = [rule("provider_item", provider_item_id=ITEM,
                      effective_to=date(2026, 6, 1), id="old"),
                 rule("provider_item", provider_item_id=ITEM, id="new")]
        chosen = resolve_rule(rules, from_unit="branch", to_unit="kg", provider_item_id=ITEM)
        self.assertEqual("new", chosen["id"])

    def test_29_a_past_calculation_still_resolves_to_the_rule_that_made_it(self):
        # What a report issued in March was priced on is still answerable in September.
        rules = [rule("provider_item", provider_item_id=ITEM, id="old",
                      effective_from=date(2026, 1, 1), effective_to=date(2026, 6, 1)),
                 rule("provider_item", provider_item_id=ITEM, id="new",
                      effective_from=date(2026, 6, 1))]
        chosen = resolve_rule(rules, from_unit="branch", to_unit="kg",
                              provider_item_id=ITEM, on_date=date(2026, 3, 1))
        self.assertEqual("old", chosen["id"])

    def test_a_rule_for_another_unit_pair_is_not_borrowed(self):
        rules = [rule("provider_item", provider_item_id=ITEM, from_unit="bag", to_unit="kg")]
        self.assertIsNone(resolve_rule(rules, from_unit="branch", to_unit="kg",
                                       provider_item_id=ITEM))

    def test_a_rule_for_another_listing_is_not_borrowed(self):
        rules = [rule("provider_item", provider_item_id="somebody-elses-listing")]
        self.assertIsNone(resolve_rule(rules, from_unit="branch", to_unit="kg",
                                       provider_item_id=ITEM))

    def test_nothing_approved_means_no_rule_rather_than_a_default(self):
        self.assertIsNone(resolve_rule([], from_unit="branch", to_unit="kg"))
        self.assertIsNone(resolve_rule(None, from_unit="branch", to_unit="kg"))


if __name__ == "__main__":
    unittest.main()
