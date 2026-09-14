# -*- coding: utf-8 -*-
"""What the material price endpoints answer with.

Every money field is an integer-IRR string and every one of them is OPTIONAL. That is not
laziness about types: a listing whose newest observation could not be read has no price,
and the only honest way to say so in JSON is `null`. A zero here would be a claim that
something is free.

The provenance fields are not decoration either. A price with no source, no date and no
unit basis cannot be judged by the person reading it, so every price travels with the
provider that quoted it, the sheet date it was quoted on, the worksheet row it came from,
and what the sheet said its unit was -- which is not the same as the unit it is displayed
in, and the two are separate fields for exactly that reason.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ApiModel


class MaterialCategoryResponse(ApiModel):
    """One material category, counted from the database rather than from a constant."""

    category: str
    item_count: int
    active_count: int
    inactive_count: int


class MaterialCategoryListResponse(ApiModel):
    items: list[MaterialCategoryResponse]


class MaterialPriceResponse(ApiModel):
    """The newest observation for one provider listing, with everything needed to judge it."""

    provider_item_id: UUID
    external_id: str
    external_name: str
    category: str
    provider_name: str
    active: bool
    inactive_reason: str | None = None
    worksheet: str | None = None

    #: Integer IRR as a string, or null. Null means "we do not have a price for this",
    #: never "it costs nothing".
    current_price_irr: Decimal | None = None
    #: What the sheet actually said, before any conversion. Kept so a reader can check.
    raw_price: str | None = None
    source_currency: Literal["IRR", "TOMAN"] = "TOMAN"
    #: Brick's price per square metre, when the sheet states one. Never the primary price.
    secondary_price_irr: Decimal | None = None
    secondary_price_basis: str | None = None

    #: What the sheet said the unit was, verbatim -- «کیلو», or nothing at all. Absent for
    #: six of the seven categories, because the sheet does not say.
    source_unit: str | None = None
    #: The same thing as a Finance unit code, or null when the spelling is one the registry
    #: cannot name. Two fields because they answer two questions: what the supplier wrote,
    #: and what this system was able to make of it.
    source_unit_code: str | None = None
    #: The unit an authorised person chose for this category, if one has been chosen.
    display_unit: str | None = None
    #: The unit the returned price is actually in. Equal to the display unit when a
    #: conversion succeeded, and null when none was possible -- a reader must never have to
    #: infer which unit a number is in.
    target_unit: str | None = None
    #: `dimension` when units alone answered it, `manual` or `sheet_attribute` when a factor
    #: stored against this product did. Null when nothing was converted.
    factor_origin: str | None = None
    #: Present only when the displayed price is a CONVERTED one, and then it says exactly
    #: what was applied. A converted price with no explanation is a number nobody can check.
    conversion_factor: Decimal | None = None
    conversion_note: str | None = None

    workflow_date_raw: str | None = None
    workflow_date_jalali: str | None = None
    workflow_date_gregorian: date | None = None
    #: Which of four things `observedAt` holds. The sheet supplies no provider timestamp,
    #: so this is normally 'workflow_date' or 'fetch_time' and never silently 'provider'.
    observed_at_source: Literal["provider", "workflow_date", "fetch_time", "unknown"]
    observed_at: datetime
    fetched_at: datetime

    validation_status: Literal["pending", "valid", "needs_review", "rejected"]
    validation_reasons: list[str] = Field(default_factory=list)
    #: One of: resolved, stale, unresolved_price, unresolved_unit, incompatible_unit,
    #: missing_factor, unresolved_mapping, invalid_source, inactive. A status, not a guess:
    #: the reader is told which kind of nothing they are looking at. `missing_factor` and
    #: `incompatible_unit` are separate because the fix differs -- one needs somebody to
    #: measure this product, the other needs a different target unit.
    resolution_status: str
    resolution_reason: str | None = None

    source_row_number: int | None = None
    source_url: str | None = None

    #: What a person wrote about this listing. All optional, all null until somebody does:
    #: an unlabelled row is a row nobody has looked at, and saying so is the point.
    label: str | None = None
    label_display_name: str | None = None
    label_product_type: str | None = None
    label_source_basis: str | None = None
    finance_resource_id: UUID | None = None
    #: A mapping only counts once somebody approved it. False means either no mapping or
    #: an unapproved one, and the resolution status says which.
    mapping_approved: bool = False
    labelled_by: UUID | None = None
    labelled_by_name: str | None = None
    labelled_at: datetime | None = None
    label_version: int | None = None


class MaterialPriceListResponse(ApiModel):
    items: list[MaterialPriceResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class MaterialPriceHistoryResponse(ApiModel):
    """One observation in a listing's history. Append-only; nothing here is ever rewritten."""

    id: UUID
    normalized_price_irr: Decimal | None = None
    raw_price: str | None = None
    source_currency: Literal["IRR", "TOMAN"]
    workflow_date_raw: str | None = None
    workflow_date_jalali: str | None = None
    workflow_date_gregorian: date | None = None
    observed_at: datetime
    observed_at_source: str
    fetched_at: datetime
    validation_status: str
    validation_reasons: list[str] = Field(default_factory=list)
    source_worksheet: str | None = None
    source_row_number: int | None = None


class MaterialPriceHistoryListResponse(ApiModel):
    items: list[MaterialPriceHistoryResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ImportRunResponse(ApiModel):
    """One import, and what it did. A failed run keeps its reason."""

    id: UUID
    status: Literal["running", "succeeded", "partially_succeeded", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    published_at: datetime | None = None
    total_items: int
    successful_items: int
    failed_items: int
    rejected_items: int
    error_message: str | None = None
    source_document_id: str | None = None
    worksheet_report: dict = Field(default_factory=dict)


class ImportRunListResponse(ApiModel):
    items: list[ImportRunResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class MaterialUnitSettingCreate(ApiModel):
    """A person choosing the unit a category is displayed in.

    `reason` is required and must not be blank, exactly as it is for a price version or a
    unit conversion: a decision with no recorded reason is one nobody can review later.
    """

    category: str = Field(min_length=1)
    resource_id: UUID | None = None
    display_unit: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class MaterialUnitSettingResponse(ApiModel):
    id: UUID
    category: str
    resource_id: UUID | None = None
    version: int
    display_unit: str
    reason: str
    created_by: UUID
    created_by_name: str | None = None
    created_at: datetime


class MaterialUnitSettingListResponse(ApiModel):
    items: list[MaterialUnitSettingResponse]


class ProviderItemLabelCreate(ApiModel):
    """What a person says one listing is.

    Every field is optional except `reason`, and that asymmetry is deliberate: a label may
    say one thing or ten, but a decision nobody explained is one nobody can review later --
    the same rule `price_versions` and `unit_conversions` already hold.

    `mappingApprovedBy` is absent on purpose. The approver is the authenticated caller,
    stamped by the service; accepting it from the request would let somebody approve a
    mapping in another person's name.
    """

    label: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=60)
    product_type: str | None = Field(default=None, max_length=60)
    #: A Finance unit code. Validated against the registry by the router, so a label cannot
    #: introduce a unit the rest of Finance has never heard of.
    source_unit: str | None = Field(default=None, max_length=20)
    #: The commercial basis in words, for when the price is per something that is not a
    #: unit at all -- "per branch of 12 metres", "per pallet".
    source_basis: str | None = Field(default=None, max_length=120)
    target_unit: str | None = Field(default=None, max_length=20)
    finance_resource_id: UUID | None = None
    mapping_approved: bool = False
    active: bool = True
    notes: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=500)


class ProviderItemLabelResponse(ApiModel):
    id: UUID
    provider_item_id: UUID
    version: int
    label: str | None = None
    display_name: str | None = None
    category: str | None = None
    product_type: str | None = None
    source_unit: str | None = None
    source_basis: str | None = None
    target_unit: str | None = None
    finance_resource_id: UUID | None = None
    mapping_approved: bool
    mapping_approved_by: UUID | None = None
    mapping_approved_at: datetime | None = None
    active: bool
    notes: str | None = None
    reason: str
    created_by: UUID
    created_by_name: str | None = None
    created_at: datetime
    #: Set when a newer version replaced this one. Null means this is the current label.
    superseded_at: datetime | None = None
    superseded_by: UUID | None = None


class ProviderItemLabelListResponse(ApiModel):
    items: list[ProviderItemLabelResponse]


class ProviderItemFactorCreate(ApiModel):
    """A measurement of one product: how much one of these is in another unit.

    This is the only way a crossing between dimensions becomes possible -- piece to
    kilogram, branch to metre. Nothing derives one; somebody weighs or measures the thing
    and records it here with a reason.
    """

    from_unit: str = Field(min_length=1, max_length=20)
    to_unit: str = Field(min_length=1, max_length=20)
    factor: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    factor_type: Literal["weight_per_piece", "weight_per_branch", "length_per_branch",
                         "mass_per_bag", "area_per_piece", "volume_per_piece", "other"]
    reason: str = Field(min_length=1, max_length=500)


class ProviderItemFactorResponse(ApiModel):
    id: UUID
    provider_item_id: UUID
    version: int
    from_unit: str
    to_unit: str
    factor: Decimal
    factor_type: str | None = None
    origin: str
    reason: str
    created_by: UUID
    created_by_name: str | None = None
    created_at: datetime
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    superseded_at: datetime | None = None


class ProviderItemFactorListResponse(ApiModel):
    items: list[ProviderItemFactorResponse]


class UnresolvedItemResponse(ApiModel):
    """A listing nobody has labelled and the sheet said nothing useful about."""

    id: UUID
    external_id: str
    external_name: str
    category: str
    source_unit: str | None = None
    source_worksheet: str | None = None
    active: bool


class UnresolvedItemListResponse(ApiModel):
    items: list[UnresolvedItemResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
