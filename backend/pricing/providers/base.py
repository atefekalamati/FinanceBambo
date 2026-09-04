"""Contract every external website adapter must implement."""

from typing import Protocol, Sequence

from app.finance.domain.price_intelligence import CollectedItem


class ProviderCollectionError(RuntimeError):
    pass


class ProviderAccessDenied(ProviderCollectionError):
    """The source does not permit collection through the configured public route."""


class PriceProvider(Protocol):
    provider_key: str

    async def health_check(self) -> bool: ...

    async def collect_items(self) -> Sequence[CollectedItem]: ...

    async def collect(self) -> Sequence[CollectedItem]: ...

    def parse_price(self, raw_value: object) -> str: ...
