from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import field_serializer

from .base import ApiModel


class LiveMetrics(ApiModel):
    initial_estimate_irr: Decimal
    actual_cost_irr: Decimal
    current_executed_value_irr: Decimal
    remaining_physical_cost_irr: Decimal
    money_required_to_continue_irr: Decimal
    forecast_final_cost_irr: Decimal
    actual_cost_per_square_meter_irr: Decimal | None
    forecast_per_square_meter_irr: Decimal | None

    @field_serializer("initial_estimate_irr","actual_cost_irr","current_executed_value_irr","remaining_physical_cost_irr","money_required_to_continue_irr","forecast_final_cost_irr","actual_cost_per_square_meter_irr","forecast_per_square_meter_irr")
    def serialize_money(self,value): return None if value is None else format(value,"f")


class TypeBreakdown(ApiModel):
    resource_type: Literal["material","labor","equipment","general_cost"]
    initial_estimate_irr: Decimal
    actual_cost_irr: Decimal
    forecast_final_irr: Decimal
    @field_serializer("initial_estimate_irr","actual_cost_irr","forecast_final_irr")
    def serialize_money(self,value): return format(value,"f")


class PriceVariance(ApiModel):
    estimate_line_id: UUID;resource_id:UUID;resource_code:str;resource_title:str;resource_type:str;variance_irr:Decimal
    @field_serializer("variance_irr")
    def serialize_money(self,value):return format(value,"f")


class QuantityVariance(ApiModel):
    estimate_line_id:UUID;resource_id:UUID;resource_code:str;resource_title:str;resource_type:str;variance_quantity:Decimal
    @field_serializer("variance_quantity")
    def serialize_quantity(self,value):return format(value,"f")


class ReportWarning(ApiModel):
    code:str;message:str;estimate_line_id:UUID|None=None


class LiveReportResponse(ApiModel):
    reporting_date:date
    progress_snapshot_id:UUID
    metrics:LiveMetrics
    breakdown:list[TypeBreakdown]
    top_price_variances:list[PriceVariance]
    top_quantity_variances:list[QuantityVariance]
    warnings:list[ReportWarning]
