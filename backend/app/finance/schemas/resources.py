from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator, model_validator

from .base import ApiModel
from .numeric import strict_optional_decimal
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
    #: Additive and optional: an existing client that ignores it is unaffected. It exists
    #: because nothing else in this response distinguishes an item read from the current
    #: schedule from one a legacy seed created -- `externalResourceId` carries a task uid
    #: on historical rows and cannot answer that question.
    source_resource_uid: int | None = None
    #: Additive and optional. True when an invoice line names this item or somebody
    #: priced it -- said here so a client can keep a row a person has worked on, whatever
    #: else it looks like. A client that ignores it behaves exactly as before.
    has_operational_records: bool = False

    @classmethod
    def from_domain(cls, value: FinanceResource):
        # Select declared fields only: the domain object carries the tenant keys,
        # which responses omit and extra="forbid" would reject.
        return cls(**{key: item for key, item in value.__dict__.items() if key in cls.model_fields})


class EstimateLineCreate(ApiModel):
    resource_id: UUID
    activity_external_id: str | None = None
    assignment_external_id: str | None = None
    original_quantity: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    original_unit_price_irr: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=0)
    source: EstimateSource

    @field_validator("original_quantity", "original_unit_price_irr", mode="before")
    @classmethod
    def strict_estimate_numbers(cls, value):
        return strict_optional_decimal(value)


class EstimateRevisionCreate(ApiModel):
    new_quantity: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    reason: str = Field(min_length=1)

    @field_validator("new_quantity", mode="before")
    @classmethod
    def strict_revision_quantity(cls, value):
        return strict_optional_decimal(value)

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
    #: Additive and optional. Without these a client cannot tell a line read from the
    #: current schedule from one a legacy seed wrote, and would have to infer it from
    #: `assignmentExternalId` -- free text that holds the same digits by accident.
    source_assignment_uid: int | None = None
    source_task_uid: int | None = None
    #: Additive and optional. Null means no confirmed invoice line names this estimate
    #: line -- not that nothing was spent. A zero here is a real zero: invoice lines that
    #: cancel out. Never derived from a schedule cost or from a price.
    actual_cost_irr: Decimal | None = None
    revised_quantity: Decimal | None
    created_by: UUID
    created_at: datetime
    revision: int
    revisions: list[EstimateRevisionResponse]

    @field_serializer("original_quantity", "revised_quantity", "original_unit_price_irr",
                      "actual_cost_irr")
    def serialize_decimal(self, value: Decimal | None):
        return None if value is None else format(value, "f")

    @classmethod
    def from_domain(cls, value: EstimateLine):
        # Select declared fields only: the domain object carries the tenant keys,
        # which responses omit and extra="forbid" would reject.
        return cls(**{key: item for key, item in value.__dict__.items() if key in cls.model_fields})
