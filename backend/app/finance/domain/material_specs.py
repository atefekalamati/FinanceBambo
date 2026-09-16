# -*- coding: utf-8 -*-
"""What a worksheet column MEANS, declared per category, and the parsing that follows.

THE RULE THIS FILE EXISTS TO ENFORCE

A number in a spreadsheet cell is not a measurement until somebody says what it measures
and in what unit. «۲۷» is not a weight; «۲۷ کیلو» is. So nothing here guesses: a column is
extracted only where this module declares its meaning, and a unit is recorded only where
the cell or the declaration states one.

WHAT THE REAL SHEETS ACTUALLY CONTAIN

Measured across all 3,707 listings in `bambo_canonical_test`, by value shape:

    angle    تعداد شاخه  bare number      ضخامت  bare number
             طول         number + «متر»   وزن    bare number
    brick    ابعاد       «7×33×2.5»       وزن    number + «گرم»       کد  text
    channel  طول         number + «متری»  وزن    bare number
    ibeam    وزن - کیلوگرم  bare number ×69, TEXT ×34
    profile  ابعاد       «60*60»          ضخامت  bare number
             طول         number + «متری»  وزن    number + «کیلو»
    rebar    واحد - وزن  text («کیلو») -- a UNIT, not a weight
    pipe, pipe_fitting                    -- nothing at all

Three of those facts changed the design:

    1. «وزن» states its unit on brick and profile and states NONE on angle and channel.
       So the unit is read from the cell where the cell gives one, and left NULL where it
       does not. A default of kilograms would be a guess worth a factor of a thousand.

    2. «وزن - کیلوگرم» on ibeam holds a WEIGHT on 69 rows and an ORIGIN on 34 -- «وارداتی»,
       «ترک-کره». A column named "weight - kilogram" containing "imported" is why a parser
       must refuse text rather than coerce it. The text rows are a manufacturer, and that
       is where they go.

    3. NO SHEET STATES A WEIGHT BASIS. Not one says whether 27 is per branch, per metre or
       per piece. So `weight_basis` is 'unknown' everywhere, and an unknown basis may never
       enter a conversion -- which is exactly what `weight_per_branch_kg` and its siblings
       would assert. Those columns are therefore left unpopulated rather than filled with
       a basis nobody stated.

WHAT IS DELIBERATELY NOT PARSED

«ابعاد» is «7×33×2.5» -- three numbers whose ORDER nobody has declared. Width first or
thickness first is the difference between a 7mm brick and a 2.5mm one, so it is kept as
text and no width, height or thickness is derived from it.

«قیمت در هر مترمربع» is a PRICE, not a specification, and does not belong in a spec column.
"""

import re
from decimal import Decimal, InvalidOperation

from .unit_registry import UNIT_REGISTRY

#: Unit words a supplier writes, and the registry code each one is. Only spellings seen in
#: a real sheet, and only where the meaning is unambiguous: «متری» is "in metres", which is
#: the same statement as «متر» about the number beside it.
SPEC_UNIT_WORDS = {
    "متر": "m", "متری": "m", "m": "m",
    "سانتیمتر": "cm", "سانتی‌متر": "cm", "cm": "cm",
    "میلیمتر": "mm", "میلی‌متر": "mm", "mm": "mm",
    "گرم": "g", "g": "g",
    "کیلو": "kg", "کیلوگرم": "kg", "kg": "kg",
    "تن": "ton",
}

#: How a value may be written, and what that shape licenses.
BARE_NUMBER = "bare_number"
NUMBER_WITH_UNIT = "number_with_unit"
TEXT = "text"

#: The declaration. One entry per (category, worksheet column), stating the target column,
#: the shape the value must have, and -- only where the COLUMN NAME itself declares it --
#: the unit to assume when the cell states none.
#:
#: `unit_from_name` is used exactly once, for «وزن - کیلوگرم», where the kilogram is in the
#: column's own name. Everywhere else a missing unit stays missing.
SPEC_MAP = {
    "angle": {
        "تعداد شاخه": {"column": "branch_count", "shape": BARE_NUMBER},
        "ضخامت": {"column": "thickness_value", "shape": BARE_NUMBER},
        "طول": {"column": "length_value", "shape": NUMBER_WITH_UNIT},
        "وزن": {"column": "weight_value", "shape": BARE_NUMBER},
    },
    "brick": {
        "ابعاد": {"column": "dimensions_text", "shape": TEXT},
        "وزن": {"column": "weight_value", "shape": NUMBER_WITH_UNIT},
        "کد": {"column": "product_code", "shape": TEXT},
    },
    "channel": {
        "طول": {"column": "length_value", "shape": NUMBER_WITH_UNIT},
        "وزن": {"column": "weight_value", "shape": BARE_NUMBER},
    },
    "ibeam": {
        # Numbers are weights in kilograms, as the column's own name says. Text is an
        # origin -- «وارداتی», «ترک-کره» -- and goes where an origin belongs.
        "وزن - کیلوگرم": {"column": "weight_value", "shape": BARE_NUMBER,
                          "unit_from_name": "kg", "text_column": "manufacturer"},
    },
    "profile": {
        "ابعاد": {"column": "dimensions_text", "shape": TEXT},
        "ضخامت": {"column": "thickness_value", "shape": BARE_NUMBER},
        "طول": {"column": "length_value", "shape": NUMBER_WITH_UNIT},
        "وزن": {"column": "weight_value", "shape": NUMBER_WITH_UNIT},
    },
    # rebar's «واحد - وزن» is «کیلو» -- the unit the PRICE is per, which already feeds
    # `source_unit`. It is not a specification and is not mapped here.
    "rebar": {},
    "pipe": {},
    "pipe_fitting": {},
}

#: Which target columns take a unit beside the value, and where that unit is stored.
UNIT_COLUMN_OF = {
    "length_value": "length_unit",
    "width_value": "width_unit",
    "height_value": "height_unit",
    "thickness_value": "thickness_unit",
    "diameter_value": "diameter_unit",
    "weight_value": "weight_unit",
}

#: What a weight is per. 'unknown' is the honest answer for every sheet read so far, and it
#: is a value a conversion must refuse rather than a value a conversion may use.
WEIGHT_BASES = ("branch", "meter", "piece", "package", "bag", "total", "unknown")

#: The bases that say what a weight is PER. An 'unknown' basis is NOT one of them: it is
#: the absence of the statement, and a crossing that rests on it would be asserting a
#: number nobody wrote down. Named here so "may this weight be used" is answered in one
#: place rather than re-decided per caller.
WEIGHT_BASES_USABLE_FOR_CONVERSION = ("branch", "meter", "piece", "package", "bag", "total")

#: Every typed specification column, in the order they are written. This is the ONE list:
#: the repository selects it, the importer writes it, the read API publishes it and the
#: backfill fills it. It used to be spelled out in three files under a comment claiming it
#: was "named once", and the drift that invites is exactly how a column gets added to the
#: database, declared in the schema, and never actually returned.
SPEC_COLUMNS = (
    "product_code", "manufacturer", "grade", "product_type", "dimensions_text",
    "length_value", "length_unit", "length_m", "width_value", "width_unit",
    "height_value", "height_unit", "thickness_value", "thickness_unit",
    "diameter_value", "diameter_unit", "weight_value", "weight_unit", "weight_basis",
    "branch_count", "pieces_per_package", "coverage_m2", "volume_m3")

#: Where a stored value came from, so a reader is never left guessing which layer answered.
FROM_COLUMN = "dedicated_column"
FROM_LABEL = "approved_label"
FROM_METADATA = "legacy_metadata"
UNRESOLVED = "unresolved"

#: Persian and Arabic-Indic digits, so a number written in either reads as one.
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_NUMBER_THEN_TEXT = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(.*)$")


def normalize_digits(text):
    """Persian and Arabic digits as ASCII, and the Persian decimal mark as a point."""
    if text is None:
        return None
    return str(text).translate(_DIGITS).replace("٫", ".").replace("،", "").strip()


def parse_number(value):
    """A Decimal, or None when the cell does not state one.

    Refuses text outright rather than salvaging a number from inside it: «ترک-کره» must not
    become a weight, and a sheet that puts an origin in a weight column is exactly the case
    this refusal exists for. NaN and infinity are refused too -- both are accepted by
    `numeric` and neither is a measurement.
    """
    text = normalize_digits(value)
    if not text:
        return None
    text = text.replace(",", "")
    if not _NUMBER.match(text):
        return None
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def parse_number_with_unit(value, *, default_unit=None):
    """`(number, unit_code)` from «۶ متر», «1150 گرم», or a bare number.

    The unit comes from the cell when the cell gives one. `default_unit` is used only where
    the COLUMN NAME declares it, and never as a guess: a bare «27» in a column called
    «وزن» stays unitless, because a kilogram and a gram are both plausible and the
    difference is a factor of a thousand.
    """
    text = normalize_digits(value)
    if not text:
        return None, None
    text = text.replace(",", "")
    match = _NUMBER_THEN_TEXT.match(text)
    if not match:
        return None, None
    number = parse_number(match.group(1))
    if number is None:
        return None, None
    tail = (match.group(2) or "").strip()
    if not tail:
        return number, (default_unit if default_unit in UNIT_REGISTRY else None)
    unit = SPEC_UNIT_WORDS.get(tail)
    if unit is None:
        # A number followed by something this module cannot name. The NUMBER is still what
        # the sheet says; the unit is not, and inventing one is the error being avoided.
        return number, None
    return number, unit


def to_metres(value, unit):
    """A length in metres, or None when the unit is not a length this system knows.

    The one normalized column populated from a raw pair, and only because the relationship
    is arithmetic: the registry's own ratios, never a guess.
    """
    if value is None or unit not in ("mm", "cm", "m"):
        return None
    factor = {"mm": Decimal("0.001"), "cm": Decimal("0.01"), "m": Decimal(1)}[unit]
    return value * factor


def extract_specs(category, metadata):
    """The typed specifications a sheet states for one listing, and nothing else.

    Returns `(values, leftovers)`: the columns that may be written, and the metadata keys
    this module did not claim. The leftovers stay in `metadata` -- they are the uncommon
    and newly-discovered attributes that layer exists for.

    A key this module declares but whose value does not have the declared SHAPE is skipped
    rather than coerced, and stays in the leftovers so nothing is lost.
    """
    declared = SPEC_MAP.get(category or "", {})
    stored = metadata if isinstance(metadata, dict) else {}
    values, claimed = {}, set()

    for key, rule in declared.items():
        if key not in stored:
            continue
        raw = stored.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        shape, column = rule["shape"], rule["column"]

        if shape == TEXT:
            values[column] = str(raw).strip()
            claimed.add(key)
            continue

        if shape == NUMBER_WITH_UNIT:
            number, unit = parse_number_with_unit(raw, default_unit=rule.get("unit_from_name"))
            if number is None:
                continue
            values[column] = number
            unit_column = UNIT_COLUMN_OF.get(column)
            if unit_column and unit:
                values[unit_column] = unit
            if column == "length_value":
                metres = to_metres(number, unit)
                if metres is not None:
                    values["length_m"] = metres
            claimed.add(key)
            continue

        # BARE_NUMBER. Text in a numeric column is not a number, and where the declaration
        # says where such text belongs, it goes there instead of being dropped.
        number = parse_number(raw)
        if number is None:
            text_column = rule.get("text_column")
            if text_column:
                values[text_column] = str(raw).strip()
                claimed.add(key)
            continue
        values[column] = number
        unit_column = UNIT_COLUMN_OF.get(column)
        if unit_column and rule.get("unit_from_name"):
            values[unit_column] = rule["unit_from_name"]
        claimed.add(key)

    # No sheet read so far states what a weight is PER. Saying 'unknown' is what stops the
    # number being used in a conversion that needs a basis.
    if "weight_value" in values:
        values.setdefault("weight_basis", "unknown")

    leftovers = {k: v for k, v in stored.items() if k not in claimed}
    return values, leftovers


def conflicts_with(existing, incoming):
    """Which incoming specifications disagree with what is already stored.

    A price is append-only and a specification is not, so an arriving sheet must not be
    allowed to overwrite a trusted measurement. NULL accepts a value; an equal value is no
    change; a DIFFERENT value is a finding -- yesterday 22 and today 220 is a parser or a
    source having gone wrong far more often than a product having changed.
    """
    disagreements = {}
    for column, value in (incoming or {}).items():
        current = (existing or {}).get(column)
        if current is None or str(current).strip() == "":
            continue
        if _same(current, value):
            continue
        disagreements[column] = {"stored": str(current), "incoming": str(value)}
    return disagreements


def _same(left, right):
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError):
            return str(left).strip() == str(right).strip()
    return str(left).strip() == str(right).strip()
