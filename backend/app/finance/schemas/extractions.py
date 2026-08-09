from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from .attachments import AttachmentResponse
from .base import ApiModel


class ExtractionFieldDto(ApiModel):
    key: str = Field(min_length=1)
    extracted_value: Any
    confirmed_value: Any = None
    confidence: float = Field(ge=0, le=1)
    edited_by_user: bool = False

    @field_validator("key")
    @classmethod
    def nonblank_key(cls, value):
        if not value.strip(): raise ValueError("field key must not be blank")
        return value.strip()


class ProviderExtractionResult(ApiModel):
    fields: list[ExtractionFieldDto]


class ExtractionRetry(ApiModel):
    hints: dict[str, Any] = Field(default_factory=dict)


class ExtractionDraftResponse(ApiModel):
    draft_id: UUID
    file: AttachmentResponse
    review_status: Literal["awaitingReview", "accepted", "rejected"]
    invoice_status: Literal["draft", "awaitingConfirmation", "confirmed", "voided", "corrected"]
    provider_adapter: str
    fields: list[ExtractionFieldDto]
    submitted_by: UUID
    financial_effect_irr: Decimal = Field(alias="financialEffectIRR")
    confirmed_by: UUID | None
    confirmed_at: datetime | None

    @field_serializer("financial_effect_irr")
    def serialize_effect(self, value): return format(value, "f")

    @classmethod
    def from_domain(cls, value):
        return cls(
            draft_id=value.draft_id,
            file=AttachmentResponse.from_domain(value.file),
            review_status=value.review_status,
            invoice_status=value.invoice_status,
            provider_adapter=value.provider_adapter,
            fields=[field.__dict__ for field in value.fields],
            submitted_by=value.submitted_by,
            financial_effect_irr=value.financial_effect_irr,
            confirmed_by=value.confirmed_by,
            confirmed_at=value.confirmed_at,
        )
