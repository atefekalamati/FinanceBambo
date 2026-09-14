# -*- coding: utf-8 -*-
"""What the item-to-daily-price endpoints answer with, and what they accept.

Every money field is an optional string. Optional because an item nobody has mapped, or one
whose units cannot be crossed, genuinely has no price -- and `null` is how JSON says that,
where `0` would say the material is free. A string because these are Decimals: a JSON number
would go through a float on the way out and stop being the figure the database holds.

Every response that can be unresolved carries BOTH a machine status and a Persian reason.
The status is what the table styles on; the reason is what the person who can fix it reads.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ApiModel


class ItemPriceStatusResponse(ApiModel):
    """One estimate line's pricing state, as the financial-items table reads it."""

    estimate_line_id: str
    status: Literal["ready", "needs_product", "needs_unit", "needs_factor",
                    "incompatible", "no_price"]
    status_label: str
    reason: str | None = None

    #: The daily price converted into the official calculation unit. Null unless ready.
    converted_daily_unit_price_irr: str | None = None
    #: quantity x converted price. Null when either is unknown -- never zero.
    daily_item_cost_irr: str | None = None

    selected_unit: str | None = None
    source_unit: str | None = None
    conversion_factor: str | None = None
    quantity: str | None = None

    provider_item_id: str | None = None
    provider_name: str | None = None
    product_name: str | None = None
    product_external_id: str | None = None
    category: str | None = None
    worksheet: str | None = None
    workflow_date_jalali: str | None = None
    mapping_version: int | None = None
    conversion_factor_id: str | None = None


class CandidateProductResponse(ApiModel):
    """One listing a person could choose, with what the sheet says about it.

    `specs` carries the worksheet's own category columns verbatim -- an angle's thickness
    and branch count, a brick's code and dimensions. They are what lets somebody tell two
    listings apart, and they are never invented: a category whose sheet states no thickness
    has no thickness key.
    """

    provider_item_id: str
    external_id: str | None = None
    external_name: str | None = None
    category: str | None = None
    category_label: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    product_type: str | None = None
    display_name: str | None = None

    source_unit: str | None = None
    source_unit_code: str | None = None
    source_basis: str | None = None

    current_price_irr: str | None = None
    raw_price: str | None = None
    source_currency: str | None = None
    workflow_date_jalali: str | None = None
    workflow_date_gregorian: date | None = None

    active: bool = True
    inactive_reason: str | None = None
    worksheet: str | None = None
    specs: dict = Field(default_factory=dict)
    spec_columns: list[dict] = Field(default_factory=list)


class CandidateListResponse(ApiModel):
    items: list[CandidateProductResponse]
    page: int
    page_size: int
    total_items: int


class MappingFiltersResponse(ApiModel):
    """What the modal may filter by, read from the data rather than hard-coded."""

    providers: list[dict] = Field(default_factory=list)
    product_types: list[str] = Field(default_factory=list)
    categories: list[dict] = Field(default_factory=list)
    units: list[dict] = Field(default_factory=list)


class ItemPriceMappingCreate(ApiModel):
    """A person saying which listing prices this line, and in which unit."""

    provider_item_id: UUID
    #: Validated against the unit registry in the service, so the error names the registry
    #: rather than a schema constraint a reader cannot look up.
    selected_unit: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=500)
    effective_from: date | None = None


class ItemPriceMappingResponse(ApiModel):
    id: UUID
    organization_id: UUID
    project_id: str
    estimate_line_id: UUID | None = None
    finance_resource_id: UUID | None = None
    source_assignment_uid: int | None = None
    source_task_uid: int | None = None
    source_resource_uid: int | None = None
    provider_item_id: UUID
    selected_unit: str
    source_price_unit: str | None = None
    source_price_basis: str | None = None
    conversion_status: Literal["automatic", "factor", "incompatible", "unknown"]
    conversion_factor_id: UUID | None = None
    version: int
    effective_from: date
    superseded_at: datetime | None = None
    superseded_by: UUID | None = None
    created_by: UUID
    created_at: datetime
    reason: str


class ConvertedPricePreviewResponse(ApiModel):
    """What a listing would cost in a unit, before anything is saved."""

    provider_item_id: str
    product_name: str | None = None
    provider_name: str | None = None
    status: Literal["ready", "needs_product", "needs_unit", "needs_factor",
                    "incompatible", "no_price"]
    status_label: str
    reason: str | None = None
    source_price_irr: str | None = None
    source_unit: str | None = None
    selected_unit: str | None = None
    converted_daily_unit_price_irr: str | None = None
    daily_item_cost_irr: str | None = None
    conversion_factor: str | None = None
    conversion_factor_id: str | None = None
    quantity: str | None = None
    workflow_date_jalali: str | None = None


class ItemPriceStatusListResponse(ApiModel):
    items: list[ItemPriceStatusResponse]
