# -*- coding: utf-8 -*-
"""What Finance is allowed to call a quantity, in one place.

A schedule is full of numbers -- work hours, durations, costs, weighting coefficients,
planning volumes. Exactly one kind of column is a quantity Finance may price: one the
planners named as such. This module is the registry of those names and the single
function that reads them, used identically by the Finance persistence
(``finance_mpp_sync``) and the Finance feed (``mpp_progress_shape``). Two readers of
"quantity" would eventually disagree, and the disagreement would surface as a priced
number nobody stated.

When no approved column exists the answer is ``(None, None)``. Not work, not a duration,
not a cost, not a percentage, and not a custom column that merely holds a number -- the
file in front of us has twenty-two custom columns and none is an approved quantity, so
today every quantity is NULL and every report says so.
"""

from decimal import Decimal, InvalidOperation

#: Column aliases that mean "this is the quantity Finance may price". Adding a spelling is
#: a deliberate, reviewable act, never a fallback.
APPROVED_QUANTITY_ALIASES = ("quantity", "مقدار",
                             "مقدار مالی")

#: Where that quantity's unit may be stated, in the same spirit.
APPROVED_QUANTITY_UNIT_ALIASES = ("quantity unit",
                                  "واحد مقدار")

#: Column aliases that mean "this is the quantity as it stands TODAY". Same rule as above
#: and for the same reason: a name on this list is a decision somebody made, never a column
#: that happened to hold a number.
#:
#: WHY THE FILE IN FRONT OF US POPULATES NONE OF THESE
#:
#: Measured on this project's schedule, every candidate whose NAME promises a current or
#: completed volume is stated on all 328 tasks and is ZERO on all 328:
#:
#:     «حجم اولیه»       initial volume    328 stated, 0 non-zero
#:     «احجام کاری»       working volumes   328 stated, 0 non-zero
#:     «حجم انجام شده»    completed volume  328 stated, 0 non-zero
#:
#: MS Project writes 0.0 into every Number column nobody filled, and MPXJ returns that
#: indistinguishably from a deliberate zero. So a zero read from one of these columns is
#: recorded as "the file states none", not as "this line uses none today" -- the second
#: reading would take every daily estimate on the project to zero on the strength of an
#: empty column. A zero a PERSON enters is a different fact and is kept as the zero it is.
APPROVED_DAILY_QUANTITY_ALIASES = ("daily quantity", "مقدار روز",
                                   "حجم انجام شده")


def approved_daily_quantity(task):
    """``(quantity, alias)`` when the schedule states a daily quantity, else ``(None, None)``.

    Returns the ALIAS beside the value, because which column it came from is part of the
    answer: the same meaning lands on a different ``NumberN`` in the next file, so the name
    the planner gave it is the only stable provenance there is.

    A zero is treated as "not stated" -- see the note on the alias list above. This is the
    one place that judgement is made, so a reader looking for it has one place to look.
    """
    raw = (task.get("raw_fields") or {})
    lowered = {str(name).strip().lower(): (name, value) for name, value in raw.items()}
    for alias in APPROVED_DAILY_QUANTITY_ALIASES:
        if alias not in lowered:
            continue
        name, value = lowered[alias]
        quantity = _decimal(value)
        if quantity is None or quantity == 0:
            # Stated as zero by MS Project's own default, which is not a statement.
            return None, None
        return quantity, name
    return None, None


def _decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def approved_quantity(task):
    """``(quantity, unit)`` when the schedule states an approved quantity, else
    ``(None, None)``.

    Reads the raw aliased columns the reader preserved, matching the planner's own column
    NAME. Name, not ``NumberN``: the slot a value sits in is not stable between files, and
    a slot-based rule would silently start reading a weighting coefficient as a quantity
    the first time a planner reordered their columns.
    """
    raw = (task.get("raw_fields") or {})
    lowered = {str(name).strip().lower(): value for name, value in raw.items()}
    quantity = None
    for alias in APPROVED_QUANTITY_ALIASES:
        if alias in lowered:
            quantity = _decimal(lowered[alias])
            break
    if quantity is None:
        return None, None
    unit = None
    for alias in APPROVED_QUANTITY_UNIT_ALIASES:
        if alias in lowered and str(lowered[alias]).strip():
            unit = str(lowered[alias]).strip()
            break
    return quantity, unit
