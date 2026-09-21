# -*- coding: utf-8 -*-
"""Where words sit on the page, and what that says about the table they belong to.

WHY THIS EXISTS

A recogniser reads an invoice as a list of fragments. Joined with newlines, a five-column
table becomes a column of strings in whatever order the detector emitted them, and the
question "which price belongs to which product" has no answer left in the text. That is
what `INVOICE_TABLE_NOT_RECOGNISED` was reporting: not a failure to read, a failure to
keep. PaddleOCR returns the position of every line it reads and the provider used to
discard it.

So this module takes the positions back and rebuilds the page:

    lines  ->  rows (by vertical overlap)  ->  columns (by horizontal clustering)
           ->  a header, if one can be found  ->  cells addressed by row and column

WHAT IT DOES NOT DO

It does not read money, dates or units, and it does not decide what a field means. It
hands `invoice_parser` a table; the parser keeps its rules about what a total is and what
may be believed. Two reasons: those rules are tested against text that has no geometry at
all and must go on working, and a layout engine that also parsed would decide the same
question in two places.

It invents nothing. A row whose cells do not line up is reported as a row that did not
line up, and a page with no header is reported as a page with no header. Every function
here can return "I could not tell", because on a scanned invoice that is frequently the
true answer and the alternative is a confident wrong one.

RIGHT TO LEFT

Persian invoices read right to left, so the first column is the RIGHTMOST one. Column
order is therefore x descending, and a caller that sorted ascending would silently mirror
every row -- putting the price where the description belongs. `columns_right_to_left`
makes that explicit rather than leaving it to each caller to remember.
"""

import re
import unicodedata
from statistics import median

#: Persian and Arabic-Indic digits, to ASCII. The recogniser returns whichever the page
#: used, and a page often uses both -- the audited invoice mixes U+06F5 and U+0665 inside
#: one number.
_DIGITS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})

#: Both thousands separators an Iranian invoice uses, and the decimal mark. U+060C is the
#: one the recogniser actually emits; U+066C is the one whose Unicode name says
#: "thousands separator". Treating only the second is how every grouped figure on a real
#: invoice was read as malformed.
ARABIC_COMMA = "،"
ARABIC_THOUSANDS = "٬"
ARABIC_DECIMAL = "٫"


def normalize(text):
    """One spelling, so a comparison does not depend on which keyboard typed the page.

    Digits to ASCII, Arabic ي and ك folded to Persian ی and ک, zero-width joiners removed,
    runs of space collapsed. The same folding `extraction.parsing` applies, repeated here
    rather than imported so this module stays usable on its own and so a change to one
    cannot silently alter the other's matching.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.translate(_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("‌", " ").replace("‏", "").replace("‎", "")
    return re.sub(r"[ \t]+", " ", text).strip()


#: What each heading means, in the words Iranian construction invoices actually use.
#: Longest first inside each role, because `مبلغ کل` must not be matched by `مبلغ`.
COLUMN_ROLES = (
    ("unit_price", ("مبلغ واحد ریال", "مبلغ واحد", "قیمت واحد", "بهای واحد", "فی",
                    "نرخ واحد", "نرخ")),
    ("amount", ("مبلغ کل ریال", "مبلغ کل", "جمع مبلغ", "قیمت کل", "مبلغ")),
    ("quantity", ("تعداد", "مقدار", "کمیت")),
    ("unit", ("واحد",)),
    ("name", ("شرح کالا", "شرح خدمات", "عنوان", "شرح", "کالا", "نام کالا")),
    ("row_number", ("ردیف", "شماره")),
)

#: A heading only counts when the cell is mostly that heading. «واحد» inside «مبلغ واحد»
#: is a substring and not a column, and matching it would make the unit column and the
#: unit-price column the same one.
_HEADING_FIT = 0.6


def role_of(text):
    """Which column a heading names, or None.

    Roles are tried in the order above and the longest spelling within each role first,
    so `مبلغ واحد ریال` is unit price rather than amount. The match must also account for
    most of the cell -- see `_HEADING_FIT` -- which is what keeps `واحد` from claiming a
    cell that says `مبلغ واحد`.
    """
    cleaned = normalize(text).lower()
    if not cleaned:
        return None
    for role, spellings in COLUMN_ROLES:
        for spelling in spellings:
            if spelling in cleaned and len(spelling) >= _HEADING_FIT * len(cleaned):
                return role
    return None


class Line:
    """One recognised line: what it says, how sure the model was, and where it sits."""

    __slots__ = ("text", "confidence", "left", "top", "right", "bottom")

    def __init__(self, text, confidence, box):
        self.text = text
        self.confidence = float(confidence or 0.0)
        self.left, self.top, self.right, self.bottom = box

    @property
    def middle_y(self):
        return (self.top + self.bottom) / 2

    @property
    def middle_x(self):
        return (self.left + self.right) / 2

    @property
    def height(self):
        return max(1.0, self.bottom - self.top)

    def __repr__(self):                                             # pragma: no cover
        return "Line(%r, x=%d..%d, y=%d..%d)" % (self.text[:18], self.left, self.right,
                                                 self.top, self.bottom)


def lines_from(raw_lines):
    """`Line` objects for the entries that have a usable position, in reading order.

    A line with no box is DROPPED from the layout -- not placed at the origin, which would
    sort it to the top-left corner and attach it to whichever row happens to be there.
    The caller still has the full text; this is only about what can be positioned.
    """
    out = []
    for entry in raw_lines or ():
        box = entry.get("box") if hasattr(entry, "get") else None
        text = (entry.get("text") if hasattr(entry, "get") else None) or ""
        if box is None or not str(text).strip():
            continue
        try:
            left, top, right, bottom = (float(v) for v in box)
        except (TypeError, ValueError):
            continue
        out.append(Line(str(text), entry.get("confidence"), (left, top, right, bottom)))
    out.sort(key=lambda line: (line.middle_y, -line.middle_x))
    return out


#: How much of a line's height must overlap another's for the two to be the same row.
#: Generous, because a tall product description and a short number beside it share a row
#: while overlapping far less than either's full height.
_ROW_OVERLAP = 0.35


def group_rows(lines):
    """Lines gathered into visual rows, top to bottom.

    Rows are found by VERTICAL OVERLAP rather than by rounding the y coordinate to a grid.
    A scanned page is never level, and a grid wide enough to tolerate the skew at the top
    of the page merges two genuine rows at the bottom of it.

    Within a row the lines are ordered right to left, which is reading order here.
    """
    rows = []
    for line in sorted(lines, key=lambda item: item.top):
        placed = False
        for row in rows:
            top = min(item.top for item in row)
            bottom = max(item.bottom for item in row)
            overlap = min(bottom, line.bottom) - max(top, line.top)
            if overlap > 0 and overlap >= _ROW_OVERLAP * min(line.height, bottom - top):
                row.append(line)
                placed = True
                break
        if not placed:
            rows.append([line])
    for row in rows:
        row.sort(key=lambda item: -item.middle_x)
    rows.sort(key=lambda row: min(item.top for item in row))
    return rows


def find_header(rows):
    """`(index, {role: x_centre})` for the row that names the columns, or `(None, {})`.

    A header is the row that names the most DISTINCT roles, and it must name at least
    two. One heading is a coincidence -- «واحد» appears in ordinary prose -- and a table
    whose columns cannot be told apart is not one this can reconstruct.

    The x centre of each heading is what the columns are then built from, because the
    heading sits over its column.
    """
    best_index, best_roles = None, {}
    for index, row in enumerate(rows):
        roles = {}
        for line in row:
            role = role_of(line.text)
            if role is not None and role not in roles:
                roles[role] = line.middle_x
        if len(roles) > len(best_roles):
            best_index, best_roles = index, roles
    if len(best_roles) < 2:
        return None, {}
    return best_index, best_roles


def assign_columns(row, anchors):
    """`{role: [Line, ...]}` for one row, each line going to its nearest column.

    Nearest by horizontal centre, and only when the line actually sits within reach of
    that column -- half the gap between neighbouring anchors. A line beyond every column
    is returned under None, because a stray mark dragged into the nearest column would
    become a quantity or a price.
    """
    if not anchors:
        return {}
    centres = sorted(anchors.items(), key=lambda pair: pair[1])
    if len(centres) > 1:
        gaps = [centres[i + 1][1] - centres[i][1] for i in range(len(centres) - 1)]
        reach = max(1.0, median(gaps)) * 0.75
    else:
        reach = float("inf")
    out = {}
    for line in row:
        role, distance = None, None
        for candidate, centre in anchors.items():
            offset = abs(line.middle_x - centre)
            if distance is None or offset < distance:
                role, distance = candidate, offset
        out.setdefault(role if distance is not None and distance <= reach else None,
                       []).append(line)
    return out


#: A page needs this many rows under the header before it is called a table. Two is a
#: heading and one row, which is as often a summary block with a stray heading in it.
_TABLE_MIN_ROWS = 2

TABLE_PAGE = "table"
SUMMARY_PAGE = "summary"
MIXED_PAGE = "mixed"
UNKNOWN_PAGE = "unknown"

#: Words that only appear where a document is totalling itself up.
_SUMMARY_WORDS = ("جمع کل", "مبلغ قابل پرداخت", "قابل پرداخت", "جمع", "تخفیف",
                  "مالیات", "ارزش افزوده", "مبلغ نهایی", "تعداد واحد", "متراژ")


def classify(rows, header_index, anchors):
    """What kind of page this is: a table, a summary, both, or neither.

    Asked BEFORE any field is read, because the two kinds want different treatment and
    guessing wrong is expensive in both directions -- looking for line items on a summary
    page invents them, and treating a table page as a summary loses every one.
    """
    body = 0 if header_index is None else max(0, len(rows) - header_index - 1)
    has_table = header_index is not None and len(anchors) >= 2 and body >= _TABLE_MIN_ROWS
    summary_hits = 0
    for row in rows:
        joined = normalize(" ".join(line.text for line in row))
        if any(word in joined for word in _SUMMARY_WORDS):
            summary_hits += 1
    has_summary = summary_hits >= 2
    if has_table and has_summary:
        return MIXED_PAGE
    if has_table:
        return TABLE_PAGE
    if has_summary:
        return SUMMARY_PAGE
    return UNKNOWN_PAGE


#: A cell is a number when this much of it is digits once normalised. Not "parses as a
#: number": a price cell reads `1,250,000` and a quantity cell reads `12 عدد`, and both are
#: numeric in the sense that matters for telling a column apart from a description.
_NUMERIC_SHARE = 0.5

#: Unit words as they appear in a unit column. Short list on purpose -- this decides a
#: column's ROLE, and a generous list would claim the description column on any invoice
#: whose products are named after their units.
_UNIT_WORDS = ("عدد", "کیلوگرم", "کیلو", "متر", "مترمربع", "مترمکعب", "شاخه", "تن",
               "بسته", "کارتن", "لیتر", "جفت", "حلقه", "رول", "ورق")


def _numeric_share(text):
    """How much of this cell is digits, 0..1."""
    cleaned = normalize(text)
    if not cleaned:
        return 0.0
    digits = sum(1 for character in cleaned if character.isdigit())
    meaningful = sum(1 for character in cleaned if not character.isspace())
    return digits / meaningful if meaningful else 0.0


def cluster_columns(rows, tolerance=None):
    """Column centres inferred from where cells actually fall, with no header.

    WHY THIS IS NEEDED AT ALL

    A header is the reliable way to name columns and it is frequently not there. On the
    audited invoice the recogniser read none of `عنوان`, `مقدار`, `واحد`, `مبلغ واحد` or
    `مبلغ کل` -- the heading band is shaded, and the model returned nothing for it. The
    table itself was still perfectly visible: five cells per row, in five vertical bands,
    down the whole page.

    So the columns are found from the BODY. Every cell centre is a vote, votes that fall
    near each other are one column, and a band that only a couple of rows use is dropped
    -- that is a stray mark, not a column.

    The tolerance defaults to a fraction of the median cell width, so it scales with the
    page's own resolution instead of a pixel count that is right for one scan.
    """
    centres = [line.middle_x for row in rows for line in row]
    if len(centres) < 4:
        return []
    if tolerance is None:
        widths = [max(1.0, line.right - line.left) for row in rows for line in row]
        tolerance = max(8.0, median(widths) * 0.6)

    bands = []
    for centre in sorted(centres):
        if bands and centre - bands[-1][-1] <= tolerance:
            bands[-1].append(centre)
        else:
            bands.append([centre])
    # A column is a band that enough DISTINCT rows use. A band fed by many cells of one
    # row is a wrapped description, not a column of its own.
    keep = []
    for band in bands:
        low, high = min(band), max(band)
        using = sum(1 for row in rows
                    if any(low - tolerance <= line.middle_x <= high + tolerance
                           for line in row))
        if using >= max(2, len(rows) // 4):
            keep.append(sum(band) / len(band))
    return sorted(keep)


def infer_roles(rows, centres):
    """Name the inferred columns from what they CONTAIN, since nothing named them.

    Three readings, in order of how much they prove:

      * a column whose cells carry unit words is the unit column
      * of the numeric columns, the one with the largest values is the amount and the next
        the unit price -- a line total is the product of the other two and is therefore
        the bigger of them on essentially every invoice
      * the widest mostly-textual column is the description

    Every one of these can decline. A column this cannot name is left unnamed rather than
    given the next role in the list, because a mislabelled column puts a quantity where a
    price belongs and nothing downstream can tell.
    """
    if not centres:
        return {}
    tolerance = None
    widths = [max(1.0, line.right - line.left) for row in rows for line in row]
    if widths:
        tolerance = max(8.0, median(widths) * 0.6)

    columns = {index: [] for index in range(len(centres))}
    for row in rows:
        for line in row:
            nearest = min(range(len(centres)),
                          key=lambda i: abs(line.middle_x - centres[i]))
            if tolerance is None or abs(line.middle_x - centres[nearest]) <= tolerance:
                columns[nearest].append(line)

    profile = {}
    for index, members in columns.items():
        if not members:
            continue
        numeric = sum(1 for line in members if _numeric_share(line.text) >= _NUMERIC_SHARE)
        units = sum(1 for line in members
                    if any(word in normalize(line.text) for word in _UNIT_WORDS))
        values = []
        for line in members:
            digits = re.sub(r"[^0-9]", "", normalize(line.text))
            if digits:
                values.append(int(digits))
        profile[index] = {
            "numeric_share": numeric / len(members),
            "unit_hits": units,
            "width": median([max(1.0, line.right - line.left) for line in members]),
            "typical": median(values) if values else 0,
            "count": len(members),
        }

    roles = {}
    unit_column = max((i for i, p in profile.items() if p["unit_hits"]),
                      key=lambda i: profile[i]["unit_hits"], default=None)
    if unit_column is not None:
        roles["unit"] = centres[unit_column]

    numeric = sorted((i for i, p in profile.items()
                      if p["numeric_share"] >= _NUMERIC_SHARE and i != unit_column),
                     key=lambda i: profile[i]["typical"], reverse=True)
    if len(numeric) >= 1:
        roles["amount"] = centres[numeric[0]]
    if len(numeric) >= 2:
        roles["unit_price"] = centres[numeric[1]]
    if len(numeric) >= 3:
        roles["quantity"] = centres[numeric[-1]]

    textual = [i for i, p in profile.items()
               if p["numeric_share"] < _NUMERIC_SHARE and i != unit_column]
    if textual:
        widest = max(textual, key=lambda i: profile[i]["width"])
        roles["name"] = centres[widest]
    return roles


#: Below this mean cell confidence the reconstruction is kept but its CELLS are not
#: offered as values. The rule the mission states: high confidence extracts a value,
#: medium offers a draft field, low keeps the raw text only.
LOW_CONFIDENCE = 0.55
MEDIUM_CONFIDENCE = 0.75

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


def confidence_band(score):
    """Which of the three bands a reconstruction falls in."""
    if score >= MEDIUM_CONFIDENCE:
        return CONFIDENCE_HIGH
    if score >= LOW_CONFIDENCE:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


class Table:
    """A reconstructed table: its header, its rows as `{role: text}`, and its confidence."""

    __slots__ = ("roles", "rows", "confidence", "page_kind", "header_row", "column_source")

    def __init__(self, roles, rows, confidence, page_kind, header_row,
                 column_source="header"):
        self.roles = roles
        self.rows = rows
        self.confidence = confidence
        self.page_kind = page_kind
        self.header_row = header_row
        #: `header` when a heading row named the columns, `inferred` when they were read
        #: off the body. A reviewer should know which: named columns are what the document
        #: says, inferred ones are what this code concluded.
        self.column_source = column_source

    @property
    def band(self):
        return confidence_band(self.confidence)

    @property
    def trustworthy(self):
        """Whether these cells may be offered as values at all.

        False keeps the reconstruction -- it is still evidence, and it still explains why
        no items were emitted -- while refusing to turn cells like `'ld'bdd` and `xl` into
        a product name and an amount on a financial draft.
        """
        return self.band != CONFIDENCE_LOW

    def as_dict(self):
        return {"roles": sorted(self.roles), "pageKind": self.page_kind,
                "rowCount": len(self.rows), "confidence": round(self.confidence, 4),
                "confidenceBand": self.band, "columnSource": self.column_source,
                "rows": self.rows}


def reconstruct(raw_lines):
    """A `Table` from positioned OCR lines, or None when the page has no table in it.

    None is a real answer and the common one on a summary page. The caller keeps the raw
    text either way -- nothing here replaces what the recogniser read, it only adds a
    reading of how it was arranged.
    """
    lines = lines_from(raw_lines)
    if not lines:
        return None
    rows = group_rows(lines)
    header_index, anchors = find_header(rows)
    kind = classify(rows, header_index, anchors)

    source = "header"
    if header_index is None or len(anchors) < 2:
        # No heading row was read. That is not the same as no table -- see
        # `cluster_columns`. The columns are inferred from the body and the body is every
        # row, since there is no header to skip.
        centres = cluster_columns(rows)
        anchors = infer_roles(rows, centres)
        if len(anchors) < 2:
            return None
        header_index, source = -1, "inferred"

    # A summary page has no line items by definition. Reconstructing one anyway turns a
    # totals block into a two-column "table" whose rows are headings paired with figures
    # -- which reads like item data and is not.
    if kind == SUMMARY_PAGE:
        return None

    body = []
    scores = []
    for row in rows[header_index + 1:]:
        cells = assign_columns(row, anchors)
        entry = {}
        for role, members in cells.items():
            if role is None:
                continue
            # Right to left within a cell: a description wrapped onto two detections is
            # read in the order a person reads it.
            members.sort(key=lambda item: -item.middle_x)
            entry[role] = " ".join(item.text for item in members).strip()
            scores.extend(item.confidence for item in members)
        if _is_line_item(entry):
            body.append(entry)
    if not body:
        return None
    confidence = (sum(scores) / len(scores)) if scores else 0.0
    header_row = ([] if header_index < 0
                  else [line.text for line in rows[header_index]])
    return Table(set(anchors), body, confidence, kind, header_row, source)


def _is_line_item(entry):
    """Whether a reconstructed row is a LINE ITEM rather than a fragment.

    A line item names something and says what it cost. A row carrying only a description
    is a wrapped continuation or a stray mark; a row carrying only a number is a page
    number or a total that belongs to the summary. Neither is an item, and admitting them
    is how a table of five real products becomes twenty-nine rows of noise.

    This is a STRUCTURAL test, not a confidence one. The two catch different things: a
    crisp scan can still produce rows that are not items, and a blurry one can produce
    items that are real but uncertain. Both gates apply.
    """
    if not entry:
        return False
    described = bool((entry.get("name") or "").strip())
    if not described:
        return False
    for role in ("amount", "unit_price"):
        value = entry.get(role) or ""
        if any(character.isdigit() for character in normalize(value)):
            return True
    return False


#: Why a page yielded no line items. A reviewer seeing an empty item list needs to know
#: whether the page was a summary, whether the table was unreadable, or whether nothing
#: was analysed at all -- three different situations that used to look identical.
NO_TABLE_SUMMARY = "summary_page"
NO_TABLE_NO_COLUMNS = "no_columns_found"
NO_TABLE_NO_ITEMS = "no_rows_looked_like_items"
NO_TABLE_EMPTY = "nothing_positioned"


def diagnose(raw_lines):
    """`(page_kind, reason)` for a page, whether or not a table came out of it.

    Always answerable, and cheap: the caller gets the page's classification even when
    `reconstruct` declined, so a draft can say WHY it carries no items instead of leaving
    a reviewer to guess between "this page has none" and "this page could not be read".

    `reason` is None exactly when a table was reconstructed.
    """
    lines = lines_from(raw_lines)
    if not lines:
        return UNKNOWN_PAGE, NO_TABLE_EMPTY
    rows = group_rows(lines)
    header_index, anchors = find_header(rows)
    kind = classify(rows, header_index, anchors)
    if kind == SUMMARY_PAGE:
        return kind, NO_TABLE_SUMMARY
    if header_index is None or len(anchors) < 2:
        if len(infer_roles(rows, cluster_columns(rows))) < 2:
            return kind, NO_TABLE_NO_COLUMNS
    return kind, (None if reconstruct(raw_lines) is not None else NO_TABLE_NO_ITEMS)


def columns_right_to_left(anchors):
    """Column roles in reading order for a Persian page: rightmost first."""
    return [role for role, _x in sorted(anchors.items(), key=lambda pair: -pair[1])]
