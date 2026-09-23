# -*- coding: utf-8 -*-
"""Adding materials to an activity, and pricing the activity from all of them.

The database is faked so every case can be stated exactly -- a component whose product has
no price, one whose units cannot be crossed, one measured per cubic metre beside one
measured as a total. That is what a real database makes tedious and a fixture makes vague.
The SQL is exercised against `bambo_canonical_test` separately; what these pin is the
reasoning.

THE WORKED EXAMPLE, throughout: «کانال‌کنی», 500 m3 of trenching, consuming

    rebar   80 kg per m3 at 1,014,600 rial/kg   -> 40,000 kg -> 40,584,000,000
    pipe    1,200 m in total at 50,000 rial/m   ->  1,200 m  ->     60,000,000
                                                              -----------------
                                                                 40,644,000,000
"""

import asyncio
import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.services.item_price_components import (ItemPriceComponentRefused,
                                                        ItemPriceComponentService)

ORG = UUID("c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
LINE = UUID("11111111-1111-4111-8111-111111111111")
OTHER_LINE = UUID("22222222-2222-4222-8222-222222222222")
REBAR = UUID("33333333-3333-4333-8333-333333333333")
PIPE = UUID("66666666-6666-4666-8666-666666666666")
BRICK = UUID("77777777-7777-4777-8777-777777777777")
FACTOR = UUID("44444444-4444-4444-8444-444444444444")
ACTOR = UUID("55555555-5555-4555-8555-555555555555")
COMPONENT = UUID("88888888-8888-4888-8888-888888888888")


class Scope:
    organization_id = ORG
    project_id = "terrace"
    actor_user_id = ACTOR


class Payload:
    def __init__(self, provider_item_id=REBAR, selected_unit="kg",
                 usage_mode="per_msp_unit", usage_quantity=Decimal("80"),
                 usage_unit=None, product_type=None, reason="بر اساس نقشهٔ اجرایی",
                 effective_from=None):
        self.provider_item_id = provider_item_id
        self.selected_unit = selected_unit
        self.usage_mode = usage_mode
        self.usage_quantity = usage_quantity
        self.usage_unit = usage_unit
        self.product_type = product_type
        self.reason = reason
        self.effective_from = effective_from


class Repo:
    """Every read the service makes, answerable from plain dicts."""

    DEFAULT_CONTEXT = {"id": LINE, "resource_id": UUID(int=7),
                       "activity_external_id": "A-101", "resource_title": "کانال‌کنی",
                       "base_unit": "m3", "msp_unit": "m3", "quantity": Decimal("500"),
                       "msp_cost_irr": Decimal("120000000"),
                       "original_unit_price_irr": Decimal("240000")}
    UNSET = object()

    def __init__(self, *, components=(), prices=None, factors=None, quantities=None,
                 listings=None, context=UNSET, providers=(), product_types=()):
        self._components = list(components)
        self._prices = prices or {}
        self._factors = factors or {}
        self._quantities = {LINE: Decimal("500")} if quantities is None else quantities
        self._listings = {REBAR: {"category": "rebar", "provider_id": UUID(int=3)},
                          PIPE: {"category": "pipe", "provider_id": UUID(int=3)},
                          BRICK: {"category": "brick", "provider_id": UUID(int=4)}} \
            if listings is None else listings
        self._context = dict(self.DEFAULT_CONTEXT) if context is Repo.UNSET else context
        self._providers = list(providers)
        self._product_types = list(product_types)
        self.appended = []
        self.filter_calls = []

    async def live_for_project(self, s):
        return list(self._components)

    async def live_for_line(self, s, line_id):
        return [c for c in self._components if c["estimate_line_id"] == line_id]

    async def history_for_line(self, s, line_id):
        return [c for c in self._components if c["estimate_line_id"] == line_id]

    async def live_component(self, s, line_id, component_id):
        for c in self._components:
            if c["estimate_line_id"] == line_id and c["component_id"] == component_id:
                return dict(c)
        return None

    async def latest_prices_for_items(self, s, ids):
        return {i: self._prices[i] for i in ids if i in self._prices}

    async def approved_factors_for_items(self, s, ids):
        return {k: v for k, v in self._factors.items() if k[0] in set(ids)}

    async def line_quantities(self, s):
        return dict(self._quantities)

    async def resource_prices(self, s, as_of):
        # Default: no line's resource carries a price, which is what every test written
        # before this rung existed assumed. A test that wants one sets `_resource_prices`.
        return dict(getattr(self, "_resource_prices", {}))

    async def line_context(self, s, line_id):
        return dict(self._context) if self._context is not None else None

    async def listing_exists(self, s, provider_item_id):
        listing = self._listings.get(provider_item_id)
        return dict(listing) if listing else None

    async def providers(self, s, category=None):
        self.filter_calls.append(("providers", category))
        return list(self._providers)

    async def product_types(self, s, *, category=None, provider_id=None):
        self.filter_calls.append(("product_types", category, provider_id))
        return list(self._product_types)

    async def append(self, s, *, component_id, estimate_line_id, values, created_by):
        self.appended.append(dict(values, component_id=component_id,
                                  estimate_line_id=estimate_line_id,
                                  created_by=created_by))
        return dict(values, id=UUID(int=9), component_id=component_id,
                    estimate_line_id=estimate_line_id, version=len(self.appended),
                    created_by=created_by)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def observation(price="1014600", unit="kg", **over):
    return dict({"normalized_price_irr": Decimal(price) if price else None,
                 "normalized_unit": unit, "source_unit": unit,
                 "source_currency": "TOMAN", "external_name": "میلگرد ساده ۲۵",
                 "external_id": "REBAR-1", "category": "rebar",
                 "provider_name": "Mashhad Foolad", "source_worksheet": "steel -Rebar",
                 "workflow_date_jalali": "1405/06/23", "metadata": {}}, **over)


def component(item=REBAR, unit="kg", usage="80", mode="per_msp_unit", *,
              component_id=COMPONENT, line=LINE, active=True, **over):
    return dict({"id": UUID(int=1), "component_id": component_id,
                 "estimate_line_id": line, "provider_item_id": item,
                 "selected_unit": unit, "usage_mode": mode,
                 "usage_quantity_decimal": Decimal(usage) if usage is not None else None,
                 "usage_unit": unit, "conversion_status": "automatic",
                 "conversion_factor_id": None, "category": None, "product_type": None,
                 "status": "ready", "reason": "بر اساس نقشه", "active": active,
                 "version": 1, "created_by": ACTOR,
                 "created_at": datetime(2026, 9, 15, 10, 0)}, **over)


class TheRowTotalTests(unittest.TestCase):
    """What the financial-items table shows in the daily-price column."""

    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_a_trench_costs_the_sum_of_its_materials(self):
        # The worked example, end to end. Two materials measured two different ways.
        service, _ = self.service(
            components=[component(REBAR, "kg", "80", "per_msp_unit"),
                        component(PIPE, "m", "1200", "total_quantity",
                                  component_id=UUID(int=2))],
            prices={REBAR: observation("1014600", "kg"),
                    PIPE: observation("50000", "m", external_name="لوله پلی اتیلن")})
        row = run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("ready", row["status"])
        self.assertEqual("40644000000", row["daily_item_cost_irr"])
        self.assertEqual((2, 2, 0), (row["component_count"], row["ready_component_count"],
                                     row["unresolved_component_count"]))

    def test_a_line_nobody_has_priced_is_present_and_says_so(self):
        # Absent would be indistinguishable from a line the caller forgot to ask about.
        service, _ = self.service(components=[])
        row = run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("needs_components", row["status"])
        self.assertEqual("نیازمند افزودن مصالح", row["status_label"])
        self.assertIsNone(row["daily_item_cost_irr"])

    def test_one_unpriced_material_does_not_silently_shrink_the_total(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80", "per_msp_unit"),
                        component(BRICK, "each", "300", "total_quantity",
                                  component_id=UUID(int=2))],
            prices={REBAR: observation("1014600", "kg")})
        row = run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("partially_unresolved", row["status"])
        self.assertEqual("40584000000", row["daily_item_cost_irr"])
        self.assertEqual(1, row["unresolved_component_count"])
        self.assertIn("قیمت روز معتبر وجود ندارد", row["reason"])

    def test_a_row_whose_every_material_is_unpriced_has_no_cost_rather_than_zero(self):
        service, _ = self.service(components=[component(REBAR, "kg", "80")], prices={})
        row = run(service.table_status(Scope()))[str(LINE)]
        self.assertIsNone(row["daily_item_cost_irr"])
        self.assertEqual("no_price", row["status"])

    def test_a_deactivated_material_leaves_the_total(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80", "per_msp_unit"),
                        component(PIPE, "m", "1200", "total_quantity",
                                  component_id=UUID(int=2), active=False)],
            prices={REBAR: observation("1014600", "kg"),
                    PIPE: observation("50000", "m")})
        row = run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("40584000000", row["daily_item_cost_irr"])
        self.assertEqual(1, row["component_count"])

    def test_one_material_names_its_product_and_several_say_how_many(self):
        single, _ = self.service(components=[component(REBAR, "kg", "80")],
                                 prices={REBAR: observation()})
        row = run(single.table_status(Scope()))[str(LINE)]
        self.assertEqual("میلگرد ساده ۲۵", row["product_name"])
        self.assertIsNone(row["source_summary"])

        many, _ = self.service(
            components=[component(REBAR, "kg", "80"),
                        component(PIPE, "m", "1200", "total_quantity",
                                  component_id=UUID(int=2))],
            prices={REBAR: observation(), PIPE: observation("50000", "m")})
        row = run(many.table_status(Scope()))[str(LINE)]
        self.assertIsNone(row["product_name"])
        self.assertIn("چند مصالح", row["source_summary"])

    def test_the_msp_quantity_is_the_schedule_s_own(self):
        # 500 m3 is what makes 80 kg/m3 into 40,000 kg. Change the schedule quantity and
        # the material quantity moves with it -- it is never entered twice.
        service, _ = self.service(components=[component(REBAR, "kg", "80")],
                                  prices={REBAR: observation("1014600", "kg")},
                                  quantities={LINE: Decimal("250")})
        row = run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("20292000000", row["daily_item_cost_irr"])


class ThePanelTests(unittest.TestCase):
    """What the price panel shows when somebody opens a line."""

    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_the_header_names_the_activity_being_priced(self):
        service, _ = self.service(components=[])
        body = run(service.components_for_line(Scope(), LINE))
        self.assertEqual("کانال‌کنی", body["line"]["title"])
        self.assertEqual("m3", body["line"]["msp_unit"])
        self.assertEqual("500", body["line"]["msp_quantity"])

    def test_each_component_reports_its_own_quantity_and_cost(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80", "per_msp_unit"),
                        component(PIPE, "m", "1200", "total_quantity",
                                  component_id=UUID(int=2))],
            prices={REBAR: observation("1014600", "kg"),
                    PIPE: observation("50000", "m")})
        body = run(service.components_for_line(Scope(), LINE))
        rebar, pipe = body["components"]
        self.assertEqual(("40000", "40584000000"),
                         (rebar["component_quantity"], rebar["component_daily_cost_irr"]))
        self.assertEqual(("1200", "60000000"),
                         (pipe["component_quantity"], pipe["component_daily_cost_irr"]))
        self.assertEqual("40644000000", body["total"]["daily_item_cost_irr"])

    def test_the_author_s_reason_is_not_replaced_by_the_pricing_reason(self):
        # Two different sentences: why this material, and why there is no number.
        service, _ = self.service(components=[component(REBAR, "kg", "80")], prices={})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("بر اساس نقشه", row["reason_text"])
        self.assertEqual("قیمت روز معتبر وجود ندارد", row["reason"])

    def test_an_inactive_component_travels_but_does_not_count(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80", active=False)],
            prices={REBAR: observation("1014600", "kg")})
        body = run(service.components_for_line(Scope(), LINE))
        self.assertEqual(1, len(body["components"]))
        self.assertFalse(body["components"][0]["active"])
        self.assertEqual("needs_components", body["total"]["status"])

    def test_a_label_supplies_the_source_unit_the_worksheet_never_stated(self):
        """The prices page has always asked the label first; this did not, and that was a
        second vocabulary. On the audited project the worksheet states a unit for rebar
        (311 of 311) and for NOTHING else -- 0 of 992 pipes, 0 of 210 bricks, 0 of 89
        ibeams -- so for most of the catalogue a person's label is the only thing that can
        say what a price is per. Without this the financial-items row reported «واحد قیمت
        مبدأ مشخص نیست» beside a prices page that had resolved the very same listing.
        """
        service, _ = self.service(
            components=[component(REBAR, "branch", "3", "total_quantity")],
            prices={REBAR: observation("22000000", None, source_unit=None,
                                       label_source_unit="branch")})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("branch", row["source_unit"])
        self.assertEqual("ready", row["status"])
        self.assertEqual("66000000", row["component_daily_cost_irr"])

    def test_a_label_outranks_the_sheet_because_somebody_looked_at_this_product(self):
        service, _ = self.service(
            components=[component(REBAR, "branch", "1", "total_quantity")],
            prices={REBAR: observation("22000000", "kg", label_source_unit="branch")})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("branch", row["source_unit"])

    def test_the_source_unit_is_read_through_the_sheet_s_own_spelling(self):
        # The sheet writes «کیلو», not `kg`, and a price stated in a spelling this system
        # cannot name would otherwise report «واحد قیمت مبدأ مشخص نیست» beside a listing
        # that plainly said کیلو.
        service, _ = self.service(
            components=[component(REBAR, "kg", "80")],
            prices={REBAR: observation("1014600", None, source_unit="کیلو")})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("kg", row["source_unit"])
        self.assertEqual("ready", row["status"])


class ConversionTests(unittest.TestCase):
    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_a_registry_crossing_needs_nobody_s_approval(self):
        # Tonne to kilogram is a fact about units, true on every project.
        service, _ = self.service(
            components=[component(REBAR, "kg", "80")],
            prices={REBAR: observation("1014600000", "ton")})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("ready", row["status"])
        self.assertEqual("1014600", row["converted_daily_unit_price_irr"])

    def test_a_product_crossing_without_an_approved_measurement_is_withheld(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80")],
            prices={REBAR: observation("22000000", "branch")})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("needs_factor", row["status"])
        self.assertIsNone(row["component_daily_cost_irr"])

    def test_an_approved_measurement_prices_the_crossing(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80")],
            prices={REBAR: observation("22000000", "branch")},
            factors={(REBAR, "branch", "kg"): {"id": FACTOR, "factor": Decimal("22")}})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("ready", row["status"])
        self.assertEqual("1000000", row["converted_daily_unit_price_irr"])

    def test_a_measurement_stored_one_way_round_answers_the_other(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80")],
            prices={REBAR: observation("22000000", "branch")},
            factors={(REBAR, "kg", "branch"): {"id": FACTOR,
                                               "factor": Decimal("1") / Decimal("22")}})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("ready", row["status"])

    def test_a_crossing_nobody_could_measure_says_so_differently(self):
        # There is no number of kilograms in an hour. «ناسازگار» means stop asking;
        # «ضریب تبدیل لازم است» means ask somebody to weigh the product.
        service, _ = self.service(
            components=[component(REBAR, "kg", "80")],
            prices={REBAR: observation("500000", "hour")})
        row = run(service.components_for_line(Scope(), LINE))["components"][0]
        self.assertEqual("incompatible", row["status"])


class AddingAMaterialTests(unittest.TestCase):
    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_a_component_records_the_product_the_unit_the_usage_and_who_said_so(self):
        service, repo = self.service(prices={REBAR: observation()})
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                  actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertEqual(REBAR, saved["provider_item_id"])
        self.assertEqual("kg", saved["selected_unit"])
        self.assertEqual("per_msp_unit", saved["usage_mode"])
        self.assertEqual(Decimal("80"), saved["usage_quantity"])
        self.assertEqual(ACTOR, saved["created_by"])
        self.assertEqual("بر اساس نقشهٔ اجرایی", saved["reason"])

    def test_the_figures_as_at_approval_are_stored_beside_the_decision(self):
        # Evidence of what was agreed. The read path recomputes from today's price, so a
        # reader can see that today differs from what was approved, and by how much.
        service, repo = self.service(prices={REBAR: observation("1014600", "kg")})
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                  actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertEqual(Decimal("1014600"), saved["converted_daily_unit_price_irr"])
        self.assertEqual(Decimal("40000"), saved["component_quantity"])
        self.assertEqual(Decimal("40584000000"), saved["component_daily_cost_irr"])

    def test_the_listing_s_category_and_provider_are_recorded_as_read(self):
        service, repo = self.service(prices={REBAR: observation()})
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                  actor_id=ACTOR))
        self.assertEqual("rebar", repo.appended[0]["category"])
        self.assertEqual(UUID(int=3), repo.appended[0]["provider_id"])

    def test_a_unit_outside_the_registry_is_refused(self):
        service, repo = self.service(prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=LINE,
                                      payload=Payload(selected_unit="گونی"),
                                      actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_blank_reason_is_refused(self):
        service, repo = self.service(prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=LINE,
                                      payload=Payload(reason="   "), actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_usage_mode_nobody_chose_is_refused(self):
        # 500 is either per cubic metre or altogether, and on a 500 m3 trench the two
        # differ by a factor of 500. Nothing here may pick one.
        service, repo = self.service(prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=LINE,
                                      payload=Payload(usage_mode="whatever"),
                                      actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_missing_usage_quantity_is_refused_rather_than_defaulted_to_one(self):
        service, repo = self.service(prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=LINE,
                                      payload=Payload(usage_quantity=None),
                                      actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_negative_usage_quantity_is_refused(self):
        service, repo = self.service(prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=LINE,
                                      payload=Payload(usage_quantity=Decimal("-1")),
                                      actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_usage_of_zero_is_a_real_answer_and_is_kept(self):
        # "This line uses none of it" is a statement, not a missing one.
        service, repo = self.service(prices={REBAR: observation()})
        run(service.add_component(Scope(), estimate_line_id=LINE,
                                  payload=Payload(usage_quantity=Decimal("0")),
                                  actor_id=ACTOR))
        self.assertEqual(Decimal("0"), repo.appended[0]["usage_quantity"])
        self.assertEqual("ready", repo.appended[0]["status"])

    def test_a_listing_this_project_does_not_have_is_refused(self):
        service, repo = self.service(prices={}, listings={})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                      actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_line_this_project_does_not_have_is_refused(self):
        service, repo = self.service(prices={REBAR: observation()}, context=None)
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.add_component(Scope(), estimate_line_id=OTHER_LINE,
                                      payload=Payload(), actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_a_product_with_no_price_yet_may_still_be_added(self):
        # Which product this is and what it currently costs are different facts. The row
        # simply reports «قیمت روز معتبر وجود ندارد» until a good price arrives.
        service, repo = self.service(prices={})
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                  actor_id=ACTOR))
        self.assertEqual("no_price", repo.appended[0]["status"])
        self.assertIsNone(repo.appended[0]["component_daily_cost_irr"])

    def test_a_caller_cannot_supply_its_own_conversion_factor(self):
        # A number typed into a component form is not a measurement anybody approved, so
        # the crossing stays unresolved until one exists.
        service, repo = self.service(prices={REBAR: observation("22000000", "branch")})
        payload = Payload()
        payload.conversion_factor = Decimal("22")            # ignored, by construction
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=payload,
                                  actor_id=ACTOR))
        self.assertEqual("unknown", repo.appended[0]["conversion_status"])
        self.assertIsNone(repo.appended[0]["conversion_factor_id"])
        self.assertEqual("needs_factor", repo.appended[0]["status"])

    def test_an_approved_measurement_is_recorded_on_the_component(self):
        service, repo = self.service(
            prices={REBAR: observation("22000000", "branch")},
            factors={(REBAR, "branch", "kg"): {"id": FACTOR, "factor": Decimal("22")}})
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                  actor_id=ACTOR))
        self.assertEqual("factor", repo.appended[0]["conversion_status"])
        self.assertEqual(FACTOR, repo.appended[0]["conversion_factor_id"])

    def test_the_usage_unit_defaults_to_the_chosen_unit_rather_than_to_nothing(self):
        service, repo = self.service(prices={REBAR: observation()})
        run(service.add_component(Scope(), estimate_line_id=LINE, payload=Payload(),
                                  actor_id=ACTOR))
        self.assertEqual("kg", repo.appended[0]["usage_unit"])


class CorrectingAndRetiringTests(unittest.TestCase):
    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_an_edit_appends_a_version_under_the_same_identity(self):
        service, repo = self.service(components=[component(REBAR, "kg", "80")],
                                     prices={REBAR: observation()})
        run(service.update_component(Scope(), estimate_line_id=LINE,
                                     component_id=COMPONENT,
                                     payload=Payload(usage_quantity=Decimal("90")),
                                     actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertEqual(COMPONENT, saved["component_id"])
        self.assertEqual(Decimal("90"), saved["usage_quantity"])
        self.assertTrue(saved["active"])

    def test_editing_a_component_of_another_line_is_refused(self):
        service, repo = self.service(components=[component(REBAR, line=OTHER_LINE)],
                                     prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.update_component(Scope(), estimate_line_id=LINE,
                                         component_id=COMPONENT, payload=Payload(),
                                         actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_retiring_a_material_appends_an_inactive_version_rather_than_deleting(self):
        service, repo = self.service(components=[component(REBAR, "kg", "80")],
                                     prices={REBAR: observation()})
        run(service.deactivate_component(Scope(), estimate_line_id=LINE,
                                         component_id=COMPONENT,
                                         reason="از نقشه حذف شد", actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertFalse(saved["active"])
        self.assertEqual("از نقشه حذف شد", saved["reason"])
        self.assertEqual(COMPONENT, saved["component_id"])

    def test_retiring_carries_the_previous_version_s_figures_forward_unchanged(self):
        # The retirement records that it stopped, not a different set of facts about it.
        service, repo = self.service(
            components=[component(REBAR, "kg", "80",
                                  component_daily_cost_irr=Decimal("40584000000"))],
            prices={REBAR: observation()})
        run(service.deactivate_component(Scope(), estimate_line_id=LINE,
                                         component_id=COMPONENT, reason="حذف",
                                         actor_id=ACTOR))
        saved = repo.appended[0]
        self.assertEqual(REBAR, saved["provider_item_id"])
        self.assertEqual(Decimal("80"), saved["usage_quantity"])
        self.assertEqual(Decimal("40584000000"), saved["component_daily_cost_irr"])

    def test_retiring_without_a_reason_is_refused(self):
        service, repo = self.service(components=[component(REBAR, "kg", "80")],
                                     prices={REBAR: observation()})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.deactivate_component(Scope(), estimate_line_id=LINE,
                                             component_id=COMPONENT, reason="  ",
                                             actor_id=ACTOR))
        self.assertEqual([], repo.appended)

    def test_retiring_a_component_that_is_not_there_is_refused(self):
        service, repo = self.service(components=[], prices={})
        with self.assertRaises(ItemPriceComponentRefused):
            run(service.deactivate_component(Scope(), estimate_line_id=LINE,
                                             component_id=COMPONENT, reason="حذف",
                                             actor_id=ACTOR))
        self.assertEqual([], repo.appended)


class PreviewTests(unittest.TestCase):
    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_a_preview_prices_a_component_without_saving_anything(self):
        service, repo = self.service(prices={REBAR: observation("1014600", "kg")})
        body = run(service.preview_component(
            Scope(), estimate_line_id=LINE, provider_item_id=REBAR, selected_unit="kg",
            usage_mode="per_msp_unit", usage_quantity=Decimal("80")))
        self.assertEqual("40584000000", body["component_daily_cost_irr"])
        self.assertEqual("500", body["msp_quantity"])
        self.assertEqual([], repo.appended)

    def test_a_preview_names_the_refusal_before_anybody_commits_to_it(self):
        service, _ = self.service(prices={REBAR: observation("22000000", "branch")})
        body = run(service.preview_component(
            Scope(), estimate_line_id=LINE, provider_item_id=REBAR, selected_unit="kg",
            usage_mode="per_msp_unit", usage_quantity=Decimal("80")))
        self.assertEqual("needs_factor", body["status"])
        self.assertEqual("نیازمند ضریب تبدیل", body["status_label"])

    def test_a_total_preview_adds_the_draft_to_what_is_already_saved(self):
        service, _ = self.service(
            components=[component(REBAR, "kg", "80", "per_msp_unit")],
            prices={REBAR: observation("1014600", "kg"),
                    PIPE: observation("50000", "m", external_name="لوله")})
        total = run(service.preview_total(Scope(), LINE, {
            "provider_item_id": PIPE, "selected_unit": "m",
            "usage_mode": "total_quantity", "usage_quantity": Decimal("1200")}))
        self.assertEqual("40644000000", total["daily_item_cost_irr"])
        self.assertEqual(2, total["component_count"])

    def test_a_total_preview_without_a_draft_is_what_is_saved(self):
        service, _ = self.service(components=[component(REBAR, "kg", "80")],
                                  prices={REBAR: observation("1014600", "kg")})
        total = run(service.preview_total(Scope(), LINE))
        self.assertEqual("40584000000", total["daily_item_cost_irr"])
        self.assertEqual(1, total["component_count"])


class CascadeTests(unittest.TestCase):
    def service(self, **kwargs):
        repo = Repo(**kwargs)
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15)), repo

    def test_product_types_are_scoped_by_category_and_provider_together(self):
        # Choosing «میلگرد» then a supplier must not offer a type that exists only on
        # somebody else's brick -- the cascade would then yield an empty product list,
        # which reads as a broken page.
        service, repo = self.service(providers=[{"id": UUID(int=3), "name": "فولاد"}],
                                     product_types=["A3"])
        run(service.filters(Scope(), category="rebar", provider_id=UUID(int=3)))
        self.assertIn(("product_types", "rebar", UUID(int=3)), repo.filter_calls)

    def test_providers_are_scoped_by_the_chosen_category(self):
        service, repo = self.service(providers=[], product_types=[])
        run(service.filters(Scope(), category="brick"))
        self.assertIn(("providers", "brick"), repo.filter_calls)

    def test_both_usage_modes_are_offered_with_persian_labels(self):
        service, _ = self.service()
        modes = run(service.filters(Scope()))["usage_modes"]
        self.assertEqual(["per_msp_unit", "total_quantity"], [m["value"] for m in modes])
        self.assertTrue(all(m["label"] and m["hint"] for m in modes))

    def test_the_units_offered_are_the_registry_s_own(self):
        from app.finance.domain.unit_registry import UNIT_REGISTRY
        service, _ = self.service()
        units = run(service.filters(Scope()))["units"]
        self.assertEqual(sorted(c for c, u in UNIT_REGISTRY.items() if u.active),
                         sorted(u["code"] for u in units))


if __name__ == "__main__":
    unittest.main()


class AResourcePriceReplacesTheDemandForComponentsTests(unittest.TestCase):
    """«نیازمند افزودن مصالح» was being shown for a truck.

    It was not merely unhelpful. A machine is hired at a rate somebody agreed; it is not
    assembled out of materials, so the table was asking for work that must never be done,
    and the line stayed unpriced for as long as nobody did it.
    """

    def _service(self, resource_prices=None, components=()):
        repo = Repo(components=list(components),
                    quantities={LINE: Decimal("100")})
        repo._resource_prices = resource_prices or {}
        return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 15))

    @staticmethod
    def _price(amount="32000000", unit="hour", source="manual_resource"):
        return {"current_unit_price_irr": Decimal(amount), "current_price_unit": unit,
                "current_price_source": source}

    def test_a_manually_priced_resource_is_priced_here_with_no_mapping_at_all(self):
        """The required case: price_versions exists, no provider_item mapping exists."""
        service = self._service({LINE: self._price()})
        answers = asyncio.run(service.table_status(Scope()))
        row = answers[str(LINE)]
        self.assertEqual("resource_price_ready", row["status"])
        # STRINGS. The schema types money as `str | None` because a Decimal serialises
        # through float and 3,200,000,000 rial does not survive that intact -- and
        # returning the Decimal made the whole endpoint 500 on its first priced row.
        self.assertEqual("3200000000", row["daily_item_cost_irr"])
        self.assertEqual("manual_resource", row["price_source"])
        self.assertEqual("hour", row["price_unit"])
        self.assertEqual("32000000", row["current_unit_price_irr"])

    def test_it_never_asks_for_components_or_a_product(self):
        service = self._service({LINE: self._price()})
        row = asyncio.run(service.table_status(Scope()))[str(LINE)]
        self.assertNotIn(row["status"], ("needs_components", "needs_product"))
        self.assertEqual("", row["reason"], "nothing is missing, so nothing is demanded")

    def test_a_resource_price_wins_over_components_the_line_also_has(self):
        """Same order as the report: price_versions first, whatever else exists.

        A line with both must not resolve one way here and another way there -- that is
        the entire defect this work exists to close.
        """
        service = self._service({LINE: self._price()},
                                components=[{"id": COMPONENT, "estimate_line_id": LINE,
                                             "provider_item_id": REBAR, "active": True,
                                             "selected_unit": "kg",
                                             "usage_mode": "per_msp_unit",
                                             "usage_quantity": Decimal("80"),
                                             "version": 1}])
        row = asyncio.run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("resource_price_ready", row["status"])
        self.assertEqual("3200000000", row["daily_item_cost_irr"])

    def test_a_sheet_priced_resource_says_so(self):
        service = self._service({LINE: self._price(amount="938400", unit="کیلو",
                                                   source="sheet")})
        row = asyncio.run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("sheet", row["price_source"])

    def test_no_price_anywhere_stays_unresolved_with_a_null_cost(self):
        row = asyncio.run(self._service().table_status(Scope()))[str(LINE)]
        self.assertEqual("needs_components", row["status"])
        self.assertIsNone(row["daily_item_cost_irr"], "null, never zero")

    def test_a_repository_without_the_lookup_still_answers(self):
        """Older doubles, and any caller wired before this rung existed.

        A subclass that HIDES the method, rather than deleting it from `Repo` -- deleting
        it mutated the class for every test that ran afterwards, and the ones that failed
        were not the one doing the deleting.
        """
        class Older(Repo):
            resource_prices = None

        service = ItemPriceComponentService(
            Older(components=[], quantities={LINE: Decimal("100")}),
            clock=lambda: date(2026, 9, 15))
        row = asyncio.run(service.table_status(Scope()))[str(LINE)]
        self.assertEqual("needs_components", row["status"])

    def test_the_row_validates_against_the_published_schema(self):
        """The 500 the frontend hit, pinned where it can be seen.

        Asserting the strings is not enough on its own -- it says what the builder emits
        and nothing about whether the response model accepts it. This runs the row through
        the model the endpoint actually returns.
        """
        from app.finance.schemas.item_price_components import ItemPriceRowStatusResponse

        row = asyncio.run(self._service({LINE: self._price()}).table_status(Scope()))
        ItemPriceRowStatusResponse(**row[str(LINE)])

    def test_a_row_with_no_quantity_states_a_price_and_no_total(self):
        repo = Repo(components=[], quantities={LINE: None})
        repo._resource_prices = {LINE: self._price()}
        row = asyncio.run(ItemPriceComponentService(
            repo, clock=lambda: date(2026, 9, 15)).table_status(Scope()))[str(LINE)]
        self.assertIsNone(row["daily_item_cost_irr"], "null, never the string '0'")
        self.assertEqual("32000000", row["current_unit_price_irr"])
