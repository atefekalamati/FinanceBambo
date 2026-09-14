# -*- coding: utf-8 -*-
"""From an observation to a price somebody can act on -- or to a stated reason they cannot.

This is where the four ways a price can be unusable are told apart, because a reader who is
shown nothing cannot tell them apart and a reader who is shown a zero is being misled:

    unresolved_price   the newest observation could not be read (blank, unparseable)
    unresolved_unit    there is a price, but not in the unit this category is displayed in,
                       and no factor exists to convert it
    unmapped           there is a price, but no approved mapping to a Finance resource
    stale              there is a price and it is older than the freshness window
    resolved           a price, in the right unit, with its provenance

CONVERSION, AND WHAT IS NEVER INVENTED

A unit price converts INVERSELY to a quantity: 1000 Toman per kilogram is 1 Toman per gram,
so the price is divided by the same factor a quantity would be multiplied by. Only two
kinds of factor are used, and both must already exist:

  * a dimension-compatible one from `unit_conversions` (gram/kilogram, metre/centimetre);
  * a product-specific one from `provider_item_unit_factors` (this brick weighs this much).

Nothing here derives a density, a weight per piece, a length per branch, a bag mass or a
coverage factor. When the factor needed is absent the answer is `unresolved_unit` with the
two units named, and the price is withheld rather than relabelled.
"""

from decimal import Decimal, ROUND_HALF_UP

#: How a converted unit price is rounded. Stated once, in one place, so two callers cannot
#: round differently and then disagree about the same price. Eight places is the same
#: precision `unit_conversions.factor` is stored at.
PRICE_QUANTUM = Decimal("0.00000001")

#: Units that mean the same thing written differently. The sheet says «کیلو», the Finance
#: unit registry says «kg», and neither is wrong. Comparing them as strings without this
#: would report `unresolved_unit` for a price that needs no conversion at all.
UNIT_ALIASES = {
    "کیلو": "kg",
    "کیلوگرم": "kg",
    "kilogram": "kg",
    "kg": "kg",
    "گرم": "g",
    "gram": "g",
    "g": "g",
    "متر": "m",
    "meter": "m",
    "metre": "m",
    "m": "m",
    "سانتیمتر": "cm",
    "سانتی‌متر": "cm",
    "cm": "cm",
    "عدد": "piece",
    "piece": "piece",
    "شاخه": "branch",
    "branch": "branch",
    "تن": "ton",
    "ton": "ton",
    "مترمربع": "m2",
    "m2": "m2",
}


def canonical_unit(unit):
    """The agreed spelling of a unit, or `None` when nothing was stated.

    An unrecognised unit is returned as it arrived, lowercased and trimmed. It is not
    mapped to a guess: an unknown unit that silently became `kg` would be worse than one
    that stays unknown and reports `unresolved_unit`.
    """
    if unit is None:
        return None
    text = str(unit).strip()
    if not text:
        return None
    return UNIT_ALIASES.get(text, UNIT_ALIASES.get(text.lower(), text.lower()))


def convert_unit_price(price, factor):
    """A unit price in a new unit. Inverse, because it is a price PER something.

    `factor` is the quantity factor: how many target units make one source unit. One
    kilogram is 1000 grams, so a per-kilogram price becomes a per-gram price by dividing
    by 1000 -- the opposite of what a quantity does, which is the mistake this function
    exists to make impossible to write by accident.
    """
    if price is None or factor is None:
        return None
    if factor <= 0:
        raise ValueError("a conversion factor must be positive, got %s" % factor)
    return (Decimal(price) / Decimal(factor)).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def resolve(observation, *, display_unit=None, conversion_lookup=None, as_of=None,
            stale_after_days=None):
    """`(price, status, reason, factor, note)` for one observation.

    `conversion_lookup(source_unit, target_unit)` returns a factor or `None`. It is passed
    in rather than reached for, so this function stays pure and the caller decides which
    of the two factor tables answers -- and, importantly, so an absent factor is an
    ordinary `None` rather than an exception nobody handles.
    """
    price = observation.get("normalized_price_irr")
    status_of_row = observation.get("validation_status")

    if price is None or status_of_row in ("rejected", "pending"):
        reasons = observation.get("validation_reasons") or []
        return (None, "unresolved_price",
                "; ".join(str(r) for r in reasons) or "the newest observation has no readable price",
                None, None)

    source = canonical_unit(observation.get("source_unit"))
    target = canonical_unit(display_unit)

    factor = None
    note = None
    if target is not None and source is not None and source != target:
        factor = conversion_lookup(source, target) if conversion_lookup else None
        if factor is None:
            return (None, "unresolved_unit",
                    "no conversion factor from %r to %r for this product; the price is "
                    "withheld rather than relabelled" % (source, target), None, None)
        price = convert_unit_price(price, factor)
        note = "converted from %s to %s by dividing the unit price by %s" % (source, target, factor)
    elif target is not None and source is None:
        # A price exists and the category is displayed in a unit, but the sheet never said
        # what the price is per. Relabelling it would be inventing the basis.
        return (None, "unresolved_unit",
                "the source states no unit for this price, so it cannot be shown per %s"
                % target, None, None)

    if stale_after_days is not None and as_of is not None:
        when = observation.get("workflow_date_gregorian")
        if when is not None and (as_of - when).days > stale_after_days:
            return (price, "stale",
                    "the newest price the sheet states is from %s, more than %d days ago"
                    % (when.isoformat(), stale_after_days), factor, note)

    return (price, "resolved", None, factor, note)
