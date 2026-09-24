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


#: Fields a reviewer may NOT overwrite, because they are evidence rather than readings.
#:
#: `rawText` and `voiceTranscript` are what the document said and what the speaker said.
#: The whole reason the voice path keeps a transcript is that a spoken amount can disagree
#: with a printed one, and a reviewer who could edit the transcript could erase the
#: disagreement -- leaving two numbers that now agree and no record that they ever did not.
#:
#: `source`, `speechProvider` and `extractionSource` say WHERE a reading came from. A
#: reviewer correcting a number is stating a better value; they are not restating its
#: origin, and letting them would make provenance unreliable for every other row too.
#:
#: Editing a value never touches `extractedValue` in any case -- the edit is written to
#: `confirmedValue` beside it -- so this list is the second lock, not the only one.
PROVENANCE_KEYS: frozenset[str] = frozenset({
    "rawText", "voiceTranscript", "source", "speechProvider", "extractionSource",
})


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
