# -*- coding: utf-8 -*-
"""What each material worksheet actually states, category by category.

Every category on the daily-price sheet has its own columns, and they are not the same
columns. An angle iron states a thickness, a weight, a length and a branch count; a brick
states a code, dimensions, a weight and a price per square metre; an I-beam states a weight
and a length and nothing else. Flattening those into one table would mean either inventing
the missing ones or dropping the present ones, and both destroy the thing the sheet is for.

WHERE THE VALUES LIVE

`provider_items.metadata` already holds them, keyed by the worksheet's own Persian headers,
exactly as read. This module does not move them and does not re-parse them: it says which
keys belong to which category and what to call them, so the API can publish a category's own
columns and the page can render them.

That is deliberately a READING of stored data and not a schema. A per-category table would
have to be migrated every time a sheet gains a column, and the sheet is not ours; a typed
attribute table would have to decide a type for «6 متری» and «5کیلو», which are strings a
human wrote. The raw value travels, and `numeric` says which ones a reader may safely treat
as numbers -- for sorting and for showing, never for pricing. Nothing here is ever a price.

WHAT IS NOT HERE

No field is invented. A category whose worksheet does not state a thickness has no thickness
column, and a row whose cell was blank publishes null rather than a zero or a dash. If a
worksheet gains a column tomorrow it appears in `metadata` immediately and is published here
only once somebody adds it below -- which is a person deciding it is real, not the importer
guessing.
"""

#: One category's own columns: the key as the worksheet writes it, the label to show, and
#: whether the value is safe to read as a number.
#:
#: `key` is the Persian header verbatim. It is the join between the sheet and the page and
#: it is not translated on the way through -- a header that changes must fail visibly here
#: rather than silently match nothing.
CATEGORY_SPECS: dict[str, tuple[dict, ...]] = {
    "rebar": (
        {"key": "واحد - وزن", "label": "واحد وزن", "numeric": False},
    ),
    "ibeam": (
        {"key": "وزن - کیلوگرم", "label": "وزن (کیلوگرم)", "numeric": True},
        {"key": "طول", "label": "طول", "numeric": False},
    ),
    "angle": (
        {"key": "ضخامت", "label": "ضخامت", "numeric": True},
        {"key": "وزن", "label": "وزن", "numeric": True},
        {"key": "طول", "label": "طول", "numeric": False},
        {"key": "تعداد شاخه", "label": "تعداد شاخه", "numeric": True},
    ),
    "channel": (
        {"key": "وزن", "label": "وزن", "numeric": True},
        {"key": "طول", "label": "طول", "numeric": False},
    ),
    "profile": (
        {"key": "ابعاد", "label": "ابعاد", "numeric": False},
        {"key": "ضخامت", "label": "ضخامت", "numeric": True},
        {"key": "وزن", "label": "وزن", "numeric": False},
        {"key": "طول", "label": "طول", "numeric": False},
    ),
    "brick": (
        {"key": "کد", "label": "کد", "numeric": False},
        {"key": "ابعاد", "label": "ابعاد", "numeric": False},
        {"key": "وزن", "label": "وزن", "numeric": False},
        {"key": "قیمت در هر مترمربع", "label": "قیمت هر مترمربع", "numeric": True},
    ),
    "pipe": (),
    "pipe_fitting": (),
}

#: What a category is called on screen. A category with no entry shows its own code, which
#: is ugly on purpose: an unnamed category is a worksheet nobody has looked at yet.
CATEGORY_LABELS: dict[str, str] = {
    "rebar": "میلگرد",
    "ibeam": "تیرآهن",
    "angle": "نبشی",
    "channel": "ناودانی",
    "profile": "پروفیل / قوطی",
    "pipe": "لوله",
    "pipe_fitting": "اتصالات لوله",
    "brick": "آجر",
}


def spec_columns(category):
    """The columns this category's worksheet states, in display order."""
    return list(CATEGORY_SPECS.get(category or "", ()))


def category_label(category):
    return CATEGORY_LABELS.get(category or "", category or "بدون دسته")


def specs_of(category, metadata):
    """One listing's own spec values, as the sheet stated them.

    Missing is null, never zero and never a placeholder: a brick with no code and a brick
    whose code is "0" are different bricks, and only one of them told us anything.
    """
    stored = metadata if isinstance(metadata, dict) else {}
    values = {}
    for column in spec_columns(category):
        raw = stored.get(column["key"])
        text = None if raw is None else str(raw).strip()
        values[column["key"]] = text or None
    return values


def unknown_spec_keys(category, metadata):
    """Keys the sheet carries that this module does not publish.

    Reported rather than dropped in silence. A worksheet that gained a column shows up here,
    which is how somebody finds out it is worth adding -- and until they do, the value is
    stored and simply not displayed, which is the honest state.
    """
    stored = metadata if isinstance(metadata, dict) else {}
    known = {column["key"] for column in spec_columns(category)}
    return sorted(key for key in stored if key not in known)
