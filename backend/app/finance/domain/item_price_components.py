# -*- coding: utf-8 -*-
"""What an MSP activity costs at today's prices, when the file never said what it consumes.

THE PROBLEM

«کانال‌کنی» is 500 cubic metres of trenching. The schedule states the activity, its unit and
its quantity, and says nothing at all about materials -- because a schedule describes work,
not a bill of materials. Yet the activity does consume things: rebar, pipe, brick. Pricing
it from today's market means somebody has to say WHICH materials and HOW MUCH, and that is a
judgement no file contains and nothing here may invent.

So a line is priced by a LIST of components. Each one names a real market listing, an
official unit, and how much of it this activity uses. One line, many materials, each priced
on its own and summed.

THE TWO WAYS TO SAY "HOW MUCH"

    per_msp_unit    this much material for each 1 unit of the activity
                    component_quantity = MSP quantity x usage_quantity
                    "80 kg of rebar per cubic metre" -> 500 m3 uses 40,000 kg

    total_quantity  this much material for the whole activity, however big it is
                    component_quantity = usage_quantity
                    "1,200 metres of pipe for the whole trench"

The distinction is the user's to make and cannot be guessed from the numbers: 500 could be
the per-unit figure or the total, and the two differ by a factor of the activity quantity.

WHY A USAGE FACTOR IS NOT A UNIT CONVERSION

"80 kg per m3" looks like a conversion and is not one. A unit conversion says two units
measure the same thing -- a kilogram and a tonne are both mass, and 1000 is a fact about the
units. "80 kg of rebar per cubic metre of trench" is a fact about THIS activity as somebody
designed it, true for one project and false for the next. It is entered, stored with a
reason and an author, and never derived. `unit_conversion` is not consulted for it and
cannot be.

WHAT IT REFUSES

A component missing any of its four answers -- which product, which unit, how much, at what
price -- contributes NOTHING and says which answer is missing, in Persian. It is never
counted as zero. A row whose components are partly resolved reports the resolved total AND
says it is partial, because a total that silently omits half the materials is worse than no
total: it looks finished.
"""

from decimal import ROUND_HALF_UP, Decimal

from .unit_conversion import (ConversionRefused, apply_product_factor, can_convert,
                              convert_unit_price)
from .unit_registry import UNIT_REGISTRY

#: Money leaves whole, as it does everywhere in Finance. `AGENTS.md` is explicit: monetary
#: values are integer-IRR strings and every fractional form is rejected, including one with
#: a zero fractional part.
WHOLE_RIAL = Decimal(1)

#: How much material this line uses, and what the number means.
PER_MSP_UNIT = "per_msp_unit"
TOTAL_QUANTITY = "total_quantity"
USAGE_MODES = (PER_MSP_UNIT, TOTAL_QUANTITY)

# ----------------------------------------------------------------- component statuses
READY = "ready"
NEEDS_PRODUCT = "needs_product"
NEEDS_PRODUCT_TYPE = "needs_product_type"
NEEDS_UNIT = "needs_unit"
NEEDS_USAGE_QUANTITY = "needs_usage_quantity"
UNKNOWN_SOURCE_UNIT = "unknown_source_unit"
NEEDS_FACTOR = "needs_factor"
INCOMPATIBLE = "incompatible"
NO_PRICE = "no_price"

# ---------------------------------------------------------------------- row statuses
#: The row has no components at all. Distinct from every component failure: nothing is
#: wrong, nobody has started.
NEEDS_COMPONENTS = "needs_components"
#: Some components priced and some did not. The resolved total is real and incomplete, and
#: the row must say both.
PARTIALLY_UNRESOLVED = "partially_unresolved"
#: The line's own RESOURCE carries a price, so it needs no material components at all.
#:
#: «نیازمند افزودن مصالح» was being shown for a truck, a grader and sixteen other machines,
#: and it was not merely unhelpful -- it was untrue. A machine is not built out of
#: materials; it is hired at a rate somebody agreed. The old vocabulary could not say
#: "priced, and nothing is missing" for anything that was not assembled from parts, so the
#: only status left to give was a demand for work that must never be done.
RESOURCE_PRICE_READY = "resource_price_ready"

STATUS_LABELS: dict[str, str] = {
    READY: "آماده",
    NEEDS_COMPONENTS: "نیازمند افزودن مصالح",
    NEEDS_PRODUCT_TYPE: "نیازمند انتخاب نوع محصول",
    NEEDS_PRODUCT: "نیازمند انتخاب محصول قیمت روز",
    NEEDS_UNIT: "نیازمند انتخاب واحد",
    NEEDS_USAGE_QUANTITY: "نیازمند مقدار مصرف مصالح",
    UNKNOWN_SOURCE_UNIT: "واحد قیمت مبدأ مشخص نیست",
    NEEDS_FACTOR: "نیازمند ضریب تبدیل",
    INCOMPATIBLE: "تبدیل واحد ناسازگار است",
    NO_PRICE: "قیمت روز معتبر وجود ندارد",
    PARTIALLY_UNRESOLVED: "بخشی از اجزای قیمت‌گذاری ناقص است",
    RESOURCE_PRICE_READY: "قیمت منبع ثبت شده است",
}

#: The sentence shown to the person who can fix it. Equal to the label for most statuses --
#: the label already names the missing thing -- and only different where a label is a
#: heading and the reason is the instruction.
STATUS_REASONS: dict[str, str] = dict(STATUS_LABELS,
                                     **{READY: "", RESOURCE_PRICE_READY: ""})


def _decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:                                              # noqa: BLE001
        return None


def _text(value):
    """A Decimal as a string, so no JSON encoder can round money through a float."""
    return None if value is None else str(value)


class PricedComponent:
    """One material of one line: what it costs, or which answer is missing."""

    __slots__ = ("component_id", "status", "reason", "unit_price_irr", "quantity",
                 "cost_irr", "selected_unit", "source_unit", "factor_applied",
                 "factor_source", "usage_mode", "usage_quantity")

    def __init__(self, status, *, component_id=None, reason=None, unit_price_irr=None,
                 quantity=None, cost_irr=None, selected_unit=None, source_unit=None,
                 factor_applied=None, factor_source=None, usage_mode=None,
                 usage_quantity=None):
        self.component_id = component_id
        self.status = status
        self.reason = STATUS_REASONS[status] if reason is None else reason
        self.unit_price_irr = unit_price_irr
        self.quantity = quantity
        self.cost_irr = cost_irr
        self.selected_unit = selected_unit
        self.source_unit = source_unit
        self.factor_applied = factor_applied
        #: Where the number that crossed the units came from. Without it two figures of
        #: very different standing share one column: a weighing of THIS product and a
        #: general rule somebody wrote for a whole category look identical, and a reviewer
        #: cannot tell which they are being asked to trust.
        #:
        #:     provider_item     a measurement recorded against this listing
        #:     conversion_rule   a rule from the scope ladder
        #:     registry          same dimension; arithmetic, true of every product
        #:     None              nothing was converted
        self.factor_source = factor_source
        self.usage_mode = usage_mode
        self.usage_quantity = usage_quantity

    @property
    def label(self):
        return STATUS_LABELS[self.status]

    def as_dict(self):
        """Snake-case, like every repository row here; `ApiModel` camel-cases the wire."""
        return {
            "component_id": None if self.component_id is None else str(self.component_id),
            "status": self.status,
            "status_label": self.label,
            "reason": self.reason or None,
            "converted_daily_unit_price_irr": _text(self.unit_price_irr),
            "component_quantity": _text(self.quantity),
            "component_daily_cost_irr": _text(self.cost_irr),
            "selected_unit": self.selected_unit,
            "source_unit": self.source_unit,
            "conversion_factor": _text(self.factor_applied),
            "factor_source": self.factor_source,
            "usage_mode": self.usage_mode,
            "usage_quantity": _text(self.usage_quantity),
        }


#: Where a conversion number came from. Three sources of very different standing, and a
#: reader has to be able to tell them apart:
#:
#:     PROVIDER_ITEM_FACTOR   somebody weighed THIS product and recorded it
#:     CONVERSION_RULE_FACTOR a rule from the scope ladder -- broader, and a claim about
#:                            a category or a supplier rather than about this listing
#:     REGISTRY_FACTOR        the unit registry's own ratio: arithmetic, true of every
#:                            product, and never a judgement about any of them
#: Re-exported from `conversion_rules`, which owns them, so the two pricing paths cannot
#: drift into spelling the same provenance differently.
from .conversion_rules import (CONVERSION_RULE_FACTOR, PROVIDER_ITEM_FACTOR,  # noqa: E402
                               REGISTRY_FACTOR)


def price_component(*, component, price_irr, source_unit, msp_quantity, factor=None,
                    factor_source=None):
    """What one material of one line costs per day, or which answer is missing.

    `component` is the stored row. `price_irr` and `source_unit` come from the newest
    observation behind its listing -- the LIVE price, because the point of a daily price is
    that it moves -- and `factor` is an approved product measurement or None.

    `msp_quantity` is the schedule's own quantity for the line. It is needed only by
    `per_msp_unit`: a component stated as a total is the same number whatever the activity
    measures, and a missing activity quantity must not stop it from pricing.
    """
    component_id = component.get("component_id") or component.get("id")
    usage_mode = component.get("usage_mode")
    usage = _decimal(component.get("usage_quantity"))

    def refuse(status, **over):
        return PricedComponent(status, component_id=component_id, usage_mode=usage_mode,
                               usage_quantity=usage, **over)

    if not component.get("provider_item_id"):
        return refuse(NEEDS_PRODUCT)

    selected = (component.get("selected_unit") or "").strip()
    if not selected or selected not in UNIT_REGISTRY:
        return refuse(NEEDS_UNIT, selected_unit=selected or None)

    # A usage of zero is a real answer -- "this line uses none of it" -- and prices to a
    # real zero cost. Only an ABSENT usage is a missing answer.
    if usage is None:
        return refuse(NEEDS_USAGE_QUANTITY, selected_unit=selected)
    if usage_mode not in USAGE_MODES:
        return refuse(NEEDS_USAGE_QUANTITY, selected_unit=selected,
                      reason="نحوهٔ مصرف مصالح مشخص نشده است")

    price = _decimal(price_irr)
    if price is None:
        return refuse(NO_PRICE, selected_unit=selected, source_unit=source_unit)

    source = (source_unit or "").strip()
    if not source or source not in UNIT_REGISTRY:
        # The price exists and nothing says what it is per. Converting would be inventing
        # the missing half of "money per what".
        return refuse(UNKNOWN_SOURCE_UNIT, selected_unit=selected, source_unit=source or None)

    if source == selected:
        converted, applied, applied_source = price, None, None
    elif can_convert(source, selected):
        # Same dimension: the registry's exact ratio, inverted because this is a price.
        converted, applied = convert_unit_price(price, source, selected), None
        applied_source = REGISTRY_FACTOR
    else:
        measured = _decimal(factor)
        if measured is None or measured == 0:
            if not _crossable(source, selected):
                return refuse(INCOMPATIBLE, selected_unit=selected, source_unit=source)
            return refuse(NEEDS_FACTOR, selected_unit=selected, source_unit=source)
        try:
            converted, applied = apply_product_factor(price, measured), measured
            applied_source = factor_source
        except (ConversionRefused, ArithmeticError):
            return refuse(INCOMPATIBLE, selected_unit=selected, source_unit=source)

    quantity = _component_quantity(usage_mode, usage, _decimal(msp_quantity))
    if quantity is None:
        # `per_msp_unit` with no activity quantity. The price per unit is still known and
        # is reported; the cost is not, and does not become zero.
        return PricedComponent(
            NEEDS_USAGE_QUANTITY, component_id=component_id,
            reason="مقدار این قلم در برنامهٔ زمان‌بندی ثبت نشده است",
            unit_price_irr=converted.quantize(WHOLE_RIAL, rounding=ROUND_HALF_UP),
            selected_unit=selected, source_unit=source, factor_applied=applied,
            factor_source=applied_source, usage_mode=usage_mode, usage_quantity=usage)

    unit_price = converted.quantize(WHOLE_RIAL, rounding=ROUND_HALF_UP)
    # The cost is computed from the EXACT converted price and rounded once, so rounding the
    # rate does not compound through the multiplication.
    cost = (quantity * converted).quantize(WHOLE_RIAL, rounding=ROUND_HALF_UP)
    return PricedComponent(READY, component_id=component_id, unit_price_irr=unit_price,
                           quantity=quantity, cost_irr=cost, selected_unit=selected,
                           source_unit=source, factor_applied=applied,
                           factor_source=applied_source, usage_mode=usage_mode,
                           usage_quantity=usage)


def _component_quantity(usage_mode, usage, msp_quantity):
    """How much of this material the line uses, by what the usage figure means."""
    if usage_mode == TOTAL_QUANTITY:
        return usage
    if msp_quantity is None:
        return None
    return msp_quantity * usage


def _crossable(source, selected):
    """Whether a product measurement could bridge these two units at all.

    What this rules out is a crossing nobody could measure: there is no number of kilograms
    in an hour. That is what makes «ناسازگار» mean something different from «ضریب تبدیل
    لازم است» -- one says ask somebody to weigh the product, the other says stop asking.
    """
    left, right = UNIT_REGISTRY.get(source), UNIT_REGISTRY.get(selected)
    if left is None or right is None:
        return False
    timeish = {"time", "equipment_time"}
    return (left.dimension in timeish) == (right.dimension in timeish)


def aggregate_row(priced):
    """One line's total from its components, and what the total is worth.

    `priced` is every ACTIVE component of the line, already priced. Returns the row's
    status, its Persian reason, the total of the components that resolved, and the counts a
    reader needs to judge that total.

    The total of a partly-resolved row is REAL and INCOMPLETE, and the row says both. Two
    alternatives were rejected: reporting null throws away figures that are correct, and
    reporting the total without the flag presents a partial sum as a finished one -- which
    is the more dangerous of the two, because it looks done.
    """
    components = list(priced)
    ready = [c for c in components if c.status == READY]
    unresolved = [c for c in components if c.status != READY]

    if not components:
        return {
            "status": NEEDS_COMPONENTS,
            "status_label": STATUS_LABELS[NEEDS_COMPONENTS],
            "reason": STATUS_REASONS[NEEDS_COMPONENTS],
            "daily_item_cost_irr": None,
            "component_count": 0, "ready_component_count": 0,
            "unresolved_component_count": 0,
        }

    total = sum((c.cost_irr for c in ready if c.cost_irr is not None), Decimal(0))
    # None, not zero, when nothing resolved: a row where every material is unpriced has no
    # cost, and «۰» would say the activity is free.
    has_total = any(c.cost_irr is not None for c in ready)

    if unresolved:
        # The distinct reasons, so a row with three components missing one thing says that
        # thing rather than a count. Ordered by first appearance, and deduplicated.
        seen, reasons = set(), []
        for component in unresolved:
            if component.reason and component.reason not in seen:
                seen.add(component.reason)
                reasons.append(component.reason)
        detail = "، ".join(reasons)
        status = PARTIALLY_UNRESOLVED if ready else unresolved[0].status
        label = STATUS_LABELS[PARTIALLY_UNRESOLVED] if ready else unresolved[0].label
        reason = ("%s: %s" % (STATUS_LABELS[PARTIALLY_UNRESOLVED], detail)) if ready else detail
    else:
        status, label, reason = READY, STATUS_LABELS[READY], ""

    return {
        "status": status,
        "status_label": label,
        "reason": reason or None,
        "daily_item_cost_irr": _text(total) if has_total else None,
        "component_count": len(components),
        "ready_component_count": len(ready),
        "unresolved_component_count": len(unresolved),
    }


def resource_priced_row(unit_price_irr, quantity, price_unit, price_source):
    """A row priced from its own resource rather than from material components.

    The cost is `quantity x unit_price`, computed HERE so that the page, the report and
    this table cannot each arrive at their own answer. `quantity` may be None -- a line
    whose quantity nobody has stated is priced per unit and has no line total, and the
    difference between "no total" and "a total of zero" is the difference between a
    question and a claim.
    """
    total = None if quantity is None else Decimal(quantity) * Decimal(unit_price_irr)
    return {
        "status": RESOURCE_PRICE_READY,
        "status_label": STATUS_LABELS[RESOURCE_PRICE_READY],
        "reason": STATUS_REASONS[RESOURCE_PRICE_READY],
        "daily_item_cost_irr": total,
        "current_unit_price_irr": Decimal(unit_price_irr),
        "price_unit": price_unit,
        "price_source": price_source,
        # No components were consulted, and saying "0 of 0 ready" would invite the reader
        # to think something is missing. Nothing is.
        "component_count": 0, "ready_component_count": 0,
        "unresolved_component_count": 0,
    }
