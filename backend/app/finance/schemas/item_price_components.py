# -*- coding: utf-8 -*-
"""What the multi-component pricing endpoints answer with, and what they accept.

Every money field is an optional STRING. Optional because a component nobody has finished --
no product chosen, no usage measured, no price today -- genuinely has no cost, and `null` is
how JSON says that where `0` would say the material is free. A string because these are
Decimals: a JSON number goes through a float on the way out and stops being the figure the
database holds.

Every response that can be unresolved carries BOTH a machine status and a Persian reason.
The status is what the table styles on; the reason is what the person who can fix it reads.

A ROW'S STATUS IS NOT A COMPONENT'S
A component fails one way at a time -- it needs a unit, or a factor, or a price. A row is an
aggregate and has two states no component has: `needs_components` (nobody has started) and
`partially_unresolved` (some materials priced and some did not, so the total is real and
incomplete and must say both). The two Literals are kept apart so neither can be answered
with the other's vocabulary.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ApiModel

#: How one component can fail. One missing answer at a time.
ComponentStatus = Literal["ready", "needs_product", "needs_product_type", "needs_unit",
                          "needs_usage_quantity", "unknown_source_unit", "needs_factor",
                          "incompatible", "no_price"]

#: How a ROW can stand. Every component status, plus the two that only an aggregate has.
RowStatus = Literal["ready", "needs_components", "partially_unresolved", "needs_product",
                    "needs_product_type", "needs_unit", "needs_usage_quantity",
                    "unknown_source_unit", "needs_factor", "incompatible", "no_price"]

UsageMode = Literal["per_msp_unit", "total_quantity"]


class ItemPriceRowStatusResponse(ApiModel):
    """One estimate line's pricing state, as the financial-items table reads it.

    The counts are not decoration: a reader looking at «۴۰٬۶۴۴٬۰۰۰٬۰۰۰» needs to know it
    came from two of three materials before they treat it as the line's cost.
    """

    estimate_line_id: str
    status: RowStatus
    status_label: str
    reason: str | None = None

    #: The sum of the components that resolved. Null when none did -- never zero.
    daily_item_cost_irr: str | None = None

    component_count: int = 0
    ready_component_count: int = 0
    unresolved_component_count: int = 0

    #: The «منبع» column. One component names its product; several say how many there are.
    provider_name: str | None = None
    product_name: str | None = None
    source_summary: str | None = None

    #: The two units the «ریز برآورد» table shows side by side, and the gap between them
    #: is the only thing stopping a daily price. Somebody about to write a conversion
    #: factor has to know FROM what TO what -- the two values the conversion dialog is
    #: filled with. Null on a line with no component, and null on a line with several,
    #: exactly as `providerName` and `productName` are: one row cannot state two units.
    source_price_unit: str | None = None
    selected_unit: str | None = None

    #: Where the number that crossed those units came from:
    #: provider_item | conversion_rule | registry | null.
    #:
    #: Without it two figures of very different standing share one column -- a weighing of
    #: this exact product and a rule written for a whole category look identical, and a
    #: reader cannot tell which they are being asked to trust. Null when nothing was
    #: converted, and null on a multi-component row for the same reason as the units.
    factor_source: str | None = None


class ItemPriceRowStatusListResponse(ApiModel):
    items: list[ItemPriceRowStatusResponse]


class PriceComponentResponse(ApiModel):
    """One material of one line: what it costs today, or which answer is missing.

    `reason` is the pricing reason -- why there is no number. `reason_text` is the person's
    own stated reason for adding this material. Two different sentences, and conflating them
    would lose the author's justification behind an automatic status message.
    """

    component_id: str
    id: str
    estimate_line_id: str
    provider_item_id: str

    status: ComponentStatus
    status_label: str
    reason: str | None = None

    #: Today's price converted into the chosen unit. Null unless it could be converted.
    converted_daily_unit_price_irr: str | None = None
    #: How much of this material the line uses, after the usage mode is applied.
    component_quantity: str | None = None
    #: quantity x converted price. Null when either is unknown -- never zero.
    component_daily_cost_irr: str | None = None

    selected_unit: str | None = None
    source_unit: str | None = None
    conversion_factor: str | None = None
    #: provider_item | conversion_rule | registry | null -- see the row status above.
    factor_source: str | None = None
    conversion_status: Literal["automatic", "factor", "incompatible", "unknown"] | None = None
    conversion_factor_id: str | None = None

    usage_mode: UsageMode | None = None
    usage_quantity: str | None = None
    usage_unit: str | None = None

    provider_name: str | None = None
    product_name: str | None = None
    product_external_id: str | None = None
    product_type: str | None = None
    category: str | None = None
    category_label: str | None = None
    worksheet: str | None = None
    workflow_date_jalali: str | None = None
    source_price_irr: str | None = None

    #: The worksheet's own columns for this category, verbatim. Never invented: a category
    #: whose sheet states no thickness has no thickness key.
    specs: dict = Field(default_factory=dict)
    spec_columns: list[dict] = Field(default_factory=list)

    active: bool = True
    version: int
    reason_text: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None


class PricedLineHeaderResponse(ApiModel):
    """What the schedule says about the activity being priced. The panel's header."""

    estimate_line_id: str
    activity_external_id: str | None = None
    title: str | None = None
    msp_unit: str | None = None
    msp_quantity: str | None = None
    msp_cost_irr: str | None = None
    original_unit_price_irr: str | None = None


class PriceComponentListResponse(ApiModel):
    """Every material of one line, with the row total beside them."""

    line: PricedLineHeaderResponse | None = None
    components: list[PriceComponentResponse] = Field(default_factory=list)
    total: ItemPriceRowStatusResponse | None = None


class PriceComponentCreate(ApiModel):
    """A person saying this activity uses this much of this material.

    `usage_quantity` is required and has NO default. A default of 1 would be this schema
    inventing the one number nobody else may: how much of a material an activity consumes is
    a judgement, and a silent 1 is that judgement made by the wrong party.
    """

    provider_item_id: UUID
    #: Validated against the unit registry in the service, so the error names the registry
    #: rather than a schema constraint a reader cannot look up.
    selected_unit: str = Field(min_length=1, max_length=32)
    usage_mode: UsageMode
    usage_quantity: Decimal = Field(ge=0)
    usage_unit: str | None = Field(default=None, max_length=32)
    product_type: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    effective_from: date | None = None


class PriceComponentDeactivate(ApiModel):
    """Retiring one material from a line. The reason is the whole record of why."""

    reason: str = Field(min_length=1, max_length=500)


class PriceComponentRow(ApiModel):
    """A stored component version, as written. The write endpoints' answer.

    This is the ROW, not the pricing: it reports what was approved and when, and the figures
    it carries are the ones that stood at approval time. What the material costs TODAY comes
    from the read endpoints, which recompute from the newest observation.
    """

    id: UUID
    component_id: UUID
    organization_id: UUID
    project_id: str
    estimate_line_id: UUID
    finance_resource_id: UUID | None = None
    provider_item_id: UUID
    category: str | None = None
    provider_id: UUID | None = None
    product_type: str | None = None
    selected_unit: str
    source_price_unit: str | None = None
    source_price_basis: str | None = None
    usage_mode: UsageMode | None = None
    usage_quantity_decimal: str | None = None
    usage_unit: str | None = None
    conversion_status: Literal["automatic", "factor", "incompatible", "unknown"]
    conversion_factor_id: UUID | None = None
    converted_daily_unit_price_irr: str | None = None
    component_quantity_decimal: str | None = None
    component_daily_cost_irr: str | None = None
    status: str | None = None
    reason: str
    active: bool
    version: int
    effective_from: date
    superseded_at: datetime | None = None
    superseded_by: UUID | None = None
    created_by: UUID
    created_at: datetime


class PriceComponentHistoryResponse(ApiModel):
    items: list[PriceComponentRow] = Field(default_factory=list)


class PriceComponentPreviewResponse(ApiModel):
    """What one component would cost, before anything is saved."""

    provider_item_id: str
    product_name: str | None = None
    provider_name: str | None = None
    status: ComponentStatus
    status_label: str
    reason: str | None = None
    source_price_irr: str | None = None
    source_unit: str | None = None
    selected_unit: str | None = None
    converted_daily_unit_price_irr: str | None = None
    component_quantity: str | None = None
    component_daily_cost_irr: str | None = None
    conversion_factor: str | None = None
    conversion_factor_id: str | None = None
    usage_mode: UsageMode | None = None
    usage_quantity: str | None = None
    msp_quantity: str | None = None
    workflow_date_jalali: str | None = None
