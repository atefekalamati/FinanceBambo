from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from datetime import date
from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from .attachments import AttachmentResponse
from .base import ApiModel
from .invoices import DirectAdjustmentAllocation, InvoiceLineCreate
from .numeric import strict_decimal


class ExtractionFieldDto(ApiModel):
    key: str = Field(min_length=1)
    extracted_value: Any
    confirmed_value: Any = None
    confidence: float = Field(ge=0, le=1)
    edited_by_user: bool = False

    @field_validator("confidence", mode="before")
    @classmethod
    def strict_confidence(cls, value):
        return strict_decimal(value)

    @field_validator("key")
    @classmethod
    def nonblank_key(cls, value):
        if not value.strip(): raise ValueError("field key must not be blank")
        return value.strip()


class ProviderExtractionResult(ApiModel):
    fields: list[ExtractionFieldDto]

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)): raise ValueError("extraction field keys must be unique")
        return self


class ExtractionRetry(ApiModel):
    hints: dict[str, Any] = Field(default_factory=dict)


class ExtractionStart(ApiModel):
    model_config = ConfigDict(json_schema_extra={"examples":[{"hints":{"locale":"fa-IR"}}]})
    hints: dict[str, Any] = Field(default_factory=dict)


class ExtractionReject(ApiModel):
    model_config = ConfigDict(json_schema_extra={"examples":[{"expectedVersion":1,"reason":"فایل فاکتور قابل خواندن نیست"}]})
    expected_version: int = Field(ge=1)
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if value is not None and not value.strip(): raise ValueError("reason must not be blank")
        return None if value is None else value.strip()


class ExtractionFieldConfirmation(ApiModel):
    key: str = Field(min_length=1)
    confirmed_value: Any


class ReviewedInvoiceCreate(ApiModel):
    # No `invoice_number`, for the same reason as `InvoiceCreate`. The vendor's own printed
    # number is not lost by this: it is an extracted FIELD, kept with the rest of what was
    # read off the document in `extraction_drafts.extracted_fields`, and it was never the
    # same thing as this system's number for the invoice.
    invoice_date: date
    vendor_name: str = Field(min_length=1)
    description: str | None = None
    duplicate_reason: str | None = None
    discount_irr: Decimal = Field(default=0, ge=0, max_digits=18, decimal_places=0)
    tax_irr: Decimal = Field(default=0, ge=0, max_digits=18, decimal_places=0)
    shipping_irr: Decimal = Field(default=0, ge=0, max_digits=18, decimal_places=0)
    other_costs_irr: Decimal = Field(default=0, ge=0, max_digits=18, decimal_places=0)
    direct_adjustment_allocations: list[DirectAdjustmentAllocation] = Field(default_factory=list)
    lines: list[InvoiceLineCreate] = Field(min_length=1)

    @field_validator("discount_irr", "tax_irr", "shipping_irr", "other_costs_irr", mode="before")
    @classmethod
    def strict_reviewed_money(cls, value):
        return strict_decimal(value)

    @field_validator("vendor_name")
    @classmethod
    def reviewed_vendor_nonblank(cls, value):
        if not value.strip(): raise ValueError("vendor name must not be blank")
        return value.strip()

    @field_validator("duplicate_reason")
    @classmethod
    def duplicate_reason_nonblank(cls, value):
        if value is not None and not value.strip(): raise ValueError("duplicate reason must not be blank")
        return None if value is None else value.strip()

    @model_validator(mode="after")
    def valid_allocations(self):
        kinds = [item.kind for item in self.direct_adjustment_allocations]
        if len(kinds) != len(set(kinds)): raise ValueError("each adjustment kind can be allocated once")
        if any(item.general_cost_line_index >= len(self.lines) for item in self.direct_adjustment_allocations): raise ValueError("general cost line index is out of range")
        return self


class ExtractionEdit(ApiModel):
    """A reviewer's corrections to a draft, before any of it becomes financial.

    The same `(key, confirmedValue)` shape confirmation already accepts, because it is the
    same act: a person saying what the value should be. Splitting it into a second vocabulary
    would mean the review screen sent one shape while editing and another while confirming.
    """

    expected_version: int = Field(ge=1)
    field_edits: list[ExtractionFieldConfirmation] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_field_edits(self):
        keys = [item.key for item in self.field_edits]
        if len(keys) != len(set(keys)): raise ValueError("each field can be edited once")
        return self


class ExtractionConfirm(ApiModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    field_confirmations: list[ExtractionFieldConfirmation] = Field(default_factory=list)
    invoice: ReviewedInvoiceCreate

    @field_validator("idempotency_key")
    @classmethod
    def confirmation_key_nonblank(cls, value):
        if not value.strip(): raise ValueError("idempotency key must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def unique_field_confirmations(self):
        keys = [item.key for item in self.field_confirmations]
        if len(keys) != len(set(keys)): raise ValueError("each field can be confirmed once")
        return self


class ExtractionDraftResponse(ApiModel):
    draft_id: UUID
    version: int = Field(ge=1)
    file: AttachmentResponse
    review_status: Literal["awaitingReview", "accepted", "rejected"]
    invoice_status: Literal["draft", "awaitingConfirmation", "confirmed", "voided", "corrected"]
    provider_adapter: str
    fields: list[ExtractionFieldDto]
    submitted_by: UUID
    created_at: datetime
    linked_invoice_id: UUID | None
    financial_effect_irr: Decimal = Field(alias="financialEffectIRR")
    confirmed_by: UUID | None
    confirmed_at: datetime | None

    @field_serializer("financial_effect_irr")
    def serialize_effect(self, value): return format(value, "f")

    @classmethod
    def from_domain(cls, value):
        return cls(
            draft_id=value.draft_id,
            version=value.version,
            file=AttachmentResponse.from_domain(value.file),
            review_status=value.review_status,
            invoice_status=value.invoice_status,
            provider_adapter=value.provider_adapter,
            fields=[field.__dict__ for field in value.fields],
            submitted_by=value.submitted_by,
            created_at=value.created_at,
            linked_invoice_id=value.file.invoice_id,
            financial_effect_irr=value.financial_effect_irr,
            confirmed_by=value.confirmed_by,
            confirmed_at=value.confirmed_at,
        )


class ExtractionListResponse(ApiModel):
    model_config = ConfigDict(json_schema_extra={"examples":[{"items":[],"page":1,"pageSize":50,"totalCount":0,"totalPages":0}]})
    items: list[ExtractionDraftResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    # totalItems is the canonical name across Finance list envelopes; totalCount is kept
    # so existing clients keep working and is mirrored from it.
    total_items: int | None = None

    @model_validator(mode="after")
    def mirror_total(self):
        if self.total_items is None:
            object.__setattr__(self, "total_items", self.total_count)
        return self
