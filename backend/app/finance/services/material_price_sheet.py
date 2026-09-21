# -*- coding: utf-8 -*-
"""The workbook, read against a contract it must satisfy before any row is believed.

Sits between `services/google_sheet.py`, which fetches bytes and judges nothing about
them, and `domain/material_price_rows.py`, which decides one row and knows nothing about
workbooks. This file is the part that says whether a worksheet is the worksheet we agreed
on -- and refuses the whole worksheet when it is not.

WHY A CONTRACT AND NOT A SNIFFER

A sheet that loses its `قیمت` column has not become a sheet with no prices. It has become
a sheet this code cannot read, and reading it anyway -- picking whichever column looks
numeric -- is how a delivery charge ends up stored as a material price. So each worksheet
declares the headers it must have, and a worksheet missing one is reported as an error
with the missing name in it. No row from that worksheet is imported.

The opposite mistake is just as easy: refusing the sheet because a NEW column appeared.
Extra columns are ignored, and a renamed optional column is simply an absent optional
column. Only a missing REQUIRED header stops a worksheet.

PARTIAL-SHEET PROTECTION

An import that read five worksheets and could not read the sixth is not a success. The
result says exactly which worksheets were read, which were refused and why, and the
caller decides -- it is not this file's place to publish half a price set.
"""

from dataclasses import dataclass, field

from ..domain.material_price_rows import (SOURCE_UNIT_HEADERS, RowStatus,
                                          decide_row)

#: Present in every one of the seven worksheets, measured. A worksheet missing any of these
#: is not importable: without an identifier there is nothing to attach a price to, and
#: without the date column there is nothing to order two observations by.
REQUIRED_HEADERS = ("source", "محصول", "قیمت", "تاریخ آپدیت ورک فلو", "productId")

# The current Google Sheet publishes English field names. The importer keeps the domain
# parser's Persian vocabulary as the canonical internal shape and maps aliases at the
# workbook boundary, so row rules and repository writes do not need a parallel model.
HEADER_ALIASES = {
    "source": ("source",),
    "محصول": ("محصول", "productName"),
    "قیمت": ("قیمت", "price"),
    "تاریخ آپدیت ورک فلو": ("تاریخ آپدیت ورک فلو", "workflowUpdateDate"),
    "productId": ("productId",),
    "واحد": ("واحد", "unit"),
    "واحد - وزن": ("واحد - وزن",),
}

HEADER_BY_ALIAS = {
    alias: canonical for canonical, aliases in HEADER_ALIASES.items() for alias in aliases
}


#: Category-specific columns, kept verbatim as attributes. All optional: brick states no
#: weight on 94 of its 213 rows and channel none on 38 of 56, and an absent attribute is
#: absent rather than an error.
ATTRIBUTE_HEADERS = ("وزن", "وزن - کیلوگرم", "طول", "ضخامت", "ابعاد",
                     "تعداد شاخه", "کد", "واحد - وزن", "قیمت در هر مترمربع")

#: The worksheets this importer will read, by title, with the gid they had when the
#: contract was written. An allowlist rather than "whatever the workbook contains": a new
#: worksheet appearing in the sheet is a change somebody should look at before its rows
#: become prices, not something to be swept up automatically.
WORKSHEET_ALLOWLIST = {
    "steel - I-beam": "0",
    "Angle iron-table": "829293631",
    "Channel_table": "167972751",
    "Hollow structural section_table": "1661528420",
    "Pipe-table": "1733863259",
    "steel -Rebar": "1257722300",
    "brick": "263140545",
}

WORKSHEET_ALIASES = {
    "steel - I-beam": ("steel - I-beam", "I-beam", "I beam", "تیرآهن"),
    "Angle iron-table": ("Angle iron-table", "Angle iron", "Angle", "نبشی"),
    "Channel_table": ("Channel_table", "Channel table", "Channel", "ناودانی"),
    "Hollow structural section_table": (
        "Hollow structural section_table",
        "Hollow structural section",
        "HSS",
        "قوطی",
        "پروفیل",
    ),
    "Pipe-table": ("Pipe-table", "Pipe", "pipe", "لوله"),
    "steel -Rebar": ("steel -Rebar", "steel - Rebar", "Rebar", "میلگرد"),
    "brick": ("brick", "Brick", "آجر"),
}

WORKSHEET_BY_ALIAS = {
    alias.casefold(): canonical
    for canonical, aliases in WORKSHEET_ALIASES.items()
    for alias in aliases
}


class SheetContractError(Exception):
    """The workbook is not the workbook this importer agreed to read."""


@dataclass
class WorksheetResult:
    """What became of one worksheet. A refused worksheet has rows=() and a reason."""

    title: str
    read: bool
    reason: str | None = None
    source_title: str | None = None
    gid: str | None = None
    headers: tuple = ()
    rows: tuple = ()

    @property
    def accepted(self):
        return tuple(row for row in self.rows if row.status == RowStatus.ACCEPTED)

    @property
    def rejected(self):
        return tuple(row for row in self.rows if row.status == RowStatus.REJECTED)


@dataclass
class WorkbookResult:
    """Every worksheet's outcome, and whether the workbook as a whole may be published."""

    worksheets: tuple = ()
    unknown_titles: tuple = ()
    missing_titles: tuple = ()

    @property
    def refused(self):
        return tuple(w for w in self.worksheets if not w.read)

    @property
    def complete(self) -> bool:
        """Every allowlisted worksheet present and readable, and none of them empty.

        Emptiness counts: a worksheet that came back with no rows is the shape a sheet has
        while somebody is editing it, and publishing that would erase a price set for a
        reason nobody chose.
        """
        return (not self.refused and not self.missing_titles
                and all(w.rows for w in self.worksheets))

    @property
    def all_rows(self):
        return tuple(row for w in self.worksheets for row in w.rows)


def read_headers(header_row) -> tuple:
    """The header row as text, with blank trailing cells dropped.

    The real export pads every worksheet out to 25 or 26 columns with `None`. Those are not
    columns and must not be counted as unnamed ones.
    """
    headers = []
    for cell in header_row or ():
        text = None if cell is None else str(cell).strip()
        headers.append(text or None)
    while headers and headers[-1] is None:
        headers.pop()
    return tuple(headers)


def _canonical_header(header):
    return HEADER_BY_ALIAS.get(header, header)


def canonical_headers(headers):
    return tuple(_canonical_header(header) if header else header for header in headers)


def check_headers(title: str, headers) -> str | None:
    """`None` if the worksheet may be read, otherwise why it may not.

    Duplicates are refused too: two columns both called `قیمت` make the row dictionary
    depend on which one is read last, which is a coin toss deciding a price.
    """
    canonical = canonical_headers(headers)
    named = [h for h in canonical if h]
    if not named:
        return "worksheet %r has no header row" % title
    duplicates = sorted({h for h in named if named.count(h) > 1})
    if duplicates:
        return "worksheet %r repeats the column(s) %s" % (title, ", ".join(duplicates))
    missing = [h for h in REQUIRED_HEADERS if h not in named]
    if missing:
        return ("worksheet %r is missing the required column(s) %s"
                % (title, ", ".join(missing)))
    # The unit is optional source evidence. An absent unit must survive as an unknown
    # basis; downstream calculation refuses to convert it to a project unit.
    present = [h for h in SOURCE_UNIT_HEADERS if h in named]
    if len(present) > 1:
        return ("worksheet %r states the pricing unit twice (%s)"
                % (title, ", ".join(present)))
    return None


def read_worksheet(title: str, rows, *, source_title=None, gid=None) -> WorksheetResult:
    """One worksheet's rows, decided -- or one refusal covering all of them."""
    body = [row for row in rows]
    while body and all(c is None or str(c).strip() == "" for c in body[-1]):
        body.pop()
    if not body:
        return WorksheetResult(title=title, source_title=source_title or title, gid=gid,
                               read=False, reason="worksheet %r is empty" % title)

    headers = read_headers(body[0])
    problem = check_headers(title, headers)
    if problem:
        return WorksheetResult(title=title, source_title=source_title or title, gid=gid,
                               read=False, reason=problem, headers=headers)
    internal_headers = canonical_headers(headers)

    decided = []
    for number, raw in enumerate(body[1:], start=2):
        if all(c is None or str(c).strip() == "" for c in raw):
            continue  # a blank spacer row is not a rejected row
        cells = {h: (raw[i] if i < len(raw) else None)
                 for i, h in enumerate(internal_headers) if h}
        decided.append(decide_row(worksheet=title, row_number=number, cells=cells,
                                  attribute_columns=_attribute_headers(internal_headers)))
    if not decided:
        return WorksheetResult(title=title, source_title=source_title or title, gid=gid,
                               read=False, headers=headers,
                               reason="worksheet %r has a header but no data rows" % title)
    return WorksheetResult(title=title, source_title=source_title or title, gid=gid,
                           read=True, headers=headers, rows=tuple(decided))


def _attribute_headers(headers):
    """Every non-contract column is metadata, with known attribute columns included."""
    common = set(REQUIRED_HEADERS) | set(SOURCE_UNIT_HEADERS)
    return tuple(header for header in headers if header and header not in common)


def read_workbook(sheets: dict) -> WorkbookResult:
    """`{title: rows}` in, every worksheet's outcome out.

    `sheets` is a plain mapping so this file never imports openpyxl and can be tested with
    literal rows. Titles outside the allowlist are reported, not read: a new worksheet is a
    change to look at, not rows to sweep up.
    """
    results = []
    unknown = []
    seen = set()
    for title, rows in sheets.items():
        canonical = WORKSHEET_BY_ALIAS.get(title.casefold())
        if canonical is None:
            unknown.append(title)
            continue
        if canonical in seen:
            results.append(WorksheetResult(
                title=canonical, source_title=title, gid=WORKSHEET_ALLOWLIST.get(canonical),
                read=False, reason="worksheet %r duplicates %r" % (title, canonical)))
            continue
        seen.add(canonical)
        results.append(read_worksheet(canonical, rows, source_title=title,
                                      gid=WORKSHEET_ALLOWLIST.get(canonical)))
    missing = tuple(sorted(set(WORKSHEET_ALLOWLIST) - seen))
    return WorkbookResult(worksheets=tuple(results), unknown_titles=tuple(sorted(unknown)),
                          missing_titles=missing)


def workbook_from_xlsx(content: bytes) -> dict:
    """`{title: [row, ...]}` from workbook bytes. The only place openpyxl is touched.

    Read-only and values-only: no formula is evaluated, and a cell holding a formula yields
    its last cached value or nothing. A spreadsheet must not be able to make this process
    compute anything.
    """
    import io

    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    try:
        return {title: [tuple(row) for row in workbook[title].iter_rows(values_only=True)]
                for title in workbook.sheetnames}
    finally:
        workbook.close()
