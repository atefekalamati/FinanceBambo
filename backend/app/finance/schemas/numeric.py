"""Strict numeric validation helpers for Finance JSON-boundary DTOs."""

from decimal import Decimal, InvalidOperation
from typing import Any


def strict_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list, tuple, set)):
        raise ValueError("must be a numeric decimal value")
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized or normalized.lower() == "null":
            raise ValueError("must be a numeric decimal value")
        value = normalized
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("must be a numeric decimal value") from None
    if not decimal.is_finite():
        raise ValueError("must be a finite numeric decimal value")
    return decimal


def strict_optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else strict_decimal(value)
