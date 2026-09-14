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

from datetime import datetime, timezone
from decimal import Decimal

from ..domain.unit_conversion import can_convert
from .material_price_resolution import Resolution, canonical_unit, resolve

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

    async def labels(self, scope, provider_item_id=None):
        return await self.repository.labels(scope, provider_item_id=provider_item_id)

    async def label_history(self, scope, provider_item_id):
        return await self.repository.label_history(scope, provider_item_id)

    async def save_label(self, scope, provider_item_id, payload, actor_id):
        """Record what a person says this listing is. Appended, never an update.

        An approval is stamped with the actor and the moment here rather than accepted from
        the request: a caller that could supply `mappingApprovedBy` could approve a mapping
        in somebody else's name.
        """
        values = {
            "label": _clean(payload.label),
            "display_name": _clean(payload.display_name),
            "category": _clean(payload.category),
            "product_type": _clean(payload.product_type),
            "source_unit": _clean(payload.source_unit),
            "source_basis": _clean(payload.source_basis),
            "target_unit": _clean(payload.target_unit),
            "finance_resource_id": payload.finance_resource_id,
            "mapping_approved": bool(payload.mapping_approved),
            "mapping_approved_by": actor_id if payload.mapping_approved else None,
            "mapping_approved_at": datetime.now(timezone.utc) if payload.mapping_approved else None,
            "active": payload.active,
            "notes": _clean(payload.notes),
            "reason": payload.reason.strip(),
        }
        return await self.repository.append_label(
            scope, provider_item_id=provider_item_id, values=values, created_by=actor_id)

    async def save_item_factor(self, scope, provider_item_id, payload, actor_id):
        """A measurement of one product, stored so a crossing becomes possible.

        `origin` is forced to 'manual': this endpoint is a person typing a number, and
        'sheet_attribute' is reserved for a factor the importer read off a column.
        """
        return await self.repository.append_item_factor(
            scope, provider_item_id=provider_item_id, from_unit=payload.from_unit,
            to_unit=payload.to_unit, factor=payload.factor,
            factor_type=payload.factor_type, origin="manual",
            reason=payload.reason.strip(), created_by=actor_id, approved_by=actor_id)

    async def unresolved(self, scope, page, page_size):
        return await self.repository.unresolved_items(scope, page=page, page_size=page_size)

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
                    if row.get("resource_id") is None and row.get("provider_item_id") is None}
        # What a person said about one listing. Fetched once for the whole page rather than
        # once per row: a project has hundreds of listings and one query answers all of them.
        labels = {}
        if hasattr(self.repository, "labels"):
            labels = {row["provider_item_id"]: row for row in await self.repository.labels(scope)}
        # The Finance unit of every approved-mapped resource, so a row can say whether the
        # unit it is priced in is the unit the schedule measures it in.
        finance_units = {}
        if hasattr(self.repository, "mapped_resource_units"):
            finance_units = await self.repository.mapped_resource_units(scope)

        resolved = []
        for row in observations:
            label = labels.get(row["provider_item_id"])
            # A label wins over the category-wide setting, and over the sheet. It is the
            # narrower statement and the only one made by somebody who looked at this row.
            # It never rewrites the observation: `row` is untouched and what the sheet said
            # still travels to the reader beside what the label made of it.
            display_unit = (label or {}).get("target_unit") or settings.get(row["category"])
            source = (canonical_unit((label or {}).get("source_unit"))
                      or canonical_unit(row.get("source_unit")))
            target = canonical_unit(display_unit)
            # Only fetched when the crossing actually needs one: a per-product factor is a
            # person's measurement, and asking for one where units already agree would
            # invite using it where it was never needed.
            factor = await self._product_factor(scope, row["provider_item_id"], source, target)
            # A label that names a Finance resource is a mapping claim, and a mapping claim
            # only counts once somebody has approved it. An unapproved one withholds the
            # price rather than quietly becoming the source of it.
            mapping_required = bool((label or {}).get("finance_resource_id"))
            outcome = resolve(
                dict(row, source_unit=source or row.get("source_unit")),
                display_unit=display_unit, product_factor=factor, as_of=as_of,
                stale_after_days=self.stale_after_days if as_of else None,
                mapping_required=mapping_required,
                mapping_approved=bool((label or {}).get("mapping_approved")),
                active=row.get("active", True) and (label or {}).get("active", True))
            resolved.append(self._shape(row, outcome, display_unit, label,
                                        finance_units.get(row["provider_item_id"])))

        total = len(resolved)
        start = (page - 1) * page_size
        return resolved[start:start + page_size], total

    async def _product_factor(self, scope, provider_item_id, source, target):
        """`(factor, origin)` for one listing's own crossing, or `None`.

        Only a factor stored against THIS listing answers here. `unit_conversions` is not
        consulted: it holds dimension-level factors, and a dimension-level factor is
        exactly what `unit_conversion.py` already knows -- reaching for it at this point
        would mean a project could quietly define its own gram.
        """
        if source is None or target is None or source == target:
            return None
        if not hasattr(self.repository, "item_unit_factors"):
            return None
        for row in await self.repository.item_unit_factors(scope, provider_item_id):
            if (canonical_unit(row["from_unit"]), canonical_unit(row["to_unit"])) == (source, target):
                return Decimal(row["factor"]), row.get("origin")
        return None


    @staticmethod
    def _shape(row, outcome, display_unit, label=None, finance_resource=None):
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
            "current_price_irr": outcome.price,
            "raw_price": row["raw_price"],
            "source_currency": row["source_currency"],
            "secondary_price_irr": row["secondary_price_irr"],
            "secondary_price_basis": row["secondary_price_basis"],
            "source_unit": row["source_unit"],
            "source_unit_code": outcome.source_unit,
            "display_unit": display_unit,
            "target_unit": outcome.target_unit,
            "conversion_factor": outcome.conversion_factor,
            "conversion_note": outcome.conversion_note,
            "factor_origin": outcome.factor_origin,
            "workflow_date_raw": row["workflow_date_raw"],
            "workflow_date_jalali": row["workflow_date_jalali"],
            "workflow_date_gregorian": row["workflow_date_gregorian"],
            "observed_at_source": row["observed_at_source"],
            "observed_at": row["observed_at"],
            "fetched_at": row["fetched_at"],
            "validation_status": row["validation_status"],
            "validation_reasons": list(row["validation_reasons"] or []),
            "resolution_status": outcome.status,
            "resolution_reason": outcome.reason,
            "source_row_number": row["source_row_number"],
            "source_url": row["source_url"],
            # What a person wrote about this listing, travelling with the price so the
            # reader can see that a human decision is part of the answer.
            "label": (label or {}).get("label"),
            "label_display_name": (label or {}).get("display_name"),
            "label_product_type": (label or {}).get("product_type"),
            "label_source_basis": (label or {}).get("source_basis"),
            "finance_resource_id": (label or {}).get("finance_resource_id"),
            "mapping_approved": bool((label or {}).get("mapping_approved")),
            "labelled_by": (label or {}).get("created_by"),
            "labelled_at": (label or {}).get("created_at"),
            "label_version": (label or {}).get("version"),
            # The MSP/Finance side of the comparison. Reported whether or not it agrees,
            # because a reader deciding whether to trust a price needs to see both units,
            # not a verdict with the evidence hidden.
            "finance_resource_title": (finance_resource or {}).get("title"),
            "finance_resource_unit": (finance_resource or {}).get("base_unit"),
            "unit_alignment": _alignment(outcome, finance_resource),
        }


def _clean(value):
    """A trimmed string, or None. An empty field is absent, not an empty string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _alignment(outcome, finance_resource):
    """Whether the price is in the unit the Finance resource is measured in.

        not_mapped         no approved mapping, so there is nothing to align with
        missing_finance_unit   the resource itself states no unit
        aligned            the price is already in the resource's unit
        convertible        a different unit, but one the registry can bridge
        needs_factor       a different unit that only a measurement of this product bridges
        unresolved         the price never resolved, so there is nothing to align

    A verdict, never a correction. Nothing here converts anything or edits an MSP unit: the
    imported quantity and its unit are what the schedule said, and this only reports whether
    the market price can be expressed the same way.
    """
    if finance_resource is None:
        return "not_mapped"
    finance_unit = canonical_unit(finance_resource.get("base_unit"))
    if finance_unit is None:
        return "missing_finance_unit"
    if not outcome.usable:
        return "unresolved"
    priced_in = outcome.target_unit or outcome.source_unit
    if priced_in is None:
        return "unresolved"
    if priced_in == finance_unit:
        return "aligned"
    return "convertible" if can_convert(priced_in, finance_unit) else "needs_factor"
