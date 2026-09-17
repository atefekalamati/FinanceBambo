# -*- coding: utf-8 -*-
"""Adding materials to an MSP line, and pricing the line from them.

THE READ SIDE answers one question for a whole table at once: for each estimate line, which
materials has somebody said it uses, what does each cost at today's price in the unit they
chose, and what does that make the line cost per day. Four queries for the page -- the
components, the newest price behind each listing, the approved factors, and the line
quantities -- and then pure arithmetic in `domain.item_price_components`, which touches
nothing.

THE WRITE SIDE refuses rather than guesses. An unknown unit, a listing from another tenant,
a usage mode nobody chose, a blank reason: each is a 422 naming what is missing. A crossing
that needs a product measurement is never satisfied by a number in the request body, because
a number typed into a component form is not a measurement anybody approved -- it has to be
in `provider_item_unit_factors` with an approver against it.

WHAT IS STORED AT SAVE TIME, AND WHY IT IS NOT THE ANSWER
The converted price, the component quantity and the cost are written onto the row as they
stood when it was approved. They are evidence, not the current figure: a daily price moves,
and the read path recomputes from the newest observation every time. Storing them lets a
reader see that today differs from what was agreed, and by how much.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from ..domain.errors import FinanceDomainError
from ..domain.item_price_components import (PER_MSP_UNIT, TOTAL_QUANTITY, USAGE_MODES,
                                            PricedComponent, aggregate_row,
                                            price_component)
from ..domain.conversion_rules import choose_conversion
from ..domain.material_categories import category_label, spec_columns, specs_of
from ..domain.unit_conversion import can_convert
from ..domain.unit_registry import UNIT_REGISTRY
from .material_price_resolution import stated_source_unit


class ItemPriceComponentRefused(FinanceDomainError):
    status = 422
    code = "FINANCE_ITEM_PRICE_COMPONENT_REFUSED"


class ItemPriceComponentService:
    """Pricing for the «ریز برآورد» table.

    THE FALLBACK THIS SERVICE GAINED

    A crossing that no listing measurement answers used to end the row at
    `needs_factor`, even where an approved project-level rule said exactly how to cross
    those two units. `finance_unit_conversion_rules` -- seven scopes, approval, history
    and precedence -- was never read on this path at all, so recording a rule had no
    effect on the number anybody saw. On the audited project that is 832 of 835 lines
    with no component measurement of their own.

    The rule is consulted ONLY where a listing measurement is absent, so no row that
    prices today changes its number.
    """

    def __init__(self, repository, clock=date.today, conversion_rules=None):
        self.repository = repository
        self.clock = clock
        #: Optional so every existing construction keeps working unchanged; when it is
        #: absent the service behaves exactly as it did before the fallback existed.
        self.conversion_rules = conversion_rules

    # --------------------------------------------------------------------------- read

    async def table_status(self, scope):
        """Every line's pricing state and total, keyed by estimate line id.

        A line with no components is PRESENT in the answer with `needs_components` --
        absent would be indistinguishable from a line the caller forgot to ask about, and
        the table has to show what is waiting.
        """
        components = await self.repository.live_for_project(scope)
        active = [c for c in components if c.get("active")]
        item_ids = {c["provider_item_id"] for c in active}
        prices = await self.repository.latest_prices_for_items(scope, item_ids)
        factors = await self.repository.approved_factors_for_items(scope, item_ids)
        quantities = await self.repository.line_quantities(scope)
        # ONE query for every unit pair the table needs, not one per component. A page of
        # 835 rows asks about a handful of distinct crossings.
        rules = await self._rule_candidates(scope, active, prices)

        by_line = {}
        for component in active:
            by_line.setdefault(component["estimate_line_id"], []).append(component)

        answers = {}
        for line_id, quantity in quantities.items():
            priced = [self._price(c, prices, factors, quantity, rules)
                      for c in by_line.get(line_id, [])]
            row = aggregate_row(priced)
            answers[str(line_id)] = dict(row, estimate_line_id=str(line_id),
                                         **self._source_summary(by_line.get(line_id, []),
                                                                prices, priced))
        # A component on a line the quantity query did not return -- a deleted line, or one
        # outside this project's estimate. Reported rather than dropped: a silently missing
        # row is how a cost disappears from a total nobody is checking.
        for line_id, items in by_line.items():
            orphaned = [self._price(c, prices, factors, None, rules) for c in items]
            answers.setdefault(str(line_id), dict(
                aggregate_row(orphaned),
                estimate_line_id=str(line_id),
                **self._source_summary(items, prices, orphaned)))
        return answers

    @staticmethod
    def _source_summary(components, prices, priced=()):
        """The «منبع» column, and the two units the conversion dialog is opened with.

        A line with ONE component can state its product, the unit its price is quoted in
        and the unit the line consumes it in -- which is exactly what somebody about to
        write a conversion factor needs, and what the table could not show before.

        A line with SEVERAL states none of them, the same way it already declines to name
        one product out of three. Two components can be priced per kilogram and per
        square metre, and putting either in a column headed «واحد شیت قیمت» would be
        picking one arbitrarily.

        No query is added: both values are already in hand.
        """
        empty = {"provider_name": None, "product_name": None, "source_summary": None,
                 "source_price_unit": None, "selected_unit": None, "factor_source": None}
        if not components:
            return empty
        if len(components) == 1:
            component = components[0]
            observation = prices.get(component["provider_item_id"]) or {}
            return {
                "provider_name": observation.get("provider_name"),
                "product_name": observation.get("external_name"),
                "source_summary": None,
                "source_price_unit": _source_unit(observation),
                "selected_unit": component.get("selected_unit"),
                "factor_source": (priced[0].factor_source if priced else None),
            }
        return dict(empty, source_summary="چند مصالح (%d قلم)" % len(components))

    async def _rule_candidates(self, scope, components, prices):
        """Approved rules for every crossing this table needs, fetched once.

        Only pairs that a listing measurement does not already answer are asked for --
        the rule is a fallback, so a crossing already covered costs nothing to look up.
        """
        if self.conversion_rules is None:
            return {}
        pairs = set()
        for component in components:
            observation = prices.get(component["provider_item_id"]) or {}
            source_unit = _source_unit(observation)
            selected = component.get("selected_unit")
            if source_unit and selected and source_unit != selected:
                pairs.add((source_unit, selected))
        if not pairs:
            return {}
        return await self.conversion_rules.candidates_by_pair(scope, pairs)

    def _price(self, component, prices, factors, msp_quantity, rules=None):
        observation = prices.get(component["provider_item_id"]) or {}
        source_unit = _source_unit(observation)
        selected = component.get("selected_unit")
        listing_factor = _factor_for(factors, component["provider_item_id"],
                                     source_unit, selected)
        # The rule ladder, behind the listing's own measurement. `choose_conversion` owns
        # the order and both pricing paths call it, so one row cannot be priced two ways.
        rule = None
        if listing_factor is None and rules and self.conversion_rules is not None:
            rule = self.conversion_rules.rule_from(
                rules, from_unit=source_unit, to_unit=selected,
                provider_item_id=component.get("provider_item_id"),
                provider_id=observation.get("provider_id"),
                category=component.get("category") or observation.get("category"))
        factor, factor_source = choose_conversion(listing_factor, rule)
        return price_component(
            component=dict(component, usage_quantity=component.get("usage_quantity_decimal")),
            price_irr=observation.get("normalized_price_irr"),
            source_unit=source_unit, msp_quantity=msp_quantity,
            factor=factor, factor_source=factor_source)

    async def components_for_line(self, scope, estimate_line_id):
        """Every live component of one line, priced, with the row total beside them.

        This is what the panel reads. Inactive components travel too -- a person who
        retired a material needs to see that they did, and to be able to look at its
        history -- but only the active ones enter the total.
        """
        components = await self.repository.live_for_line(scope, estimate_line_id)
        context = await self.repository.line_context(scope, estimate_line_id)
        quantity = (context or {}).get("quantity")
        item_ids = {c["provider_item_id"] for c in components}
        prices = await self.repository.latest_prices_for_items(scope, item_ids)
        factors = await self.repository.approved_factors_for_items(scope, item_ids)
        # The same fallback the table uses. If the panel and the table consulted different
        # sources, one row would show two different prices depending on which screen
        # opened it, which is worse than either answer alone.
        rules = await self._rule_candidates(scope, components, prices)

        rows, priced_active = [], []
        for component in components:
            priced = self._price(component, prices, factors, quantity, rules)
            observation = prices.get(component["provider_item_id"]) or {}
            rows.append(dict(
                priced.as_dict(),
                id=str(component["id"]),
                estimate_line_id=str(component["estimate_line_id"]),
                provider_item_id=str(component["provider_item_id"]),
                category=component.get("category") or observation.get("category"),
                category_label=category_label(component.get("category")
                                              or observation.get("category")),
                provider_name=observation.get("provider_name"),
                product_name=observation.get("external_name"),
                product_external_id=observation.get("external_id"),
                product_type=component.get("product_type"),
                worksheet=observation.get("source_worksheet"),
                workflow_date_jalali=observation.get("workflow_date_jalali"),
                source_price_irr=_text(observation.get("normalized_price_irr")),
                usage_unit=component.get("usage_unit"),
                conversion_status=component.get("conversion_status"),
                conversion_factor_id=(str(component["conversion_factor_id"])
                                      if component.get("conversion_factor_id") else None),
                active=bool(component.get("active")),
                version=component["version"],
                reason_text=component.get("reason"),
                created_by=component.get("created_by"),
                created_at=component.get("created_at"),
                specs=specs_of(component.get("category") or observation.get("category"),
                               observation.get("metadata")),
                spec_columns=spec_columns(component.get("category")
                                          or observation.get("category"))))
            if component.get("active"):
                priced_active.append(priced)

        return {
            "line": _line_header(context),
            "components": rows,
            "total": aggregate_row(priced_active),
        }

    async def history_for_line(self, scope, estimate_line_id):
        return await self.repository.history_for_line(scope, estimate_line_id)

    async def filters(self, scope, *, category=None, provider_id=None):
        """What the modal's cascading dropdowns may offer at this point in the cascade.

        Providers are scoped by the chosen category and types by category AND provider,
        because the alternative is offering a choice that yields no products -- which reads
        as a broken page rather than as an empty category.
        """
        return {
            "providers": await self.repository.providers(scope, category=category),
            "product_types": await self.repository.product_types(
                scope, category=category, provider_id=provider_id),
            "usage_modes": [
                {"value": PER_MSP_UNIT,
                 "label": "به ازای هر واحد فعالیت",
                 "hint": "مقدار مصالح برای یک واحد از این قلم؛ در مقدار فعالیت ضرب می‌شود"},
                {"value": TOTAL_QUANTITY,
                 "label": "مقدار کل برای این قلم",
                 "hint": "مقدار کل مصالح برای تمام این قلم، مستقل از مقدار فعالیت"},
            ],
            "units": [{"code": code, "label": unit.label_fa, "dimension": unit.dimension,
                       "dimension_label": unit.dimension_label_fa}
                      for code, unit in UNIT_REGISTRY.items() if unit.active],
        }

    async def preview_component(self, scope, *, estimate_line_id, provider_item_id,
                                selected_unit, usage_mode, usage_quantity):
        """What one component would cost, before anything is saved.

        The modal calls it on every change, so «ضریب تبدیل لازم است» is something a person
        sees while choosing rather than discovers after committing.
        """
        prices = await self.repository.latest_prices_for_items(scope, [provider_item_id])
        observation = prices.get(provider_item_id) or {}
        factors = await self.repository.approved_factors_for_items(scope, [provider_item_id])
        source_unit = _source_unit(observation)
        factor = _factor_for(factors, provider_item_id, source_unit, selected_unit)
        context = await self.repository.line_context(scope, estimate_line_id)
        priced = price_component(
            component={"component_id": None, "provider_item_id": provider_item_id,
                       "selected_unit": selected_unit, "usage_mode": usage_mode,
                       "usage_quantity": usage_quantity},
            price_irr=observation.get("normalized_price_irr"),
            source_unit=source_unit, msp_quantity=(context or {}).get("quantity"),
            factor=(factor or {}).get("factor"))
        return dict(priced.as_dict(),
                    provider_item_id=str(provider_item_id),
                    product_name=observation.get("external_name"),
                    provider_name=observation.get("provider_name"),
                    source_price_irr=_text(observation.get("normalized_price_irr")),
                    workflow_date_jalali=observation.get("workflow_date_jalali"),
                    conversion_factor_id=(str(factor["id"]) if factor else None),
                    msp_quantity=_text((context or {}).get("quantity")))

    async def preview_total(self, scope, estimate_line_id, draft=None):
        """The line's total as it stands, optionally including one unsaved component.

        `draft` lets the modal show what the row WILL total before the component is saved,
        which is the difference between choosing deliberately and choosing then checking.
        """
        body = await self.components_for_line(scope, estimate_line_id)
        if draft is None:
            return body["total"]
        preview = await self.preview_component(
            scope, estimate_line_id=estimate_line_id,
            provider_item_id=draft["provider_item_id"],
            selected_unit=draft["selected_unit"], usage_mode=draft.get("usage_mode"),
            usage_quantity=draft.get("usage_quantity"))
        live = [_as_priced(row) for row in body["components"] if row["active"]]
        return aggregate_row(live + [_as_priced(preview)])

    # -------------------------------------------------------------------------- write

    async def add_component(self, scope, *, estimate_line_id, payload, actor_id):
        return await self._append(scope, estimate_line_id=estimate_line_id,
                                  component_id=uuid4(), payload=payload,
                                  actor_id=actor_id, active=True)

    async def update_component(self, scope, *, estimate_line_id, component_id, payload,
                               actor_id):
        existing = await self.repository.live_component(scope, estimate_line_id, component_id)
        if existing is None:
            raise ItemPriceComponentRefused("این جزء مصالح برای این ردیف یافت نشد")
        return await self._append(scope, estimate_line_id=estimate_line_id,
                                  component_id=component_id, payload=payload,
                                  actor_id=actor_id, active=True)

    async def deactivate_component(self, scope, *, estimate_line_id, component_id, reason,
                                   actor_id):
        """Retire one material from the line. Appended, never deleted.

        The row stays because a report issued while it was active was calculated with it,
        and a total whose components have vanished cannot be explained afterwards.
        """
        existing = await self.repository.live_component(scope, estimate_line_id, component_id)
        if existing is None:
            raise ItemPriceComponentRefused("این جزء مصالح برای این ردیف یافت نشد")
        text = (reason or "").strip()
        if not text:
            raise ItemPriceComponentRefused("دلیل غیرفعال‌کردن این جزء الزامی است")
        values = {k: existing.get(k) for k in (
            "finance_resource_id", "provider_item_id", "category", "provider_id",
            "product_type", "selected_unit", "source_price_unit", "source_price_basis",
            "usage_mode", "usage_unit", "conversion_status", "conversion_factor_id",
            "converted_daily_unit_price_irr", "component_daily_cost_irr", "status")}
        values["usage_quantity"] = existing.get("usage_quantity_decimal")
        values["component_quantity"] = existing.get("component_quantity_decimal")
        values["reason"] = text
        values["active"] = False
        values["effective_from"] = self.clock()
        return await self.repository.append(
            scope, component_id=component_id, estimate_line_id=estimate_line_id,
            values=values, created_by=actor_id)

    async def _append(self, scope, *, estimate_line_id, component_id, payload, actor_id,
                      active):
        selected = (payload.selected_unit or "").strip()
        if selected not in UNIT_REGISTRY:
            raise ItemPriceComponentRefused(
                "واحد رسمی باید یکی از واحدهای ثبت‌شده در سامانه باشد")
        reason = (payload.reason or "").strip()
        if not reason:
            raise ItemPriceComponentRefused("دلیل ثبت این جزء الزامی است")
        if payload.usage_mode not in USAGE_MODES:
            raise ItemPriceComponentRefused(
                "نحوهٔ مصرف مصالح باید «به ازای هر واحد فعالیت» یا «مقدار کل» باشد")
        if payload.usage_quantity is None:
            raise ItemPriceComponentRefused("مقدار مصرف مصالح الزامی است")
        if payload.usage_quantity < 0:
            raise ItemPriceComponentRefused("مقدار مصرف مصالح نمی‌تواند منفی باشد")

        context = await self.repository.line_context(scope, estimate_line_id)
        if context is None:
            raise ItemPriceComponentRefused("این ردیف برآورد در این پروژه یافت نشد")
        listing = await self.repository.listing_exists(scope, payload.provider_item_id)
        if listing is None:
            raise ItemPriceComponentRefused("این محصول در فهرست قیمت روز این پروژه نیست")

        prices = await self.repository.latest_prices_for_items(
            scope, [payload.provider_item_id])
        observation = prices.get(payload.provider_item_id) or {}
        source_unit = _source_unit(observation)
        factors = await self.repository.approved_factors_for_items(
            scope, [payload.provider_item_id])
        factor = _factor_for(factors, payload.provider_item_id, source_unit, selected)
        status, factor_id = _conversion_for(source_unit, selected, factor)

        # The figures AS AT APPROVAL. Evidence, not the answer -- see the module docstring.
        priced = price_component(
            component={"component_id": component_id,
                       "provider_item_id": payload.provider_item_id,
                       "selected_unit": selected, "usage_mode": payload.usage_mode,
                       "usage_quantity": payload.usage_quantity},
            price_irr=observation.get("normalized_price_irr"), source_unit=source_unit,
            msp_quantity=context.get("quantity"), factor=(factor or {}).get("factor"))

        values = {
            "finance_resource_id": context.get("resource_id"),
            "provider_item_id": payload.provider_item_id,
            "category": listing.get("category"),
            "provider_id": listing.get("provider_id"),
            "product_type": (payload.product_type or "").strip() or None,
            "selected_unit": selected,
            "source_price_unit": source_unit,
            "source_price_basis": observation.get("source_currency"),
            "usage_mode": payload.usage_mode,
            "usage_quantity": payload.usage_quantity,
            "usage_unit": (payload.usage_unit or "").strip() or selected,
            "conversion_status": status,
            "conversion_factor_id": factor_id,
            "converted_daily_unit_price_irr": priced.unit_price_irr,
            "component_quantity": priced.quantity,
            "component_daily_cost_irr": priced.cost_irr,
            "status": priced.status,
            "reason": reason,
            "active": active,
            "effective_from": payload.effective_from or self.clock(),
        }
        return await self.repository.append(
            scope, component_id=component_id, estimate_line_id=estimate_line_id,
            values=values, created_by=actor_id)


def _line_header(context):
    """What the panel shows at the top: which activity is being priced."""
    if context is None:
        return None
    return {
        "estimate_line_id": str(context["id"]),
        "activity_external_id": context.get("activity_external_id"),
        "title": context.get("resource_title"),
        "msp_unit": context.get("msp_unit") or context.get("base_unit"),
        "msp_quantity": _text(context.get("quantity")),
        "msp_cost_irr": _text(context.get("msp_cost_irr")),
        "original_unit_price_irr": _text(context.get("original_unit_price_irr")),
    }


def _conversion_for(source_unit, selected_unit, factor):
    """Which kind of crossing this component needs, recorded on the row.

    Stored so a later change to the factor is visible as a change, rather than as a
    silently different price under an unchanged component.
    """
    if not source_unit or source_unit not in UNIT_REGISTRY:
        return "unknown", None
    if source_unit == selected_unit or can_convert(source_unit, selected_unit):
        return "automatic", None
    if factor is not None:
        return "factor", factor["id"]
    # No approved measurement. Recorded as unknown rather than refused: naming the product
    # is still a true statement, and the row says «ضریب تبدیل لازم است» until somebody
    # measures it.
    return "unknown", None


def _source_unit(observation):
    """The unit this listing's price is stated in, or None.

    One rule, shared with the prices page: a label a person recorded wins, then the
    observation's own normalized unit, then the raw sheet text -- all through the same
    spelling table, so a spelling nothing recognises stays unresolved.
    """
    return stated_source_unit(observation,
                              {"source_unit": observation.get("label_source_unit")})


def _factor_for(factors, provider_item_id, source_unit, target_unit):
    """An approved measurement for this listing and this crossing, either direction.

    Stored one way round and usable both: 22 kg per branch answers branch->kg directly, and
    the reverse is the same measurement read backwards.
    """
    if not provider_item_id or not source_unit or not target_unit:
        return None
    direct = factors.get((provider_item_id, source_unit, target_unit))
    if direct is not None:
        return direct
    reverse = factors.get((provider_item_id, target_unit, source_unit))
    if reverse is not None and reverse.get("factor"):
        try:
            return dict(reverse, factor=1 / reverse["factor"])
        except (ZeroDivisionError, ArithmeticError):
            return None
    return None


def _as_priced(row):
    """A response row back into the object `aggregate_row` sums.

    Only the three fields the total depends on -- the status that decides whether it counts,
    the reason the row repeats, and the cost. Rebuilding it this way rather than threading
    the priced objects through keeps one shape on the wire and one in the arithmetic.
    """
    cost = row.get("component_daily_cost_irr")
    return PricedComponent(
        row["status"], component_id=row.get("component_id"), reason=row.get("reason"),
        cost_irr=None if cost in (None, "") else Decimal(cost))


def _text(value):
    return None if value is None else str(value)
