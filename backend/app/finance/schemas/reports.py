from datetime import date,datetime
from decimal import Decimal
from typing import Annotated,Literal
from uuid import UUID

from pydantic import Field,field_serializer

from .base import ApiModel


class LiveMetrics(ApiModel):
    #: None when a line in the project states no baseline of its own. A total built
    #: from some of its lines is not the total, and a number is not the way to say so.
    initial_estimate_irr: Decimal | None
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
    """One resource type's share, with the same nullability as the totals above it.

    `initialEstimateIrr` and `revisedEstimateIrr` are nullable, and the two figures DERIVED
    from them are too -- whenever the estimate behind a row is unknown, the remaining cost
    and the forecast computed from it are unknown as well, and the response has to be able
    to say so rather than raise a validation error. `LiveMetrics` and `WbsNode` both carry
    the same null.

    A row with lines that state no baseline is NOT one of those cases. It publishes the sum
    of the lines that do state one, `missingEstimateLineCount` says how many it could not
    include, and `calculationStatus` is `incomplete`. A subtotal a reader can see and
    qualify beats a blank they can only wonder about -- and the blank was reaching them for
    equipment, which this file states no price for anywhere, so the material estimate on the
    same row disappeared with it.

    Nullable is not the same as defaulted. `calculate_live_report` always states both
    figures for a row it could compute, so a null here means the calculation said so.
    """
    resource_type: Literal["material","labor","equipment","general_cost"]
    initial_estimate_irr: Decimal | None
    revised_estimate_irr: Decimal | None = Decimal(0)
    actual_cost_irr: Decimal
    remaining_physical_cost_irr: Decimal | None = Decimal(0)
    forecast_final_irr: Decimal | None
    calculation_status: Literal["complete","incomplete"] = "complete"
    excluded_estimate_line_count: int = 0
    #: Lines of this type that state no baseline of their own, and so are not in the two
    #: estimate figures above. Zero means the row's estimate is its total.
    missing_estimate_line_count: int = 0
    @field_serializer("initial_estimate_irr","revised_estimate_irr","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr")
    def serialize_money(self,value): return None if value is None else format(value,"f")


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
    #: What kind of number executedQuantity is, beside which field it came from. Notably
    #: "work_effort" means it is reported effort in an unstated unit rather than a measured
    #: quantity in baseUnit -- see PROGRESS_WORK_NOT_QUANTITY. None when nothing was
    #: measured at all. Typed as str, like source_method beside it, so a new kind added in
    #: the domain cannot turn a report into a 500 at response validation.
    measurement_type:str|None=None
    #: Whether this line reached a progress source at all, and if not, why:
    #: "mapped" | "unmapped_assignment" | "unmapped_activity" | "progress_not_available".
    #: Read it together with executedQuantity, which is 0 in three of those four cases:
    #: "mapped" with 0 executed is a source that measured zero, and any other status with 0
    #: executed is an absence of data. Before this field the two were indistinguishable.
    progress_status:str|None=None
    actual_cost_irr:Decimal|None=None;remaining_physical_cost_irr:Decimal|None=None;forecast_final_irr:Decimal|None=None;impact_share_percent:Decimal|None=None
    price_available:bool=True
    @field_serializer("variance_quantity","initial_quantity","revised_quantity","executed_quantity","remaining_quantity","quantity_variance_percent","actual_cost_irr","remaining_physical_cost_irr","forecast_final_irr","impact_share_percent")
    def serialize_quantity(self,value):return None if value is None else format(value,"f")


class ReportWarning(ApiModel):
    code:str;message:str;estimate_line_id:UUID|None=None
    resource_id:UUID|None=None;resource_code:str|None=None;activity_external_id:str|None=None
    severity:str|None=None;excluded_from_calculation:bool|None=None;affected_metric_keys:list[str]|None=None
    #: Present on the three progress codes, absent elsewhere: which of the four progress
    #: states this line is in. It says whether the warning means "the data is somewhere
    #: else" or "nobody has reported it", which the code alone does not.
    progress_status:str|None=None
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
    #: A subset of assignment_actual_count, not a sibling of it: lines whose executed
    #: quantity is reported work effort rather than a measured quantity. The value did come
    #: from the assignment's actual, so it is counted there too; this says how many of those
    #: are effort. Non-zero always forces complete=False.
    work_as_quantity_count:int=0
    #: unmapped_line_count split into the two situations behind it, because they are fixed
    #: by different people: unmapped_assignment_count is lines naming an assignment that
    #: matched nothing (a broken reference on the line), unmapped_activity_count is lines
    #: reachable only through an activity that matched nothing, or naming neither. The two
    #: always sum to unmapped_line_count, which keeps its previous meaning and value.
    #:
    #: The third state, PROGRESS_NOT_AVAILABLE, is missing_count above -- a line that did
    #: reach an assignment which reported nothing. It is not repeated here under a second
    #: name.
    unmapped_assignment_count:int=0
    unmapped_activity_count:int=0
    #: These three partition every estimate line read for the reporting date, so their sum
    #: is the line count. General cost is its own bucket because progress does not apply
    #: to it, which previously left those lines in no bucket at all.
    mapped_line_count:int=0
    unmapped_line_count:int=0
    general_cost_line_count:int=0


class LiveReportResponse(ApiModel):
    reporting_date:date
    #: None when the Core snapshot behind this calculation has never been pinned. Reading a
    #: report does not create a Finance reference -- viewing a page must not write -- so
    #: until something is issued or overridden there is no Finance identifier to give. It
    #: appears as soon as one exists. Clients must tolerate null and must not substitute
    #: hostSnapshotId for it: one is a Finance UUID, the other a Core bigint.
    progress_snapshot_id:UUID|None=None
    #: Which Core snapshot was actually calculated from, pinned or not.
    host_snapshot_id:int|None=None
    metrics:LiveMetrics
    breakdown:list[TypeBreakdown]
    top_price_variances:list[PriceVariance]
    top_quantity_variances:list[QuantityVariance]
    warnings:list[ReportWarning]
    calculation_status:Literal["complete","incomplete"]="complete"
    incomplete_metric_keys:list[str]=Field(default_factory=list)
    missing_price_count:int=0
    #: Estimate lines that state no baseline. When this is not zero, `initialEstimateIrr`
    #: is the sum of the lines that DO state one -- a subtotal, named as such by
    #: `incompleteMetricKeys` -- rather than the project's estimate.
    missing_estimate_line_count:int=0
    excluded_estimate_line_count:int=0
    #: How many estimate lines the figures above actually rest on, and how many the
    #: project has. The metrics are sums over the computable lines; without the pair a sum
    #: over 2 of 715 lines reads exactly like a sum over all 715.
    computed_line_count:int=0
    total_line_count:int=0
    excluded_estimate_line_ids:list[UUID]=Field(default_factory=list,
        description="Reporting-only: names individual estimate lines and is absent from the finance.view projection.")
    progress_quality:ProgressQuality|None=Field(default=None,
        description="Aggregate counts only; named records stay in excludedEstimateLineIds. Present in the finance.view projection alongside missingPriceCount, which is the same kind of fact.")


class OperationalOverviewResponse(ApiModel):
    """Read-only operational projection for finance.view.

    Deliberately narrower than LiveReportResponse: reporting-only fields stay
    behind finance_report.view. The completeness counters are in, because they qualify the
    operational metrics themselves, and progressQuality joins them for the same reason --
    it is aggregate counts, naming no record, and the reader of these metrics needs to know
    how many lines the progress feed could not answer for. excludedEstimateLineIds stays
    out: it names individual estimate lines.
    """

    reporting_date:date
    #: None until the Core snapshot behind this calculation has been pinned. This is a
    #: read projection, and reading does not create a Finance reference.
    progress_snapshot_id:UUID|None=None
    #: Which Core snapshot was calculated from, pinned or not. A Core bigint -- never
    #: interchangeable with the Finance UUID above.
    host_snapshot_id:int|None=None
    metrics:LiveMetrics
    breakdown:list[TypeBreakdown]
    top_price_variances:list[PriceVariance]
    top_quantity_variances:list[QuantityVariance]
    warnings:list[ReportWarning]
    calculation_status:Literal["complete","incomplete"]="complete"
    incomplete_metric_keys:list[str]=Field(default_factory=list)
    missing_price_count:int=0
    #: The same counter as on the full report: it qualifies an operational metric, so it
    #: belongs in the operational projection beside missingPriceCount.
    missing_estimate_line_count:int=0
    excluded_estimate_line_count:int=0
    #: How many estimate lines the figures above actually rest on, and how many the
    #: project has. The metrics are sums over the computable lines; without the pair a sum
    #: over 2 of 715 lines reads exactly like a sum over all 715.
    computed_line_count:int=0
    total_line_count:int=0
    progress_quality:ProgressQuality|None=None


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
    def serialize_money(self,value):return None if value is None else format(value,"f")


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
    # reportingDate is the selected schedule period; actualDataThroughDate is the latest
    # effective financial document inside it. They are intentionally not conflated.
    reporting_date:date
    actual_data_through_date:date|None=None
    progress_snapshot_id:UUID|None=None
    estimate_source:Literal["unavailable","schedule","manual_plan"]="unavailable"
    actual_source:Literal["confirmed_financial_documents"]="confirmed_financial_documents"
    calculation_status:Literal["complete","incomplete"]="complete"
    warnings:list[ReportWarning]=Field(default_factory=list)


class WbsNode(ApiModel):
    """One WBS stage, with its whole subtree rolled into it.

    `moneyRequiredIrr`, `remainingPhysicalCostIrr` and `forecastFinalIrr` are null when the
    engine could not compute them for this node -- a missing current price, or a unit it
    cannot convert. Null rather than "0", for the same reason executed quantity is null
    rather than zero: an amount nobody could work out is not an amount of nothing.
    `calculationStatus` says which of the two a null is.
    """
    wbs_code:str
    title:str|None=None
    parent_wbs_code:str|None=None
    #: Activities at or below this node, counted the way the activity catalogue counts them:
    #: distinct activity codes, so tasks sharing a code count once and a task carrying no
    #: resolvable code counts not at all.
    activity_count:int=0
    child_count:int=0
    estimate_line_count:int=0
    #: Of those lines, how many state no baseline of their own. The estimate figures below
    #: are the sum of the rest, which is why this number has to travel with them.
    missing_estimate_line_count:int=0
    initial_estimate_irr:Decimal|None
    revised_estimate_irr:Decimal|None=Decimal(0)
    actual_cost_irr:Decimal
    remaining_physical_cost_irr:Decimal|None=None
    money_required_irr:Decimal|None=None
    forecast_final_irr:Decimal|None=None
    calculation_status:Literal["complete","incomplete"]="complete"
    #: Actual cost at this node split by resource type.
    breakdown:dict[str,Decimal]=Field(default_factory=dict)

    @field_serializer("initial_estimate_irr","revised_estimate_irr","actual_cost_irr",
                      "remaining_physical_cost_irr","money_required_irr","forecast_final_irr")
    def serialize_money(self,value):return None if value is None else format(value,"f")

    @field_serializer("breakdown")
    def serialize_breakdown(self,value):
        return {kind:(None if amount is None else format(amount,"f")) for kind,amount in value.items()}


class WbsReportResponse(ApiModel):
    """The live report rolled up to WBS stages.

    The three actual-cost figures partition the project exactly:
    `sum(items.actualCostIrr)` over the root level, plus `unattributedActualIrr`, plus
    `unmappedWbsActualIrr`, equals `totals.actualCostIrr`. They are separate because they
    are fixed by different people -- one is an invoice never tied to an estimate line, the
    other an estimate line whose activity carries no stage.

    THE ESTIMATE IS PARTITIONED THE SAME WAY, AND UNTIL NOW WAS NOT
    `sum(items.initialEstimateIrr)` plus `unmappedEstimateIrr` equals
    `totals.initialEstimateIrr`. `unmappedEstimateLineCount` said how MANY lines reached no
    stage and nothing said what they were WORTH, so a reader adding the stages up got a
    smaller number than the project's own and had nothing to explain the gap with.
    Measured on the candidate: 408,000,000 rial across 75 lines, missing from the stage
    total and disclosed nowhere -- while the same response has disclosed the actual-cost
    equivalent all along.
    """
    reporting_date:date
    progress_snapshot_id:UUID|None=None
    host_snapshot_id:int|None=None
    #: The level requested, or null when children of a specific parent were requested.
    level:int|None=None
    parent_wbs_code:str|None=None
    items:list[WbsNode]
    unattributed_actual_irr:Decimal=Decimal(0)
    unmapped_wbs_actual_irr:Decimal=Decimal(0)
    unmapped_estimate_line_count:int=0
    #: What those lines are worth. Null when the estimate behind them cannot be worked out
    #: at all -- the same null `initialEstimateIrr` uses, and never a stand-in zero, which
    #: would read as "they are worth nothing" rather than "nobody could say".
    unmapped_estimate_irr:Decimal|None=Decimal(0)
    totals:LiveMetrics
    calculation_status:Literal["complete","incomplete"]="complete"
    warnings:list[ReportWarning]=Field(default_factory=list)

    @field_serializer("unattributed_actual_irr","unmapped_wbs_actual_irr",
                      "unmapped_estimate_irr")
    def serialize_money(self,value):return None if value is None else format(value,"f")
