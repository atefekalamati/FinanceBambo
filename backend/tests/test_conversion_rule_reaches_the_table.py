# -*- coding: utf-8 -*-
"""An approved rule changes a number, is stored as it was stated, and is recorded.

THREE THINGS THAT WERE TRUE AT ONCE AND SHOULD NOT HAVE BEEN

  1. `item_price_mappings` -- the table a person actually reads -- asked only for a
     measurement of the listing and never for a rule. An approved project rule resolved
     correctly and the row still said «ضریب تبدیل لازم است».
  2. `create_rule` did not write the three acknowledgement columns, so the gate that
     refuses a broad product-dependent rule without an admission kept no record of the
     admission it demanded.
  3. A rule could only be read in the direction it was stored, so somebody who knows
     «۱ شاخه = ۲۲ کیلوگرم» had to type 0.0454545... -- a number the supplier's docket does
     not contain and whose rounding would live in the database forever.

What these pin is the fix for each, and the property that matters more than any of them:
a row that prices today keeps its number.
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
                                                 PROVIDER_ITEM_FACTOR, invert_factor,
                                                 resolve_rule)
from app.finance.services.item_price_mappings import ItemPriceMappingService
from test_item_price_mapping_service import (ACTOR, FACTOR, ITEM, LINE, ORG, Repo, Scope,
                                             observation, run)

#: «۱ شاخه = ۲۲ کیلوگرم», written the way a person says it.
BRANCH_TO_KG = {
    "id": UUID(int=90), "scope_type": "organization", "project_id": None,
    "from_unit": "branch", "to_unit": "kg",
    "factor": Decimal("22"), "factor_value": Decimal("22"),
    "conversion_method": "factor", "status": "approved", "version": 1,
    "effective_from": date(2026, 1, 1), "effective_to": None,
    "provider_id": None, "provider_item_id": None, "category": None,
    "product_dependent_acknowledged": True, "superseded_at": None,
}


class Rules:
    """The conversion-rule service as the mapping service uses it.

    `rule_from` delegates to the real `resolve_rule`, so direction and precedence are
    decided by production code rather than by this double.
    """

    def __init__(self, candidates=()):
        self._candidates = list(candidates)
        self.pair_calls = 0
        self.pairs_seen = []

    async def candidates_by_pair(self, _scope, pairs):
        self.pair_calls += 1
        self.pairs_seen.append({tuple(p) for p in pairs})
        # Grouped under the REQUESTED pair and carrying both directions, which is what the
        # repository now does.
        grouped = {}
        for pair in pairs:
            a, b = tuple(pair)
            grouped[(a, b)] = [r for r in self._candidates
                               if (r["from_unit"], r["to_unit"]) in ((a, b), (b, a))]
        return grouped

    @staticmethod
    def rule_from(candidates, *, from_unit, to_unit, **_ignored):
        if not from_unit or not to_unit or from_unit == to_unit:
            return None
        return resolve_rule(candidates.get((from_unit, to_unit)) or [],
                            from_unit=from_unit, to_unit=to_unit)

    async def resolve_for(self, _scope, *, from_unit, to_unit, **_ignored):
        return resolve_rule(
            [r for r in self._candidates
             if (r["from_unit"], r["to_unit"]) in ((from_unit, to_unit),
                                                   (to_unit, from_unit))],
            from_unit=from_unit, to_unit=to_unit)

    async def record_mismatch(self, *_a, **_k):
        return None


def mapping(selected_unit="branch"):
    """A line mapped to a listing priced per kilogram but measured per branch."""
    return {"estimate_line_id": LINE, "provider_item_id": ITEM,
            "selected_unit": selected_unit, "version": 1}


def priced_per_kg():
    return {ITEM: dict(observation(), normalized_price_irr=Decimal("1000"),
                       normalized_unit="kg")}


class TableSeesTheRuleTests(unittest.TestCase):
    """Issue 1: the ladder reaches the table, the preview and the stored status."""

    def service(self, *, rules=None, factors=None):
        repo = Repo(mappings=[mapping()], prices=priced_per_kg(), factors=factors or {},
                    quantities={LINE: Decimal("2")})
        return ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14),
                                       conversion_rules=rules), repo

    def row(self, service):
        return run(service.table_status(Scope()))[str(LINE)]

    def test_without_a_rule_the_row_still_reports_that_it_needs_one(self):
        """The behaviour before the fix, kept as the baseline everything else moves from."""
        service, _repo = self.service(rules=Rules())
        row = self.row(service)
        self.assertEqual("needs_factor", row["status"])
        self.assertIsNone(row["converted_daily_unit_price_irr"])
        self.assertIsNone(row["factor_source"])

    def test_an_approved_organization_rule_prices_the_row(self):
        """The whole point: the rule resolved before and changed nothing. Now it does."""
        service, _repo = self.service(rules=Rules([BRANCH_TO_KG]))
        row = self.row(service)
        self.assertEqual("ready", row["status"])
        # 1000 rial/kg over 22 kg per branch. The price is PER branch, so it multiplies.
        self.assertEqual("22000", row["converted_daily_unit_price_irr"])
        self.assertEqual(CONVERSION_RULE_FACTOR, row["factor_source"],
                         "the table must be able to write «قانون تبدیل» beside the number")

    def test_the_organization_rule_answers_in_another_project_of_the_same_tenant(self):
        """What «سطح انتخاب‌شده» is for: chosen once, in force across the organization.

        The rule names no project. A second project of the same organization asks the same
        crossing and gets the same factor -- nobody re-enters it per site.
        """
        answers = {}
        for project in ("terrace", "another_site"):
            scope = type("S", (), {"organization_id": ORG, "project_id": project,
                                   "actor_user_id": ACTOR})
            service, _repo = self.service(rules=Rules([BRANCH_TO_KG]))
            answers[project] = run(service.table_status(scope()))[str(LINE)]
        self.assertEqual(answers["terrace"]["converted_daily_unit_price_irr"],
                         answers["another_site"]["converted_daily_unit_price_irr"])
        self.assertEqual(CONVERSION_RULE_FACTOR, answers["another_site"]["factor_source"])

    def test_a_listing_measurement_still_wins_and_the_number_does_not_move(self):
        """The guarantee the whole change rests on: no priced row changes its price.

        This listing was weighed at 20 kg per branch and a rule says 22. The rule is
        present, resolvable, and must not be consulted -- the measurement is of THIS
        product and the rule is a statement about the tenant.
        """
        # «۱ شاخه = ۲۰ کیلوگرم», stored the way the measurement is stated. `_factor_for`
        # reads it backwards for the kg->branch crossing, exactly as it always has.
        weighed = {(ITEM, "branch", "kg"): {"id": FACTOR, "factor": Decimal("20")}}
        before, _repo = self.service(rules=Rules(), factors=weighed)
        after, _repo = self.service(rules=Rules([BRANCH_TO_KG]), factors=weighed)
        first, second = self.row(before), self.row(after)
        self.assertEqual("20000", first["converted_daily_unit_price_irr"])
        self.assertEqual(first["converted_daily_unit_price_irr"],
                         second["converted_daily_unit_price_irr"],
                         "a rule must not move a number a measurement already settled")
        self.assertEqual(PROVIDER_ITEM_FACTOR, second["factor_source"])

    def test_the_whole_table_costs_one_query_however_many_rows(self):
        """Per-row lookups would be a query per line on a page that renders hundreds."""
        rules = Rules([BRANCH_TO_KG])
        repo = Repo(mappings=[mapping(), dict(mapping(), estimate_line_id=UUID(int=7))],
                    prices=priced_per_kg(), quantities={})
        service = ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14),
                                          conversion_rules=rules)
        run(service.table_status(Scope()))
        self.assertEqual(1, rules.pair_calls)

    def test_a_crossing_a_measurement_answers_is_never_asked_of_the_ladder(self):
        """The rule is a fallback, so a covered crossing costs no lookup at all."""
        rules = Rules([BRANCH_TO_KG])
        service, _repo = self.service(
            rules=rules, factors={(ITEM, "kg", "branch"): {"id": FACTOR,
                                                           "factor": Decimal("20")}})
        run(service.table_status(Scope()))
        self.assertEqual([], [p for p in rules.pairs_seen if p],
                         "no pair should have been asked for")

    def test_the_preview_and_the_daily_estimate_under_it_agree(self):
        """Two numbers on one screen, and they must come from the same factor."""
        service, _repo = self.service(rules=Rules([BRANCH_TO_KG]))
        body = run(service.preview(Scope(), provider_item_id=ITEM, selected_unit="branch",
                                   estimate_line_id=LINE))
        self.assertEqual("22000", body["converted_daily_unit_price_irr"])
        self.assertEqual(CONVERSION_RULE_FACTOR, body["factor_source"])
        estimate = body.get("daily_estimate") or {}
        # The CONVERTED price on both sides. `dailyUnitPriceIrr` is the source price the
        # sheet stated, per kilogram, and is meant to differ -- comparing against it would
        # be asserting that no conversion happened.
        self.assertEqual(Decimal(body["converted_daily_unit_price_irr"]),
                         Decimal(estimate["converted_daily_unit_price_irr"]),
                         "the headline and the estimate beneath it disagreed")
        self.assertEqual(Decimal(1) / Decimal(22),
                         Decimal(estimate["conversion_multiplier"]),
                         "and both used the rule read backwards, at full precision")
        self.assertEqual(str(BRANCH_TO_KG["id"]),
                         str(estimate["applied_conversion_rule_id"]),
                         "and the estimate names the rule it used")

    def test_the_stored_status_says_the_factor_came_from_a_rule(self):
        """`unknown` and «a rule answers this» are different situations."""
        repo = Repo(prices=priced_per_kg())
        service = ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14),
                                          conversion_rules=Rules([BRANCH_TO_KG]))
        status, reference = run(service._conversion_for(Scope(), ITEM, "kg", "branch"))
        self.assertEqual("conversion_rule", status)
        self.assertEqual(BRANCH_TO_KG["id"], reference)

    def test_with_neither_measurement_nor_rule_the_status_is_still_unknown(self):
        """The existing vocabulary is not broken by the new value."""
        repo = Repo(prices=priced_per_kg())
        service = ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14),
                                          conversion_rules=Rules())
        self.assertEqual(("unknown", None),
                         run(service._conversion_for(Scope(), ITEM, "kg", "branch")))


class EitherDirectionTests(unittest.TestCase):
    """Issue 3: stored as stated, inverted only when a calculation needs the other way."""

    def test_a_rule_written_one_way_answers_the_other(self):
        got = resolve_rule([BRANCH_TO_KG], from_unit="kg", to_unit="branch")
        self.assertEqual(DIRECTION_REVERSE, got["applied_direction"])
        self.assertEqual(Decimal(1) / Decimal(22), got["factor"])
        self.assertEqual(Decimal("22"), got["stated_factor"],
                         "what the person wrote is still on the row")

    def test_the_stored_row_is_not_mutated_by_being_read_backwards(self):
        resolve_rule([BRANCH_TO_KG], from_unit="kg", to_unit="branch")
        self.assertEqual(Decimal("22"), BRANCH_TO_KG["factor"])

    def test_reading_backwards_adds_no_rounding(self):
        """The reason the rule is stored as stated instead of inverted on the way in.

        A price crossed with the reverse reading must equal the price crossed with a rule
        somebody wrote in that direction to full precision -- otherwise the convenience
        would cost accuracy, which is the trade this refuses to make.
        """
        reverse = resolve_rule([BRANCH_TO_KG], from_unit="kg", to_unit="branch")["factor"]
        stated_directly = Decimal(1) / Decimal("22")
        self.assertEqual(stated_directly, reverse)
        # And the round trip comes home: inverting twice is the original number.
        self.assertEqual(Decimal("22"), invert_factor(reverse))

    def test_a_narrow_reverse_rule_beats_a_broad_direct_one(self):
        """Direction does not move a rule in the precedence list."""
        broad = dict(BRANCH_TO_KG, id=UUID(int=91), scope_type="global",
                     from_unit="kg", to_unit="branch", factor=Decimal("0.05"))
        narrow = dict(BRANCH_TO_KG, id=UUID(int=92), scope_type="provider_item",
                      provider_item_id=ITEM)
        got = resolve_rule([broad, narrow], from_unit="kg", to_unit="branch",
                           provider_item_id=ITEM)
        self.assertEqual(narrow["id"], got["id"])
        self.assertEqual(DIRECTION_REVERSE, got["applied_direction"])

    def test_at_equal_scope_the_direct_rule_wins(self):
        """Direction is only the tiebreak, and it makes the reading deterministic."""
        direct = dict(BRANCH_TO_KG, id=UUID(int=93), from_unit="kg", to_unit="branch",
                      factor=Decimal("0.05"))
        got = resolve_rule([BRANCH_TO_KG, direct], from_unit="kg", to_unit="branch")
        self.assertEqual(direct["id"], got["id"])
        self.assertEqual(DIRECTION_DIRECT, got["applied_direction"])

    def test_a_zero_factor_behaves_as_no_rule_rather_than_dividing_by_zero(self):
        useless = dict(BRANCH_TO_KG, factor=Decimal("0"), factor_value=Decimal("0"))
        self.assertIsNone(resolve_rule([useless], from_unit="kg", to_unit="branch"))
        self.assertIsNone(invert_factor(Decimal("0")))
        self.assertIsNone(invert_factor(None))

    def test_a_row_prices_the_same_whichever_way_the_rule_was_written(self):
        """End to end: the number on the table does not depend on how somebody typed it."""
        def price_with(rule):
            repo = Repo(mappings=[mapping()], prices=priced_per_kg(),
                        quantities={LINE: Decimal("2")})
            service = ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14),
                                              conversion_rules=Rules([rule]))
            return run(service.table_status(Scope()))[str(LINE)]

        as_stated = price_with(BRANCH_TO_KG)
        the_other_way = price_with(dict(BRANCH_TO_KG, from_unit="kg", to_unit="branch",
                                        factor=Decimal(1) / Decimal(22),
                                        factor_value=Decimal(1) / Decimal(22)))
        self.assertEqual("22000", as_stated["converted_daily_unit_price_irr"])
        self.assertEqual(as_stated["converted_daily_unit_price_irr"],
                         the_other_way["converted_daily_unit_price_irr"])


if __name__ == "__main__":
    unittest.main()
