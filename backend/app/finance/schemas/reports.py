from datetime import date,datetime
from decimal import Decimal
from typing import Annotated,Literal
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
    calculation_status: Literal["complete","incomplete"] = "complete"
    excluded_estimate_line_count: int = 0
    @field_serializer("initial_estimate_irr","revised_estimate_irr","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr")
    def serialize_money(self,value): return format(value,"f")


class PriceVariance(ApiModel):
    variance_kind: Literal["price"] = "price"
    estimate_line_id: UUID;resource_id:UUID;resource_code:str;resource_title:str;resource_type:str;variance_irr:Decimal
    activity_external_id:str|None=None;activity_title:str|None=None;wbs_code:str|None=None;base_unit:str|None=None
    revised_quantity:Decimal|None=None;remaining_quantity:Decimal|None=None
    estimate_base_unit_price_irr:Decimal|None=None;current_unit_price_irr:Decimal|None=None
    price_variance_percent:Decimal|None=None;actual_cost_irr:Decimal|None=None
    remaining_physical_cost_irr:Decimal|None=None;forecast_final_irr:Decimal|None=None;impact_share_percent:Decimal|None=None
    price_available:bool=True
    current_price_scope:str|None=None;current_price_effective_from:date|None=None
    current_price_version_id:UUID|None=None;estimate_price_version_id:UUID|None=None
    @field_serializer("variance_irr","revised_quantity","remaining_quantity","estimate_base_unit_price_irr","current_unit_price_irr","price_variance_percent","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr","impact_share_percent")
    def serialize_money(self,value):return None if value is None else format(value,"f")


class QuantityVariance(ApiModel):
    variance_kind: Literal["quantity"] = "quantity"
    estimate_line_id:UUID;resource_id:UUID;resource_code:str;resource_title:str;resource_type:str;variance_quantity:Decimal
    activity_external_id:str|None=None;activity_title:str|None=None;wbs_code:str|None=None;base_unit:str|None=None
    initial_quantity:Decimal|None=None;revised_quantity:Decimal|None=None;executed_quantity:Decimal|None=None;remaining_quantity:Decimal|None=None
    quantity_variance_percent:Decimal|None=None;source_method:str|None=None;progress_snapshot_id:UUID|None=None
    actual_cost_irr:Decimal|None=None;remaining_physical_cost_irr:Decimal|None=None;forecast_final_irr:Decimal|None=None;impact_share_percent:Decimal|None=None
    price_available:bool=True
    @field_serializer("variance_quantity","initial_quantity","revised_quantity","executed_quantity","remaining_quantity","quantity_variance_percent","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr","impact_share_percent")
    def serialize_quantity(self,value):return None if value is None else format(value,"f")


class ReportWarning(ApiModel):
    code:str;message:str;estimate_line_id:UUID|None=None
    resource_id:UUID|None=None;resource_code:str|None=None;activity_external_id:str|None=None
    severity:str|None=None;excluded_from_calculation:bool|None=None;affected_metric_keys:list[str]|None=None
    # QUANTITY_OVERRUN carries how far past the revised quantity the line went. The model
    # forbids extras, so leaving these undeclared turned every report containing an
    # overrun into a 500 at response validation.
    deviation_quantity:str|None=None;deviation_percent:str|None=None


class ProgressQuality(ApiModel):
    complete:bool
    manual_override_count:int=0
    task_fallback_count:int=0
    #: Lines that DID reach an assignment but found no usable quantity on it. Lines that
    #: reached no assignment are counted by unmapped_line_count, not here.
    missing_count:int=0
    assignment_actual_count:int=0
    assignment_percent_fallback_count:int=0
    #: These three partition every estimate line read for the reporting date, so their sum
    #: is the line count. General cost is its own bucket because progress does not apply
    #: to it, which previously left those lines in no bucket at all.
    mapped_line_count:int=0
    unmapped_line_count:int=0
    general_cost_line_count:int=0


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
    excluded_estimate_line_ids:list[UUID]=Field(default_factory=list,
        description="Reporting-only: names individual estimate lines and is absent from the finance.view projection.")
    progress_quality:ProgressQuality|None=Field(default=None,
        description="Reporting-only: progress-feed diagnostics, absent from the finance.view projection.")


class OperationalOverviewResponse(ApiModel):
    """Read-only operational projection for finance.view.

    Deliberately narrower than LiveReportResponse: reporting-only fields stay
    behind finance_report.view. The two completeness counters are in, because they
    qualify the operational metrics themselves; excludedEstimateLineIds and
    progressQuality name individual records and stay out.
    """

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


class ReportVarianceListResponse(ApiModel):
    # Discriminated so a mixed page cannot be validated into the wrong shape.
    items:list[Annotated[PriceVariance|QuantityVariance,Field(discriminator="variance_kind")]]
    page:int
    page_size:int
    total_items:int
    total_pages:int


class ReportSnapshotCreate(ApiModel):
    reporting_date:date
    progress_snapshot_id:UUID|None=None


class ReportSnapshotSummary(ApiModel):
    """One issued report, without the arrays the detail endpoint carries.

    A snapshot pins every resource, price, revision, conversion and invoice it was built
    from; sending those on a listing would grow the payload with the project rather than
    with the page. A count answers what a list is asked for.
    """

    report_snapshot_id:UUID
    reporting_date:date
    issued_at:datetime
    issued_by:UUID
    progress_snapshot_id:UUID
    invoice_count:int
    price_version_count:int


class ReportSnapshotListResponse(ApiModel):
    items:list[ReportSnapshotSummary]
    page:int
    page_size:int
    total_items:int
    total_pages:int


class ReportSnapshotReference(ApiModel):
    report_snapshot_id:UUID
    organization_id:UUID
    project_id:str=Field(pattern=r"^[A-Za-z0-9_-]+$")
    reporting_date:date
    issued_at:datetime
    issued_by:UUID
    progress_snapshot_id:UUID
    resource_version_ids:list[UUID]=Field(min_length=1)
    price_version_ids:list[UUID]=Field(min_length=1)
    invoice_ids:list[UUID]
    unit_conversion_ids:list[UUID]
    calculated_metrics:dict[str,str]=Field(min_length=1)
    immutable:Literal[True]


class MonthlyBreakdown(ApiModel):
    """Signed actual cost of one Persian month, split by the resource type of each line.

    Every invoice line carries a NOT NULL resource_id, so the four buckets are exhaustive
    and always sum to the month's actualCostIrr — there is no uncategorised remainder.
    """

    material:Decimal
    labor:Decimal
    equipment:Decimal
    general_cost:Decimal
    @field_serializer("material","labor","equipment","general_cost")
    def serialize_money(self,value):return format(value,"f")


class MonthlyPoint(ApiModel):
    persian_year:int=Field(ge=1)
    persian_month:int=Field(ge=1,le=12)
    actual_cost_irr:Decimal
    # None, never zero: no estimate line carries a planned date, so there is no monthly
    # baseline to report. Zero would assert that nothing was budgeted for this month.
    estimate_irr:Decimal|None=None
    # Documents that add cost (financial_effect_sign 1) and documents that remove it
    # (-1) are counted apart, so a reversal never reads as new purchasing activity.
    invoice_count:int=Field(ge=0)
    reversal_count:int=Field(ge=0)
    breakdown:MonthlyBreakdown
    @field_serializer("actual_cost_irr","estimate_irr")
    def serialize_money(self,value):return None if value is None else format(value,"f")


class MonthlyReportResponse(ApiModel):
    months:list[MonthlyPoint]
    window_start:date
    window_end:date
    estimate_source:Literal["unavailable","schedule","manual_plan"]="unavailable"
    actual_source:Literal["confirmed_financial_documents"]="confirmed_financial_documents"
    calculation_status:Literal["complete","incomplete"]="complete"
    warnings:list[ReportWarning]=Field(default_factory=list)
