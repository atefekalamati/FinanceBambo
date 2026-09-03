from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .attachments import FinanceAttachment


@dataclass(frozen=True)
class ExtractionField:
    key: str
    extracted_value: Any
    confirmed_value: Any
    confidence: float
    edited_by_user: bool = False


@dataclass(frozen=True)
class ExtractionDraft:
    draft_id: UUID
    organization_id: UUID
    project_id: str
    file: FinanceAttachment
    version: int
    review_status: str
    invoice_status: str
    provider_adapter: str
    fields: list[ExtractionField]
    submitted_by: UUID
    created_at: datetime
    financial_effect_irr: Decimal = Decimal(0)
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
