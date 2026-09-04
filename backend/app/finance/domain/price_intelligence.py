"""Provider-neutral rules for external price evidence.

An external value is never a Finance price by itself.  It becomes eligible for resolution
only after explicit currency/unit normalization, an approved resource mapping and anomaly
validation.  The caller may then append a new ``PriceVersion`` through the existing price
service; this module deliberately has no update path for that ledger.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal, Mapping, Sequence
from uuid import UUID


Currency = Literal["IRR", "TOMAN"]
ValidationStatus = Literal["valid", "needs_review", "rejected"]

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class PriceNormalizationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CollectedItem:
    external_id: str
    external_name: str
    category: str
    url: str
    source_unit: str | None
    raw_price: str
    currency: Currency
    availability: Literal["available", "unavailable", "unknown"]
    observed_at: datetime
    raw_data: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ValidatedObservation:
    normalized_price_irr: Decimal | None
    status: ValidationStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvableObservation:
    observation_id: UUID
    provider_id: UUID
    price_irr: Decimal
    confidence_score: Decimal
    observed_at: datetime


def normalize_price(raw_price: object, currency: Currency) -> Decimal:
    """Return exact whole IRR; currency is explicit and is never inferred from magnitude."""
    if isinstance(raw_price, bool) or not isinstance(raw_price, (str, int, Decimal)):
        raise PriceNormalizationError("price must be an exact numeric value")
    text = str(raw_price).translate(_DIGITS).strip().replace(",", "").replace("٬", "")
    if not text or any(character not in "0123456789.-+" for character in text):
        raise PriceNormalizationError("price contains non-numeric characters")
    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise PriceNormalizationError("price is not a valid decimal") from error
    if not value.is_finite() or value <= 0:
        raise PriceNormalizationError("price must be finite and greater than zero")
    if currency == "TOMAN":
        value *= Decimal(10)
    elif currency != "IRR":
        raise PriceNormalizationError("currency is not supported")
    if value != value.to_integral_value():
        raise PriceNormalizationError("normalized IRR must be a whole number")
    if len(format(value, "f").lstrip("-")) > 18:
        raise PriceNormalizationError("normalized IRR exceeds numeric(18,0)")
    return value


def validate_observation(
    item: CollectedItem,
    *,
    mapping_approved: bool,
    normalized_unit: str | None,
    previous_price_irr: Decimal | None,
    anomaly_threshold_percent: Decimal,
) -> ValidatedObservation:
    reasons: list[str] = []
    try:
        normalized = normalize_price(item.raw_price, item.currency)
    except PriceNormalizationError as error:
        return ValidatedObservation(None, "rejected", (str(error),))

    if item.availability != "available":
        reasons.append("product is not currently available")
    if not mapping_approved:
        reasons.append("approved resource mapping is required")
    if not item.source_unit or not normalized_unit:
        reasons.append("a valid source and normalized unit are required")
    if previous_price_irr is not None and previous_price_irr > 0:
        change = abs(normalized - previous_price_irr) * Decimal(100) / previous_price_irr
        if change > anomaly_threshold_percent:
            reasons.append("price change exceeds the configured anomaly threshold")

    if reasons:
        return ValidatedObservation(normalized, "needs_review", tuple(reasons))
    return ValidatedObservation(normalized, "valid", ())


def resolve_price(
    observations: Sequence[ResolvableObservation],
    *,
    strategy: Literal["median", "preferred_provider", "weighted_provider", "manual_approval"],
    preferred_provider_id: UUID | None = None,
    provider_weights: Mapping[str, Decimal] | None = None,
) -> Decimal | None:
    """Resolve validated evidence without mutating it or the official price ledger."""
    if not observations or strategy == "manual_approval":
        return None
    if strategy == "preferred_provider":
        eligible = [item for item in observations if item.provider_id == preferred_provider_id]
        if not eligible:
            return None
        return max(eligible, key=lambda item: (item.observed_at, str(item.observation_id))).price_irr
    if strategy == "median":
        values = sorted(item.price_irr for item in observations)
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / Decimal(2)
    if strategy == "weighted_provider":
        weights = provider_weights or {}
        weighted_total = Decimal(0)
        total_weight = Decimal(0)
        for item in observations:
            weight = Decimal(weights.get(str(item.provider_id), item.confidence_score))
            if weight <= 0:
                continue
            weighted_total += item.price_irr * weight
            total_weight += weight
        return None if total_weight == 0 else weighted_total / total_weight
    raise ValueError("unsupported price resolution strategy")


def freshness(observed_at: datetime, now: datetime | None = None) -> Literal["fresh", "old", "expired"]:
    current = now or datetime.now(timezone.utc)
    age = current - observed_at.astimezone(timezone.utc)
    if age.total_seconds() < 24 * 3600:
        return "fresh"
    if age.total_seconds() <= 7 * 24 * 3600:
        return "old"
    return "expired"
