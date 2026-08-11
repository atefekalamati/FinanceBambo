from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator, model_validator

from .base import ApiModel
from ..domain.resources import EstimateLine, FinanceResource

ResourceType = Literal["material", "labor", "equipment", "general_cost"]
EstimateSource = Literal["progress_feed", "excel_import", "manual_entry"]


class ResourceCreate(ApiModel):
    type: ResourceType
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    base_unit: str | None = None
    dimension: str | None = None
    external_resource_id: str | None = None

    @field_validator("code", "title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError("value must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def require_quantity_metadata(self):
        if self.type != "general_cost" and not self.base_unit:
            raise ValueError("quantified resources require baseUnit")
        return self


class ResourcePatch(ApiModel):
    type: ResourceType | None = None
    code: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    base_unit: str | None = None
    dimension: str | None = None
    external_resource_id: str | None = None


class ResourceResponse(ResourceCreate):
    id: UUID
    created_by: UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, value: FinanceResource):
        return cls(**value.__dict__)


class EstimateLineCreate(ApiModel):
    resource_id: UUID
    activity_external_id: str | None = None
    assignment_external_id: str | None = None
    original_quantity: Decimal | None = None
    original_unit_price_irr: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=0)
    source: EstimateSource


class EstimateRevisionCreate(ApiModel):
    new_quantity: Decimal | None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def trim_reason(self):
        if not self.reason.strip(): raise ValueError("reason must not be blank")
        return self

class EstimateRevisionResponse(ApiModel):
    id: UUID
    revision: int
    previous_quantity: Decimal | None
    new_quantity: Decimal | None
    reason: str
    created_by: UUID
    created_at: datetime

    @field_serializer("previous_quantity", "new_quantity")
    def serialize_quantity(self, value):
        return None if value is None else format(value, "f")


class EstimateLineResponse(EstimateLineCreate):
    id: UUID
    activity_title: str | None = None
    wbs_code: str | None = None
    revised_quantity: Decimal | None
    created_by: UUID
    created_at: datetime
    revision: int
    revisions: list[EstimateRevisionResponse]

    @field_serializer("original_quantity", "revised_quantity", "original_unit_price_irr")
    def serialize_decimal(self, value: Decimal | None):
        return None if value is None else format(value, "f")

    @classmethod
    def from_domain(cls, value: EstimateLine):
        return cls(**value.__dict__)
