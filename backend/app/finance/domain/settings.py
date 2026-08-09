"""Immutable finance-project settings domain model."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from .errors import FinanceDomainError


class FinanceSettingsNotFound(FinanceDomainError):
    status = 404
    code = "FINANCE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Finance settings were not found in this scope.")


class StaleSettingsVersion(FinanceDomainError):
    status = 409
    code = "STALE_VERSION"

    def __init__(self) -> None:
        super().__init__("Finance settings version is stale.")


@dataclass(frozen=True, slots=True)
class FinanceProjectSettings:
    id: UUID
    organization_id: UUID
    project_id: str
    gross_built_area: Decimal
    currency: Literal["IRR"]
    revision: int
    effective_from: date
    reason: str
    created_by: UUID
    created_at: datetime
