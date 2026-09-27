# -*- coding: utf-8 -*-
"""A line linked to a crew's or a machine's hourly rate (0039).

Asked for 2026-09-27: the rates set in settings under «قیمت‌گذاری نیرو و تجهیزات» must
be linkable to lines from the items page, beside «ویرایش نرخ ساعتی», with the newest
decision winning: link, then edit -> the edit; edit, then link -> the link.
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

from app.finance.domain.item_price_components import RESOURCE_PRICE_READY
from app.finance.domain.price_resolution import (MANUAL_WINS, RATE_WINS, RESOLVED_PRICE_COLUMNS,
                                                 SOURCE_LINKED_RATE, SOURCE_MANUAL_RESOURCE,
                                                 resolved_price_columns, resolved_price_joins)
from app.finance.services.item_price_components import (ItemPriceComponentRefused,
                                                        ItemPriceComponentService)
from test_item_price_component_service import LINE, Repo, Scope

CRANE = UUID("aaaaaaaa-0000-4000-8000-000000000001")
STEEL = UUID("aaaaaaaa-0000-4000-8000-000000000002")


class LinkRepo(Repo):
    """The component repository double, plus the three rate-link reads and writes."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.resources = {CRANE: {"id": CRANE, "title": "جرثقیل ۳۰ تن", "base_unit": "hour",
                                  "resource_type": "work"},
                          STEEL: {"id": STEEL, "title": "آهن آلات", "base_unit": "kg",
                                  "resource_type": "material"}}
        self.links = []

    async def rate_resource(self, s, resource_id):
        return self.resources.get(resource_id)

    async def live_rate_link(self, s, line_id):
        live = [l for l in self.links if l["estimate_line_id"] == line_id and l["superseded_at"] is None]
        if not live:
            return None
        link = live[-1]
        resource = self.resources[link["rate_resource_id"]]
        return dict(link, rate_resource_title=resource["title"], rate_unit=resource["base_unit"])

    async def append_rate_link(self, s, *, estimate_line_id, rate_resource_id, reason, created_by):
        for link in self.links:
            if link["estimate_line_id"] == estimate_line_id and link["superseded_at"] is None:
                link["superseded_at"] = "now"
        self.links.append({"id": UUID(int=len(self.links) + 1), "estimate_line_id": estimate_line_id,
                           "rate_resource_id": rate_resource_id, "reason": reason,
                           "created_by": created_by, "created_at": "t%d" % len(self.links),
                           "superseded_at": None})
        return await self.live_rate_link(s, estimate_line_id)


def service(resource_prices=None):
    repo = LinkRepo(quantities={LINE: Decimal("60")})
    repo._resource_prices = resource_prices or {}
    return ItemPriceComponentService(repo, clock=lambda: date(2026, 9, 27)), repo


class LinkingTests(unittest.TestCase):
    def test_a_line_links_to_a_machine_and_a_second_link_supersedes_the_first(self):
        svc, repo = service()
        asyncio.run(svc.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=CRANE,
                                  reason="نرخ جرثقیل", actor_id=UUID(int=9)))
        asyncio.run(svc.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=CRANE,
                                  reason="دوباره", actor_id=UUID(int=9)))
        live = [l for l in repo.links if l["superseded_at"] is None]
        self.assertEqual(1, len(live), "one live link; the first is superseded, not deleted")
        self.assertEqual(2, len(repo.links))

    def test_only_an_hourly_resource_may_be_linked_to(self):
        svc, _ = service()
        with self.assertRaises(ItemPriceComponentRefused):
            asyncio.run(svc.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=STEEL,
                                      reason="r", actor_id=UUID(int=9)))

    def test_a_blank_reason_and_an_unknown_resource_are_refused(self):
        svc, _ = service()
        with self.assertRaises(ItemPriceComponentRefused):
            asyncio.run(svc.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=CRANE,
                                      reason="  ", actor_id=UUID(int=9)))
        with self.assertRaises(ItemPriceComponentRefused):
            asyncio.run(svc.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=UUID(int=77),
                                      reason="r", actor_id=UUID(int=9)))

    def test_the_link_reports_whether_it_prices_the_line_today(self):
        # The ladder says the link is the newest decision: in force, with its rate.
        svc, _ = service({LINE: {"current_unit_price_irr": Decimal("5650000"),
                                 "current_price_unit": "hour",
                                 "current_price_source": SOURCE_LINKED_RATE}})
        link = asyncio.run(svc.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=CRANE,
                                         reason="r", actor_id=UUID(int=9)))
        self.assertTrue(link["in_force"])
        self.assertEqual(("5650000", "hour", "جرثقیل ۳۰ تن"),
                         (link["current_unit_price_irr"], link["price_unit"], link["rate_resource_title"]))
        # A rate typed afterwards on the line's own resource is the newer decision: the
        # link is kept, shown, and not in force.
        svc2, repo2 = service({LINE: {"current_unit_price_irr": Decimal("6000000"),
                                      "current_price_unit": "hour",
                                      "current_price_source": SOURCE_MANUAL_RESOURCE}})
        asyncio.run(svc2.link_rate(Scope(), estimate_line_id=LINE, rate_resource_id=CRANE,
                                   reason="r", actor_id=UUID(int=9)))
        link = asyncio.run(svc2.rate_link_for_line(Scope(), LINE))
        self.assertFalse(link["in_force"])
        self.assertIsNone(link["current_unit_price_irr"])


class TheStatusTableTests(unittest.TestCase):
    def test_a_linked_line_is_priced_at_the_linked_rate_and_names_the_machine(self):
        svc, _ = service({LINE: {"current_unit_price_irr": Decimal("5650000"),
                                 "current_price_unit": "hour",
                                 "current_price_source": SOURCE_LINKED_RATE,
                                 "current_price_link_title": "جرثقیل ۳۰ تن"}})
        row = asyncio.run(svc.table_status(Scope()))[str(LINE)]
        self.assertEqual(RESOURCE_PRICE_READY, row["status"])
        self.assertEqual("339000000", row["daily_item_cost_irr"], "60 hours × 5,650,000")
        self.assertEqual(SOURCE_LINKED_RATE, row["price_source"])
        self.assertEqual("جرثقیل ۳۰ تن", row["product_name"])


class TheLadderTests(unittest.TestCase):
    """Three decisions, one clock. Asserted on the SQL."""

    def test_the_rate_link_is_the_third_lateral_join_and_reads_the_linked_resources_rate(self):
        joins = resolved_price_joins("l")
        # manual_price, sheet_price, rate_link -- and the rate lookup nested in the third.
        self.assertEqual(4, joins.count(" ON TRUE"))
        self.assertLess(joins.index("sheet_price ON TRUE"), joins.index("rate_link ON TRUE"))
        self.assertIn("FROM finance_item_rate_links rl", joins)
        self.assertIn("pv.resource_id=rl.rate_resource_id", joins)
        self.assertIn("rl.estimate_line_id=l.id", joins)
        self.assertIn("rl.superseded_at IS NULL", joins)

    def test_the_newest_decision_that_can_answer_wins(self):
        for clock in ("manual_price.price_recorded_at", "sheet_price.linked_at", "rate_link.linked_at"):
            self.assertIn(clock, MANUAL_WINS, clock)
        self.assertIn("NOT", RATE_WINS)
        self.assertIn("rate_link.linked_at", RATE_WINS)
        # A decision with no price behind it is NULL on its clock, and a NULL neither wins
        # nor blocks: COALESCE to the contender itself.
        self.assertIn("COALESCE(", MANUAL_WINS)
        self.assertIn("THEN 'linked_rate'", RESOLVED_PRICE_COLUMNS)
        self.assertIn("rate_link.title END AS current_price_link_title", RESOLVED_PRICE_COLUMNS)
        self.assertIn("THEN rate_link.base_unit", resolved_price_columns("r.base_unit"))


if __name__ == "__main__":
    unittest.main()
