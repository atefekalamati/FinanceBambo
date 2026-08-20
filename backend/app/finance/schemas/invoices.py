from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict,Field,field_serializer,field_validator,model_validator
from .base import ApiModel
from .numeric import strict_decimal,strict_optional_decimal
Money=Decimal
class InvoiceLineCreate(ApiModel):
 model_config=ConfigDict(json_schema_extra={"examples":[{"resourceId":"77777777-7777-4777-8777-777777777777","lineAmountIrr":"12000000","description":"هزینه مجوز"}]})
 estimate_line_id:UUID|None=None;resource_id:UUID;quantity:Decimal|None=Field(default=None,max_digits=18,decimal_places=4);unit:str|None=None;unit_price_irr:Decimal|None=Field(default=None,ge=0,max_digits=18,decimal_places=0);line_amount_irr:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=0);description:str|None=None
 @field_validator("quantity","unit_price_irr","line_amount_irr",mode="before")
 @classmethod
 def strict_line_numbers(cls,v):return strict_optional_decimal(v)
 @model_validator(mode="after")
 def valid_amount_shape(self):
  if self.line_amount_irr is not None and any(value is not None for value in (self.quantity,self.unit,self.unit_price_irr)):
   raise ValueError("direct line amount cannot be combined with quantity, unit, or unit price")
  return self
class DirectAdjustmentAllocation(ApiModel):
 kind:Literal["discount","tax","shipping","other"];general_cost_line_index:int=Field(ge=0)
class InvoiceCreate(ApiModel):
 invoice_number:str|None=None;invoice_date:date;vendor_name:str=Field(min_length=1);description:str|None=None;source:Literal["manual"]="manual";discount_irr:Decimal=Field(default=0,ge=0,max_digits=18,decimal_places=0);tax_irr:Decimal=Field(default=0,ge=0,max_digits=18,decimal_places=0);shipping_irr:Decimal=Field(default=0,ge=0,max_digits=18,decimal_places=0);other_costs_irr:Decimal=Field(default=0,ge=0,max_digits=18,decimal_places=0);idempotency_key:str=Field(min_length=1);duplicate_reason:str|None=None;direct_adjustment_allocations:list[DirectAdjustmentAllocation]=Field(default_factory=list);lines:list[InvoiceLineCreate]=Field(min_length=1)
 @field_validator("discount_irr","tax_irr","shipping_irr","other_costs_irr",mode="before")
 @classmethod
 def strict_invoice_money(cls,v):return strict_decimal(v)
 @field_validator("vendor_name","idempotency_key")
 @classmethod
 def nonblank(cls,v):
  if not v.strip():raise ValueError("must not be blank")
  return v.strip()
 @model_validator(mode="after")
 def valid_allocations(self):
  kinds=[x.kind for x in self.direct_adjustment_allocations]
  if len(kinds)!=len(set(kinds)):raise ValueError("each adjustment kind can be allocated once")
  if any(x.general_cost_line_index>=len(self.lines) for x in self.direct_adjustment_allocations):raise ValueError("general cost line index is out of range")
  return self
class InvoicePatch(ApiModel):
 description:str|None=None;status:Literal["awaitingConfirmation"]|None=None;expected_version:int=Field(ge=1)
class InvoiceConfirm(ApiModel):
 expected_version:int=Field(ge=1);idempotency_key:str=Field(min_length=1)
 @field_validator("idempotency_key")
 @classmethod
 def confirm_key_nonblank(cls,v):
  if not v.strip():raise ValueError("must not be blank")
  return v.strip()
class InvoiceVoid(ApiModel):
 expected_version:int=Field(ge=1);idempotency_key:str=Field(min_length=1);reason:str=Field(min_length=1)
 @field_validator("idempotency_key","reason")
 @classmethod
 def void_nonblank(cls,v):
  if not v.strip():raise ValueError("must not be blank")
  return v.strip()
class CorrectiveInvoiceCreate(InvoiceCreate):
 source:Literal["corrective"]="corrective";financial_effect_sign:Literal[-1,1];reason:str=Field(min_length=1)
 @field_validator("reason")
 @classmethod
 def correction_reason_nonblank(cls,v):
  if not v.strip():raise ValueError("must not be blank")
  return v.strip()
class InvoiceLineResponse(ApiModel):
 estimate_line_id:UUID|None=None;resource_id:UUID;quantity:Decimal|None;unit:str|None;unit_price_irr:Decimal|None;line_amount_irr:Decimal|None=None;raw_amount_irr:Decimal;allocated_discount_irr:Decimal;allocated_tax_irr:Decimal;allocated_shipping_irr:Decimal;allocated_other_costs_irr:Decimal;final_line_amount_irr:Decimal;description:str|None=None
 @field_serializer("quantity","unit_price_irr","line_amount_irr","raw_amount_irr","allocated_discount_irr","allocated_tax_irr","allocated_shipping_irr","allocated_other_costs_irr","final_line_amount_irr")
 def number(self,v):return None if v is None else format(v,"f")
class InvoiceResponse(ApiModel):
 id:UUID;invoice_number:str|None;invoice_date:date;vendor_name:str;description:str|None;source:str;status:str;discount_irr:Decimal;tax_irr:Decimal;shipping_irr:Decimal;other_costs_irr:Decimal;final_amount_irr:Decimal;financial_effect_sign:Literal[-1,1]=1;original_invoice_id:UUID|None=None;idempotency_key:str;version:int;submitted_by:UUID;confirmed_by:UUID|None=None;confirmed_at:datetime|None=None;created_at:datetime;lines:list[InvoiceLineResponse]
 @field_serializer("discount_irr","tax_irr","shipping_irr","other_costs_irr","final_amount_irr")
 def money(self,v):return format(v,"f")
 @classmethod
 def from_domain(cls,v):return cls(**v.__dict__)
class InvoiceListResponse(ApiModel):
 model_config=ConfigDict(json_schema_extra={"examples":[{"items":[],"page":1,"pageSize":50,"totalItems":0,"totalPages":0}]})
 items:list[InvoiceResponse];page:int;page_size:int;total_items:int;total_pages:int
