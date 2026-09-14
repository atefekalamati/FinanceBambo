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

    #: What the sheet said the unit was. Absent for six of the seven categories, because
    #: the sheet does not say. Never treated as the display unit.
    source_unit: str | None = None
    #: The unit an authorised person chose for this category, if one has been chosen.
    display_unit: str | None = None
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
    #: `resolved` | `unresolved_price` | `unresolved_unit` | `unmapped` | `stale`.
    #: A status, not a guess: the reader is told which of these it is.
    resolution_status: str
    resolution_reason: str | None = None

    source_row_number: int | None = None
    source_url: str | None = None


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
