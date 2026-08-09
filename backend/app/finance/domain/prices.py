from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

@dataclass(frozen=True)
class PriceVersion:
    id: UUID; organization_id: UUID; project_id: str; resource_id: UUID
    scope_kind: str; version: int; unit_price_irr: Decimal
    effective_from: date; reason: str; created_by: UUID; created_at: datetime
