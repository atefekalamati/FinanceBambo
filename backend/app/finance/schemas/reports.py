from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field,field_serializer

from .base import ApiModel


class LiveMetrics(ApiModel):
    initial_estimate_irr: Decimal
    actual_cost_irr: Decimal
    current_executed_value_irr: Decimal | None
    remaining_physical_cost_irr: Decimal | None
    money_required_to_continue_irr: Decimal | None
    forecast_final_cost_irr: Decimal | None
    actual_cost_per_square_meter_irr: Decimal | None
    forecast_per_square_meter_irr: Decimal | None

    @field_serializer("initial_estimate_irr","actual_cost_irr","current_executed_value_irr","remaining_physical_cost_irr","money_required_to_continue_irr","forecast_final_cost_irr","actual_cost_per_square_meter_irr","forecast_per_square_meter_irr")
    def serialize_money(self,value): return None if value is None else format(value,"f")


class TypeBreakdown(ApiModel):
    resource_type: Literal["material","labor","equipment","general_cost"]
    initial_estimate_irr: Decimal
    revised_estimate_irr: Decimal = Decimal(0)
    actual_cost_irr: Decimal
    remaining_physical_cost_irr: Decimal = Decimal(0)
    forecast_final_irr: Decimal
    @field_serializer("initial_estimate_irr","revised_estimate_irr","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr")
    def serialize_money(self,value): return format(value,"f")


class PriceVariance(ApiModel):
    estimate_line_id: UUID;resource_id:UUID;resource_code:str;resource_title:str;resource_type:str;variance_irr:Decimal
    activity_external_id:str|None=None;activity_title:str|None=None;wbs_code:str|None=None;base_unit:str|None=None
    revised_quantity:Decimal|None=None;remaining_quantity:Decimal|None=None
    estimate_base_unit_price_irr:Decimal|None=None;current_unit_price_irr:Decimal|None=None
    price_variance_percent:Decimal|None=None;actual_cost_irr:Decimal|None=None
    remaining_physical_cost_irr:Decimal|None=None;forecast_final_irr:Decimal|None=None;impact_share_percent:Decimal|None=None
    current_price_scope:str|None=None;current_price_effective_from:date|None=None
    current_price_version_id:UUID|None=None;estimate_price_version_id:UUID|None=None
    @field_serializer("variance_irr","revised_quantity","remaining_quantity","estimate_base_unit_price_irr","current_unit_price_irr","price_variance_percent","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr","impact_share_percent")
    def serialize_money(self,value):return None if value is None else format(value,"f")


class QuantityVariance(ApiModel):
    estimate_line_id:UUID;resource_id:UUID;resource_code:str;resource_title:str;resource_type:str;variance_quantity:Decimal
    activity_external_id:str|None=None;activity_title:str|None=None;wbs_code:str|None=None;base_unit:str|None=None
    initial_quantity:Decimal|None=None;revised_quantity:Decimal|None=None;executed_quantity:Decimal|None=None;remaining_quantity:Decimal|None=None
    quantity_variance_percent:Decimal|None=None;source_method:str|None=None;progress_snapshot_id:UUID|None=None
    actual_cost_irr:Decimal|None=None;remaining_physical_cost_irr:Decimal|None=None;forecast_final_irr:Decimal|None=None;impact_share_percent:Decimal|None=None
    @field_serializer("variance_quantity","initial_quantity","revised_quantity","executed_quantity","remaining_quantity","quantity_variance_percent","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr","impact_share_percent")
    def serialize_quantity(self,value):return None if value is None else format(value,"f")


class ReportWarning(ApiModel):
    code:str;message:str;estimate_line_id:UUID|None=None
    resource_id:UUID|None=None;resource_code:str|None=None;activity_external_id:str|None=None
    severity:str|None=None;excluded_from_calculation:bool|None=None;affected_metric_keys:list[str]|None=None


class ProgressQuality(ApiModel):
    complete:bool
    manual_override_count:int=0
    task_fallback_count:int=0
    missing_count:int=0
    assignment_actual_count:int=0
    assignment_percent_fallback_count:int=0


class LiveReportResponse(ApiModel):
    reporting_date:date
    progress_snapshot_id:UUID
    metrics:LiveMetrics
    breakdown:list[TypeBreakdown]
    top_price_variances:list[PriceVariance]
    top_quantity_variances:list[QuantityVariance]
    warnings:list[ReportWarning]
    calculation_status:Literal["complete","incomplete"]="complete"
    incomplete_metric_keys:list[str]=Field(default_factory=list)
    missing_price_count:int=0
    excluded_estimate_line_count:int=0
    excluded_estimate_line_ids:list[UUID]=Field(default_factory=list)
    progress_quality:ProgressQuality|None=None


class ReportVarianceListResponse(ApiModel):
    items:list[PriceVariance|QuantityVariance]
    page:int
    page_size:int
    total_items:int
    total_pages:int


class ReportSnapshotCreate(ApiModel):
    reporting_date:date
    progress_snapshot_id:UUID|None=None


class ReportSnapshotReference(ApiModel):
    report_snapshot_id:UUID
    organization_id:UUID
    project_id:str=Field(pattern=r"^[A-Za-z0-9_-]+$")
    issued_at:datetime
    issued_by:UUID
    progress_snapshot_id:UUID
    resource_version_ids:list[UUID]=Field(min_length=1)
    price_version_ids:list[UUID]=Field(min_length=1)
    invoice_ids:list[UUID]
    unit_conversion_ids:list[UUID]
    calculated_metrics:dict[str,str]=Field(min_length=1)
    immutable:Literal[True]
