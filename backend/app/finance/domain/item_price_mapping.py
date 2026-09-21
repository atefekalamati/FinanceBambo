# -*- coding: utf-8 -*-
"""What a mapped schedule item costs at today's price, and why it sometimes cannot say.

One pure function, `price_item`, and the vocabulary it answers in. No database, no clock, no
network: everything it needs is handed in, so every case below can be stated as a test
without a fixture.

THE ARITHMETIC, AND WHY THE PRICE DIVIDES

    converted_daily_unit_price = daily price converted into the selected official unit
    daily_item_cost            = MSP quantity x converted_daily_unit_price

A quantity multiplies by the factor and a unit PRICE divides by it, because a price is money
PER unit. Going from kilograms to grams multiplies a quantity by 1000 and divides a price by
1000: 1000 toman/kg is 1 toman/g. Getting that backwards turns a correct price into one off
by the square of the factor, and it looks plausible.

A product factor crosses a dimension the registry cannot: «شاخه» to kilogram is a fact about
one product, not about units. 92,560 toman per branch at 22 kg per branch is 4,207.27 toman
per kilogram -- again a division, for the same reason.

WHAT IT REFUSES

Nothing here guesses. No default unit, no assumed factor, no "near enough" crossing, and no
zero standing in for an unknown. Every refusal returns a status and a Persian reason naming
what is missing, because the person who can fix it is reading the page, not the log.
"""

from decimal import ROUND_HALF_UP, Decimal

from .unit_conversion import (ConversionRefused, PRICE_PRECISION, apply_product_factor,
                              can_convert, convert_unit_price)
from .unit_registry import UNIT_REGISTRY
from .conversion_rules import (PROVIDER_ITEM_FACTOR, REGISTRY_FACTOR)

#: Money leaves this module whole. See `_priced` for why -- both the system's own rule and
#: the one the page can actually render.
WHOLE_RIAL = Decimal(1)

#: Ready: a price, a unit, and a crossing that worked.
READY = "ready"
#: Nobody has said which market product this item is.
NEEDS_PRODUCT = "needs_product"
#: No official calculation unit has been chosen.
NEEDS_UNIT = "needs_unit"
#: The units cross a dimension, and no approved factor exists for this product.
NEEDS_FACTOR = "needs_factor"
#: The units cannot be crossed at all, factor or not.
INCOMPATIBLE = "incompatible"
#: There is a mapping and a unit, but no readable price behind it.
NO_PRICE = "no_price"

#: What each status says to the person who can act on it. Persian, because the page is.
STATUS_REASONS: dict[str, str] = {
    READY: "",
    NEEDS_PRODUCT: "محصول قیمت روز انتخاب نشده",
    NEEDS_UNIT: "واحد رسمی انتخاب نشده",
    NEEDS_FACTOR: "ضریب تبدیل لازم است",
    INCOMPATIBLE: "تبدیل واحد ناسازگار است",
    NO_PRICE: "قیمت روز معتبر وجود ندارد",
}

#: The label the table shows for each status.
STATUS_LABELS: dict[str, str] = {
    READY: "آماده",
    NEEDS_PRODUCT: "نیازمند انتخاب نوع قلم",
    NEEDS_UNIT: "نیازمند انتخاب واحد",
    NEEDS_FACTOR: "نیازمند ضریب تبدیل",
    INCOMPATIBLE: "ناسازگار",
    NO_PRICE: "بدون قیمت روز",
}


class ItemPrice:
    """One item's answer: a status, a reason, and the figures when there are any."""

    __slots__ = ("status", "reason", "unit_price_irr", "item_cost_irr", "selected_unit",
                 "source_unit", "factor_applied", "factor_source", "quantity")

    def __init__(self, status, *, reason=None, unit_price_irr=None, item_cost_irr=None,
                 selected_unit=None, source_unit=None, factor_applied=None,
                 factor_source=None, quantity=None):
        self.status = status
        self.reason = STATUS_REASONS[status] if reason is None else reason
        self.unit_price_irr = unit_price_irr
        self.item_cost_irr = item_cost_irr
        self.selected_unit = selected_unit
        self.source_unit = source_unit
        self.factor_applied = factor_applied
        #: WHERE the factor came from -- a measurement of this listing, or a rule from the
        #: scope ladder. The number alone cannot say, and a reader deciding whether to
        #: trust a converted price needs to know whether somebody weighed this product or
        #: whether a project-wide rule answered for it. `price_component` has carried this
        #: since components were added; the item path reported the number and not its
        #: provenance, so the table could not write «قانون تبدیل» beside it.
        self.factor_source = factor_source
        self.quantity = quantity

    @property
    def label(self):
        return STATUS_LABELS[self.status]

    def as_dict(self):
        """Snake-case, like every repository row in this codebase.

        `ApiModel` is what turns these into camelCase on the wire, and `router._declared`
        selects by the model's own field names -- which are the python ones. Returning
        camelCase here produced a 500 that named two "missing" fields that were both
        present under another spelling.
        """
        return {
            "status": self.status,
            "status_label": self.label,
            "reason": self.reason or None,
            "converted_daily_unit_price_irr": _text(self.unit_price_irr),
            "daily_item_cost_irr": _text(self.item_cost_irr),
            "selected_unit": self.selected_unit,
            "source_unit": self.source_unit,
            "conversion_factor": _text(self.factor_applied),
            "factor_source": self.factor_source,
            "quantity": _text(self.quantity),
        }


def _text(value):
    """Decimal as a string, so no JSON encoder can round money into a float."""
    return None if value is None else str(value)


def _decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:                                              # noqa: BLE001
        return None


def price_item(*, mapping, price_irr, source_unit, quantity, factor=None,
               factor_source=None):
    """What one item costs per day, or which answer is missing.

    `mapping` is the stored row (or None when nobody has mapped this item). `price_irr` and
    `source_unit` come from the newest observation behind it -- the LIVE price, not the one
    recorded when the mapping was approved, because the point of a daily price is that it
    moves. `factor` is an approved product measurement as a Decimal, or None.

    `quantity` is the schedule's own quantity for this item. Missing quantity is not a
    failure of pricing: the unit price is still stated and the item cost is null, because a
    cost nobody can compute must not become zero.

    `factor_source` travels with `factor` and says which kind of evidence it is. It is
    carried, never derived: this function has no way to know where a number came from, and
    guessing would put a label on somebody else's decision.
    """
    if mapping is None or not mapping.get("provider_item_id"):
        return ItemPrice(NEEDS_PRODUCT)

    selected = (mapping.get("selected_unit") or "").strip()
    if not selected or selected not in UNIT_REGISTRY:
        # An unknown code is as unusable as an absent one, and says the same thing to the
        # person who has to choose: the official unit is not settled.
        return ItemPrice(NEEDS_UNIT, selected_unit=selected or None)

    price = _decimal(price_irr)
    if price is None:
        return ItemPrice(NO_PRICE, selected_unit=selected, source_unit=source_unit)

    source = (source_unit or "").strip()
    if not source or source not in UNIT_REGISTRY:
        # The price exists but nothing says what it is per. Converting would be inventing
        # the missing half of "money per what".
        return ItemPrice(NEEDS_UNIT, reason="واحد قیمت مبدأ مشخص نیست",
                         selected_unit=selected, source_unit=source or None)

    quantity_value = _decimal(quantity)

    if source == selected:
        # No crossing at all, so no factor and nothing to attribute.
        return _priced(price, quantity_value, selected, source, None)

    if can_convert(source, selected):
        # Same dimension: the registry's exact ratio, inverted because this is a price.
        # `REGISTRY_FACTOR` rather than None -- «کیلوگرم» to «تن» IS a conversion and a
        # reader asking where the number came from deserves the true answer, which is
        # arithmetic rather than anybody's judgement.
        converted = convert_unit_price(price, source, selected)
        return _priced(converted, quantity_value, selected, source, None, REGISTRY_FACTOR)

    # Different dimensions. Only a measurement of THIS product can cross them, and only if
    # somebody approved one -- see `provider_item_unit_factors`.
    measured = _decimal(factor)
    if measured is None or measured == 0:
        if not _crossable(source, selected):
            return ItemPrice(INCOMPATIBLE, selected_unit=selected, source_unit=source)
        return ItemPrice(NEEDS_FACTOR, selected_unit=selected, source_unit=source)

    try:
        converted = apply_product_factor(price, measured)
    except (ConversionRefused, ArithmeticError):
        return ItemPrice(INCOMPATIBLE, selected_unit=selected, source_unit=source)
    return _priced(converted, quantity_value, selected, source, measured,
                   factor_source or PROVIDER_ITEM_FACTOR)


def _crossable(source, selected):
    """Whether a product measurement could bridge these two at all.

    Both have to be units the registry knows; beyond that a factor is a statement about a
    product and this module is in no position to rule it out. What it DOES rule out is a
    crossing nobody could measure -- there is no number of kilograms in an hour.
    """
    left, right = UNIT_REGISTRY.get(source), UNIT_REGISTRY.get(selected)
    if left is None or right is None:
        return False
    timeish = {"time", "equipment_time"}
    # A physical amount and a duration are not two units of one thing. Refusing here is what
    # makes «ناسازگار» mean something different from «ضریب تبدیل لازم است».
    return (left.dimension in timeish) == (right.dimension in timeish)


def _priced(unit_price, quantity, selected, source, factor, factor_source=None):
    """Both figures as WHOLE RIALS, which is what money is everywhere else in Finance.

    The conversion itself keeps full precision -- the cost is computed from the exact
    converted price and only then rounded, so rounding the rate does not compound through
    the multiplication. What leaves is whole, for two reasons.

    It is the rule this system already holds. `_file_rate_rials` says "a per-unit rate in
    whole rials. Money is whole here, and a rate is money", `price_versions` is checked for
    it by a finance invariant, and `estimate_lines` by another.

    And it is the only thing the page can render. `irrToToman` matches `^-?\\d+$` and
    converts with BigInt, deliberately, so a decimal string is not money to it and comes
    back as an em dash. Sending `913600.00000000` therefore printed «—» in the قیمت روز
    column while the status beside it said «آماده» -- a row claiming to be priced and
    showing nothing, which is worse than either alone.

    Precision is not lost where it matters: a whole rial is a tenth of a toman, so the
    specification's 4,207.27 toman/kg is 42,073 rials and still reads as 4,207.3 toman.
    """
    if unit_price is None:
        return ItemPrice(READY, unit_price_irr=None, item_cost_irr=None,
                         selected_unit=selected, source_unit=source, factor_applied=factor,
                         factor_source=factor_source, quantity=quantity)
    exact_cost = None if quantity is None else quantity * unit_price
    return ItemPrice(READY,
                     unit_price_irr=unit_price.quantize(WHOLE_RIAL, rounding=ROUND_HALF_UP),
                     item_cost_irr=(None if exact_cost is None
                                    else exact_cost.quantize(WHOLE_RIAL,
                                                             rounding=ROUND_HALF_UP)),
                     selected_unit=selected, source_unit=source, factor_applied=factor,
                     factor_source=factor_source, quantity=quantity)
