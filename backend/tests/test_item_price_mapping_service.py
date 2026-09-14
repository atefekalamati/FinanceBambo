# -*- coding: utf-8 -*-
"""Saving a mapping, and reading a whole table's worth of prices from one.

The database is faked here so every case can be stated exactly -- a listing with no price,
a crossing with an approved factor, a crossing without one -- which is what a real database
makes tedious and a fixture makes vague. The SQL itself is exercised against
`bambo_canonical_test` separately; what these pin is the reasoning.
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

from app.finance.services.item_price_mappings import (ItemPriceMappingRefused,
                                                      ItemPriceMappingService)

ORG = UUID("c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
LINE = UUID("11111111-1111-4111-8111-111111111111")
OTHER_LINE = UUID("22222222-2222-4222-8222-222222222222")
ITEM = UUID("33333333-3333-4333-8333-333333333333")
FACTOR = UUID("44444444-4444-4444-8444-444444444444")
ACTOR = UUID("55555555-5555-4555-8555-555555555555")


class Scope:
    organization_id = ORG
    project_id = "terrace"
    actor_user_id = ACTOR


class Payload:
    def __init__(self, provider_item_id=ITEM, selected_unit="kg", reason="بررسی شد",
                 effective_from=None):
        self.provider_item_id = provider_item_id
        self.selected_unit = selected_unit
        self.reason = reason
        self.effective_from = effective_from


class Repo:
    """Every read the service makes, answerable from plain dicts."""

    #: `context=None` has to mean "there is no such line", and a default argument of None
    #: cannot say that as well as "the caller did not choose" -- so the default is its own
    #: object and None keeps its literal meaning.
    DEFAULT_CONTEXT = {"source_assignment_uid": 9703, "source_task_uid": 1212,
                       "source_resource_uid": 155}
    UNSET = object()

    def __init__(self, *, mappings=(), prices=None, factors=None, quantities=None,
                 listings=(ITEM,), context=UNSET):
        self._mappings = list(mappings)
        self._prices = prices or {}
        self._factors = factors or {}
        self._quantities = quantities or {}
        self._listings = set(listings)
        self._context = dict(self.DEFAULT_CONTEXT) if context is Repo.UNSET else context
        self.appended = []

    async def current_for_project(self, s):
        return list(self._mappings)

    async def latest_prices_for_items(self, s, ids):
        return {i: self._prices[i] for i in ids if i in self._prices}

    async def approved_factors_for_items(self, s, ids):
        return {k: v for k, v in self._factors.items() if k[0] in set(ids)}

    async def line_quantities(self, s):
        return dict(self._quantities)

    async def listing_exists(self, s, provider_item_id):
        return provider_item_id in self._listings

    async def line_context(self, s, line_id):
        return dict(self._context) if self._context is not None else None

    async def append_mapping(self, s, *, estimate_line_id, finance_resource_id, values,
                             created_by):
        self.appended.append(dict(values, estimate_line_id=estimate_line_id,
                                  created_by=created_by))
        return dict(values, id=UUID(int=9), estimate_line_id=estimate_line_id,
                    version=len(self.appended), created_by=created_by)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def observation(price="1014600", unit="kg", **over):
    return dict({"normalized_price_irr": Decimal(price) if price else None,
                 "normalized_unit": unit, "source_unit": unit,
                 "source_currency": "TOMAN", "external_name": "میلگرد ساده ۲۵",
                 "external_id": "REBAR-1", "category": "rebar",
                 "provider_name": "Mashhad Foolad", "source_worksheet": "steel -Rebar",
                 "workflow_date_jalali": "1405/06/23"}, **over)


def mapping(unit="kg", **over):
    return dict({"estimate_line_id": LINE, "provider_item_id": ITEM,
                 "selected_unit": unit, "version": 1, "conversion_factor_id": None},
                **over)


class SavingAMappingTests(unittest.TestCase):
    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14)), repo

    def test_a_mapping_records_the_listing_the_unit_and_who_said_so(self):
        service, repo = self.service(prices={ITEM: observation()})
        run(service.save_mapping(Scope(), estimate_line_id=LINE, payload=Payload(),
                                 actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertEqual(ITEM, saved["provider_item_id"])
        self.assertEqual("kg", saved["selected_unit"])
        self.assertEqual(ACTOR, saved["created_by"])
        self.assertEqual("بررسی شد", saved["reason"])

    def test_the_schedule_identifiers_travel_onto_the_mapping(self):
        # So the mapping stays legible after a re-import issues new database ids.
        service, repo = self.service(prices={ITEM: observation()})
        run(service.save_mapping(Scope(), estimate_line_id=LINE, payload=Payload(),
                                 actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertEqual((9703, 1212, 155), (saved["source_assignment_uid"],
                                             saved["source_task_uid"],
                                             saved["source_resource_uid"]))

    def test_the_price_unit_is_recorded_as_read_at_the_moment_of_mapping(self):
        service, repo = self.service(prices={ITEM: observation(unit="kg")})
        run(service.save_mapping(Scope(), estimate_line_id=LINE, payload=Payload(),
                                 actor_id=ACTOR))
        self.assertEqual("kg", repo.appended[0]["source_price_unit"])
        self.assertEqual("TOMAN", repo.appended[0]["source_price_basis"])

    def test_a_unit_outside_the_registry_is_refused_before_anything_is_written(self):
        service, repo = self.service(prices={ITEM: observation()})
        with self.assertRaises(ItemPriceMappingRefused) as refused:
            run(service.save_mapping(Scope(), estimate_line_id=LINE,
                                     payload=Payload(selected_unit="furlong"),
                                     actor_id=ACTOR))
        self.assertIn("واحد", str(refused.exception))
        self.assertEqual([], repo.appended)

    def test_a_blank_reason_is_refused(self):
        service, repo = self.service(prices={ITEM: observation()})
        with self.assertRaises(ItemPriceMappingRefused):
            run(service.save_mapping(Scope(), estimate_line_id=LINE,
                                     payload=Payload(reason="   "), actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_listing_this_project_does_not_have_is_refused(self):
        service, repo = self.service(listings=())
        with self.assertRaises(ItemPriceMappingRefused) as refused:
            run(service.save_mapping(Scope(), estimate_line_id=LINE, payload=Payload(),
                                     actor_id=ACTOR))
        self.assertIn("قیمت روز", str(refused.exception))
        self.assertEqual([], repo.appended)

    def test_a_line_that_is_not_this_projects_is_refused(self):
        service, repo = self.service(prices={ITEM: observation()}, context=None)
        with self.assertRaises(ItemPriceMappingRefused):
            run(service.save_mapping(Scope(), estimate_line_id=LINE, payload=Payload(),
                                     actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_listing_with_no_price_yet_may_still_be_mapped(self):
        # Which product this is and what it costs today are different facts. The row then
        # reports «بدون قیمت روز» rather than refusing the person's decision.
        service, repo = self.service(prices={})
        run(service.save_mapping(Scope(), estimate_line_id=LINE, payload=Payload(),
                                 actor_id=ACTOR))
        self.assertEqual(1, len(repo.appended))
        self.assertEqual("unknown", repo.appended[0]["conversion_status"])


class TheRecordedConversionStatusTests(unittest.TestCase):
    def save(self, *, price_unit, selected, factors=None):
        repo = Repo(prices={ITEM: observation(unit=price_unit)}, factors=factors or {})
        service = ItemPriceMappingService(repo, clock=lambda: date(2026, 9, 14))
        run(service.save_mapping(Scope(), estimate_line_id=LINE,
                                 payload=Payload(selected_unit=selected), actor_id=ACTOR))
        return repo.appended[0]

    def test_the_same_unit_needs_no_conversion(self):
        self.assertEqual("automatic", self.save(price_unit="kg", selected="kg")["conversion_status"])

    def test_a_same_dimension_crossing_is_automatic(self):
        self.assertEqual("automatic", self.save(price_unit="kg", selected="g")["conversion_status"])

    def test_a_crossing_with_an_approved_factor_names_it(self):
        saved = self.save(price_unit="branch", selected="kg",
                          factors={(ITEM, "branch", "kg"): {"id": FACTOR,
                                                            "factor": Decimal("22")}})
        self.assertEqual("factor", saved["conversion_status"])
        self.assertEqual(FACTOR, saved["conversion_factor_id"])

    def test_a_crossing_with_no_approved_factor_is_unknown_not_refused(self):
        # The mapping is still a true statement about which product this is. The row says
        # «ضریب تبدیل لازم است» until somebody measures it.
        saved = self.save(price_unit="branch", selected="kg")
        self.assertEqual("unknown", saved["conversion_status"])
        self.assertIsNone(saved["conversion_factor_id"])


class ReadingTheWholeTableTests(unittest.TestCase):
    def status(self, **kwargs):
        service = ItemPriceMappingService(Repo(**kwargs))
        return run(service.table_status(Scope()))

    def test_a_ready_line_reports_the_converted_price_and_the_cost(self):
        answers = self.status(mappings=[mapping("kg")],
                              prices={ITEM: observation("1014600", "kg")},
                              quantities={LINE: Decimal("2299")})
        row = answers[str(LINE)]
        self.assertEqual("ready", row["status"])
        self.assertEqual("آماده", row["status_label"])
        self.assertEqual(Decimal("1014600"), Decimal(row["converted_daily_unit_price_irr"]))
        self.assertEqual(Decimal("2332565400"), Decimal(row["daily_item_cost_irr"]))

    def test_an_unmapped_line_is_present_and_asks_for_a_product(self):
        # Absent would be indistinguishable from a line the caller forgot to ask about.
        answers = self.status(mappings=[], quantities={OTHER_LINE: Decimal("5")})
        self.assertIn(str(OTHER_LINE), answers)
        self.assertEqual("needs_product", answers[str(OTHER_LINE)]["status"])
        self.assertEqual("محصول قیمت روز انتخاب نشده", answers[str(OTHER_LINE)]["reason"])

    def test_a_mapped_line_with_no_price_says_so_rather_than_costing_nothing(self):
        answers = self.status(mappings=[mapping("kg")], prices={},
                              quantities={LINE: Decimal("10")})
        row = answers[str(LINE)]
        self.assertEqual("no_price", row["status"])
        self.assertIsNone(row["daily_item_cost_irr"])

    def test_a_crossing_without_a_factor_asks_for_one(self):
        answers = self.status(mappings=[mapping("kg")],
                              prices={ITEM: observation("92560", "branch")},
                              quantities={LINE: Decimal("10")})
        row = answers[str(LINE)]
        self.assertEqual("needs_factor", row["status"])
        self.assertEqual("ضریب تبدیل لازم است", row["reason"])
        self.assertIsNone(row["converted_daily_unit_price_irr"])

    def test_an_approved_factor_prices_the_crossing(self):
        answers = self.status(
            mappings=[mapping("kg")],
            prices={ITEM: observation("92560", "branch")},
            factors={(ITEM, "branch", "kg"): {"id": FACTOR, "factor": Decimal("22")}},
            quantities={LINE: Decimal("100")})
        row = answers[str(LINE)]
        self.assertEqual("ready", row["status"])
        self.assertEqual(Decimal("4207.27272727"),
                         Decimal(row["converted_daily_unit_price_irr"]))

    def test_a_factor_stored_the_other_way_round_is_the_same_measurement(self):
        answers = self.status(
            mappings=[mapping("kg")],
            prices={ITEM: observation("92560", "branch")},
            factors={(ITEM, "kg", "branch"): {"id": FACTOR,
                                              "factor": Decimal("1") / Decimal("22")}},
            quantities={LINE: Decimal("1")})
        self.assertEqual("ready", answers[str(LINE)]["status"])

    def test_the_row_carries_where_the_price_came_from(self):
        answers = self.status(mappings=[mapping("kg")],
                              prices={ITEM: observation()}, quantities={LINE: Decimal("1")})
        row = answers[str(LINE)]
        self.assertEqual("Mashhad Foolad", row["provider_name"])
        self.assertEqual("میلگرد ساده ۲۵", row["product_name"])
        self.assertEqual("1405/06/23", row["workflow_date_jalali"])

    def test_no_row_ever_reports_zero_for_something_unknown(self):
        answers = self.status(
            mappings=[mapping("kg")], prices={},
            quantities={LINE: Decimal("10"), OTHER_LINE: Decimal("4")})
        for row in answers.values():
            with self.subTest(status=row["status"]):
                if row["status"] != "ready":
                    self.assertIsNone(row["daily_item_cost_irr"])
                    self.assertIsNone(row["converted_daily_unit_price_irr"])


if __name__ == "__main__":
    unittest.main()
