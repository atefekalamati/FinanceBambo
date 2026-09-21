# -*- coding: utf-8 -*-
"""Which conversion rule answers a question, and which rule nobody may write.

TWO DECISIONS LIVE HERE AND NEITHER BELONGS IN SQL

    which of several approved rules applies  -- precedence
    which rules may exist at all             -- scope safety

Both are judgements about meaning, and a query that sorted by a column would encode them
somewhere a reader cannot see.

PRECEDENCE, MOST SPECIFIC FIRST

    1. provider_item   this exact listing
    2. provider + category   this supplier's products of this kind
    3. category        every product of this kind
    4. provider        every product from this supplier
    5. project         this project
    6. organization    this tenant
    7. global          everywhere
    8. the unit registry, which needs no rule at all

The order is the order of who looked hardest. A measurement of one listing beats a
statement about a category, because somebody weighed that listing.

The registry is LAST in this list and FIRST in practice: `calculate_daily_estimate` asks
the registry before it asks for a rule at all, because a kilogram is a thousandth of a
tonne whatever anybody writes down. A rule is only consulted where the registry has no
answer.

WHY «GLOBAL» IS NOT A SYNONYM FOR «SAFE»

    1 ton = 1000 kg      a fact about units. True on every project that will ever run.
    1 branch = 22 kg     a fact about ONE PRODUCT. False for the next size of angle.

Both are conversions; only one may be written down once and believed everywhere. The
difference is whether the two units measure the same KIND of thing. Mass to mass is
arithmetic. Count to mass is a weighing, and what was weighed matters.

So a cross-dimension rule is refused at any scope broader than one listing. A supplier's
whole category is not narrow enough either: one supplier's angles come in a dozen sizes
and each has its own branch weight, so a rule at that scope would be right for one size and
silently wrong for eleven.
"""

from decimal import Decimal, InvalidOperation

from .unit_conversion import can_convert
from .unit_registry import UNIT_REGISTRY

#: Most specific first. The resolver walks this and stops at the first approved match.
SCOPE_PRECEDENCE = (
    "provider_item",
    "provider_category",
    "category",
    "provider",
    "project",
    "organization",
    "global",
)

#: The scope a product-dependent rule may be written at, and the only one.
NARROW_SCOPES = frozenset({"provider_item"})

#: What the table stores. `provider_category` is a `provider` row that also names a
#: category; it is a precedence step rather than a `scope_type` of its own.
STORED_SCOPES = frozenset({"global", "organization", "project", "provider", "category",
                           "provider_item"})


class ConversionRuleRefused(Exception):
    """A rule that must not exist, with the reason a person can act on."""

    def __init__(self, message, code, message_fa=None):
        super().__init__(message)
        self.code = code
        self.message_fa = message_fa


def crosses_dimensions(from_unit, to_unit):
    """Whether these two units measure different KINDS of thing.

    `can_convert` is the registry's own answer to "is there arithmetic between these", and
    it is true exactly when the two share a dimension. Anything else needs a measurement of
    something, and what was measured is a property of that thing.
    """
    left, right = UNIT_REGISTRY.get(from_unit or ""), UNIT_REGISTRY.get(to_unit or "")
    if left is None or right is None:
        return True
    if left.dimension == right.dimension:
        return False
    return not can_convert(from_unit, to_unit)


def validate_scope(*, scope_type, from_unit, to_unit, project_id=None, provider_id=None,
                   provider_item_id=None, category=None,
                   product_dependent_acknowledged=False):
    """Refuse a rule whose breadth its evidence cannot carry.

    Checked here rather than as a database constraint because the database cannot know
    that branch-to-kilogram is a weighing and tonne-to-kilogram is arithmetic. That is a
    statement about the units' meanings, and meanings live in the registry.
    """
    if scope_type not in STORED_SCOPES:
        raise ConversionRuleRefused(
            "unknown scope %r" % scope_type, "FINANCE_CONVERSION_SCOPE_UNKNOWN",
            "دامنهٔ این قانون معتبر نیست.")
    if from_unit not in UNIT_REGISTRY or to_unit not in UNIT_REGISTRY:
        raise ConversionRuleRefused(
            "both units must be registry codes", "FINANCE_CONVERSION_UNIT_UNKNOWN",
            "هر دو واحد باید از واحدهای ثبت‌شدهٔ سامانه باشند.")
    if from_unit == to_unit:
        raise ConversionRuleRefused(
            "a rule must cross two different units", "FINANCE_CONVERSION_UNITS_EQUAL",
            "واحد مبدأ و مقصد یکی است.")

    # WHY AN ADMISSION IS ALLOWED TO PASS WHERE A REFUSAL STOOD
    #
    # Everything the refusal says is still true: «1 branch = 22 kg» is a weighing of one
    # product, and stating it for a whole category asserts every product in that category
    # weighs the same. What changed is the discovery that the narrow scope it points at --
    # `provider_item` -- cannot be written until a listing is attached to the line, and on
    # the audited project 832 of 835 lines have no component at all. The rule sent people
    # to a door that was locked.
    #
    # So the claim may be made, and it carries a name. `product_dependent_acknowledged`
    # is set only by a caller that said so in the request, the actor and the moment are
    # stored beside it, and `factorSource` tells every reader of a price that the number
    # came from a rule rather than from a weighing of the product in front of them.
    #
    # The default is False, so nothing that was refused before is quietly allowed now.
    if (crosses_dimensions(from_unit, to_unit) and scope_type not in NARROW_SCOPES
            and not product_dependent_acknowledged):
        raise ConversionRuleRefused(
            "%s to %s depends on the product and cannot be stated at %s scope"
            % (from_unit, to_unit, scope_type),
            "FINANCE_CONVERSION_SCOPE_TOO_BROAD",
            "تبدیل «%s» به «%s» به خودِ محصول بستگی دارد و نمی‌توان آن را برای یک دسته یا "
            "کل سامانه ثبت کرد. این قانون را برای همان محصول مشخص تعریف کنید."
            % (from_unit, to_unit))

    # The scope columns must say what the scope type says. The database checks this too;
    # here it produces a sentence instead of a constraint name.
    required = {
        "project": ("project_id", project_id),
        "provider": ("provider_id", provider_id),
        "category": ("category", category),
        "provider_item": ("provider_item_id", provider_item_id),
    }.get(scope_type)
    if required and not required[1]:
        raise ConversionRuleRefused(
            "a %s rule must name its %s" % (scope_type, required[0]),
            "FINANCE_CONVERSION_SCOPE_INCOMPLETE",
            "برای این دامنه باید مرجع مربوط مشخص شود.")
    return True


def rank_of(rule, *, provider_id=None, category=None):
    """Where a rule sits in the precedence list, or None when it does not apply.

    `provider_category` is a provider rule that also names the category being asked about:
    narrower than either alone, and the reason the stored scope and the precedence step are
    not the same vocabulary.
    """
    scope = rule.get("scope_type")
    if scope == "provider" and rule.get("category"):
        if category is not None and rule.get("category") != category:
            return None
        scope = "provider_category"
    try:
        return SCOPE_PRECEDENCE.index(scope)
    except ValueError:
        return None


def invert_factor(value):
    """`1/value` as an exact Decimal, or None when there is nothing to invert.

    Decimal throughout, never float: these numbers multiply prices in rials, and a rule
    read backwards must give back exactly what the same rule stated forwards. `1/22` as a
    float and as a Decimal differ, and the difference lands in money.

    Zero and None both mean "no usable factor" rather than an error. A rule stating a
    factor of zero says a branch weighs nothing, which is not a conversion anybody can
    price from -- treating it as absent is the same choice `choose_conversion` makes.
    """
    if value is None:
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
        if number == 0:
            return None
        return Decimal(1) / number
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return None


#: How a resolved rule was read. Stored on the returned row so a caller -- and a reader --
#: can tell a rule that was written for this crossing from one written for its opposite.
DIRECTION_DIRECT = "direct"
DIRECTION_REVERSE = "reverse"


def resolve_rule(rules, *, from_unit, to_unit, provider_id=None, provider_item_id=None,
                 category=None, on_date=None):
    """The one rule that applies, out of everything approved for this crossing.

    `rules` is every APPROVED rule the repository found for this tenant and unit pair --
    filtering by status is the repository's job, because a draft must never reach here at
    all. What this does is choose between the ones that survived.

    EITHER DIRECTION, BECAUSE A PERSON KNOWS IT ONE WAY ROUND

    Somebody knows "one branch is 22 kg". Asking them for kg->branch makes them type
    0.0454545..., which is not what the supplier's docket says, cannot be checked against
    it, and keeps its rounding forever. So the rule is stored exactly as stated and the
    inversion happens here, per calculation, at full Decimal precision.

    A rule written the other way round is therefore a candidate for this crossing, with its
    factor inverted. Two things about how it competes:

      * Scope ranking is untouched. A narrow reverse rule still beats a broad direct one,
        because which rule is more SPECIFIC has nothing to do with which way somebody
        happened to write it.
      * Direction is only the tiebreak. Two rules at the SAME rank -- which means somebody
        wrote both directions into one scope -- resolve to the direct one, so the reading
        is at least deterministic. The service refuses to create that second rule in the
        first place; this is what happens to rows that predate the refusal.

    The returned row is a COPY when it was read backwards: `factor` is the inverted number
    and `applied_direction` says so. Nothing mutates the caller's candidates.
    """
    best, best_key = None, None
    for rule in rules or ():
        if rule.get("status") != "approved":
            continue
        stated = (rule.get("from_unit"), rule.get("to_unit"))
        if stated == (from_unit, to_unit):
            direction = DIRECTION_DIRECT
        elif stated == (to_unit, from_unit) and from_unit != to_unit:
            direction = DIRECTION_REVERSE
        else:
            continue
        if not _in_effect(rule, on_date):
            continue
        if not _applies_to(rule, provider_id, provider_item_id, category):
            continue
        rank = rank_of(rule, provider_id=provider_id, category=category)
        if rank is None:
            continue
        factor = rule.get("factor")
        if direction == DIRECTION_REVERSE:
            factor = invert_factor(factor)
            if factor is None:
                # Nothing to read backwards. Skipped rather than returned with a null
                # factor, so a broader rule that DOES state one can still answer.
                continue
        # Rank first, direction second: specificity decides, and direction only separates
        # two rules that are equally specific.
        key = (rank, 0 if direction == DIRECTION_DIRECT else 1)
        if best_key is None or key < best_key:
            best_key = key
            # BOTH factor keys are inverted, not just one. `choose_conversion` reads
            # `factor` and `daily_estimate` reads `factor_value`, and a copy that inverted
            # only one would price the table from 1/22 and the estimate beneath it from 22
            # -- the same row, two numbers, differing by the square of the factor.
            best = (rule if direction == DIRECTION_DIRECT
                    else dict(rule, factor=factor, factor_value=factor,
                              from_unit=from_unit, to_unit=to_unit,
                              applied_direction=DIRECTION_REVERSE,
                              stated_from_unit=rule.get("from_unit"),
                              stated_to_unit=rule.get("to_unit"),
                              stated_factor=rule.get("factor"),
                              stated_factor_value=rule.get("factor_value")))
            if best is rule:
                best = dict(rule, applied_direction=DIRECTION_DIRECT)
    return best


def _applies_to(rule, provider_id, provider_item_id, category):
    """Whether this rule is about the thing being asked about.

    A rule that names a listing, a supplier or a category answers only for that one. A rule
    that names none of them is about the project, the tenant or everything, and answers for
    all of them.
    """
    if rule.get("provider_item_id") and rule["provider_item_id"] != provider_item_id:
        return False
    if rule.get("provider_id") and rule["provider_id"] != provider_id:
        return False
    if rule.get("category") and rule["category"] != category:
        return False
    return True


def _in_effect(rule, on_date):
    """Whether the rule was live on the day being asked about.

    A superseded rule keeps answering for the dates it covered, which is what lets a report
    issued last month still be explained by the rule that produced it.
    """
    if on_date is None:
        return rule.get("effective_to") is None
    start = rule.get("effective_from")
    end = rule.get("effective_to")
    if start is not None and start > on_date:
        return False
    if end is not None and end <= on_date:
        return False
    return True


#: Named here rather than in either service, because the whole point is that both use the
#: same order. Two screens deciding a row's price differently is worse than either answer.
PROVIDER_ITEM_FACTOR = "provider_item"
CONVERSION_RULE_FACTOR = "conversion_rule"
#: The unit registry's own ratio -- «کیلوگرم» to «تن» -- which is arithmetic true of every
#: product and nobody's judgement about any of them. Defined here beside the other two so
#: the three names have one home; `item_price_components` re-exports the same strings.
REGISTRY_FACTOR = "registry"


def choose_conversion(listing_factor, rule):
    """`(factor, source)` for one crossing: the listing's own measurement, then a rule.

    THE ORDER, AND WHY IT IS THIS WAY ROUND

    A measurement recorded against THIS listing is a weighing of the thing being priced.
    A rule is a statement about a category, a supplier or a project -- broader by
    construction, and broader means it was made without looking at this product. So the
    narrow evidence wins and the rule fills the gap behind it.

    That ordering has a consequence worth stating plainly: no row that prices today
    changes its number. A rule is consulted only where a listing factor is absent, which
    is exactly where the row reports `needs_factor` now.

    Both callers -- the components table and the single-mapping preview -- go through
    here, so a row cannot be priced one way on one screen and another way on the next.

    `rule` is whatever `resolve_rule` returned: a row with a `factor`, or None. A rule
    that resolved but states no usable factor is treated as absent rather than as zero,
    because zero is a price of nothing and no rule means that.
    """
    if listing_factor is not None and listing_factor.get("factor"):
        return listing_factor["factor"], PROVIDER_ITEM_FACTOR
    if rule is not None and rule.get("factor"):
        return rule["factor"], CONVERSION_RULE_FACTOR
    return None, None
