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


class DuplicateExternalResourceId(FinanceDomainError):
    """Another live resource in this scope already claims this external id.

    The uniqueness is 0009's partial index -- it is what makes the MPP import's
    UID-to-resource matching deterministic -- and a violation is the CALLER's
    conflict to resolve, not a server fault: 409, never a raw 500.
    """

    code = "DUPLICATE_EXTERNAL_RESOURCE_ID"
    status = 409


class UnitNotFound(FinanceDomainError):
    code = "UNIT_NOT_FOUND"
    status = 422


class UnitInactive(FinanceDomainError):
    code = "UNIT_INACTIVE"
    status = 422


class ActivityNotFound(FinanceDomainError):
    code = "ACTIVITY_NOT_FOUND"
    status = 404


class ActivityInactive(FinanceDomainError):
    code = "ACTIVITY_INACTIVE"
    status = 422


class ActivityProviderUnavailable(FinanceDomainError):
    code = "ACTIVITY_PROVIDER_UNAVAILABLE"
    status = 503


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
    #: The MPP Resource UID this item was read from, or None when it was not read from a
    #: schedule. This is the ONLY field that says so: `external_resource_id` holds a legacy
    #: value on this database -- MSP task uids written by an old seed -- so anything
    #: deciding "did this come from the current file?" must read this and not that.
    source_resource_uid: int | None = None

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
    revision: int = 1
    revisions: tuple = ()
    activity_title: str | None = None
    wbs_code: str | None = None
    #: The MPP Assignment and Task this line was read from, or None when it was not read
    #: from a schedule. `assignment_external_id` is not these: it is free text that merely
    #: happens to hold the same digits today, and a reader deciding "is this line part of
    #: the current schedule?" must not depend on a coincidence.
    source_assignment_uid: int | None = None
    source_task_uid: int | None = None

    def with_revised_quantity(self, quantity: Decimal | None):
        return replace(self, revised_quantity=quantity)
