from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field,field_serializer,field_validator,model_validator
from .base import ApiModel
from .numeric import strict_decimal
class ConversionCreate(ApiModel):
 scope_kind:Literal["organization","project"];source_unit:str=Field(min_length=1);target_unit:str=Field(min_length=1);dimension:str=Field(min_length=1);factor:Decimal=Field(gt=0,max_digits=24,decimal_places=8);effective_from:date;reason:str=Field(min_length=1)
 @field_validator("factor",mode="before")
 @classmethod
 def strict_factor(cls,v):return strict_decimal(v)
 @model_validator(mode="after")
 def valid(self):
  if self.source_unit.strip()==self.target_unit.strip():raise ValueError("sourceUnit and targetUnit must differ")
  if not self.reason.strip():raise ValueError("reason must not be blank")
  return self
class ConversionPatch(ApiModel):
 factor:Decimal=Field(gt=0,max_digits=24,decimal_places=8);effective_from:date;reason:str=Field(min_length=1)
 @field_validator("factor",mode="before")
 @classmethod
 def strict_factor(cls,v):return strict_decimal(v)
 @field_validator("reason")
 @classmethod
 def validate_reason(cls,v):
  if not v.strip():raise ValueError("reason must not be blank")
  return v.strip()
class ConversionResponse(ConversionCreate):
 id:UUID;version:int;created_by:UUID;created_at:datetime
 # What the host calls this actor, filled at the API boundary and never stored.
 # None when the host has no directory or does not know the id; the reader then sees
 # the id, exactly as before. See `app.finance.domain.actors`.
 created_by_name:str|None=None
 @field_serializer("factor")
 def decimal_string(self,v):return format(v,"f")
 @classmethod
 def from_domain(cls,v):return cls(**{k:x for k,x in v.__dict__.items() if k in cls.model_fields})


class ConversionListResponse(ApiModel):
 """Paged envelope, matching the invoice listing field for field.

 Conversions are appended and never deleted, so this listing grows for the life of a
 project and a client needs to be told how much of it it is holding.
 """
 items:list[ConversionResponse]
 page:int
 page_size:int
 total_items:int
 total_pages:int
