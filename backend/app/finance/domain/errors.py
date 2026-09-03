"""Domain errors contain no HTTP or database concerns."""


class FinanceDomainError(Exception):
    """Base class for violations of an approved Finance invariant."""
