from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ..domain.resources import (EstimateLine, FinanceRecordNotFound, FinanceResource,
                                MppResourceRequired, UnitMismatch)
from ..domain.resources import ActivityInactive, ActivityNotFound, ActivityProviderUnavailable, UnitInactive, UnitNotFound
from ..domain.unit_registry import UNIT_REGISTRY
from ..schemas.resources import EstimateLineCreate, EstimateRevisionCreate, ResourceCreate, ResourcePatch
from ..security.guards import FinanceScope


class FinanceResourcesService:
    def __init__(self, repository, id_factory: Callable[[], UUID] = uuid4,
                 activity_provider=None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._repository, self._id_factory, self._activity_provider, self._clock = repository, id_factory, activity_provider, clock

    @staticmethod
    def _actor(scope):
        if scope.actor_user_id is None: raise PermissionError("authenticated actor is required")
        return scope.actor_user_id

    async def list_resources(self, scope): return await self._repository.list_resources(scope)
    async def get_resource(self, scope, resource_id):
        value = await self._repository.get_resource(scope, resource_id)
        if value is None: raise FinanceRecordNotFound("finance resource not found")
        return value

    async def create_resource(self, scope, command: ResourceCreate):
        """REFUSED. A project resource is something the schedule states, not something
        this endpoint makes.

        Every row this method could write would carry `source_resource_uid = NULL` -- the
        INSERT below never had a column for it -- and a resource with no MPP UID is one
        no schedule can account for, which still appears in the project total and can
        still be invoiced against.

        The import path is untouched: `coreint/finance_mpp_mapping.py` writes resources
        with their UIDs through its own statement and never calls this.
        """
        raise MppResourceRequired(
            "a project resource must come from an imported MPP source version; "
            "this endpoint cannot state which MPP resource it would be")

    async def update_resource(self, scope, resource_id, command: ResourcePatch):
        changes = command.model_dump(exclude_unset=True)
        current = await self.get_resource(scope, resource_id)
        candidate = current.with_changes(**changes)
        if "base_unit" in changes or "dimension" in changes or "type" in changes:
            base_unit, dimension = self._normalize_unit(candidate.type, candidate.base_unit, candidate.dimension)
            changes["base_unit"], changes["dimension"] = base_unit, dimension
        value = await self._repository.update_resource(scope, resource_id, changes, self._id_factory(), self._clock())
        if value is None: raise FinanceRecordNotFound("finance resource not found")
        return value

    @staticmethod
    def _normalize_unit(resource_type, base_unit, requested_dimension):
        if resource_type == "general_cost":
            return None, None
        unit = UNIT_REGISTRY.get(base_unit or "")
        if unit is None: raise UnitNotFound("unit is not registered")
        if not unit.active: raise UnitInactive("unit is inactive")
        if requested_dimension is not None and requested_dimension != unit.dimension:
            raise UnitMismatch("baseUnit and dimension are incompatible")
        return unit.code, unit.dimension

    async def list_activities(self, scope, query=None, status=None, page=1, page_size=50):
        if self._activity_provider is None:
            return [], 0
        value = await self._activity_provider.list_activities(
            str(scope.organization_id), scope.project_id, query, status, page, page_size)
        if isinstance(value, tuple): return value
        return value.get("items", []), value.get("total_items", len(value.get("items", [])))

    async def _activity(self, scope, activity_external_id):
        if not activity_external_id or self._activity_provider is None:
            return None
        value = await self._activity_provider.get_activity(str(scope.organization_id), scope.project_id, activity_external_id)
        if value is None: raise ActivityNotFound("activity not found")
        if value.get("status") != "active": raise ActivityInactive("activity is inactive")
        return value

    async def create_activity(self, scope, command):
        self._actor(scope)
        if self._activity_provider is None or not hasattr(self._activity_provider, "create_activity"):
            raise ActivityProviderUnavailable("activity creation must be provided by the host project module")
        return await self._activity_provider.create_activity(
            str(scope.organization_id), scope.project_id, command.title.strip(),
            command.wbs_code, command.parent_task_external_id)

    async def list_estimate_lines(self, scope): return await self._repository.list_estimate_lines(scope)
    async def list_task_resource_mappings(self, scope, page=1, page_size=100):
        return await self._repository.list_task_resource_mappings(scope, page, page_size)
    async def create_estimate_line(self, scope, command: EstimateLineCreate):
        """REFUSED unless the resource it names is itself MPP-derived.

        The gate is the RESOURCE's `source_resource_uid`, not a flag on the request: a
        caller cannot assert provenance it does not have, and the only trustworthy
        statement about whether something came from the schedule is the UID the importer
        wrote. A line on an MPP resource is a line the file can account for; a line on a
        resource with no UID is the source-less row this whole model exists to stop.

        120 such rows already exist on the audited project, carrying 1,615,000,000 IRR of
        the reported initial estimate. They are not deleted -- two of them are invoiced
        against -- they are marked `legacy_unlinked` by 0030 and kept out of MPP-derived
        totals. This is what stops the 121st.
        """
        resource = await self.get_resource(scope, command.resource_id)
        if getattr(resource, "source_resource_uid", None) is None:
            raise MppResourceRequired(
                "an estimate line must belong to a resource imported from an MPP source "
                "version; this resource states no MPP resource UID")
        activity = await self._activity(scope, command.activity_external_id)
        if resource.type != "general_cost" and command.original_quantity is None:
            raise UnitMismatch("quantified estimate line requires quantity")
        original_quantity=command.original_quantity;revised_quantity=command.original_quantity;original_price=command.original_unit_price_irr
        if resource.type == "general_cost":
            if command.original_quantity is not None and command.original_unit_price_irr is not None:
                raise UnitMismatch("general cost amount must be provided once")
            amount=command.original_unit_price_irr if command.original_unit_price_irr is not None else command.original_quantity
            if amount is None or amount<0 or amount!=amount.to_integral_value():
                raise UnitMismatch("general cost requires an exact integer IRR amount")
            original_quantity=None;revised_quantity=amount;original_price=amount
        value = EstimateLine(self._id_factory(), scope.organization_id, scope.project_id,
            command.resource_id, command.activity_external_id, command.assignment_external_id,
            original_quantity, revised_quantity, original_price,
            command.source, self._actor(scope), self._clock(),
            activity_title=None if activity is None else activity.get("title"),
            wbs_code=None if activity is None else activity.get("wbsCode") or activity.get("wbs_code"))
        return await self._repository.create_estimate_line(scope, value, self._id_factory())

    async def revise_estimate_line(self, scope, line_id, command: EstimateRevisionCreate):
        value = await self._repository.append_estimate_revision(scope, line_id, self._id_factory(),
            self._id_factory(), command.new_quantity, command.reason.strip(), self._actor(scope), self._clock())
        if value is None: raise FinanceRecordNotFound("estimate line not found")
        return value
