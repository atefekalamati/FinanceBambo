from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, field_serializer, field_validator
from .base import ApiModel
from .numeric import strict_decimal
from ..domain.prices import PriceVersion

class PriceCreate(ApiModel):
    scope_kind: Literal["organization","project"]
    unit_price_irr: Decimal = Field(ge=0,max_digits=18,decimal_places=0)
    effective_from: date
    reason: str = Field(min_length=1)
    @field_validator("unit_price_irr", mode="before")
    @classmethod
    def strict_money(cls,v):
        return strict_decimal(v)
    @field_validator("reason")
    @classmethod
    def reason_required(cls,v):
        if not v.strip(): raise ValueError("reason must not be blank")
        return v.strip()

class PriceResponse(PriceCreate):
    id: UUID; resource_id: UUID; version: int; created_by: UUID; created_at: datetime
    # What the host calls this actor, filled at the API boundary and never stored.
    # None when the host has no directory or does not know the id; the reader then
    # sees the id, exactly as before. See `app.finance.domain.actors`.
    created_by_name: str | None = None
    @field_serializer("unit_price_irr")
    def money(self,v): return format(v,"f")
    @classmethod
    def from_domain(cls,v:PriceVersion):
        return cls(id=v.id,resourceId=v.resource_id,scopeKind=v.scope_kind,version=v.version,
            unitPriceIrr=v.unit_price_irr,effectiveFrom=v.effective_from,reason=v.reason,
            createdBy=v.created_by,createdAt=v.created_at)


class PriceTrendPoint(ApiModel):
    effective_from:date
    unit_price_irr:Decimal
    @field_serializer("unit_price_irr")
    def money(self,v):return format(v,"f")


class CurrentPriceTrendResponse(ApiModel):
    resource_id:UUID
    organization_price_irr:Decimal|None=None
    organization_effective_from:date|None=None
    project_price_irr:Decimal|None=None
    project_effective_from:date|None=None
    current_price_irr:Decimal|None
    current_effective_from:date|None=None
    previous_price_irr:Decimal|None
    latest_change_percent:Decimal|None
    trend_direction:Literal["up","down","flat","none"]
    scope_kind:Literal["organization","project"]|None
    trend_points:list[PriceTrendPoint]
    @field_serializer("organization_price_irr","project_price_irr","current_price_irr","previous_price_irr","latest_change_percent")
    def decimal_string(self,v):return None if v is None else format(v,"f")



class PriceHistoryListResponse(ApiModel):
    """Paged envelope, so a reader cannot mistake an unfetched page for the end of the history.

    `totalItems` is what the filter matched, not what this page holds -- the difference is
    the whole reason the envelope exists on an append-only table.
    """

    items: list[PriceResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
