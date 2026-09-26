# -*- coding: utf-8 -*-
"""Reading the unit a schedule states, and refusing to invent one it does not.

A schedule names its units in free text a person typed: «مترمکعب», «متر مربع», «عدد»,
and — on this project's own file — «مترمرکعب», which is a misspelling of the first. Finance
has a closed registry of units it can convert and price with, so somewhere the two have to
meet.

They meet here, and the meeting is allowed to fail. Three answers are possible:

    exact   the file named a registry code outright ("m3", "kg")
    alias   the file used a spelling this module knows for one ("مترمکعب" -> m3)
    low     nothing recognised it, and the answer is None

The third is the one that matters. A schedule that says «اصل» or «واحد» is not saying a
unit at all, and a module that answered "count" to be helpful would turn a shrug into a
fact -- and every conversion, every price and every total downstream would inherit it. So
an unrecognised unit stays None, is recorded as low confidence, and is reported.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
It does not read the resource's NAME. Guessing m3 from «بتن» or hour from «کارگر» is a rule
about what a thing usually is, and it is wrong exactly when it matters: a schedule that
prices concrete by the truckload, or labour by the day, would be silently restated. If a
unit is to be inferred from a name, a person should confirm it once and it should be stored
as their decision. (WORK resources are the exception with a basis: MS Project states their
work in hours, and the mapper records `hour` for them -- see `WORK_UNIT`.)
"""

from app.finance.domain.unit_registry import UNIT_REGISTRY

#: Spellings seen in real schedules, mapped to the registry code they name. Persian is
#: written with and without the space, and «مترمرکعب» is in this file because the project's
#: own schedule contains it: five assignments spell «مترمکعب» that way. A misspelling that
#: appears in the data and has exactly one plausible reading is an alias, not a guess.
UNIT_ALIASES = {
    # volume
    "مترمکعب": "m3",
    "متر مکعب": "m3",
    "مترمرکعب": "m3",
    "متر مرکعب": "m3",
    "m³": "m3",
    "متر3": "m3",
    # area
    "مترمربع": "m2",
    "متر مربع": "m2",
    "m²": "m2",
    "متر2": "m2",
    # length
    "متر": "m",
    "مترطول": "m",
    "متر طول": "m",
    "مترول": "m",
    # mass
    "کیلوگرم": "kg",
    "کیلو گرم": "kg",
    "کیلو": "kg",
    "تن": "ton",
    # time
    "ساعت": "hour",
    "روز": "day",
    # count
    "عدد": "each",
    "تعداد": "each",
}

#: What the file says when it is not naming a unit. Recorded so that «واحد» is reported as
#: "the file named no unit" rather than as an unrecognised one -- the two are different
#: problems and only the second is worth a person's time.
NOT_A_UNIT = {"", "واحد", "اصل", "مقطوع", "درصد", "%", "-", "—"}


def normalize_unit(raw):
    """`(code, source, confidence)` for a unit a schedule states.

    `code` is a registry code or None. `source` says what answered: `registry` when the
    file named a code, `alias` when it named a spelling of one, `none` when nothing did.
    `confidence` is `exact`, `alias` or `low`, and `low` always comes with a None code.
    """
    text = "" if raw is None else str(raw).strip()
    # A canonical code is authoritative even when it is one character (metre: m).
    if text in UNIT_REGISTRY:
        return text, "registry", "exact"
    if len(text) == 1:
        # A single character is an initial, not a unit. MS Project defaults `Initials` to
        # the first letter of the resource's name, and a schedule that leaves the material
        # label empty hands that letter over instead. Measured on this project: every
        # single-character value -- «د» x103, «ت» x64, «ج» x56, «پ» x51 and seven more --
        # sits on a WORK resource, and not one names a unit.
        return None, "resource_initial", "low"
    if text in NOT_A_UNIT:
        # The file said something, and that something is not a unit. Nothing to recognise.
        return None, "not_a_unit", "low"
    folded = text.replace("‌", "").replace(" ", "")
    for spelling, code in UNIT_ALIASES.items():
        if folded == spelling.replace("‌", "").replace(" ", ""):
            return code, "alias", "alias"
    return None, "none", "low"
