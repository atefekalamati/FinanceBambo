"""Settings request and response DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from ..domain.settings import FinanceProjectSettings
from .base import ApiModel


PositiveArea = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]


class FinanceSettingsPatch(ApiModel):
    gross_built_area: PositiveArea
    effective_from: date
    reason: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized


class FinanceSettingsResponse(ApiModel):
    id: UUID
    project_id: str
    gross_built_area: Decimal
    currency: Literal["IRR"]
    revision: int
    effective_from: date
    reason: str
    created_by: UUID
    created_at: datetime

    @field_serializer("gross_built_area")
    def serialize_area(self, value: Decimal) -> str:
        return format(value, "f")

    @classmethod
    def from_domain(cls, value: FinanceProjectSettings) -> "FinanceSettingsResponse":
        return cls(
            id=value.id,
            project_id=value.project_id,
            gross_built_area=value.gross_built_area,
            currency=value.currency,
            revision=value.revision,
            effective_from=value.effective_from,
            reason=value.reason,
            created_by=value.created_by,
            created_at=value.created_at,
        )


class FinanceSummaryResponse(ApiModel):
    gross_built_area: Decimal
    currency: Literal["IRR"]
    settings_revision: int

    @field_serializer("gross_built_area")
    def serialize_area(self, value: Decimal) -> str:
        return format(value, "f")

    @classmethod
    def from_domain(cls, value: FinanceProjectSettings) -> "FinanceSummaryResponse":
        return cls(
            gross_built_area=value.gross_built_area,
            currency=value.currency,
            settings_revision=value.revision,
        )
