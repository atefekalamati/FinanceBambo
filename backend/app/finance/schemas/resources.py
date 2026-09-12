from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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
    # What the host calls this actor, filled at the API boundary and never stored. None when
    # the host has no directory or does not know the id; the reader then sees the id, exactly
    # as before. See `app.finance.domain.actors`.
    created_by_name: str | None = None
    created_at: datetime

    @field_serializer("previous_quantity", "new_quantity")
    def serialize_quantity(self, value):
        return None if value is None else format(value, "f")


class EstimateLineResponse(EstimateLineCreate):
    """What a line IS, which is not the same contract as what a person may create.

    Inheriting the create model shares the field list and the serialisers, and that is
    worth keeping -- but it also inherited `ge=0`, and a validation rule about what may be
    TYPED became a rule about what may be REPORTED. The two are not the same rule, and
    when they disagree the response cannot be produced at all: the whole list answers 500
    because one row is outside the bound, which is the least useful way for a database to
    tell a reader something is unusual.

    A negative amount reaches here from the schedule. MS Project states a task Fixed Cost
    of -2,972,160,000 on «نصب بتن پیش ساخته دال» against +5,290,960,000.5 on the activity
    beside it: one correction spread across two related activities, which nets to what the
    project actually plans. Dropping it would publish a total the file does not have, and
    refusing to serialise it hides every other line as well.

    So the bound is lifted HERE and nowhere else. `EstimateLineCreate` keeps it, so a
    person still cannot enter a negative amount by hand; a correction someone means to
    make goes through a corrective invoice, which is what that workflow is for.
    """

    id: UUID
    activity_title: str | None = None
    wbs_code: str | None = None
    #: No lower bound, unlike the create model above. See the class docstring: the file
    #: states a negative fixed cost on one activity, and a report that cannot say so is
    #: not a safer report, only an emptier one.
    original_unit_price_irr: Decimal | None = Field(default=None, max_digits=18,
                                                    decimal_places=0)
    #: Additive and optional. Without these a client cannot tell a line read from the
    #: current schedule from one a legacy seed wrote, and would have to infer it from
    #: `assignmentExternalId` -- free text that holds the same digits by accident.
    source_assignment_uid: int | None = None
    source_task_uid: int | None = None
    #: Additive and optional. Null means no confirmed invoice line names this estimate
    #: line -- not that nothing was spent. A zero here is a real zero: invoice lines that
    #: cancel out. Never derived from a schedule cost or from a price.
    actual_cost_irr: Decimal | None = None
    #: Additive and optional: what the schedule planned for this line's assignment.
    #: Deliberately named for the schedule and never for money-in-general, because a
    #: reader who saw `unitPrice` or `cost` here would reasonably pair it with the
    #: financial columns beside it, and it is not one of them.
    mpp_quantity: Decimal | None = None
    mpp_unit: str | None = None
    #: `exact` when the file named a registry unit, `alias` a known spelling of one,
    #: `low` when nothing recognised it -- and then `mpp_unit` is null rather than guessed.
    mpp_unit_confidence: str | None = None
    mpp_cost_irr: Decimal | None = None
    #: Constant, and said out loud so nobody has to assume it. The file states toman; the
    #: conversion happened once, at import.
    mpp_cost_currency: str = "IRR"
    #: Additive and optional: where the two original figures above came from.
    #: `recorded` -- written into the line when it was created.
    #: `source_completion` -- recorded later from the exact source version the line was
    #: mapped from, because the mapper of the day wrote NULL and the file said otherwise.
    #: Null -- nothing states an original, and the line is unmeasured rather than zero.
    original_value_source: str | None = None
    revised_quantity: Decimal | None
    created_by: UUID
    created_at: datetime
    revision: int
    revisions: list[EstimateRevisionResponse]

    @field_serializer("mpp_cost_irr", "original_unit_price_irr")
    def serialize_rials(self, value: Decimal | None):
        # Rials are whole. The schedule's figure arrives with a fractional tail -- the
        # file's own arithmetic, x10 -- and every money formatter downstream reads an
        # integer string, so a value like "15234765668.0" reaches the page as "—".
        return None if value is None else format(value.quantize(Decimal(1), ROUND_HALF_UP), "f")

    @field_serializer("original_quantity", "revised_quantity",
                      "actual_cost_irr", "mpp_quantity")
    def serialize_decimal(self, value: Decimal | None):
        return None if value is None else format(value, "f")

    @classmethod
    def from_domain(cls, value: EstimateLine):
        # Select declared fields only: the domain object carries the tenant keys,
        # which responses omit and extra="forbid" would reject.
        return cls(**{key: item for key, item in value.__dict__.items() if key in cls.model_fields})
