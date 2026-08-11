import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.resources import ActivityInactive, ActivityNotFound, EstimateLine, FinanceResource, UnitMismatch, UnitNotFound
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


class ActivityProvider:
    async def list_activities(self, organization_id, project_id, query=None, status=None, page=1, page_size=50):
        items = [
            {"activityExternalId": "A1", "taskExternalId": "task-1", "title": "اجرای فونداسیون", "wbsCode": "1.2", "status": "active"},
            {"activityExternalId": "OLD", "taskExternalId": "task-old", "title": "فعالیت قدیمی", "wbsCode": "1.1", "status": "inactive"},
        ]
        if status: items = [item for item in items if item["status"] == status]
        if query: items = [item for item in items if query in item["title"] or query in item["activityExternalId"]]
        return items[(page-1)*page_size:page*page_size], len(items)

    async def get_activity(self, organization_id, project_id, activity_external_id):
        if activity_external_id == "A1":
            return {"activityExternalId": "A1", "taskExternalId": "task-1", "title": "اجرای فونداسیون", "wbsCode": "1.2", "status": "active"}
        if activity_external_id == "OLD":
            return {"activityExternalId": "OLD", "taskExternalId": "task-old", "title": "فعالیت قدیمی", "wbsCode": "1.1", "status": "inactive"}
        return None

    async def create_activity(self, organization_id, project_id, title, wbs_code=None, parent_task_external_id=None):
        return {"activityExternalId": "A2", "taskExternalId": parent_task_external_id or "task-2", "title": title, "wbsCode": wbs_code, "status": "active"}


class ResourceEstimateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ids = iter((RESOURCE, UUID("44444444-4444-4444-8444-444444444444"), LINE,
                    UUID("55555555-5555-4555-8555-555555555555"),
                    UUID("66666666-6666-4666-8666-666666666666"),
                    UUID("77777777-7777-4777-8777-777777777777")))
        self.repo = Repo()
        self.service = FinanceResourcesService(self.repo, lambda: next(ids), ActivityProvider(), lambda: NOW)
        self.scope = FinanceScope(ORG, "sample_site_01", ACTOR)

    def test_four_types_and_general_cost_optional_unit(self):
        for kind in ("material", "labor", "equipment"):
            command = ResourceCreate(type=kind, code="X", title="قلم", baseUnit="kg")
            self.assertIsNone(command.dimension)
        ResourceCreate(type="general_cost", code="GC", title="هزینه عمومی")
        with self.assertRaises(ValueError):
            ResourceCreate(type="material", code="M", title="مصالح")

    async def test_uuid_is_stable_and_original_quantity_is_not_rewritten(self):
        resource = await self.service.create_resource(
            self.scope, ResourceCreate(type="material", code="M1", title="سیمان", baseUnit="kg")
        )
        self.assertEqual("mass", resource.dimension)
        line = await self.service.create_estimate_line(
            self.scope, EstimateLineCreate(resourceId=resource.id, activityExternalId="A1", assignmentExternalId="AS1", originalQuantity="10.0000", originalUnitPriceIrr="12000", source="manual_entry")
        )
        self.assertEqual(("اجرای فونداسیون", "1.2"), (line.activity_title, line.wbs_code))
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

    async def test_activity_provider_validates_active_activity_for_new_estimate_line(self):
        resource = await self.service.create_resource(
            self.scope, ResourceCreate(type="material", code="M2", title="میلگرد", baseUnit="kg")
        )
        with self.assertRaises(ActivityNotFound):
            await self.service.create_estimate_line(
                self.scope,
                EstimateLineCreate(resourceId=resource.id, activityExternalId="NOPE", originalQuantity="1", source="manual_entry"),
            )
        with self.assertRaises(ActivityInactive):
            await self.service.create_estimate_line(
                self.scope,
                EstimateLineCreate(resourceId=resource.id, activityExternalId="OLD", originalQuantity="1", source="manual_entry"),
            )

    async def test_unknown_unit_is_rejected_and_dimension_mismatch_is_rejected(self):
        with self.assertRaises(UnitNotFound):
            await self.service.create_resource(
                self.scope, ResourceCreate(type="material", code="BAD", title="ناشناخته", baseUnit="parsec")
            )
        with self.assertRaises(UnitMismatch):
            await self.service.create_resource(
                self.scope, ResourceCreate(type="material", code="BAD2", title="ناسازگار", baseUnit="kg", dimension="area")
            )

    async def test_activity_creation_is_delegated_to_host_provider(self):
        from app.finance.schemas.activities import ActivityCreate
        created = await self.service.create_activity(
            self.scope,
            ActivityCreate(title="دیوارچینی", wbsCode="3.2", parentTaskExternalId="task-floor-2"),
        )
        self.assertEqual(("A2", "دیوارچینی", "3.2"), (created["activityExternalId"], created["title"], created["wbsCode"]))


if __name__ == "__main__": unittest.main()
