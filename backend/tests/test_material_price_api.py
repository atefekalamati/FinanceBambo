# -*- coding: utf-8 -*-
"""The material price endpoints: what they answer, and who may ask.

Two things are being checked, and they fail differently. The permission gate is a property
of the router and needs no database. The SHAPE of an answer -- a null price with a status
beside it rather than a zero, an empty list rather than a sample row -- is a property of
the service, and is checked with a repository whose rows this test wrote, so the assertion
is about the code and not about whatever happens to be in a database.
"""

import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.services.material_prices import MaterialPriceService
from app.main import create_app

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
ITEM = UUID("22222222-2222-4222-8222-222222222222")
RESOURCE = UUID("33333333-3333-4333-8333-333333333333")
PROJECT = "sample_site_01"
BASE = "/projects/%s/finance" % PROJECT


def observation(**changes):
    """One row shaped exactly as `latest_observations` returns it."""
    row = {
        "provider_item_id": ITEM,
        "external_id": "REBAR-1",
        "external_name": "میلگرد آجدار 8 A3",
        "category": "rebar",
        "provider_name": "Mashhad Foolad",
        "active": True,
        "inactive_reason": None,
        "item_worksheet": "steel -Rebar",
        "source_worksheet": "steel -Rebar",
        "normalized_price_irr": Decimal("955000"),
        "raw_price": "95500",
        "source_currency": "TOMAN",
        "secondary_price_irr": None,
        "secondary_price_basis": None,
        "source_unit": "کیلو",
        "workflow_date_raw": "1405-06-22",
        "workflow_date_jalali": "1405/06/22",
        "workflow_date_gregorian": date(2026, 9, 13),
        "observed_at_source": "workflow_date",
        "observed_at": datetime(2026, 9, 13, tzinfo=timezone.utc),
        "fetched_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
        "validation_status": "valid",
        "validation_reasons": [],
        "source_row_number": 2,
        "source_url": "https://docs.google.com/spreadsheets/d/X/export?format=xlsx&gid=0",
    }
    row.update(changes)
    return row


class FakeRepository:
    """Rows this test wrote, so the assertions are about the service and not a database."""

    def __init__(self, rows=(), settings=(), factors=(), labels=(), finance_units=None):
        self.rows = list(rows)
        self.settings = list(settings)
        self.factors = list(factors)
        self._labels = list(labels)
        self._finance_units = dict(finance_units or {})

    async def labels(self, _scope, provider_item_id=None, active_only=True):
        if provider_item_id is None:
            return self._labels
        return [row for row in self._labels if row["provider_item_id"] == provider_item_id]

    async def mapped_resource_units(self, _scope):
        return self._finance_units

    async def latest_observations(self, _scope, *, category=None, only_active=True):
        rows = self.rows
        if category is not None:
            rows = [r for r in rows if r["category"] == category]
        if only_active:
            rows = [r for r in rows if r["active"]]
        return rows

    async def unit_settings(self, _scope, category=None):
        if category is None:
            return self.settings
        return [s for s in self.settings if s["category"] == category]

    async def item_unit_factors(self, _scope, _item):
        """Factors a person stored against this listing. `origin` says who supplied them."""
        return [dict(row, origin=row.get("origin", "manual")) for row in self.factors]

    async def categories(self, _scope):
        return [{"category": "rebar", "item_count": 1, "active_count": 1,
                 "inactive_count": 0}]

    async def runs_page(self, _scope, *, page, page_size):
        return [], 0

    async def invalid_observations_page(self, _scope, *, page, page_size):
        return [], 0

    async def observation_history(self, _scope, _item, *, page, page_size):
        return [], 0


def service(**kwargs):
    return MaterialPriceService(FakeRepository(**kwargs))


class ServiceShapeTests(unittest.IsolatedAsyncioTestCase):
    """What one row of the answer looks like, and what it refuses to look like."""

    class Scope:
        organization_id = ORG
        project_id = PROJECT
        actor_user_id = ACTOR

    async def current(self, **kwargs):
        items, total = await service(**kwargs).current(self.Scope())
        return items, total

    async def test_a_readable_price_is_resolved_and_carries_its_provenance(self):
        items, total = await self.current(rows=[observation()])
        self.assertEqual(1, total)
        row = items[0]
        self.assertEqual(Decimal("955000"), row["current_price_irr"])
        self.assertEqual("resolved", row["resolution_status"])
        self.assertEqual("Mashhad Foolad", row["provider_name"])
        self.assertEqual("1405/06/22", row["workflow_date_jalali"])
        self.assertEqual("workflow_date", row["observed_at_source"])
        self.assertEqual("95500", row["raw_price"], "what the sheet said is kept")

    async def test_an_unreadable_price_is_null_with_a_status_never_zero(self):
        items, _ = await self.current(rows=[observation(
            normalized_price_irr=None, validation_status="rejected",
            validation_reasons=["price is blank"])])
        row = items[0]
        self.assertIsNone(row["current_price_irr"])
        # The import already judged this row and said so. `invalid_source` keeps that
        # judgement visible instead of flattening it into "we have no price".
        self.assertEqual("invalid_source", row["resolution_status"])
        self.assertIn("blank", row["resolution_reason"])
        self.assertNotEqual(0, row["current_price_irr"])

    async def test_an_empty_database_gives_an_empty_list_not_a_sample_row(self):
        items, total = await self.current(rows=[])
        self.assertEqual([], items)
        self.assertEqual(0, total)

    async def test_a_missing_factor_is_reported_and_the_price_is_withheld(self):
        """kg to each needs a weight this product never stated. `each` is the Finance word;
        `piece` is not a unit here, which is why the earlier draft of this test used one."""
        items, _ = await self.current(
            rows=[observation()],
            settings=[{"category": "rebar", "resource_id": None, "display_unit": "each"}])
        row = items[0]
        self.assertIsNone(row["current_price_irr"])
        self.assertEqual("missing_factor", row["resolution_status"],
                         "this crossing CAN be answered -- by measuring this product")
        self.assertEqual("each", row["display_unit"])
        self.assertEqual("کیلو", row["source_unit"], "the sheet's spelling is still reported")
        self.assertEqual("kg", row["source_unit_code"], "and so is what it was read as")

    async def test_a_converted_price_explains_itself(self):
        items, _ = await self.current(
            rows=[observation()],
            settings=[{"category": "rebar", "resource_id": None, "display_unit": "g"}],
            factors=[{"from_unit": "kg", "to_unit": "g", "factor": Decimal("1000")}])
        row = items[0]
        self.assertEqual(Decimal("955"), row["current_price_irr"])
        self.assertEqual(Decimal("1000"), row["conversion_factor"])
        self.assertEqual("dimension", row["factor_origin"],
                         "units alone answered this; no product measurement was needed")
        # The note is read by a person on a Finance page, so it is written in the language
        # of that page. It must name both units and say what was done to the number.
        self.assertIn("کیلوگرم", row["conversion_note"])
        self.assertIn("گرم", row["conversion_note"])
        self.assertIn("تقسیم", row["conversion_note"])

    async def test_an_inactive_listing_is_left_out_of_the_active_answer(self):
        items, total = await self.current(rows=[observation(
            active=False, category="pipe_fitting", inactive_reason="not a pipe")])
        self.assertEqual(0, total, "a fitting is not part of the active pipe list")


class PermissionTests(unittest.TestCase):
    """Every endpoint is behind the gate, and an unauthenticated caller gets 401/403."""

    def setUp(self):
        self.client = TestClient(create_app(), raise_server_exceptions=False)

    def test_reading_material_prices_requires_authorisation(self):
        for path in ("/material-prices/categories", "/material-prices/current",
                     "/material-prices/runs", "/material-prices/invalid-rows",
                     "/material-prices/unit-settings"):
            with self.subTest(path=path):
                response = self.client.get(BASE + path)
                self.assertIn(response.status_code, (401, 403, 404),
                              "%s answered %d without a host context" % (path, response.status_code))
                self.assertNotEqual(200, response.status_code)

    def test_setting_a_unit_requires_authorisation(self):
        response = self.client.post(BASE + "/material-prices/unit-settings", json={
            "category": "rebar", "displayUnit": "kg", "reason": "because"})
        self.assertNotEqual(201, response.status_code)
        self.assertIn(response.status_code, (401, 403, 404, 422))


class ContractTests(unittest.TestCase):
    """The endpoints are in the exported contract, and money is nullable there."""

    def setUp(self):
        import json
        self.contract = json.loads(
            (BACKEND_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))

    def test_every_material_price_endpoint_is_published(self):
        paths = self.contract["paths"]
        for suffix in ("categories", "current", "runs", "invalid-rows", "unit-settings",
                       "{providerItemId}/history"):
            with self.subTest(suffix=suffix):
                # `/api` is the prefix the exported contract carries; the router's own
                # paths do not, and the test had the router's spelling.
                wanted = "/api/projects/{projectId}/finance/material-prices/" + suffix
                self.assertIn(wanted, paths)

    def test_the_current_price_field_is_nullable_in_the_contract(self):
        """A consumer must be able to see from the contract that a price can be absent."""
        schema = self.contract["components"]["schemas"]["MaterialPriceResponse"]
        field = schema["properties"]["currentPriceIrr"]
        text = str(field)
        self.assertIn("null", text,
                      "currentPriceIrr must be nullable: a missing price is not a zero")


if __name__ == "__main__":
    unittest.main()


def label(**changes):
    """A label exactly as `labels()` returns one."""
    row = {
        "provider_item_id": ITEM,
        "version": 1,
        "label": "میلگرد",
        "display_name": None,
        "category": "rebar",
        "product_type": None,
        "source_unit": None,
        "source_basis": None,
        "target_unit": None,
        "finance_resource_id": None,
        "mapping_approved": False,
        "active": True,
        "created_by": ACTOR,
        "created_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
    }
    row.update(changes)
    return row


class LabelAffectsResolutionTests(unittest.IsolatedAsyncioTestCase):
    """A label is configuration, and configuration is what makes a price usable."""

    class Scope:
        organization_id = ORG
        project_id = PROJECT
        actor_user_id = ACTOR

    async def current(self, **kwargs):
        return await service(**kwargs).current(self.Scope())

    async def test_a_label_supplies_the_unit_the_sheet_never_stated(self):
        """The pipe case: a price, no basis, and a person who says it is per metre."""
        items, _ = await self.current(
            rows=[observation(source_unit=None, category="pipe")],
            labels=[label(source_unit="m", target_unit="m", category="pipe")])
        row = items[0]
        self.assertEqual("resolved", row["resolution_status"],
                         "without the label this row has no basis at all")
        self.assertEqual(Decimal("955000"), row["current_price_irr"])
        self.assertEqual("m", row["target_unit"])
        self.assertEqual("میلگرد", row["label"])

    async def test_a_label_never_rewrites_what_the_sheet_said(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(source_unit="m", target_unit="m")])
        row = items[0]
        self.assertEqual("کیلو", row["source_unit"],
                         "the sheet's own spelling still travels to the reader")

    async def test_an_unapproved_mapping_withholds_the_price(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=False)])
        row = items[0]
        self.assertEqual("unresolved_mapping", row["resolution_status"])
        self.assertIsNone(row["current_price_irr"])
        self.assertFalse(row["mapping_approved"])

    async def test_an_approved_mapping_lets_it_through(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)])
        self.assertEqual("resolved", items[0]["resolution_status"])
        self.assertTrue(items[0]["mapping_approved"])

    async def test_an_inactive_label_takes_the_listing_out_of_resolution(self):
        items, _ = await self.current(rows=[observation()], labels=[label(active=False)])
        self.assertEqual("inactive", items[0]["resolution_status"])
        self.assertIsNone(items[0]["current_price_irr"])


class MspAlignmentTests(unittest.IsolatedAsyncioTestCase):
    """Whether the price is in the unit the schedule measures the resource in."""

    class Scope:
        organization_id = ORG
        project_id = PROJECT
        actor_user_id = ACTOR

    async def current(self, **kwargs):
        return await service(**kwargs).current(self.Scope())

    def finance_unit(self, base_unit):
        return {ITEM: {"provider_item_id": ITEM, "finance_resource_id": RESOURCE,
                       "base_unit": base_unit, "dimension": "mass",
                       "title": "میلگرد آجدار"}}

    async def test_without_a_mapping_there_is_nothing_to_align_with(self):
        items, _ = await self.current(rows=[observation()])
        self.assertEqual("not_mapped", items[0]["unit_alignment"])
        self.assertIsNone(items[0]["finance_resource_unit"])

    async def test_the_same_unit_on_both_sides_is_aligned(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)],
            finance_units=self.finance_unit("kg"))
        row = items[0]
        self.assertEqual("aligned", row["unit_alignment"])
        self.assertEqual("kg", row["finance_resource_unit"])
        self.assertEqual("میلگرد آجدار", row["finance_resource_title"])

    async def test_a_bridgeable_difference_is_convertible_and_both_units_are_reported(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)],
            finance_units=self.finance_unit("ton"))
        row = items[0]
        self.assertEqual("convertible", row["unit_alignment"])
        self.assertEqual("ton", row["finance_resource_unit"],
                         "the reader sees both units, not a verdict with the evidence hidden")

    async def test_a_difference_only_a_measurement_bridges_says_so(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)],
            finance_units=self.finance_unit("each"))
        self.assertEqual("needs_factor", items[0]["unit_alignment"])

    async def test_a_finance_resource_with_no_unit_of_its_own_says_that(self):
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)],
            finance_units=self.finance_unit(None))
        self.assertEqual("missing_finance_unit", items[0]["unit_alignment"])

    async def test_an_unusable_price_has_nothing_to_align(self):
        items, _ = await self.current(
            rows=[observation(normalized_price_irr=None)],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)],
            finance_units=self.finance_unit("kg"))
        self.assertEqual("unresolved", items[0]["unit_alignment"])

    async def test_alignment_never_converts_or_edits_the_msp_unit(self):
        """A verdict, not a correction: the reported price is untouched by alignment."""
        items, _ = await self.current(
            rows=[observation()],
            labels=[label(finance_resource_id=RESOURCE, mapping_approved=True)],
            finance_units=self.finance_unit("ton"))
        self.assertEqual(Decimal("955000"), items[0]["current_price_irr"],
                         "the price is still per kilogram; alignment only reports")
