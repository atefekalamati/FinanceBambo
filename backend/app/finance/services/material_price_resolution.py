# -*- coding: utf-8 -*-
"""From an observation to a price somebody can act on -- or to a stated reason they cannot.

This is where the ways a price can be unusable are told apart, because a reader who is
shown nothing cannot tell them apart and a reader who is shown a zero is being misled.

    resolved             a price, in the right unit, with its provenance
    stale                older than the freshness window -- kept, and labelled
    unresolved_price     the newest observation could not be read
    unresolved_unit      the source states no unit, so there is no basis to convert from
    incompatible_unit    both units are known and belong to different dimensions
    missing_factor       the crossing is real but needs a fact about THIS product
    unresolved_mapping   a price with no approved mapping to a Finance resource
    invalid_source       the observation itself was rejected at import
    inactive             the listing is kept but is not part of the active list

THE ONE VOCABULARY

Units are named by `domain/unit_registry.py` and nothing else. What arrives from the sheet
is Persian text a supplier typed -- «کیلو», «متر», «شاخه» -- and `SHEET_UNIT_SPELLINGS`
maps those onto registry codes. That is an input normaliser, not a second vocabulary: every
value it produces is a key of `UNIT_REGISTRY`, and a test asserts it.

An earlier draft of this file kept its own list and invented `piece`, `g`, `cm` and
`branch` as unit names of its own. Four of those the registry did not have at all and one
was a synonym for `each`, so a price and a Finance resource could only have agreed about a
unit by accident.
"""

from decimal import Decimal

from ..domain.unit_conversion import (ConversionRefused, apply_product_factor, can_convert,
                                      convert_unit_price, quantity_factor)
from ..domain.unit_registry import UNIT_REGISTRY

#: How the sheet spells a unit, and which registry code that is. Left side: what people
#: write. Right side: always a key of UNIT_REGISTRY.
SHEET_UNIT_SPELLINGS = {
    "کیلو": "kg", "کیلوگرم": "kg", "kilogram": "kg", "kilo": "kg",
    "گرم": "g", "gram": "g",
    "تن": "ton", "tonne": "ton",
    "متر": "m", "متری": "m", "meter": "m", "metre": "m", "مترطول": "m",
    "سانتیمتر": "cm", "centimeter": "cm",
    "میلیمتر": "mm", "millimeter": "mm",
    "مترمربع": "m2", "square meter": "m2", "sqm": "m2", "متر مرکعب": "m3",
    "مترمکعب": "m3", "cubic meter": "m3", "cmb": "m3", "مترمرکعب": "m3",
    "لیتر": "liter", "litre": "liter",
    # Count. The registry's code is `each`; «عدد», «دانه», «تعداد», «قطعه» and the English
    # `piece`/`number` are spellings of it, not units of their own. An earlier draft of
    # this file invented `piece` as a separate name and a price could then agree with a
    # resource only by accident -- see the note above.
    "عدد": "each", "piece": "each", "pcs": "each", "قطعه": "each",
    "دانه": "each", "تعداد": "each", "number": "each",
    "شاخه": "branch",
    "کیسه": "bag", "پاکت": "bag",
    # Time, which the sheet does state for hired plant.
    "روز": "day", "ساعت": "hour",
}

#: Spellings deliberately left OUT, and why. «بسته», «رول», «برگ», «جفت» and «ست» are real
#: units somebody writes, and the registry has no code for any of them. Mapping them to a
#: name invented here would produce a unit with no dimension and no conversion -- it would
#: read as resolved and could never be crossed with anything, which is worse than being
#: unrecognised. They return None until the registry gains real codes for them.
UNMAPPED_SHEET_SPELLINGS = ("بسته", "رول", "برگ", "جفت", "ست", "package", "roll",
                            "sheet", "pair", "set",
                            # Seen on real listings and just as unnameable: the registry
                            # has no decimetre-cubed, and deriving one from m3 here would
                            # put a conversion factor in a spelling table.
                            "دسیمترمکعب")

#: Letters that are one letter written two ways. A supplier typing on an Arabic keyboard
#: produces «كيلو» where a Persian one produces «کیلو», and a map keyed on one spelling
#: silently fails to recognise the other -- which is how a perfectly good unit becomes
#: `unresolved_unit`.
_LETTER_FOLD = {"ي": "ی", "ى": "ی", "ك": "ک",
                "ة": "ه"}

#: Persian and Arabic digits, for units written «متر 2» or «m٢».
_DIGIT_FOLD = {ord(digit): str(index)
               for index, digit in enumerate("۰۱۲۳۴"
                                             "۵۶۷۸۹")}
_DIGIT_FOLD.update({ord(digit): str(index)
                    for index, digit in enumerate("٠١٢٣٤"
                                                  "٥٦٧٨٩")})


def normalize_unit_text(unit):
    """What a person typed, reduced to what two spellings of one unit have in common.

    Folds the Arabic/Persian letter pairs, converts Persian and Arabic digits to ASCII,
    removes the zero-width non-joiner, collapses runs of whitespace to one space, and
    lowercases. It does NOT decide what the unit is -- that is `canonical_unit`'s job, and
    keeping them apart is what lets this be tested on its own.
    """
    if unit is None:
        return ""
    text = str(unit)
    for source, target in _LETTER_FOLD.items():
        text = text.replace(source, target)
    text = text.translate(_DIGIT_FOLD).replace("‌", "")
    return " ".join(text.split()).lower()

#: Statuses, named once so the API, the UI and these tests cannot drift apart.
RESOLVED = "resolved"
STALE = "stale"
UNRESOLVED_PRICE = "unresolved_price"
UNRESOLVED_UNIT = "unresolved_unit"
INCOMPATIBLE_UNIT = "incompatible_unit"
MISSING_FACTOR = "missing_factor"
UNRESOLVED_MAPPING = "unresolved_mapping"
INVALID_SOURCE = "invalid_source"
INACTIVE = "inactive"

ALL_STATUSES = (RESOLVED, STALE, UNRESOLVED_PRICE, UNRESOLVED_UNIT, INCOMPATIBLE_UNIT,
                MISSING_FACTOR, UNRESOLVED_MAPPING, INVALID_SOURCE, INACTIVE)


class Resolution:
    """What one observation resolved to. Every field a reader needs to judge it."""

    __slots__ = ("price", "status", "reason", "source_unit", "target_unit",
                 "conversion_factor", "conversion_note", "factor_origin")

    def __init__(self, price=None, status=UNRESOLVED_PRICE, reason=None, source_unit=None,
                 target_unit=None, conversion_factor=None, conversion_note=None,
                 factor_origin=None):
        self.price = price
        self.status = status
        self.reason = reason
        self.source_unit = source_unit
        self.target_unit = target_unit
        self.conversion_factor = conversion_factor
        self.conversion_note = conversion_note
        self.factor_origin = factor_origin

    @property
    def usable(self) -> bool:
        """Whether a Finance calculation may use this. Stale counts; unresolved never does."""
        return self.status in (RESOLVED, STALE) and self.price is not None


def canonical_unit(unit):
    """A registry code, or `None` when nothing usable was stated.

    An unrecognised spelling returns `None` rather than itself: a unit this system cannot
    name is a unit it cannot convert, and returning the raw text would let it travel on
    looking like a code.
    """
    if unit is None:
        return None
    text = str(unit).strip()
    if not text:
        return None
    if text in UNIT_REGISTRY:
        return text
    lowered = text.lower()
    if lowered in UNIT_REGISTRY:
        return lowered
    # Folded last, so an exact registry code is never altered on its way through. What the
    # folding buys is the spellings that differ only in keyboard: «كيلو» for «کیلو»,
    # «متر  مربع» with two spaces, «m٢» with an Arabic digit.
    folded = normalize_unit_text(text)
    if folded in UNIT_REGISTRY:
        return folded
    named = (SHEET_UNIT_SPELLINGS.get(text) or SHEET_UNIT_SPELLINGS.get(lowered)
             or SHEET_UNIT_SPELLINGS.get(folded))
    if named is not None:
        return named
    # Last: the same lookup with the spaces taken out, so «متر مربع» and «مترمربع» are one
    # spelling. Listing both in the map covered the two people happen to write; a supplier
    # writing «متر  مربع» or «سانتی متر» was still unrecognised, and a unit this system
    # cannot name is a price it cannot use.
    tight = folded.replace(" ", "")
    if tight in UNIT_REGISTRY:
        return tight
    return SHEET_UNIT_SPELLINGS.get(tight)



def stated_source_unit(observation, label=None):
    """The unit a daily price is stated in, as a REGISTRY CODE, or None.

    Two things can say it and they are asked in the order of who looked hardest:

      1. A LABEL a person recorded against this listing. It is the narrower statement and
         the only one made by somebody who looked at this product -- and for most of the
         catalogue it is the only one there is, because the worksheet states a unit for
         rebar and for nothing else.
      2. The observation itself: `normalized_unit` when the importer settled one, else the
         raw `source_unit` text the sheet carried.

    Everything goes through `canonical_unit`, so a spelling this system cannot name stays
    unresolved rather than travelling on looking like a code.

    WHY THIS IS SHARED

    `material_prices` already asked the label first and the item-pricing services did not,
    so a label recorded to make a listing usable changed the prices page and left the
    financial-items row still saying «واحد قیمت مبدأ مشخص نیست». One listing, two answers,
    on two pages of the same product -- which is the second vocabulary this area keeps
    being warned about. One function now, called by both.
    """
    stated = ((label or {}).get("source_unit")
              or observation.get("normalized_unit")
              or observation.get("source_unit"))
    return canonical_unit(stated) or None

def unit_label(code):
    """The Persian name of a registry code, for a message a person will read."""
    definition = UNIT_REGISTRY.get(code or "")
    return definition.label_fa if definition else (code or "نامشخص")


def resolve(observation, *, display_unit=None, product_factor=None, as_of=None,
            stale_after_days=None, mapping_required=False, mapping_approved=False,
            active=True):
    """Resolve one observation against the unit a person chose.

    `product_factor` is `(factor, origin)` or `None`: a number somebody stored against THIS
    listing. It is consulted only when the units are known and cross a dimension, which is
    the only situation no fact about units can answer.
    """
    if not active:
        return Resolution(status=INACTIVE, reason="این قلم در فهرست فعال نیست")

    price = observation.get("normalized_price_irr")
    row_status = observation.get("validation_status")
    source = canonical_unit(observation.get("source_unit"))
    target = canonical_unit(display_unit)

    if row_status in ("rejected",):
        return Resolution(status=INVALID_SOURCE, source_unit=source, target_unit=target,
                          reason=_reasons(observation)
                          or "این ردیف هنگام درون‌ریزی نامعتبر شناخته شد")
    if price is None or row_status == "pending":
        return Resolution(status=UNRESOLVED_PRICE, source_unit=source, target_unit=target,
                          reason=_reasons(observation)
                          or "آخرین مشاهده قیمت خوانا ندارد")

    price = Decimal(price)
    factor = None
    note = None
    origin = None

    if source is None:
        return Resolution(status=UNRESOLVED_UNIT, target_unit=target,
                          reason="منبع واحدی برای این قیمت اعلام نکرده است؛ قیمت در محاسبه قابل استفاده نیست")

    if target is not None:
        if source != target:
            if can_convert(source, target):
                factor = quantity_factor(source, target)
                price = convert_unit_price(price, source, target)
                origin = "dimension"
                note = ("از %s به %s: قیمت واحد بر %s تقسیم شد"
                        % (unit_label(source), unit_label(target), factor))
            else:
                stored, stored_origin = (product_factor or (None, None))
                if stored is None:
                    return Resolution(status=_crossing_status(source, target),
                                      source_unit=source, target_unit=target,
                                      reason=_crossing_reason(source, target))
                try:
                    price = apply_product_factor(price, stored)
                except ConversionRefused as exc:
                    return Resolution(status=MISSING_FACTOR, source_unit=source,
                                      target_unit=target, reason=str(exc))
                factor = Decimal(stored)
                origin = stored_origin or "manual"
                note = ("از %s به %s با ضریب ثبت‌شدهٔ همین کالا (%s): قیمت واحد تقسیم شد"
                        % (unit_label(source), unit_label(target), factor))

    if mapping_required and not mapping_approved:
        return Resolution(price=None, status=UNRESOLVED_MAPPING, source_unit=source,
                          target_unit=target,
                          reason="این کالا هنوز به قلم هزینهٔ مالی وصل و تأیید نشده است")

    if stale_after_days is not None and as_of is not None:
        when = observation.get("workflow_date_gregorian")
        if when is not None and (as_of - when).days > stale_after_days:
            return Resolution(price=price, status=STALE, source_unit=source,
                              target_unit=target, conversion_factor=factor,
                              conversion_note=note, factor_origin=origin,
                              reason="تازه‌ترین قیمتی که برگه اعلام کرده مربوط به %s است"
                                     % when.isoformat())

    return Resolution(price=price, status=RESOLVED, source_unit=source, target_unit=target,
                      conversion_factor=factor, conversion_note=note, factor_origin=origin)


def _crossing_status(source, target):
    """`incompatible_unit` when nothing could ever bridge them; `missing_factor` otherwise.

    Both are refusals. They are separate because the fix is different: one needs somebody to
    choose a different target unit, the other needs somebody to measure this product.
    """
    left, right = UNIT_REGISTRY.get(source), UNIT_REGISTRY.get(target)
    if left is None or right is None:
        return INCOMPATIBLE_UNIT
    # A count crossing into a physical dimension is exactly what a per-product factor
    # answers: how much one piece weighs, how long one branch is.
    if "count" in (left.dimension, right.dimension):
        return MISSING_FACTOR
    # mass to length, area to volume: no measurement of one product bridges these either.
    return MISSING_FACTOR if {left.dimension, right.dimension} <= {
        "mass", "length", "area", "volume"} else INCOMPATIBLE_UNIT


def _crossing_reason(source, target):
    return ("برای تبدیل %s به %s ضریبی لازم است که مخصوص همین کالاست و هنوز ثبت نشده؛ "
            "قیمت نمایش داده نمی‌شود تا برچسب اشتباه نخورد"
            % (unit_label(source), unit_label(target)))


def _reasons(observation):
    values = observation.get("validation_reasons") or []
    return "; ".join(str(value) for value in values) or None
