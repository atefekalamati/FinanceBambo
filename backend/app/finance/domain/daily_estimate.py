# -*- coding: utf-8 -*-
"""What a schedule line costs at today's prices, and why it sometimes cannot be said.

THE SEVEN FACTS AND THE TWO ANSWERS

    a  quantity                    what the schedule planned
    f  daily_quantity              what the schedule says today, when it says anything
    b  initial_unit_price_irr      the estimated rate
    c  initial_estimated_cost_irr  the estimated total
    d  daily_unit_price_irr        today's market rate for the chosen product
    e  daily_estimated_cost_irr    what that makes this line cost today

`c` is the ESTIMATE and `e` is TODAY. They are two different answers to two different
questions and this module never lets one stand in for the other: a line whose product has
no price today still reports its estimate, and the estimate is never relabelled as a daily
figure.

WHY f IS NOT "a CONVERTED"

`daily_quantity` is a quantity the schedule states separately, not `quantity` expressed in
another unit. NULL means the schedule says nothing and the planned quantity is used; ZERO
means somebody said none, and none is a real answer that produces a real zero cost. The
difference is checked with `is None`, never with truthiness -- `if daily_quantity:` would
turn a stated zero into a fallback to the planned figure, which is the opposite of what the
person entering it meant.

WHY A UNIT MISMATCH IS NOT AN ERROR

A price per branch and a line measured in kilograms is an ordinary, expected state of a
half-configured project. It is not a 500 and it is not a zero. It is an answer --
`conversion_rule_required` -- carrying everything needed to fix it: both units, the
identifiers, a Persian sentence, and where to go. What it never carries is a number, and
what it never does is quietly apply a factor of one.

    Applying 1 where no rule exists is the single most expensive mistake available here.
    A price per branch used as a price per kilogram is wrong by the weight of a branch --
    on the reference product, by a factor of 22 -- and it looks entirely plausible.

THE ARITHMETIC IS ONE WAY ROUND AND ONLY ONE

A conversion rule is stored as a statement about QUANTITY -- `1 from_unit = factor to_unit`
-- and the price conversion is derived from it here, in one place. 1 branch = 22 kg means a
price per branch becomes a price per kilogram by DIVISION. Storing "the price multiplier"
instead would invite a call site to get it backwards, and backwards is a factor of 484.
"""

from decimal import ROUND_HALF_UP, Decimal

from .unit_conversion import ConversionRefused, can_convert, convert_unit_price
from .unit_registry import UNIT_REGISTRY

#: Money leaves whole, as everywhere in Finance: `AGENTS.md` is explicit that monetary
#: values are integer-IRR strings and every fractional form is rejected.
WHOLE_RIAL = Decimal(1)

# ------------------------------------------------------------------ unit match status
MATCHED = "matched"
CONVERTIBLE_BY_REGISTRY = "convertible_by_registry"
CONVERSION_RULE_AVAILABLE = "conversion_rule_available"
UNIT_SELECTION_REQUIRED = "unit_selection_required"
DAILY_PRICE_UNIT_MISSING = "daily_price_unit_missing"
CONVERSION_RULE_REQUIRED = "conversion_rule_required"
INCOMPATIBLE = "incompatible"

# ------------------------------------------------------------------ calculation status
READY = "ready"
DAILY_PRICE_MISSING = "daily_price_missing"
QUANTITY_MISSING = "quantity_missing"

#: Where the effective daily quantity came from. Named, because "80" tells a reader
#: nothing about whether the schedule said it today or last quarter.
FROM_DAILY_QUANTITY = "daily_quantity"
FROM_QUANTITY = "quantity"

#: How the conversion was licensed. `identity` is not a conversion at all and is named so
#: that a reader can tell "the units agreed" from "a factor of one was applied".
SOURCE_IDENTITY = "identity"
SOURCE_UNIT_REGISTRY = "unit_registry"
SOURCE_CONVERSION_RULE = "conversion_rule"

FACTOR = "factor"
FORMULA = "formula"

ACTION_DEFINE_CONVERSION_RULE = "define_conversion_rule"
ACTION_SELECT_UNIT = "select_unit"
ACTION_MAP_DAILY_PRICE = "map_daily_price"
ACTION_TARGET_SETTINGS = "project_financial_settings"
ACTION_TARGET_ITEM = "financial_items"

#: The sentence a person reads. Kept beside the code so the two cannot drift, and written
#: for the person who can fix it rather than for the developer who wrote it.
MESSAGES_FA = {
    CONVERSION_RULE_REQUIRED: (
        "واحد قلم پروژه با واحد قیمت روز یکسان نیست. برای محاسبه برآورد روز، قانون تبدیل "
        "این دو واحد را در تنظیمات مالی پروژه تعریف کنید."),
    UNIT_SELECTION_REQUIRED: (
        "واحد رسمی این قلم مشخص نیست. واحد را از فهرست واحدهای سامانه انتخاب کنید."),
    DAILY_PRICE_UNIT_MISSING: (
        "واحد قیمت روز این محصول در برگه مصالح ثبت نشده است. واحد مبدأ را در تنظیمات مالی "
        "پروژه مشخص کنید."),
    INCOMPATIBLE: (
        "این دو واحد از دو سنجهٔ متفاوت‌اند و تبدیلشان معنا ندارد."),
    DAILY_PRICE_MISSING: (
        "برای این محصول قیمت روز معتبری وجود ندارد."),
    QUANTITY_MISSING: (
        "مقدار این قلم در برنامهٔ زمان‌بندی ثبت نشده است."),
}

#: What is true of a conversion nobody could measure. There is no number of kilograms in an
#: hour, so asking somebody to weigh the product is the wrong instruction.
_TIMEISH = {"time", "equipment_time"}


class DailyEstimate:
    """One line's two answers, and the reason for any that is missing."""

    __slots__ = ("effective_daily_quantity", "effective_daily_quantity_source",
                 "initial_unit_price_irr", "initial_unit_price_source",
                 "initial_estimated_cost_irr", "initial_estimated_cost_source",
                 "daily_unit_price_irr", "daily_price_unit", "resource_unit",
                 "unit_match_status", "applied_conversion_rule_id",
                 "applied_conversion_rule_version", "conversion_method",
                 "conversion_multiplier", "converted_daily_unit_price_irr",
                 "daily_estimated_cost_irr", "calculation_status", "calculation_reason",
                 "action_required", "action_target")

    def __init__(self, **values):
        for name in self.__slots__:
            setattr(self, name, values.get(name))

    @property
    def unit_mismatch(self):
        """Whether the two units differ at all -- true even when a rule resolves it.

        A reader wants to know that a conversion happened, not only that it succeeded.
        """
        return self.unit_match_status not in (MATCHED, None)

    @property
    def conversion_rule_required(self):
        return self.unit_match_status == CONVERSION_RULE_REQUIRED

    @property
    def unit_selection_required(self):
        return self.unit_match_status == UNIT_SELECTION_REQUIRED

    @property
    def user_message_fa(self):
        return MESSAGES_FA.get(self.calculation_status)

    def as_dict(self):
        """Snake-case, like every row here; `ApiModel` camel-cases the wire."""
        return {
            "effective_daily_quantity": _text(self.effective_daily_quantity),
            "effective_daily_quantity_source": self.effective_daily_quantity_source,
            "initial_unit_price_irr": _text(self.initial_unit_price_irr),
            "initial_unit_price_source": self.initial_unit_price_source,
            "initial_estimated_cost_irr": _text(self.initial_estimated_cost_irr),
            "initial_estimated_cost_source": self.initial_estimated_cost_source,
            "daily_unit_price_irr": _text(self.daily_unit_price_irr),
            "daily_price_unit": self.daily_price_unit,
            "resource_unit": self.resource_unit,
            "unit_match_status": self.unit_match_status,
            "unit_mismatch": self.unit_mismatch,
            "unit_selection_required": self.unit_selection_required,
            "conversion_rule_required": self.conversion_rule_required,
            "applied_conversion_rule_id": (None if self.applied_conversion_rule_id is None
                                           else str(self.applied_conversion_rule_id)),
            "applied_conversion_rule_version": self.applied_conversion_rule_version,
            "conversion_method": self.conversion_method,
            "conversion_multiplier": _text(self.conversion_multiplier),
            "converted_daily_unit_price_irr": _text(self.converted_daily_unit_price_irr),
            "daily_estimated_cost_irr": _text(self.daily_estimated_cost_irr),
            "calculation_status": self.calculation_status,
            "calculation_reason": self.calculation_reason,
            "user_message_fa": self.user_message_fa,
            "action_required": self.action_required,
            "action_target": self.action_target,
        }


def effective_daily_quantity(quantity, daily_quantity):
    """Which quantity today's cost is computed on, and where it came from.

    NULL is the only thing that falls back. A stated zero is an answer -- "this line uses
    none of it today" -- and it produces a real zero cost rather than reverting to the
    planned figure.
    """
    daily = _decimal(daily_quantity)
    if daily is not None:
        return daily, FROM_DAILY_QUANTITY
    planned = _decimal(quantity)
    if planned is not None:
        return planned, FROM_QUANTITY
    return None, None


def initial_cost(quantity, initial_unit_price_irr, authoritative_initial_cost_irr):
    """The estimate: what the schedule states, or what its own numbers make.

    The file's assignment Cost is a TOTAL and takes priority -- multiplying it by the
    quantity again is the 7.5x error this schedule makes available, because the cost column
    is already the whole assignment. Only when the file states no cost is the total built
    from quantity times rate.

    Returns (cost, cost_source, unit_price, unit_price_source).
    """
    stated = _decimal(authoritative_initial_cost_irr)
    quantity = _decimal(quantity)
    price = _decimal(initial_unit_price_irr)

    if stated is not None:
        # The rate can be recovered from a total and a quantity, and saying so is more use
        # than leaving it blank. Never at zero quantity: that is a division, not a rate.
        if price is None and quantity is not None and quantity != 0:
            derived = (stated / quantity).quantize(WHOLE_RIAL, rounding=ROUND_HALF_UP)
            return stated, "mpp_assignment_cost", derived, "derived_from_mpp_cost_and_quantity"
        return stated, "mpp_assignment_cost", price, ("recorded" if price is not None else None)

    if quantity is not None and price is not None:
        return ((quantity * price).quantize(WHOLE_RIAL, rounding=ROUND_HALF_UP),
                "quantity_times_unit_price", price, "recorded")
    return None, None, price, ("recorded" if price is not None else None)


def match_units(resource_unit, daily_price_unit, conversion_rule=None):
    """How -- and whether -- a price in one unit can be read in another.

    Both units are expected to be REGISTRY CODES already: the caller normalises the sheet's
    Persian spellings before asking, so this compares vocabulary rather than labels.
    """
    resource_unit = _code(resource_unit)
    daily_price_unit = _code(daily_price_unit)

    if resource_unit is None:
        return UNIT_SELECTION_REQUIRED
    if daily_price_unit is None:
        return DAILY_PRICE_UNIT_MISSING
    if resource_unit == daily_price_unit:
        return MATCHED
    if can_convert(daily_price_unit, resource_unit):
        return CONVERTIBLE_BY_REGISTRY
    if conversion_rule is not None:
        return CONVERSION_RULE_AVAILABLE
    if not _crossable(daily_price_unit, resource_unit):
        return INCOMPATIBLE
    return CONVERSION_RULE_REQUIRED


def convert_daily_unit_price(daily_unit_price_irr, daily_price_unit, resource_unit,
                             conversion_rule=None):
    """Today's price expressed per the line's own unit.

    Returns (converted_price, multiplier, method, source) or (None, ...) when no trusted
    route exists. The multiplier returned is the QUANTITY factor that licensed it --
    `1 daily_price_unit = multiplier resource_unit` -- because that is the statement the
    rule makes, and the price arithmetic is its inverse.
    """
    price = _decimal(daily_unit_price_irr)
    if price is None:
        return None, None, None, None
    daily_price_unit = _code(daily_price_unit)
    resource_unit = _code(resource_unit)
    if resource_unit is None or daily_price_unit is None:
        return None, None, None, None

    if resource_unit == daily_price_unit:
        return price, Decimal(1), None, SOURCE_IDENTITY

    if can_convert(daily_price_unit, resource_unit):
        from .unit_conversion import quantity_factor
        factor = quantity_factor(daily_price_unit, resource_unit)
        return (convert_unit_price(price, daily_price_unit, resource_unit),
                factor, FACTOR, SOURCE_UNIT_REGISTRY)

    if conversion_rule is None:
        return None, None, None, None

    method = conversion_rule.get("conversion_method") or FACTOR
    if method != FACTOR:
        # Formula rules are storable and contract-visible; nothing evaluates them yet, and
        # a half-evaluated formula is worse than an honest refusal.
        return None, None, method, None
    factor = _decimal(conversion_rule.get("factor_value"))
    if factor is None or factor <= 0:
        return None, None, method, None
    # `1 from_unit = factor to_unit`, so a price PER from_unit becomes a price per to_unit
    # by division. This is the only place the direction is decided.
    try:
        converted = (price / factor).quantize(Decimal("0.00000001"))
    except (ArithmeticError, ConversionRefused):
        return None, None, method, None
    return converted, factor, method, SOURCE_CONVERSION_RULE


def calculate_daily_estimate(*, quantity=None, daily_quantity=None,
                             initial_unit_price_irr=None,
                             authoritative_initial_cost_irr=None,
                             daily_unit_price_irr=None, resource_unit=None,
                             daily_price_unit=None, conversion_rule=None):
    """Both answers for one line, and the reason for whichever is missing.

    Pure: no database, no clock, no request. Everything it needs is an argument, which is
    what lets every branch below be stated exactly in a test rather than arranged in a
    fixture.
    """
    effective, effective_source = effective_daily_quantity(quantity, daily_quantity)
    cost, cost_source, price, price_source = initial_cost(
        quantity, initial_unit_price_irr, authoritative_initial_cost_irr)

    answer = dict(
        effective_daily_quantity=effective,
        effective_daily_quantity_source=effective_source,
        initial_unit_price_irr=price,
        initial_unit_price_source=price_source,
        initial_estimated_cost_irr=cost,
        initial_estimated_cost_source=cost_source,
        daily_unit_price_irr=_decimal(daily_unit_price_irr),
        daily_price_unit=_code(daily_price_unit),
        resource_unit=_code(resource_unit),
        applied_conversion_rule_id=(conversion_rule or {}).get("id"),
        applied_conversion_rule_version=(conversion_rule or {}).get("version"),
    )

    match = match_units(resource_unit, daily_price_unit, conversion_rule)
    answer["unit_match_status"] = match

    # The order of these refusals is the order a person can act on them. A missing unit is
    # asked about before a missing price, because choosing the unit is what makes the
    # price question answerable at all.
    if match == UNIT_SELECTION_REQUIRED:
        return _blocked(answer, UNIT_SELECTION_REQUIRED,
                        "The line states no official unit, so no price can be read in it.",
                        ACTION_SELECT_UNIT, ACTION_TARGET_ITEM)
    if _decimal(daily_unit_price_irr) is None:
        return _blocked(answer, DAILY_PRICE_MISSING,
                        "No valid daily price exists for the mapped product.",
                        ACTION_MAP_DAILY_PRICE, ACTION_TARGET_ITEM)
    if match == DAILY_PRICE_UNIT_MISSING:
        return _blocked(answer, DAILY_PRICE_UNIT_MISSING,
                        "The daily price states no source unit, so there is no basis to "
                        "convert from.", ACTION_DEFINE_CONVERSION_RULE,
                        ACTION_TARGET_SETTINGS)
    if match == INCOMPATIBLE:
        return _blocked(answer, INCOMPATIBLE,
                        "%s and %s measure different things; no factor can bridge them."
                        % (_code(daily_price_unit), _code(resource_unit)),
                        None, None)
    if match == CONVERSION_RULE_REQUIRED:
        return _blocked(answer, CONVERSION_RULE_REQUIRED,
                        "No approved conversion rule exists for %s to %s."
                        % (_code(daily_price_unit), _code(resource_unit)),
                        ACTION_DEFINE_CONVERSION_RULE, ACTION_TARGET_SETTINGS)

    converted, multiplier, method, source = convert_daily_unit_price(
        daily_unit_price_irr, daily_price_unit, resource_unit, conversion_rule)
    answer["converted_daily_unit_price_irr"] = converted
    answer["conversion_multiplier"] = multiplier
    answer["conversion_method"] = method

    if converted is None:
        # A rule was found and could not be applied -- a formula nothing evaluates yet, or
        # a factor that is not a usable number. Reported as still needing a rule, because
        # from the person's side that is exactly what it needs.
        answer["unit_match_status"] = CONVERSION_RULE_REQUIRED
        return _blocked(answer, CONVERSION_RULE_REQUIRED,
                        "The conversion rule for %s to %s could not be applied."
                        % (_code(daily_price_unit), _code(resource_unit)),
                        ACTION_DEFINE_CONVERSION_RULE, ACTION_TARGET_SETTINGS)

    if effective is None:
        return _blocked(answer, QUANTITY_MISSING,
                        "Neither a planned nor a daily quantity is stated for this line.",
                        None, None)

    # Computed from the EXACT converted price and rounded once, so rounding the rate does
    # not compound through the multiplication.
    answer["daily_estimated_cost_irr"] = (effective * converted).quantize(
        WHOLE_RIAL, rounding=ROUND_HALF_UP)
    answer["calculation_status"] = READY
    answer["calculation_reason"] = None
    answer["action_required"] = None
    answer["action_target"] = None
    return DailyEstimate(**answer)


def _blocked(answer, status, reason, action, target):
    """No daily figure, and the reason in its place. Never a zero."""
    answer["daily_estimated_cost_irr"] = None
    answer.setdefault("converted_daily_unit_price_irr", None)
    answer["calculation_status"] = status
    answer["calculation_reason"] = reason
    answer["action_required"] = action
    answer["action_target"] = target
    return DailyEstimate(**answer)


def _crossable(source, target):
    """Whether any measurement could bridge these two units.

    What this rules out is a crossing nobody could make: there is no number of kilograms in
    an hour. It is what makes «ناسازگار» mean something different from «قانون تبدیل لازم
    است» -- one says stop asking, the other says go and measure the product.
    """
    left, right = UNIT_REGISTRY.get(source), UNIT_REGISTRY.get(target)
    if left is None or right is None:
        return False
    return (left.dimension in _TIMEISH) == (right.dimension in _TIMEISH)


def _code(unit):
    """A registry code, or None. A unit this system cannot name is one it cannot use."""
    if unit is None:
        return None
    text = str(unit).strip()
    return text if text in UNIT_REGISTRY else None


def _decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:                                                  # noqa: BLE001
        return None


def _text(value):
    """A Decimal as a string, so no JSON encoder can round money through a float."""
    return None if value is None else str(value)
