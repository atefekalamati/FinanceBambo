# -*- coding: utf-8 -*-
"""Two readings of one page, compared field by field.

WHAT THIS IS FOR

The pipeline now reads every invoice twice: PaddleOCR transcribes it and a vision model
looks at it. Two readings are only worth having if disagreement is visible, so nothing
here picks a winner and overwrites the loser. Where the two agree, the agreement is
recorded and confidence rises. Where they differ, BOTH values survive on the row and the
row is marked for a person.

WHY NOT JUST TRUST THE BETTER SOURCE

Because neither is reliably better, and the errors are the dangerous kind. Measured
against ground truth on the audited BAMBO invoices:

    true   544,222,000
    vision 544,322,000     one digit
    true   317,453,000
    vision 3,174,535,000   one digit INSERTED

The best model reproduced 3 of 9 prices exactly; another scored 0 of 15. A single digit
in 544,222,000 is a hundred million rial, and the wrong number looks exactly as
plausible as the right one. A fusion layer that silently preferred either source would
launder that error into a draft that reads as agreed.

WHAT AGREEMENT MEANS HERE

Money and quantities are compared as NUMBERS, so `۵۴۴,۲۲۲,۰۰۰` and `544222000` are the
same reading recorded twice, not a conflict. Names are compared with digit script,
spacing and dash noise normalised, because `آیتم ۳` and `آیتم 3` are the same name. What
is NOT normalised away is the value itself: 544222000 and 544322000 stay different, which
is the entire point.

SILENCE IS NOT AGREEMENT

A field one source read and the other did not is `single_source`, never `agreed`. This
matters most where it is least obvious: every vision model tested invented an invoice
number on every page, on documents that carry only a project number. OCR was correctly
silent. Calling that agreement would promote an invention; calling it a conflict would
cry wolf on a field that is simply absent from one reading. It is its own state, it
carries `requiresReview`, and a reader can see which source spoke.
"""

import re

#: The fields both readers are expected to produce, in the order a person reads them.
COMPARED_FIELDS = ("supplierName", "invoiceNumber", "invoiceDate", "currency",
                   "totalAmount")

#: Fields whose values are money or counts, compared numerically rather than as text.
NUMERIC_FIELDS = frozenset({"totalAmount", "quantity", "unitPrice", "totalPrice"})

AGREED = "agreed"
CONFLICT = "conflict"
SINGLE_SOURCE = "single_source"
ABSENT = "absent"

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ascii_digits(value):
    """Persian and Arabic digits as ASCII. Everything else is left alone.

    Deliberately not a general normaliser: it moves digits between scripts and touches
    nothing else, so a Persian product name survives it unchanged.
    """
    if value is None:
        return None
    text = str(value)
    for index, digit in enumerate(PERSIAN_DIGITS):
        text = text.replace(digit, str(index))
    for index, digit in enumerate(ARABIC_DIGITS):
        text = text.replace(digit, str(index))
    return text


def as_number(value):
    """A money or quantity value as a number, or None when it is not one.

    Accepts the spellings these documents and models actually produce: Persian digits,
    Latin digits, ASCII and Arabic thousands separators, stray spaces. Returns None rather
    than a guess for anything else -- a value that cannot be read as a number must not
    become one, because the number it became would be compared against a real one.
    """
    text = ascii_digits(value)
    if text is None:
        return None
    text = text.replace(",", "").replace("،", "").replace("٬", "")
    text = text.replace(" ", "").replace("‌", "").strip()
    if not text or not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    number = float(text)
    return int(number) if number == int(number) else number


def comparable_text(value):
    """A name reduced to what two readers should agree on: digits, spacing, case."""
    text = ascii_digits(value)
    if text is None:
        return None
    text = re.sub(r"[\s\-–—_]+", " ", text).strip().lower()
    return text or None


def _same(field, left, right):
    """Whether two readings of one field say the same thing."""
    if field in NUMERIC_FIELDS:
        left_number, right_number = as_number(left), as_number(right)
        if left_number is not None and right_number is not None:
            return left_number == right_number
    return comparable_text(left) == comparable_text(right)


def _present(value):
    return value is not None and str(value).strip() != ""


def compare_field(field, ocr_value, vision_value):
    """One field's verdict, with both readings kept whatever it is.

    The shape is the same in every state so a consumer never has to branch on the
    verdict to find a value.
    """
    ocr_there, vision_there = _present(ocr_value), _present(vision_value)
    if not ocr_there and not vision_there:
        status = ABSENT
    elif ocr_there and vision_there:
        status = AGREED if _same(field, ocr_value, vision_value) else CONFLICT
    else:
        status = SINGLE_SOURCE
    return {
        "field": field,
        "status": status,
        "conflict": status == CONFLICT,
        # A person is asked wherever the two readings do not positively agree. `absent`
        # is the one state that needs nobody: neither reader saw anything to check.
        "requiresReview": status in (CONFLICT, SINGLE_SOURCE),
        "sources": [
            {"type": "ocr", "value": None if not ocr_there else str(ocr_value)},
            {"type": "vision", "value": None if not vision_there else str(vision_value)},
        ],
        # The agreed reading, and ONLY when they agree. Never a pick between two
        # different numbers -- that choice belongs to the person, not to this module.
        "value": str(ocr_value) if status == AGREED else None,
    }


def compare_items(ocr_items, vision_items):
    """Line items compared by position, which is how a page presents them.

    Position, not name: on these invoices the names are «آیتم ۱» … «آیتم ۱۵» and carry no
    information a matcher could use. Where the two readers disagree about how MANY rows
    exist, the surplus rows are reported as single-source rather than dropped -- a row one
    reader saw is a row a person should be shown.
    """
    ocr_items = list(ocr_items or [])
    vision_items = list(vision_items or [])
    rows = []
    for index in range(max(len(ocr_items), len(vision_items))):
        mine = ocr_items[index] if index < len(ocr_items) else {}
        theirs = vision_items[index] if index < len(vision_items) else {}
        fields = {name: compare_field(name, mine.get(name), theirs.get(name))
                  for name in ("name", "quantity", "unit", "unitPrice", "totalPrice")}
        rows.append({
            "index": index,
            "fields": fields,
            "conflict": any(f["conflict"] for f in fields.values()),
            "requiresReview": any(f["requiresReview"] for f in fields.values()),
        })
    return {
        "rows": rows,
        "ocrRowCount": len(ocr_items),
        "visionRowCount": len(vision_items),
        "rowCountAgrees": len(ocr_items) == len(vision_items),
    }


def fuse(ocr_fields, vision_fields, ocr_items=None, vision_items=None):
    """The whole comparison for one page.

    `ocr_fields` and `vision_fields` are plain `{field: value}` mappings -- whatever each
    reader produced. Returns a record a draft can carry verbatim and a reviewer can read
    without knowing anything about either provider.
    """
    ocr_fields = ocr_fields or {}
    vision_fields = vision_fields or {}
    header = [compare_field(name, ocr_fields.get(name), vision_fields.get(name))
              for name in COMPARED_FIELDS]
    items = compare_items(ocr_items, vision_items)

    conflicts = [entry for entry in header if entry["conflict"]]
    conflicted_rows = [row["index"] for row in items["rows"] if row["conflict"]]
    agreed = [entry["field"] for entry in header if entry["status"] == AGREED]

    return {
        "fields": header,
        "items": items,
        "agreedFields": agreed,
        "conflictFields": [entry["field"] for entry in conflicts],
        "conflictRows": conflicted_rows,
        # One question for the review screen: does a person have to look at this page?
        # True whenever the readers disagree anywhere, or either of them saw a row count
        # the other did not.
        "requiresReview": bool(conflicts) or bool(conflicted_rows)
                          or not items["rowCountAgrees"]
                          or any(entry["status"] == SINGLE_SOURCE for entry in header),
    }
