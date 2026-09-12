"""Settings request and response DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from ..domain.settings import FinanceProjectSettings
from .base import ApiModel
from .numeric import strict_decimal


PositiveArea = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]


class FinanceSettingsPatch(ApiModel):
    gross_built_area: PositiveArea
    effective_from: date
    reason: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)

    @field_validator("gross_built_area", mode="before")
    @classmethod
    def strict_area(cls, value):
        return strict_decimal(value)

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
    # Whether this actor may revise the area, so the UI can offer the form without
    # having to reimplement the backend's role policy. Defaults closed.
    can_edit: bool = False

    @field_serializer("gross_built_area")
    def serialize_area(self, value: Decimal) -> str:
        return format(value, "f")

    @classmethod
    def from_domain(cls, value: FinanceProjectSettings, can_edit: bool = False) -> "FinanceSettingsResponse":
        return cls(
            can_edit=can_edit,
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


class FinanceSettingsRevisionResponse(ApiModel):
    """One append-only settings revision, paired with the area it replaced."""

    id: UUID
    revision: int
    gross_built_area: Decimal
    previous_gross_built_area: Decimal | None = None
    # What the host calls this actor, filled at the API boundary and never stored.
    # None when the host has no directory or does not know the id; the reader then
    # sees the id, exactly as before. See `app.finance.domain.actors`.
    created_by_name: str | None = None
    effective_from: date
    reason: str
    created_by: UUID
    created_at: datetime

    @field_serializer("gross_built_area", "previous_gross_built_area")
    def serialize_area(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")

    @classmethod
    def from_domain(cls, value: FinanceProjectSettings, previous: Decimal | None) -> "FinanceSettingsRevisionResponse":
        return cls(
            id=value.id,
            revision=value.revision,
            gross_built_area=value.gross_built_area,
            previous_gross_built_area=previous,
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
