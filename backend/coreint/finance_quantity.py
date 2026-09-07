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
