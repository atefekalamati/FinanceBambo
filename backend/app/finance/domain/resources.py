"""Finance resource and estimate entities defined by PRD FR-010..014."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .errors import FinanceDomainError


class FinanceRecordNotFound(FinanceDomainError):
    code = "FINANCE_NOT_FOUND"
    status = 404


class UnitMismatch(FinanceDomainError):
    code = "UNIT_MISMATCH"
    status = 422


@dataclass(frozen=True)
class FinanceResource:
    id: UUID
    organization_id: UUID
    project_id: str
    type: str
    code: str
    title: str
    base_unit: str | None
    dimension: str | None
    external_resource_id: str | None
    created_by: UUID
    created_at: datetime

    def with_changes(self, **changes):
        return replace(self, **changes)


@dataclass(frozen=True)
class EstimateLine:
    id: UUID
    organization_id: UUID
    project_id: str
    resource_id: UUID
    activity_external_id: str | None
    assignment_external_id: str | None
    original_quantity: Decimal | None
    revised_quantity: Decimal | None
    original_unit_price_irr: Decimal | None
    source: str
    created_by: UUID
    created_at: datetime

    def with_revised_quantity(self, quantity: Decimal | None):
        return replace(self, revised_quantity=quantity)
