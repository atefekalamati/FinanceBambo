from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal,ROUND_HALF_UP
from uuid import UUID

from .errors import FinanceDomainError


class PricePeriodOverlap(FinanceDomainError):
    """A resource may not hold two prices of the same scope effective on the same day."""

    status = 409
    code = "PRICE_PERIOD_OVERLAP"


@dataclass(frozen=True)
class PriceVersion:
    id: UUID; organization_id: UUID; project_id: str; resource_id: UUID
    scope_kind: str; version: int; unit_price_irr: Decimal
    effective_from: date; reason: str; created_by: UUID; created_at: datetime


def latest_price_trend(versions):
    if not versions:return None
    ordered=sorted(versions,key=lambda value:(value.effective_from,value.version,value.created_at,value.id))
    current=ordered[-1]
    previous=ordered[-2] if len(ordered)>1 else None
    if previous is None:return current,None,None,"none",ordered
    if current.unit_price_irr>previous.unit_price_irr:direction="up"
    elif current.unit_price_irr<previous.unit_price_irr:direction="down"
    else:direction="flat"
    percent=None if previous.unit_price_irr==0 else ((current.unit_price_irr-previous.unit_price_irr)*Decimal(100)/previous.unit_price_irr).quantize(Decimal("0.000001"),rounding=ROUND_HALF_UP)
    return current,previous,percent,direction,ordered
