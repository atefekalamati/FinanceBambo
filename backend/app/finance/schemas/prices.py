from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, field_serializer, field_validator
from .base import ApiModel
from ..domain.prices import PriceVersion

class PriceCreate(ApiModel):
    scope_kind: Literal["organization","project"]
    unit_price_irr: Decimal = Field(ge=0,max_digits=18,decimal_places=0)
    effective_from: date
    reason: str = Field(min_length=1)
    @field_validator("reason")
    @classmethod
    def reason_required(cls,v):
        if not v.strip(): raise ValueError("reason must not be blank")
        return v.strip()

class PriceResponse(PriceCreate):
    id: UUID; resource_id: UUID; version: int; created_by: UUID; created_at: datetime
    @field_serializer("unit_price_irr")
    def money(self,v): return format(v,"f")
    @classmethod
    def from_domain(cls,v:PriceVersion): return cls(**v.__dict__)
