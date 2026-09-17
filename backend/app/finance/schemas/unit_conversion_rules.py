# -*- coding: utf-8 -*-
"""What the conversion-rule and mismatch endpoints accept and answer.

Every factor and every money value is a STRING on the wire. A factor of 22 is exact and a
JSON number would pass it through a float on the way out; on a price divided by it, that is
a rounding error in a figure somebody signs.

A blocked calculation is a successful response. `conversion_rule_required` is an ordinary,
expected state of a half-configured project -- not a 500, and not a zero. It travels as a
200 carrying the reason, the two units, the identifiers and where to go next.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ApiModel

ScopeType = Literal["global", "organization", "project", "provider", "category",
                    "provider_item"]
ConversionMethod = Literal["factor", "formula"]
RuleStatus = Literal["draft", "approved", "rejected", "superseded"]
IssueStatus = Literal["open", "resolved", "obsolete"]

UnitMatchStatus = Literal["matched", "convertible_by_registry", "conversion_rule_available",
                          "unit_selection_required", "daily_price_unit_missing",
                          "conversion_rule_required", "incompatible"]

CalculationStatus = Literal["ready", "matched", "convertible_by_registry",
                            "conversion_rule_available", "unit_selection_required",
                            "daily_price_unit_missing", "conversion_rule_required",
                            "incompatible", "daily_price_missing", "quantity_missing"]


class ConversionRuleResponse(ApiModel):
    """One stored rule: `1 from_unit = factor to_unit`, at a stated scope.

    The direction is a column rather than a convention, so a reader never has to work out
    which way round the number goes.
    """

    id: UUID
    organization_id: UUID
    project_id: str | None = None
    provider_item_id: UUID | None = None
    provider_id: UUID | None = None
    category: str | None = None
    scope_type: ScopeType

    #: Whether somebody admitted this rule is product-dependent, and who. All three are
    #: null/false on the ordinary rule; together they are what lets a reader of a price
    #: see that a broad claim stands behind it and whose claim it is.
    product_dependent_acknowledged: bool = False
    product_dependent_acknowledged_by: UUID | None = None
    product_dependent_acknowledged_at: datetime | None = None

    from_unit: str
    to_unit: str
    conversion_method: ConversionMethod
    #: Exact, and a string for that reason.
    factor_value: str | None = None
    formula_definition: dict | None = None
    formula_schema_version: str | None = None
    direction_definition: str

    status: RuleStatus
    version: int
    effective_from: date
    effective_to: date | None = None
    supersedes_rule_id: UUID | None = None
    evidence_source: str | None = None
    reason: str
    created_by: UUID
    created_at: datetime
    approved_by: UUID | None = None
    approved_at: datetime | None = None


class ConversionRuleListResponse(ApiModel):
    items: list[ConversionRuleResponse] = Field(default_factory=list)
    #: The units a rule may name, and which crossings into each are product-dependent, so
    #: the settings form can explain an unavailable scope rather than only refusing a save.
    units: list[dict] = Field(default_factory=list)


class ConversionRuleCreate(ApiModel):
    """A person stating a conversion. It arrives as a DRAFT and changes nothing yet."""

    scope_type: ScopeType
    from_unit: str = Field(min_length=1, max_length=32)
    to_unit: str = Field(min_length=1, max_length=32)
    conversion_method: ConversionMethod = "factor"
    #: `1 from_unit = factor_value to_unit`. Strictly positive; the price arithmetic is
    #: derived from this in the domain and never stored.
    factor_value: Decimal | None = Field(default=None, gt=0)
    formula_definition: dict | None = None
    formula_schema_version: str | None = Field(default=None, max_length=32)
    direction_definition: str | None = Field(default=None, max_length=64)

    project_id: str | None = None
    provider_id: UUID | None = None
    provider_item_id: UUID | None = None
    category: str | None = Field(default=None, max_length=64)

    effective_from: date | None = None
    supersedes_rule_id: UUID | None = None
    evidence_source: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=1, max_length=500)

    #: "I know this crossing depends on the product, and I am stating it anyway."
    #:
    #: Required only for a rule that crosses dimensions at a scope wider than one listing
    #: -- «شاخه» to «کیلوگرم» for a whole project, say. Without it such a rule is refused
    #: exactly as before. `registryUnits()` already tells the client which crossings are
    #: product-dependent, so the checkbox appears on precisely those and nowhere else.
    #:
    #: Sending it for a crossing that does NOT depend on the product is not an error; it
    #: is stored as false, because an admission about nothing would later read as a
    #: warning about a rule that never needed one.
    product_dependent_acknowledged: bool = False


class ConversionRuleApprove(ApiModel):
    reason: str | None = Field(default=None, max_length=500)


class ConversionRuleSupersede(ApiModel):
    effective_to: date | None = None
    reason: str | None = Field(default=None, max_length=500)


class ConversionRulePreviewResponse(ApiModel):
    """What a rule would do to a price, and whether it is allowed to.

    A draft may be previewed -- that is what a draft is for -- and `appliedToCalculations`
    says plainly that it is not in use.
    """

    rule_id: str
    version: int
    status: RuleStatus
    applied_to_calculations: bool
    from_unit: str
    to_unit: str
    conversion_method: str | None = None
    conversion_multiplier: str | None = None
    source_price_irr: str | None = None
    converted_price_irr: str | None = None
    conversion_source: str | None = None


class ConversionIssueResponse(ApiModel):
    """A mismatch that blocked a daily estimate, as a record somebody can be given.

    `occurrenceCount` is why one open row exists rather than two hundred: a preview
    refreshed all afternoon counts, it does not multiply.
    """

    id: UUID
    project_id: str
    estimate_line_id: UUID | None = None
    finance_resource_id: UUID | None = None
    provider_item_id: UUID | None = None
    source_task_uid: int | None = None
    source_assignment_uid: int | None = None
    source_resource_uid: int | None = None
    resource_unit: str | None = None
    daily_price_unit: str | None = None
    error_code: str
    status: IssueStatus
    first_detected_at: datetime
    last_detected_at: datetime
    occurrence_count: int
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None
    resolution_rule_id: UUID | None = None


class ConversionIssueListResponse(ApiModel):
    items: list[ConversionIssueResponse] = Field(default_factory=list)


class DailyEstimateResponse(ApiModel):
    """The whole calculation for one line, including the reason it is blocked.

    Money and quantities are strings; anything the backend could not establish is null and
    never zero. `userMessageFa` is the sentence for the person who can fix it.
    """

    estimate_line_id: str | None = None

    quantity: str | None = None
    quantity_source: str | None = None
    daily_quantity: str | None = None
    daily_quantity_source: str | None = None
    daily_quantity_source_field: str | None = None
    daily_quantity_as_of: date | None = None
    effective_daily_quantity: str | None = None
    effective_daily_quantity_source: str | None = None

    resource_id: str | None = None
    resource_name: str | None = None
    source_resource_uid: int | None = None
    source_task_uid: int | None = None
    source_assignment_uid: int | None = None

    resource_unit: str | None = None
    resource_unit_source: str | None = None
    resource_unit_confidence: str | None = None
    unit_selection_required: bool = False

    provider_item_id: str | None = None
    daily_price_unit: str | None = None

    unit_match_status: UnitMatchStatus | None = None
    unit_mismatch: bool = False
    conversion_rule_required: bool = False
    applied_conversion_rule_id: str | None = None
    applied_conversion_rule_version: int | None = None
    #: True when the rule behind this number is one somebody admitted depends on the
    #: product -- a broad claim rather than a weighing of the item being priced.
    applied_conversion_rule_is_product_dependent: bool = False
    conversion_method: str | None = None
    conversion_multiplier: str | None = None

    initial_unit_price_irr: str | None = None
    initial_unit_price_source: str | None = None
    initial_estimated_cost_irr: str | None = None
    initial_estimated_cost_source: str | None = None

    daily_unit_price_irr: str | None = None
    converted_daily_unit_price_irr: str | None = None
    daily_estimated_cost_irr: str | None = None

    calculation_status: CalculationStatus
    calculation_reason: str | None = None
    user_message_fa: str | None = None
    action_required: str | None = None
    action_target: str | None = None
    conversion_issue_id: str | None = None


class DailyEstimateListResponse(ApiModel):
    items: list[DailyEstimateResponse] = Field(default_factory=list)
