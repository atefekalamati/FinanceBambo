import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.finance.domain.price_intelligence import (
    CollectedItem,
    PriceNormalizationError,
    ResolvableObservation,
    freshness,
    normalize_price,
    resolve_price,
    validate_observation,
)
from pricing.providers.ahanonline import AhanOnlineProvider
from pricing.providers.base import ProviderAccessDenied


NOW = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
PROVIDER_A = UUID("11111111-1111-4111-8111-111111111111")
PROVIDER_B = UUID("22222222-2222-4222-8222-222222222222")


def item(**changes):
    values = {
        "external_id": "rebar-16",
        "external_name": "میلگرد ۱۶",
        "category": "rebar",
        "url": "https://example.invalid/rebar-16",
        "source_unit": "kg",
        "raw_price": "۳۲٬۵۰۰",
        "currency": "TOMAN",
        "availability": "available",
        "observed_at": NOW,
        "raw_data": {"display": "۳۲٬۵۰۰ تومان"},
    }
    values.update(changes)
    return CollectedItem(**values)


@pytest.mark.parametrize("value,currency,expected", [
    ("325000", "IRR", Decimal("325000")),
    ("۳۲٬۵۰۰", "TOMAN", Decimal("325000")),
    (325000, "IRR", Decimal("325000")),
    (Decimal("325000"), "IRR", Decimal("325000")),
])
def test_money_normalization_is_exact_and_currency_is_explicit(value, currency, expected):
    assert normalize_price(value, currency) == expected


@pytest.mark.parametrize("value", ["10 میلیون", "100abc", "NaN", "Infinity", True, {}, []])
def test_invalid_raw_prices_are_rejected(value):
    with pytest.raises(PriceNormalizationError):
        normalize_price(value, "IRR")


def test_valid_observation_requires_mapping_unit_and_availability():
    result = validate_observation(
        item(), mapping_approved=True, normalized_unit="kg",
        previous_price_irr=Decimal("320000"), anomaly_threshold_percent=Decimal("25"),
    )
    assert (result.normalized_price_irr, result.status, result.reasons) == (
        Decimal("325000"), "valid", ())


def test_anomaly_is_saved_for_review_and_not_treated_as_valid():
    result = validate_observation(
        item(raw_price="90000"), mapping_approved=True, normalized_unit="kg",
        previous_price_irr=Decimal("325000"), anomaly_threshold_percent=Decimal("25"),
    )
    assert result.status == "needs_review"
    assert "anomaly threshold" in result.reasons[0]


def test_missing_mapping_never_becomes_an_official_candidate():
    result = validate_observation(
        item(), mapping_approved=False, normalized_unit="kg",
        previous_price_irr=None, anomaly_threshold_percent=Decimal("25"),
    )
    assert result.status == "needs_review"
    assert any("mapping" in reason for reason in result.reasons)


def observations():
    return [
        ResolvableObservation(UUID(int=1), PROVIDER_A, Decimal("325000"), Decimal("0.9"), NOW),
        ResolvableObservation(UUID(int=2), PROVIDER_B, Decimal("327000"), Decimal("0.8"), NOW),
        ResolvableObservation(UUID(int=3), PROVIDER_A, Decimal("326000"), Decimal("0.9"), NOW),
    ]


def test_resolution_strategies_are_configurable_and_decimal_only():
    rows = observations()
    assert resolve_price(rows, strategy="median") == Decimal("326000")
    assert resolve_price(rows, strategy="preferred_provider", preferred_provider_id=PROVIDER_B) == Decimal("327000")
    weighted = resolve_price(rows, strategy="weighted_provider", provider_weights={
        str(PROVIDER_A): Decimal("2"), str(PROVIDER_B): Decimal("1")})
    assert weighted == Decimal("1629000") / Decimal("5")
    assert resolve_price(rows, strategy="manual_approval") is None


def test_freshness_boundaries_are_deterministic():
    assert freshness(NOW - timedelta(hours=2), NOW) == "fresh"
    assert freshness(NOW - timedelta(days=2), NOW) == "old"
    assert freshness(NOW - timedelta(days=8), NOW) == "expired"


def test_ahanonline_fails_closed_while_price_routes_are_disallowed():
    provider = AhanOnlineProvider()
    assert asyncio.run(provider.health_check()) is False
    with pytest.raises(ProviderAccessDenied):
        asyncio.run(provider.collect())


def test_migration_separates_observations_from_append_only_price_versions():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0008_price_intelligence.py"
    spec = spec_from_file_location("finance_revision_0008", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    sql = module.UPGRADE_SQL.lower()
    assert "create table price_observations" in sql
    assert "price_version_id uuid" in sql
    assert "price_observations_immutable" in sql
    assert "update price_versions" not in sql
    assert "delete from price_versions" not in sql
