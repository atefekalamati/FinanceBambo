"""AhanOnline registration boundary.

The site's public robots policy currently disallows its PriceList/price-list and query
routes.  No scraper is shipped for those paths.  Keeping an explicit fail-closed adapter
prevents a future operator from mistaking an absent implementation for permission to crawl.
Enable only after an allowed public feed/path or written authorization is configured and
reviewed.
"""

from .base import ProviderAccessDenied


class AhanOnlineProvider:
    provider_key = "ahanonline"
    domain = "ahanonline.com"
    enabled = False

    async def health_check(self) -> bool:
        return False

    async def collect_items(self):
        raise ProviderAccessDenied(
            "AhanOnline price routes are disallowed by its current robots policy; "
            "configure an explicitly permitted source before enabling collection"
        )

    async def collect(self):
        return await self.collect_items()

    def parse_price(self, raw_value: object) -> str:
        raise ProviderAccessDenied("price parsing is disabled until an allowed source is approved")
