from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ..domain.resources import EstimateLine, FinanceRecordNotFound, FinanceResource, UnitMismatch
from ..schemas.resources import EstimateLineCreate, EstimateRevisionCreate, ResourceCreate, ResourcePatch
from ..security.guards import FinanceScope


class FinanceResourcesService:
    def __init__(self, repository, id_factory: Callable[[], UUID] = uuid4,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._repository, self._id_factory, self._clock = repository, id_factory, clock

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
        now, actor = self._clock(), self._actor(scope)
        value = FinanceResource(self._id_factory(), scope.organization_id, scope.project_id,
            command.type, command.code.strip(), command.title.strip(), command.base_unit,
            command.dimension, command.external_resource_id, actor, now)
        return await self._repository.create_resource(scope, value, self._id_factory())

    async def update_resource(self, scope, resource_id, command: ResourcePatch):
        changes = command.model_dump(exclude_unset=True)
        current = await self.get_resource(scope, resource_id)
        candidate = current.with_changes(**changes)
        if candidate.type != "general_cost" and not (candidate.base_unit and candidate.dimension):
            raise UnitMismatch("quantified resources require baseUnit and dimension")
        value = await self._repository.update_resource(scope, resource_id, changes, self._id_factory(), self._clock())
        if value is None: raise FinanceRecordNotFound("finance resource not found")
        return value

    async def list_estimate_lines(self, scope): return await self._repository.list_estimate_lines(scope)
    async def create_estimate_line(self, scope, command: EstimateLineCreate):
        resource = await self.get_resource(scope, command.resource_id)
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
            command.source, self._actor(scope), self._clock())
        return await self._repository.create_estimate_line(scope, value, self._id_factory())

    async def revise_estimate_line(self, scope, line_id, command: EstimateRevisionCreate):
        value = await self._repository.append_estimate_revision(scope, line_id, self._id_factory(),
            self._id_factory(), command.new_quantity, command.reason.strip(), self._actor(scope), self._clock())
        if value is None: raise FinanceRecordNotFound("estimate line not found")
        return value
