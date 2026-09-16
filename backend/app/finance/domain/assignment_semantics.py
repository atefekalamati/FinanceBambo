# -*- coding: utf-8 -*-
"""What an MPP assignment's "Units" number actually MEANS, and what may be done with it.

THE MISTAKE THIS MODULE EXISTS TO PREVENT

Microsoft Project puts one column called Units on every assignment, and the number in it
means different things depending on the resource. On the audited file, task 1219
«کانال کنی» has four assignments:

    uid 152  کانال کنی     MATERIAL  مترمکعب -> m3   units 7516.4   cost 15,234,765,668
    uid 134  بسترکوبی      MATERIAL  مترمربع -> m2   units 3956.0   cost    197,800,000
    uid 158  بیل مکانیکی   WORK      «ب»     -> --   units 1.0      cost              0
    uid 171  کامیون        WORK      «ک»     -> --   units 1.0      cost              0

The first two are cubic metres and square metres -- physical amounts somebody will buy.
The last two are 100% -- an allocation, one machine assigned full-time. MPXJ scales
allocation by 100, so 1.0 IS 100%.

Multiplying 1.0 by a price per cubic metre produces a number. It is not a small error and
it is not a visible one: it looks like a cheap excavator. Multiplying 100 by it -- if the
scaling is undone in the wrong place -- looks like an expensive one. Neither is a cost.

    A number whose meaning is not established is not a quantity. It is a number.

WHAT DECIDES THE MEANING

Not a guess, and not the resource name. The importer already recorded the two facts that
settle it, on every row of `finance_mpp_rows`:

    resource_type     MATERIAL / WORK / (null on task-level fixed-cost rows)
    unit_source       how the unit text was resolved -- 'alias' when «مترمکعب» became m3,
                      'not_a_unit' when «ب» resolved to nothing, 'none' when absent

A MATERIAL whose unit resolved to a registry code is measuring something. A WORK resource
whose unit did not resolve is allocating something. Anything else is `unknown`, and
`unknown` is an answer this module gives rather than a case it guesses through.

WHAT IS NEVER DONE HERE

No fallback between quantity columns. `Quantity`, `Daily Quantity` and «احجام» are three
different statements about a project and one is never substituted for another -- the rule
predates this module and is not relaxed by it. Nothing here reads
`source_daily_quantity`, `source_material_quantity` or a progress figure; an assignment's
own Units is the only value it interprets.
"""

from decimal import Decimal

#: The four things an assignment's value can be. Anything not established is `UNKNOWN`,
#: which is a refusal to price, not a default.
PHYSICAL_QUANTITY = "physical_quantity"
ALLOCATION_PERCENTAGE = "allocation_percentage"
WORK = "work"
UNKNOWN = "unknown"

#: MPXJ reports an allocation of 100% as 1.0. Stated once, because the constant is the
#: whole difference between "one excavator" and "one hundred of something".
ALLOCATION_SCALE = Decimal(100)

#: Why a row could not be priced. Each names the thing a person would have to supply, so
#: the answer is an instruction rather than a verdict.
ALLOCATION_NOT_QUANTITY = "allocation_percentage_not_quantity"
MISSING_WORK_QUANTITY = "missing_work_quantity"
MISSING_RATE = "missing_rate"
UNSUPPORTED_RESOURCE_TYPE = "unsupported_resource_type"
MISSING_QUANTITY = "missing_quantity"
MISSING_PRICE = "missing_price"
MISSING_CONVERSION = "missing_conversion"
UNKNOWN_SEMANTICS = "unknown_assignment_semantics"
NOT_MPP_DERIVED = "not_mpp_derived"

#: What a row's estimate ended up being.
CALCULATED = "calculated"
NOT_CALCULABLE = "not_calculable"

#: Resource types the file states, upper-cased as MPXJ hands them over.
FILE_MATERIAL = "MATERIAL"
FILE_WORK = "WORK"


def value_kind(resource_type, normalized_unit, unit_source):
    """What this assignment's Units number is, judged from what the importer recorded.

        MATERIAL + a unit that resolved     -> a physical quantity
        WORK / equipment                    -> an allocation percentage
        anything else                       -> unknown

    A MATERIAL whose unit did NOT resolve is `unknown`, not a quantity: «ب» is not a unit,
    and 12 rows of the audited file are exactly that. Calling them quantities would price
    four resources against a unit nobody can name.
    """
    declared = (resource_type or "").strip().upper()
    if declared == FILE_MATERIAL:
        return PHYSICAL_QUANTITY if normalized_unit else UNKNOWN
    if declared == FILE_WORK:
        return ALLOCATION_PERCENTAGE
    return UNKNOWN


def allocation_percent(units):
    """`units` as a percentage, or None when there is nothing to convert.

    Only meaningful for an allocation. Returned so a reader sees «۱۰۰٪» rather than 1.0
    and cannot mistake the stored number for an amount of anything.
    """
    if units is None:
        return None
    return Decimal(units) * ALLOCATION_SCALE


def physical_quantity(kind, units):
    """The assignment's quantity, and ONLY when its value is one.

    Returns None for an allocation. That is the point: there is no quantity to return,
    and returning `units` "just in case" is how 1.0 becomes one cubic metre.
    """
    if kind != PHYSICAL_QUANTITY or units is None:
        return None
    return Decimal(units)


def assignment_estimate(kind, units, converted_unit_price_irr):
    """`(estimate, status, issue_codes)` for one assignment.

    The estimate is `quantity x converted unit price` and nothing else. Every path that
    cannot produce both operands returns None -- never zero, because a row nobody could
    price and a row that costs nothing are different rows, and a total that adds the first
    as zero is quietly wrong in the direction that looks fine.

    Zero survives. A quantity of exactly 0 is a statement the file made, so it prices to
    0 and is `calculated`: "zero of them" is not "we do not know".
    """
    issues = []
    if kind == ALLOCATION_PERCENTAGE:
        # The one refusal that is about meaning rather than absence. A percentage is not
        # a purchase, and no price makes it one.
        return None, NOT_CALCULABLE, (ALLOCATION_NOT_QUANTITY,)
    if kind == UNKNOWN:
        return None, NOT_CALCULABLE, (UNKNOWN_SEMANTICS,)
    if kind == WORK:
        return None, NOT_CALCULABLE, (MISSING_WORK_QUANTITY,)

    quantity = physical_quantity(kind, units)
    if quantity is None:
        issues.append(MISSING_QUANTITY)
    if converted_unit_price_irr is None:
        issues.append(MISSING_PRICE)
    if issues:
        return None, NOT_CALCULABLE, tuple(issues)
    return quantity * Decimal(converted_unit_price_irr), CALCULATED, ()


def rolls_up(status):
    """Whether an assignment's amount may enter a total.

    One rule, used by the resource aggregate, the WBS aggregate and the project total
    alike -- so "what is in this number" has the same answer at every level, and a row
    cannot be counted at one and dropped at another.
    """
    return status == CALCULATED


def roll_up(amounts):
    """`(total, counted, excluded)` over assignment amounts.

    `excluded` is returned rather than discarded: a total that quietly leaves rows out
    reads as complete. The caller is expected to report it.
    """
    counted = [a for a in amounts if a is not None]
    return (sum(counted, Decimal(0)) if counted else None,
            len(counted), len(amounts) - len(counted))
