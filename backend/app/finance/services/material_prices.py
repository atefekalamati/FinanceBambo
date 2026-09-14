# -*- coding: utf-8 -*-
"""The read side of material prices: what the API answers with.

Everything here comes from the database. There is no fallback, no sample row and no
default price: an endpoint with nothing to return returns an empty list, and a listing
with no readable price returns a null price and a status saying which kind of nothing it
is.

Freshness is expressed in days against the date the caller asks about, and the caller
supplies both. This service does not read a clock -- a report for a date in the past must
not be told that everything in it is stale.
"""

from decimal import Decimal

from .material_price_resolution import canonical_unit, resolve

#: How old the newest workflow date may be before a price is labelled stale. Seven days is
#: the sheet's own rhythm -- its four dates span five days -- and it is a label, never a
#: reason to withhold: a stale price is still the best figure anybody has.
DEFAULT_STALE_AFTER_DAYS = 7


class MaterialPriceService:
    def __init__(self, repository, conversion_repository=None,
                 stale_after_days=DEFAULT_STALE_AFTER_DAYS):
        self.repository = repository
        self.conversions = conversion_repository
        self.stale_after_days = stale_after_days

    async def categories(self, scope):
        return await self.repository.categories(scope)

    async def runs(self, scope, page, page_size):
        return await self.repository.runs_page(scope, page=page, page_size=page_size)

    async def invalid_rows(self, scope, page, page_size):
        return await self.repository.invalid_observations_page(
            scope, page=page, page_size=page_size)

    async def history(self, scope, provider_item_id, page, page_size):
        return await self.repository.observation_history(
            scope, provider_item_id, page=page, page_size=page_size)

    async def unit_settings(self, scope, category=None):
        return await self.repository.unit_settings(scope, category=category)

    async def set_unit(self, scope, payload, actor_id):
        """Record a unit decision. Append-only: the previous decision stays readable."""
        return await self.repository.append_unit_setting(
            scope, category=payload.category, resource_id=payload.resource_id,
            display_unit=payload.display_unit, reason=payload.reason.strip(),
            created_by=actor_id)

    async def current(self, scope, *, category=None, as_of=None, page=1, page_size=50,
                      only_active=True):
        """The newest observation per listing, resolved, paged.

        Paged in memory after resolution rather than in SQL, and deliberately: the status a
        row ends up with depends on the unit settings and the factors available to it, so a
        SQL page would be a page of rows whose statuses were not yet known. The population
        is one project's provider listings -- hundreds, not millions -- and correctness is
        worth more than the query here.
        """
        observations = await self.repository.latest_observations(
            scope, category=category, only_active=only_active)
        settings = {row["category"]: row["display_unit"]
                    for row in await self.repository.unit_settings(scope)
                    if row["resource_id"] is None}

        resolved = []
        for row in observations:
            display_unit = settings.get(row["category"])
            lookup = await self._factor_lookup(scope, row["provider_item_id"])
            price, status, reason, factor, note = resolve(
                row, display_unit=display_unit, conversion_lookup=lookup, as_of=as_of,
                stale_after_days=self.stale_after_days if as_of else None)
            resolved.append(self._shape(row, price, status, reason, factor, note,
                                        display_unit))

        total = len(resolved)
        start = (page - 1) * page_size
        return resolved[start:start + page_size], total

    async def _factor_lookup(self, scope, provider_item_id):
        """A `(source, target) -> factor` for one listing, product-specific first.

        A product-specific factor wins over a dimension one on purpose: "this brick weighs
        1.2 kg" is a fact about this brick, and a generic piece-to-kilogram factor cannot
        exist. The generic table answers only the crossings that are true of every product,
        like gram to kilogram.
        """
        specific = {}
        if hasattr(self.repository, "item_unit_factors"):
            for row in await self.repository.item_unit_factors(scope, provider_item_id):
                key = (canonical_unit(row["from_unit"]), canonical_unit(row["to_unit"]))
                specific[key] = Decimal(row["factor"])

        generic = {}
        if self.conversions is not None:
            for row in await self.conversions.list(scope):
                key = (canonical_unit(row.source_unit), canonical_unit(row.target_unit))
                generic[key] = Decimal(row.factor)

        def lookup(source, target):
            return specific.get((source, target)) or generic.get((source, target))

        return lookup

    @staticmethod
    def _shape(row, price, status, reason, factor, note, display_unit):
        """One row of the API's answer. Every provenance field travels with the price."""
        return {
            "provider_item_id": row["provider_item_id"],
            "external_id": row["external_id"],
            "external_name": row["external_name"],
            "category": row["category"],
            "provider_name": row["provider_name"],
            "active": row["active"],
            "inactive_reason": row["inactive_reason"],
            "worksheet": row.get("item_worksheet") or row.get("source_worksheet"),
            "current_price_irr": price,
            "raw_price": row["raw_price"],
            "source_currency": row["source_currency"],
            "secondary_price_irr": row["secondary_price_irr"],
            "secondary_price_basis": row["secondary_price_basis"],
            "source_unit": row["source_unit"],
            "display_unit": display_unit,
            "conversion_factor": factor,
            "conversion_note": note,
            "workflow_date_raw": row["workflow_date_raw"],
            "workflow_date_jalali": row["workflow_date_jalali"],
            "workflow_date_gregorian": row["workflow_date_gregorian"],
            "observed_at_source": row["observed_at_source"],
            "observed_at": row["observed_at"],
            "fetched_at": row["fetched_at"],
            "validation_status": row["validation_status"],
            "validation_reasons": list(row["validation_reasons"] or []),
            "resolution_status": status,
            "resolution_reason": reason,
            "source_row_number": row["source_row_number"],
            "source_url": row["source_url"],
        }
