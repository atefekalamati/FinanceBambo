# -*- coding: utf-8 -*-
"""The manual route to a daily price, when the imported files do not supply one.

WHAT WAS BLOCKED

`item_price_components` read conversion factors from exactly one place --
`provider_item_unit_factors`, a measurement recorded against one listing.
`finance_unit_conversion_rules`, with its seven scopes, approval, history and precedence,
was never consulted on that path at all. So an approved project-level rule saying exactly
how to cross two units changed nothing about the number anybody saw, and the row kept
reporting «ضریب تبدیل لازم است».

On the audited project that is 832 of 835 estimate lines with no component of their own,
against a price sheet that states a unit for 311 of 1,735 listings. The manual route
existed in the database and was invisible to the code that prices.

WHAT THESE PIN

  * The rule is a FALLBACK. A listing's own measurement still wins, so no row that prices
    today changes its number -- the rule is reached only where `needs_factor` was the
    answer before.
  * Both pricing paths use one precedence, so a row cannot cost one thing on the table and
    another in the panel.
  * A draft rule changes nothing, because approval is what lets a number into a report.
  * The answer says WHERE the factor came from. A weighing of this product and a rule for
    a whole category are worth different amounts of trust and must not share a column
    silently.
"""

import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.conversion_rules import choose_conversion
from app.finance.services.item_price_components import ItemPriceComponentService
from test_item_price_component_service import (ACTOR, COMPONENT, LINE, REBAR, Repo,
                                               component)

#: `factor_value` only: that is the column the rules table has, so it is the only key a
#: row from the repository arrives with. Carrying `factor` beside it here is what let a
#: domain reading the wrong key pass this file while pricing nothing against real data.
PROJECT_RULE = {
    "id": UUID(int=90), "scope_type": "project", "project_id": "p1",
    "from_unit": "kg", "to_unit": "branch",
    "factor_value": Decimal("22"), "conversion_method": "factor",
    "status": "approved", "version": 1, "effective_from": date(2026, 1, 1),
    "effective_to": None, "provider_id": None, "provider_item_id": None,
    "category": None, "product_dependent_acknowledged": True,
}


class Rules:
    """The conversion-rule service, as the components service uses it."""

    def __init__(self, candidates=()):
        self._candidates = list(candidates)
        self.pair_calls = 0

    async def candidates_by_pair(self, _scope, pairs):
        self.pair_calls += 1
        grouped = {}
        for rule in self._candidates:
            grouped.setdefault((rule["from_unit"], rule["to_unit"]), []).append(rule)
        return {pair: grouped.get(tuple(pair), []) for pair in pairs}

    @staticmethod
    def rule_from(candidates, *, from_unit, to_unit, **_ignored):
        from app.finance.domain.conversion_rules import resolve_rule
        if not from_unit or not to_unit or from_unit == to_unit:
            return None
        return resolve_rule(candidates.get((from_unit, to_unit)) or [],
                            from_unit=from_unit, to_unit=to_unit)


def priced_in_branches(**over):
    """A rebar component consumed per branch, priced per kilogram: a real crossing."""
    return component(REBAR, "branch", "3", "total_quantity", **over)


OBSERVATION = {REBAR: {"normalized_price_irr": Decimal("1000"), "normalized_unit": "kg",
                       "provider_name": "فولاد مشهد", "external_name": "میلگرد ۱۴",
                       "category": "rebar", "provider_id": UUID(int=3)}}


class FallbackTests(unittest.IsolatedAsyncioTestCase):
    def service(self, *, rules=None, factors=None):
        repo = Repo(components=[priced_in_branches()], prices=OBSERVATION,
                    factors=factors or {})
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15),
                                         conversion_rules=rules), repo

    async def test_an_approved_project_rule_prices_a_row_that_used_to_refuse(self):
        """The whole point. Today this row answers `needs_factor`."""
        without, _ = self.service()
        blocked = (await without.table_status(object()))[str(LINE)]
        self.assertEqual("needs_factor", blocked["status"])

        service, _ = self.service(rules=Rules([PROJECT_RULE]))
        row = (await service.table_status(object()))[str(LINE)]
        self.assertEqual("ready", row["status"])
        self.assertIsNotNone(row["daily_item_cost_irr"])

    async def test_a_listing_measurement_wins_over_a_rule(self):
        """A weighing of THIS product beats a statement about its category."""
        measured = {(REBAR, "kg", "branch"): {"id": UUID(int=5), "factor": Decimal("11")}}
        both, _ = self.service(rules=Rules([PROJECT_RULE]), factors=measured)
        rule_only, _ = self.service(rules=Rules([PROJECT_RULE]))
        from_measurement = (await both.table_status(object()))[str(LINE)]
        from_rule = (await rule_only.table_status(object()))[str(LINE)]
        self.assertEqual("provider_item", from_measurement["factor_source"])
        self.assertEqual("conversion_rule", from_rule["factor_source"])
        self.assertNotEqual(from_measurement["daily_item_cost_irr"],
                            from_rule["daily_item_cost_irr"],
                            "11 and 22 are different measurements and must not agree")

    async def test_a_draft_rule_changes_nothing(self):
        """Approval is what lets a number into a report."""
        draft = dict(PROJECT_RULE, status="draft")
        service, _ = self.service(rules=Rules([draft]))
        row = (await service.table_status(object()))[str(LINE)]
        self.assertEqual("needs_factor", row["status"])

    async def test_a_rule_for_another_crossing_is_not_used(self):
        elsewhere = dict(PROJECT_RULE, from_unit="m", to_unit="m2")
        service, _ = self.service(rules=Rules([elsewhere]))
        self.assertEqual("needs_factor",
                         (await service.table_status(object()))[str(LINE)]["status"])

    async def test_a_row_that_prices_today_is_untouched(self):
        """Same dimension: the registry answers, and no rule is consulted."""
        repo = Repo(components=[component(REBAR, "ton", "2", "total_quantity")],
                    prices=OBSERVATION)
        plain = ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15))
        rules = Rules([PROJECT_RULE])
        withrules = ItemPriceComponentService(
            Repo(components=[component(REBAR, "ton", "2", "total_quantity")],
                 prices=OBSERVATION), clock=lambda: date(2026, 9, 15),
            conversion_rules=rules)
        before = (await plain.table_status(object()))[str(LINE)]
        after = (await withrules.table_status(object()))[str(LINE)]
        self.assertEqual(before["daily_item_cost_irr"], after["daily_item_cost_irr"])
        self.assertEqual("registry", after["factor_source"],
                         "the registry crossed it; no rule was involved")


class QueryCountTests(unittest.IsolatedAsyncioTestCase):
    """One request must not become one query per row."""

    async def test_many_rows_cost_one_rule_lookup(self):
        components = [priced_in_branches(component_id=UUID(int=200 + n),
                                         line=UUID(int=300 + n))
                      for n in range(40)]
        quantities = {UUID(int=300 + n): Decimal("500") for n in range(40)}
        rules = Rules([PROJECT_RULE])
        service = ItemPriceComponentService(
            Repo(components=components, prices=OBSERVATION, quantities=quantities),
            clock=lambda: date(2026, 9, 15), conversion_rules=rules)
        answers = await service.table_status(object())
        self.assertEqual(40, len(answers))
        self.assertEqual(1, rules.pair_calls,
                         "40 rows and one lookup; a call per row is the N+1 this avoids")

    async def test_a_project_with_nothing_to_cross_asks_nothing(self):
        rules = Rules([PROJECT_RULE])
        service = ItemPriceComponentService(
            Repo(components=[component(REBAR, "kg", "80", "per_msp_unit")],
                 prices=OBSERVATION),
            clock=lambda: date(2026, 9, 15), conversion_rules=rules)
        await service.table_status(object())
        self.assertEqual(0, rules.pair_calls,
                         "source and selected unit agree; there is nothing to look up")


class PrecedenceTests(unittest.TestCase):
    """The shared chooser both pricing paths call.

    The two arguments are rows of two different tables and are keyed accordingly: a
    listing measurement comes from `provider_item_unit_factors`, whose column is `factor`,
    and a rule from `finance_unit_conversion_rules`, whose column is `factor_value`.
    """

    def test_the_listing_measurement_comes_first(self):
        self.assertEqual((22, "provider_item"),
                         choose_conversion({"factor": 22}, {"factor_value": 25}))

    def test_the_rule_fills_the_gap_behind_it(self):
        self.assertEqual((25, "conversion_rule"),
                         choose_conversion(None, {"factor_value": 25}))

    def test_a_rule_with_no_usable_factor_is_absent_not_zero(self):
        self.assertEqual((None, None), choose_conversion(None, {"factor_value": None}))
        self.assertEqual((None, None), choose_conversion(None, {"factor_value": 0}))

    def test_a_rule_keyed_the_listing_way_does_not_price(self):
        """The bug, stated as a test: `factor` on a rule is not a factor."""
        self.assertEqual((None, None), choose_conversion(None, {"factor": 25}))

    def test_nothing_at_all(self):
        self.assertEqual((None, None), choose_conversion(None, None))


class UnitsOnTheRowTests(unittest.IsolatedAsyncioTestCase):
    """The two units the «ریز برآورد» table shows, and the conversion dialog opens with."""

    async def test_one_component_states_both_units(self):
        service = ItemPriceComponentService(
            Repo(components=[priced_in_branches()], prices=OBSERVATION),
            clock=lambda: date(2026, 9, 15))
        row = (await service.table_status(object()))[str(LINE)]
        self.assertEqual("kg", row["source_price_unit"])
        self.assertEqual("branch", row["selected_unit"])

    async def test_a_line_with_no_component_states_neither(self):
        service = ItemPriceComponentService(
            Repo(components=[], prices={}), clock=lambda: date(2026, 9, 15))
        row = (await service.table_status(object()))[str(LINE)]
        self.assertIsNone(row["source_price_unit"])
        self.assertIsNone(row["selected_unit"])

    async def test_several_components_state_neither(self):
        """Two materials can be priced per kilogram and per metre; neither is 'the' unit."""
        from test_item_price_component_service import PIPE
        prices = dict(OBSERVATION)
        prices[PIPE] = {"normalized_price_irr": Decimal("500"), "normalized_unit": "m",
                        "provider_name": "لوله‌سازی", "external_name": "لوله ۶",
                        "category": "pipe", "provider_id": UUID(int=3)}
        service = ItemPriceComponentService(
            Repo(components=[priced_in_branches(),
                             component(PIPE, "m", "10", "total_quantity",
                                       component_id=UUID(int=99))],
                 prices=prices),
            clock=lambda: date(2026, 9, 15))
        row = (await service.table_status(object()))[str(LINE)]
        self.assertIsNone(row["source_price_unit"])
        self.assertIsNone(row["selected_unit"])
        self.assertIsNotNone(row["source_summary"], "it says how many instead")


if __name__ == "__main__":
    unittest.main()
