# -*- coding: utf-8 -*-
"""Connecting a schedule item to a market listing, and pricing it from one.

The read side answers one question for a whole table at once: for each estimate line, which
listing is it mapped to, what does that listing cost today in the unit somebody chose, and
what does that make this line cost per day. Where any part of that is missing the answer
names which part, in Persian, and never substitutes a number.

THREE QUERIES FOR THE WHOLE PAGE
The estimate has hundreds of lines. Asking per line would be hundreds of round trips for a
table that renders at once, so this reads the mappings, the newest price behind each mapped
listing, and the approved factors, and then does the arithmetic in memory. The arithmetic is
`domain.item_price_mapping.price_item`, which touches nothing.

WHAT THE WRITE SIDE REFUSES
A mapping is a financial decision, so it is refused rather than guessed at when the request
does not carry enough to make it: an unknown unit, a listing from another tenant, a blank
reason. And a crossing that needs a product measurement is refused unless an APPROVED one
exists for that listing and that pair of units -- the caller cannot pass a factor inline,
because a number typed into a mapping request is not a measurement anybody approved.
"""

from datetime import date

from ..domain.item_price_mapping import (INCOMPATIBLE, NEEDS_FACTOR, price_item)
from ..domain.unit_conversion import can_convert
from ..domain.unit_registry import UNIT_REGISTRY
from .material_price_resolution import stated_source_unit
from ..domain.errors import FinanceDomainError


class ItemPriceMappingRefused(FinanceDomainError):
    status = 422
    code = "FINANCE_ITEM_PRICE_MAPPING_REFUSED"


class ItemPriceMappingService:
    def __init__(self, repository, clock=date.today):
        self.repository = repository
        self.clock = clock

    # --------------------------------------------------------------------------- read

    async def candidates(self, scope, *, category=None, query=None, provider_id=None,
                         product_type=None, page=1, page_size=25):
        rows, total = await self.repository.candidates(
            scope, category=category, query=query, provider_id=provider_id,
            product_type=product_type, page=page, page_size=page_size)
        return rows, total

    async def filters(self, scope, category=None):
        """What the modal can filter by, read from what exists rather than hard-coded."""
        return {
            "providers": await self.repository.providers(scope),
            "productTypes": await self.repository.product_types(scope, category=category),
        }

    async def mapping_for_line(self, scope, estimate_line_id):
        return await self.repository.current_for_line(scope, estimate_line_id)

    async def history_for_line(self, scope, estimate_line_id):
        return await self.repository.history_for_line(scope, estimate_line_id)

    async def table_status(self, scope):
        """Every line's pricing state, keyed by estimate line id.

        This is what the financial-items table reads. A line with no mapping is present in
        the answer with status `needs_product` -- absent would be indistinguishable from a
        line the caller forgot to ask about.
        """
        mappings = [m for m in await self.repository.current_for_project(scope)
                    if m.get("estimate_line_id") is not None]
        item_ids = {m["provider_item_id"] for m in mappings}
        prices = await self.repository.latest_prices_for_items(scope, item_ids)
        factors = await self.repository.approved_factors_for_items(scope, item_ids)
        quantities = await self.repository.line_quantities(scope)

        answers = {}
        for mapping in mappings:
            line_id = mapping["estimate_line_id"]
            observation = prices.get(mapping["provider_item_id"]) or {}
            source_unit = _source_unit(observation)
            factor = _factor_for(factors, mapping, source_unit)
            priced = price_item(
                mapping=mapping,
                price_irr=observation.get("normalized_price_irr"),
                source_unit=source_unit,
                quantity=quantities.get(line_id),
                factor=(factor or {}).get("factor"))
            answers[str(line_id)] = dict(
                priced.as_dict(),
                estimate_line_id=str(line_id),
                provider_item_id=str(mapping["provider_item_id"]),
                provider_name=observation.get("provider_name"),
                product_name=observation.get("external_name"),
                product_external_id=observation.get("external_id"),
                category=observation.get("category"),
                worksheet=observation.get("source_worksheet"),
                workflow_date_jalali=observation.get("workflow_date_jalali"),
                mapping_version=mapping["version"],
                conversion_factor_id=(str(mapping["conversion_factor_id"])
                                    if mapping.get("conversion_factor_id") else None))
        # Lines nobody has mapped. Reported, so the table can show what is waiting.
        for line_id in quantities:
            answers.setdefault(str(line_id), dict(
                price_item(mapping=None, price_irr=None, source_unit=None,
                           quantity=quantities.get(line_id)).as_dict(),
                estimate_line_id=str(line_id), provider_item_id=None, provider_name=None,
                product_name=None, product_external_id=None, category=None, worksheet=None,
                workflow_date_jalali=None, mapping_version=None, conversion_factor_id=None))
        return answers

    async def preview(self, scope, *, provider_item_id, selected_unit, estimate_line_id=None):
        """What this listing would cost in this unit, before anything is saved.

        The modal calls it on every change so a person sees the converted price and the
        refusal BEFORE committing to a mapping -- which is how «ضریب تبدیل لازم است» stops
        being a surprise discovered after saving.
        """
        prices = await self.repository.latest_prices_for_items(scope, [provider_item_id])
        observation = prices.get(provider_item_id) or {}
        source_unit = _source_unit(observation)
        factors = await self.repository.approved_factors_for_items(scope, [provider_item_id])
        trial = {"provider_item_id": provider_item_id, "selected_unit": selected_unit}
        factor = _factor_for(factors, trial, source_unit)
        quantity = None
        if estimate_line_id is not None:
            quantity = (await self.repository.line_quantities(scope)).get(estimate_line_id)
        priced = price_item(mapping=trial,
                            price_irr=observation.get("normalized_price_irr"),
                            source_unit=source_unit, quantity=quantity,
                            factor=(factor or {}).get("factor"))
        return dict(priced.as_dict(),
                    provider_item_id=str(provider_item_id),
                    product_name=observation.get("external_name"),
                    provider_name=observation.get("provider_name"),
                    source_price_irr=_text(observation.get("normalized_price_irr")),
                    workflow_date_jalali=observation.get("workflow_date_jalali"),
                    conversion_factor_id=(str(factor["id"]) if factor else None))

    # -------------------------------------------------------------------------- write

    async def save_mapping(self, scope, *, estimate_line_id, payload, actor_id):
        """Record which listing prices this line, in which unit. Appended, never edited."""
        selected = (payload.selected_unit or "").strip()
        if selected not in UNIT_REGISTRY:
            raise ItemPriceMappingRefused(
                "واحد رسمی باید یکی از واحدهای ثبت‌شده در سامانه باشد")
        reason = (payload.reason or "").strip()
        if not reason:
            raise ItemPriceMappingRefused("دلیل ثبت اتصال الزامی است")

        context = await self.repository.line_context(scope, estimate_line_id)
        if context is None:
            raise ItemPriceMappingRefused("این ردیف برآورد در این پروژه یافت نشد")

        # The listing must be this tenant's, and that is established by looking it up in
        # scope rather than by trusting the id in the body.
        if not await self._listing_exists(scope, payload.provider_item_id):
            raise ItemPriceMappingRefused("این محصول در فهرست قیمت روز این پروژه نیست")

        # A listing with no validated observation yet may still be mapped: which product
        # this is and what it currently costs are different facts, and the row simply
        # reports «بدون قیمت روز» until a good price arrives.
        prices = await self.repository.latest_prices_for_items(
            scope, [payload.provider_item_id])
        observation = prices.get(payload.provider_item_id)

        source_unit = _source_unit(observation or {})
        status, factor_id = await self._conversion_for(
            scope, payload.provider_item_id, source_unit, selected)

        values = {
            "provider_item_id": payload.provider_item_id,
            "selected_unit": selected,
            "source_price_unit": source_unit,
            "source_price_basis": (observation or {}).get("source_currency"),
            "conversion_status": status,
            "conversion_factor_id": factor_id,
            "effective_from": payload.effective_from or self.clock(),
            "reason": reason,
            "source_assignment_uid": context.get("source_assignment_uid"),
            "source_task_uid": context.get("source_task_uid"),
            "source_resource_uid": context.get("source_resource_uid"),
        }
        return await self.repository.append_mapping(
            scope, estimate_line_id=estimate_line_id, finance_resource_id=None,
            values=values, created_by=actor_id)

    async def _listing_exists(self, scope, provider_item_id):
        """Whether this project has this listing at all.

        Inactive ones count: an operator maps the product the schedule actually used, and a
        listing that left the sheet is still what was bought. The row then says so.
        """
        return await self.repository.listing_exists(scope, provider_item_id)

    async def _conversion_for(self, scope, provider_item_id, source_unit, selected_unit):
        """Which kind of crossing this mapping needs, and the factor when it needs one.

        Stored on the mapping so a reader sees what was approved, and so a later change to
        the factor is visible as a change rather than as a silently different price.
        """
        if not source_unit or source_unit not in UNIT_REGISTRY:
            return "unknown", None
        if source_unit == selected_unit or can_convert(source_unit, selected_unit):
            return "automatic", None
        factors = await self.repository.approved_factors_for_items(scope, [provider_item_id])
        factor = _factor_for(factors, {"provider_item_id": provider_item_id,
                                       "selected_unit": selected_unit}, source_unit)
        if factor is not None:
            return "factor", factor["id"]
        # No approved measurement. Recorded as unknown rather than refused: the mapping
        # itself is still a true statement about which product this is, and the row reports
        # «ضریب تبدیل لازم است» until somebody measures it.
        return "unknown", None


def _source_unit(observation):
    """The unit this listing's price is stated in, or None.

    One rule, shared with the prices page and with the component pricing: a label a person
    recorded wins, then the observation's own normalized unit, then the raw sheet text --
    all through the same spelling table. Without the label the mapping reported «واحد قیمت
    مبدأ مشخص نیست» beside a prices page that had resolved the very same listing.
    """
    return stated_source_unit(observation,
                              {"source_unit": observation.get("label_source_unit")})


def _factor_for(factors, mapping, source_unit):
    """An approved measurement for this listing and this crossing, either direction.

    Stored one way round and usable both: a factor of 22 kg per branch answers branch->kg
    directly, and the reverse is the same measurement read backwards.
    """
    item = mapping.get("provider_item_id")
    target = mapping.get("selected_unit")
    if not item or not target or not source_unit:
        return None
    direct = factors.get((item, source_unit, target))
    if direct is not None:
        return direct
    reverse = factors.get((item, target, source_unit))
    if reverse is not None and reverse.get("factor"):
        try:
            inverted = dict(reverse)
            inverted["factor"] = 1 / reverse["factor"]
            return inverted
        except (ZeroDivisionError, ArithmeticError):
            return None
    return None


def _text(value):
    return None if value is None else str(value)
