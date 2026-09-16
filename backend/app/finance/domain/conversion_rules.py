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
                   provider_item_id=None, category=None):
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

    if crosses_dimensions(from_unit, to_unit) and scope_type not in NARROW_SCOPES:
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


def resolve_rule(rules, *, from_unit, to_unit, provider_id=None, provider_item_id=None,
                 category=None, on_date=None):
    """The one rule that applies, out of everything approved for this crossing.

    `rules` is every APPROVED rule the repository found for this tenant and unit pair --
    filtering by status is the repository's job, because a draft must never reach here at
    all. What this does is choose between the ones that survived.

    Ties cannot happen: the database permits one active rule per exact scope and unit pair,
    so two candidates always differ in scope and the ranking separates them.
    """
    best, best_rank = None, len(SCOPE_PRECEDENCE)
    for rule in rules or ():
        if rule.get("from_unit") != from_unit or rule.get("to_unit") != to_unit:
            continue
        if rule.get("status") != "approved":
            continue
        if not _in_effect(rule, on_date):
            continue
        if not _applies_to(rule, provider_id, provider_item_id, category):
            continue
        rank = rank_of(rule, provider_id=provider_id, category=category)
        if rank is None:
            continue
        if rank < best_rank:
            best, best_rank = rule, rank
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
