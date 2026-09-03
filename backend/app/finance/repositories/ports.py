"""Minimal persistence boundary; feature-specific methods come with features."""

from typing import Protocol


class FinanceRepository(Protocol):
    """Marker protocol for scope-aware, parameterized-SQL repositories."""

    pass
