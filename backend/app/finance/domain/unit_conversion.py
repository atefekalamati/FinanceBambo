# -*- coding: utf-8 -*-
"""Exact conversion between units the registry already defines.

WHY NOT PINT

The brief allows a library, and the honest answer is that this project already has the
boundary a library would be hidden behind: `unit_registry.UNIT_REGISTRY` says which units
exist and what dimension each belongs to, `units_are_compatible` says whether two may be
compared, `finance_resources.base_unit` is validated against it, and the frontend builds
its dropdowns from `/unit-registry`. What was missing was one thing only -- the RATIO
between two units of the same dimension.

That is a table of eleven exact numbers. Adding a dependency to supply them would mean a
second vocabulary of unit names beside the registry's, which is exactly the parallel system
this is not allowed to become; and Pint computes in float unless carefully configured,
while money here must be Decimal end to end. So the ratios are stated here, exactly, and
everything else stays where it already was.

WHAT IS DELIBERATELY ABSENT

  * day <-> hour. Both are in the registry and `units_are_compatible` already pairs them,
    but a working day is not 24 hours and not 8 either -- it is a project's decision. It
    stays in `unit_conversions`, where a project records its own with a reason and a date.
  * Everything that crosses a dimension: piece to kilogram, branch to metre, bag to
    kilogram, cubic metre to ton, brick count to square metre. None of those is a fact
    about units; each is a fact about one product, and inventing one would be inventing a
    density, a weight per piece or a length per branch. They are refused here and answered
    -- if at all -- by a factor a person stored against that specific listing.
"""

from decimal import Decimal, InvalidOperation

from .unit_registry import UNIT_REGISTRY, units_are_compatible

#: How many base units one of this unit is. Exact, and exact on purpose: every one of these
#: is a power of ten, so `Decimal` holds it without approximation and a round trip returns
#: the number that went in.
#:
#: The base of each dimension is the unit whose ratio is 1: kg for mass, m for length, m2
#: for area, m3 for volume, each for count.
RATIO_TO_BASE: dict[str, Decimal] = {
    # mass, base kilogram
    "g": Decimal("0.001"),
    "kg": Decimal("1"),
    "ton": Decimal("1000"),
    # length, base metre
    "mm": Decimal("0.001"),
    "cm": Decimal("0.01"),
    "m": Decimal("1"),
    # area, base square metre
    "cm2": Decimal("0.0001"),
    "m2": Decimal("1"),
    # volume, base cubic metre
    "liter": Decimal("0.001"),
    "m3": Decimal("1"),
    # count. A branch and a bag are each one countable thing, which is all this says: it
    # does NOT say how much a branch weighs or how long it is, and nothing here can.
    "each": Decimal("1"),
    "branch": Decimal("1"),
    "bag": Decimal("1"),
}

#: Where a converted unit price is rounded, stated once so two callers cannot disagree.
#: Eight places matches `unit_conversions.factor` and `provider_item_unit_factors.factor`.
PRICE_PRECISION = Decimal("0.00000001")


class ConversionRefused(Exception):
    """The two units cannot be converted, and the message says which part is missing."""


def _known(unit):
    definition = UNIT_REGISTRY.get(unit or "")
    if definition is None or not definition.active:
        return None
    return definition


def can_convert(source_unit: str, target_unit: str) -> bool:
    """Whether a ratio exists for this pair. Not whether it is a good idea."""
    source, target = _known(source_unit), _known(target_unit)
    if source is None or target is None:
        return False
    if source.dimension != target.dimension:
        return False
    return source_unit in RATIO_TO_BASE and target_unit in RATIO_TO_BASE


def quantity_factor(source_unit: str, target_unit: str) -> Decimal:
    """How many target units one source unit is. Raises rather than guessing.

    This is the QUANTITY factor. A price uses its reciprocal -- see `convert_unit_price`,
    which is a separate function precisely so the two cannot be confused at a call site.
    """
    source, target = _known(source_unit), _known(target_unit)
    if source is None:
        raise ConversionRefused("unit %r is not in the Finance unit registry" % source_unit)
    if target is None:
        raise ConversionRefused("unit %r is not in the Finance unit registry" % target_unit)
    if source.dimension != target.dimension:
        raise ConversionRefused(
            "%r is %s and %r is %s; crossing a dimension needs a fact about the product, "
            "not about units" % (source_unit, source.dimension, target_unit, target.dimension))
    if not units_are_compatible(source_unit, target_unit, source.dimension):
        raise ConversionRefused(
            "the registry does not pair %r with %r" % (source_unit, target_unit))
    if source_unit not in RATIO_TO_BASE or target_unit not in RATIO_TO_BASE:
        # day <-> hour lands here, and should: how long a working day is belongs to a
        # project, and `unit_conversions` is where a project says so.
        raise ConversionRefused(
            "no fixed ratio between %r and %r; this pair is configured per project in "
            "unit_conversions" % (source_unit, target_unit))
    return RATIO_TO_BASE[source_unit] / RATIO_TO_BASE[target_unit]


def convert_quantity(value, source_unit: str, target_unit: str) -> Decimal:
    """A quantity in a new unit. 2 kg is 2000 g: multiplied by the factor."""
    if value is None:
        return None
    if source_unit == target_unit:
        return _decimal(value)
    return _decimal(value) * quantity_factor(source_unit, target_unit)


def convert_unit_price(price, source_unit: str, target_unit: str) -> Decimal:
    """A price PER something, in a new unit. The inverse, and that is the whole point.

    1000 Toman per kilogram is 1 Toman per gram. A quantity going kg -> g is multiplied by
    1000; a price per kg going to a price per g is DIVIDED by it. Writing this as its own
    function, rather than as a flag on the one above, is what stops a call site getting it
    backwards -- and getting it backwards is a factor-of-a-million error in a price.
    """
    if price is None:
        return None
    if source_unit == target_unit:
        return _decimal(price)
    factor = quantity_factor(source_unit, target_unit)
    return (_decimal(price) / factor).quantize(PRICE_PRECISION)


def apply_product_factor(price, factor):
    """A price converted by a factor a PERSON stored against one listing.

    Separate from everything above because its authority is different: the ratios in this
    module are facts about units, and this is somebody's measurement of one product. The
    arithmetic is the same inverse; the reason it is allowed to happen is not.
    """
    if price is None or factor is None:
        return None
    factor = _decimal(factor)
    if factor <= 0:
        raise ConversionRefused("a conversion factor must be positive, got %s" % factor)
    return (_decimal(price) / factor).quantize(PRICE_PRECISION)


def _decimal(value) -> Decimal:
    """Decimal, built from a string when it has to be. Never from a float directly.

    `Decimal(0.1)` is 0.1000000000000000055511151231257827021181583404541015625. Going
    through `str` gives what was written, which is what a price is.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ConversionRefused("%r is not a number" % (value,)) from exc
