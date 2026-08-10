import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.resources import EstimateLine, FinanceResource, UnitMismatch
from app.finance.schemas.resources import (
    EstimateLineCreate,
    EstimateRevisionCreate,
    ResourceCreate,
)
from app.finance.services.resources import FinanceResourcesService
from app.finance.security.guards import FinanceScope

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
RESOURCE = UUID("22222222-2222-4222-8222-222222222222")
LINE = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class Repo:
    def __init__(self):
        self.resources = []
        self.lines = []
        self.revisions = []

    async def list_resources(self, scope): return self.resources
    async def get_resource(self, scope, resource_id):
        return next((x for x in self.resources if x.id == resource_id), None)
    async def create_resource(self, scope, value, audit_id):
        self.resources.append(value); return value
    async def update_resource(self, scope, resource_id, changes, audit_id, occurred_at):
        current = await self.get_resource(scope, resource_id)
        if current is None: return None
        updated = current.with_changes(**changes)
        self.resources[self.resources.index(current)] = updated
        return updated
    async def list_estimate_lines(self, scope): return self.lines
    async def create_estimate_line(self, scope, value, audit_id):
        self.lines.append(value); return value
    async def append_estimate_revision(self, scope, line_id, revision_id, audit_id, new_quantity, reason, actor, occurred_at):
        line = next((x for x in self.lines if x.id == line_id), None)
        if line is None: return None
        self.revisions.append((line.original_quantity, new_quantity, reason))
        revised = line.with_revised_quantity(new_quantity)
        self.lines[self.lines.index(line)] = revised
        return revised


class ResourceEstimateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ids = iter((RESOURCE, UUID("44444444-4444-4444-8444-444444444444"), LINE,
                    UUID("55555555-5555-4555-8555-555555555555"),
                    UUID("66666666-6666-4666-8666-666666666666"),
                    UUID("77777777-7777-4777-8777-777777777777")))
        self.repo = Repo()
        self.service = FinanceResourcesService(self.repo, lambda: next(ids), lambda: NOW)
        self.scope = FinanceScope(ORG, "sample_site_01", ACTOR)

    def test_four_types_and_general_cost_optional_unit(self):
        for kind in ("material", "labor", "equipment"):
            ResourceCreate(type=kind, code="X", title="قلم", baseUnit="kg", dimension="mass")
        ResourceCreate(type="general_cost", code="GC", title="هزینه عمومی")
        with self.assertRaises(ValueError):
            ResourceCreate(type="material", code="M", title="مصالح")

    async def test_uuid_is_stable_and_original_quantity_is_not_rewritten(self):
        resource = await self.service.create_resource(
            self.scope, ResourceCreate(type="material", code="M1", title="سیمان", baseUnit="kg", dimension="mass")
        )
        line = await self.service.create_estimate_line(
            self.scope, EstimateLineCreate(resourceId=resource.id, activityExternalId="A1", assignmentExternalId="AS1", originalQuantity="10.0000", originalUnitPriceIrr="12000", source="manual_entry")
        )
        revised = await self.service.revise_estimate_line(
            self.scope, line.id, EstimateRevisionCreate(newQuantity="12.5000", reason="اصلاح متره")
        )
        self.assertEqual(RESOURCE, resource.id)
        self.assertEqual(LINE, line.id)
        self.assertEqual(Decimal("10.0000"), revised.original_quantity)
        self.assertEqual(Decimal("12.5000"), revised.revised_quantity)
        self.assertEqual(1, len(self.repo.revisions))

    async def test_general_cost_ui_amount_is_normalized_to_money_not_quantity(self):
        resource = await self.service.create_resource(
            self.scope, ResourceCreate(type="general_cost", code="GC", title="هزینه مجوز")
        )
        line = await self.service.create_estimate_line(
            self.scope, EstimateLineCreate(resourceId=resource.id, activityExternalId="A1", originalQuantity="2500000", source="manual_entry")
        )
        self.assertIsNone(line.original_quantity)
        self.assertEqual((Decimal("2500000"),Decimal("2500000")),(line.original_unit_price_irr,line.revised_quantity))
        with self.assertRaises(UnitMismatch):
            await self.service.create_estimate_line(self.scope,EstimateLineCreate(resourceId=resource.id,activityExternalId="A1",originalQuantity="2.5",source="manual_entry"))

    def test_source_is_closed_enum_and_reason_is_required(self):
        with self.assertRaises(ValueError):
            EstimateLineCreate(resourceId=RESOURCE, originalQuantity="1", source="guess")
        with self.assertRaises(ValueError):
            EstimateRevisionCreate(newQuantity="2", reason="   ")

    def test_v11_fractional_irr_unit_price_is_rejected(self):
        with self.assertRaises(ValueError):
            EstimateLineCreate(
                resourceId=RESOURCE,
                originalQuantity="1.0000",
                originalUnitPriceIrr="100.5",
                source="manual_entry",
            )


if __name__ == "__main__": unittest.main()
