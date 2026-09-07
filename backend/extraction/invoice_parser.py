# -*- coding: utf-8 -*-
"""Recognised invoice text turned into structured candidate fields, deterministically.

Everything this module produces is a CANDIDATE for a human to confirm. It never creates an
invoice, never confirms a draft, and never repairs a number it is unsure about. When the
text does not support a field, the field is absent and the reason is a warning -- because a
reviewer can act on "I could not read the total" and cannot act on a total that is quietly
wrong.

THE THREE REFUSALS
  * It does not infer digits. `135,00,0` is not `135,000,000`: the grouping is broken, so
    the value is reported as AMBIGUOUS evidence and never as a total. A clean, independent
    `TOTAL: 135,000,000 IRR` on another line is what the total comes from.
  * It does not derive one field from others. Quantity and total without a unit price gives
    quantity and total. Dividing would put a number nobody wrote on an invoice.
  * It does not infer currency from magnitude. A large number is not evidence of rials.
    Currency comes from a currency word, or it is absent.

WHY THE TABLE IS READ BY COLUMN ORDER, NOT BY LINE
OCR flattens a ruled table into reading order, so one visual row arrives as several lines:

    مبلغ كل / قيمت واحد / واحد / تعداد / شرح كالا      <- the header row, right to left
    50,000,000 / 5,000,000 / مترمكعب / 10 / بتن آماده  <- one item, same order

A single-line regex cannot see that. This parser finds the header sequence, learns the
column ORDER from it, and then reads the following cells in blocks of that width. The header
row is the evidence that the order is what it thinks; without a header block it reports no
items rather than guessing which number was a price.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from .parsing import CURRENCIES, UNITS, find_unit, normalize, to_decimal

#: How sure the PARSER is about a field. Deliberately not the recogniser's confidence:
#: OCR can be certain about characters that spell an unreadable number.
EXACT = "EXACT"
AMBIGUOUS = "AMBIGUOUS"
NOT_FOUND = "NOT_FOUND"

TOTAL_MATCH = "TOTAL_MATCH"
TOTAL_MISMATCH = "TOTAL_MISMATCH"
TOTAL_UNVERIFIABLE = "TOTAL_UNVERIFIABLE"

#: A number whose thousands groups are well formed: `1`, `135`, `135,000,000`. Anything
#: else -- `135,00,0` -- is a misread, not a number.
_WELL_GROUPED = re.compile(r"^\d{1,3}(,\d{3})*$")
_PLAIN_DIGITS = re.compile(r"^\d+$")
_NUMBER_TOKEN = re.compile(r"\d[\d,]*")

#: Column headers as Iranian invoices write them, mapped to the role each column plays.
#: Matched by containment because OCR glues neighbours together ("مبلغ كلريال").
_HEADERS = (
    ("قیمت واحد", "unit_price"),
    ("بهای واحد", "unit_price"),
    ("مبلغ کل", "amount"),
    ("جمع مبلغ", "amount"),
    ("شرح کالا", "name"),
    ("شرح", "name"),
    ("تعداد", "quantity"),
    ("مقدار", "quantity"),
    ("واحد", "unit"),
)

_LABELS = {
    "invoice_number": ("invoice no", "invoice number", "شماره فاکتور", "شماره فاكتور",
                       "سریال فاکتور"),
    "invoice_date": ("date", "تاریخ", "تاريخ"),
    "supplier_name": ("فروشنده", "تامین کننده", "تأمین کننده", "seller", "supplier"),
    "buyer_name": ("خریدار", "خريدار", "buyer", "customer"),
    "total": ("total", "جمع کل", "مبلغ کل", "قابل پرداخت", "مبلغ نهایی", "جمع"),
}

_JALALI_DATE = re.compile(r"\b(1[34]\d{2})[/\-](\d{1,2})[/\-](\d{1,2})\b")


@dataclass(frozen=True)
class ParsedValue:
    """One candidate field: what was read, the text it came from, how sure the parse is."""

    value: Any = None
    evidence: Optional[str] = None
    certainty: str = NOT_FOUND

    @property
    def found(self):
        return self.certainty == EXACT and self.value is not None


@dataclass(frozen=True)
class ParsedItem:
    name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    evidence: Optional[str] = None
    warnings: tuple = ()


@dataclass
class StructuredInvoiceParseResult:
    invoice_number: ParsedValue = field(default_factory=ParsedValue)
    invoice_date: ParsedValue = field(default_factory=ParsedValue)
    supplier_name: ParsedValue = field(default_factory=ParsedValue)
    buyer_name: ParsedValue = field(default_factory=ParsedValue)
    items: list = field(default_factory=list)
    total_amount: ParsedValue = field(default_factory=ParsedValue)
    currency: ParsedValue = field(default_factory=ParsedValue)
    warnings: list = field(default_factory=list)
    validation_status: str = TOTAL_UNVERIFIABLE

    def warn(self, code, message, evidence=None):
        entry = {"code": code, "message": message}
        if evidence:
            entry["evidence"] = evidence
        self.warnings.append(entry)


# --------------------------------------------------------------------------- numbers
def strict_amount(token):
    """A money figure, or `(None, reason)` when the digits do not form one.

    Separate from `parsing.to_decimal`, which strips separators and answers with whatever
    digits remain. That is right for a quantity cell and wrong for money: stripping the
    commas out of `135,00,0` yields a confident `135000` that the invoice never stated.
    """
    if token is None:
        return None, "empty"
    cleaned = normalize(str(token)).strip().rstrip(".,")
    cleaned = cleaned.replace("٬", ",").replace(" ", "")
    if not cleaned:
        return None, "empty"
    if _PLAIN_DIGITS.match(cleaned):
        return Decimal(cleaned), None
    if _WELL_GROUPED.match(cleaned):
        return Decimal(cleaned.replace(",", "")), None
    if any(ch.isdigit() for ch in cleaned):
        return None, "malformed_grouping"
    return None, "not_a_number"


def _first_number_token(line):
    match = _NUMBER_TOKEN.search(normalize(line))
    return match.group() if match else None


# ---------------------------------------------------------------------------- labels
def _label_value(line, labels):
    """The text after a label on this line, or None. The label proves the role."""
    lowered = normalize(line).lower()
    for label in labels:
        position = lowered.find(label.lower())
        if position < 0:
            continue
        rest = normalize(line)[position + len(label):]
        rest = rest.lstrip(" :：-–—\t")
        if rest.strip():
            return rest.strip()
    return None


def _labelled(lines, labels):
    for line in lines:
        value = _label_value(line, labels)
        if value:
            return value, line
    return None, None


# ----------------------------------------------------------------------------- table
def _header_roles(line):
    """The column roles this line names, in the order they appear.

    Longest label first, and each match consumes its span, so "قیمت واحد" is not also
    counted as "واحد" -- which would invent a unit column that is not there.
    """
    text = normalize(line)
    hits = []
    taken = []
    for label, role in sorted(_HEADERS, key=lambda pair: -len(pair[0])):
        start = 0
        while True:
            position = text.find(label, start)
            if position < 0:
                break
            span = (position, position + len(label))
            if not any(a < span[1] and span[0] < b for a, b in taken):
                taken.append(span)
                hits.append((position, role))
            start = position + 1
    return [role for _, role in sorted(hits)]


def _find_header_block(lines):
    """`(roles, index_after)` for the table header, or `(None, None)`.

    The header may be one line ("شرح کالا تعداد واحد قیمت واحد مبلغ کل") or one line per
    cell, which is what a flattened table looks like. Both are read the same way: collect
    roles from consecutive header-bearing lines until a line names none.
    """
    for start in range(len(lines)):
        roles = _header_roles(lines[start])
        if not roles:
            continue
        index = start + 1
        while index < len(lines):
            more = _header_roles(lines[index])
            if not more:
                break
            roles.extend(more)
            index += 1
        # A usable header names at least a description column and one money column.
        if "name" in roles and ("amount" in roles or "unit_price" in roles):
            deduped = []
            for role in roles:
                if role not in deduped:
                    deduped.append(role)
            return deduped, index
        return None, None
    return None, None


def _is_footer(line):
    text = normalize(line).lower()
    return any(word in text for word in ("total", "جمع کل", "جمع", "قابل پرداخت",
                                         "مهر", "امضا", "fixture"))


def _cell_kind(cell):
    """Whether a flattened cell reads as a number, a unit word, or a description."""
    text = normalize(cell).strip()
    if not text:
        return "empty"
    if _NUMBER_TOKEN.fullmatch(text.replace(" ", "")):
        return "number"
    unit, _word = find_unit(text)
    if unit and len(text) <= 12:
        return "unit"
    return "text"


def _parse_items(lines, roles, start, result):
    """Items read as fixed-width blocks in the header's own column order."""
    width = len(roles)
    cells = []
    for line in lines[start:]:
        if _is_footer(line):
            break
        if normalize(line).strip():
            cells.append(line.strip())
    items = []
    for offset in range(0, len(cells) - width + 1, width):
        block = cells[offset:offset + width]
        item, problem = _item_from_block(block, roles)
        if item is not None:
            items.append(item)
        else:
            result.warn("INVOICE_ROW_AMBIGUOUS",
                        "A table block did not match the column roles the header names, "
                        "so no item was created from it (%s)." % problem,
                        evidence=" | ".join(block))
    leftover = len(cells) % width
    if leftover and cells:
        result.warn("INVOICE_ROW_INCOMPLETE",
                    "%d cell(s) remained after the last complete row and were not read "
                    "as an item." % leftover,
                    evidence=" | ".join(cells[-leftover:]))
    return items


def _item_from_block(block, roles):
    values = dict(zip(roles, block))
    name = values.get("name")
    if not name or _cell_kind(name) == "number":
        return None, "the description cell is missing or numeric"
    quantity = to_decimal(values.get("quantity")) if "quantity" in values else None
    unit_price, price_problem = strict_amount(values.get("unit_price"))
    amount, amount_problem = strict_amount(values.get("amount"))
    if unit_price is None and amount is None:
        return None, "no readable money cell (%s/%s)" % (price_problem, amount_problem)
    unit_code, unit_word = (None, None)
    if "unit" in values:
        unit_code, unit_word = find_unit(values["unit"])
    warnings = []
    if quantity is not None and unit_price is not None and amount is not None:
        if quantity * unit_price != amount:
            warnings.append({
                "code": "INVOICE_ITEM_ARITHMETIC_MISMATCH",
                "message": "quantity x unitPrice does not equal the stated amount; both "
                           "values are reported as read.",
                "evidence": "%s x %s != %s" % (quantity, unit_price, amount)})
    return ParsedItem(name=normalize(name).strip(), quantity=quantity,
                      unit=unit_word or (values.get("unit") or "").strip() or None,
                      unit_price=unit_price, amount=amount,
                      evidence=" | ".join(block), warnings=tuple(warnings)), None


# --------------------------------------------------------------------------- currency
def _find_currency(lines, total_line):
    """Currency from an explicit word, preferring the line the total came from.

    Never from magnitude. If the document names two currencies the total's own wins and
    the other is kept as a warning, because a rial figure read as tomans is wrong by ten.
    """
    seen = []
    for line in lines:
        text = normalize(line)
        if re.search(r"\bIRR\b", text, re.I):
            seen.append(("IRR", "IRR", line))
        for word, code in CURRENCIES.items():
            if word in text:
                seen.append((code, word, line))
    if not seen:
        return ParsedValue(), []
    if total_line:
        for code, word, line in seen:
            if line == total_line:
                others = {c for c, _w, _l in seen} - {code}
                return ParsedValue(code, word, EXACT), sorted(others)
    codes = {code for code, _w, _l in seen}
    code, word, _line = seen[0]
    if len(codes) > 1:
        return ParsedValue(code, word, AMBIGUOUS), sorted(codes - {code})
    return ParsedValue(code, word, EXACT), []


# ------------------------------------------------------------------------------ total
def _find_total(lines, result):
    """The stated total: the best-supported clean figure, with the rest kept as evidence.

    A line whose number is malformed does not become the total, however clearly it is
    labelled. It is recorded so a reviewer sees that the document disagreed with itself.
    """
    candidates = []
    for line in lines:
        if not any(label in normalize(line).lower() for label in _LABELS["total"]):
            continue
        token = _first_number_token(line)
        if token is None:
            continue
        value, problem = strict_amount(token)
        candidates.append((value, problem, line.strip()))
    clean = [(value, line) for value, problem, line in candidates if value is not None]
    for value, problem, line in candidates:
        if value is None:
            result.warn("INVOICE_TOTAL_UNREADABLE",
                        "A total line was found but its digits do not form a number "
                        "(%s); it was not used." % problem, evidence=line)
    if not clean:
        return ParsedValue(), None
    distinct = {value for value, _line in clean}
    if len(distinct) > 1:
        result.warn("INVOICE_TOTAL_AMBIGUOUS",
                    "The document states more than one total; none was chosen.",
                    evidence=" | ".join(line for _value, line in clean))
        return ParsedValue(None, " | ".join(line for _v, line in clean), AMBIGUOUS), None
    value, line = clean[0]
    return ParsedValue(value, line, EXACT), line


# ------------------------------------------------------------------------------ parse
def parse_invoice(raw_text: str) -> StructuredInvoiceParseResult:
    """Structured candidates from recognised text. Pure: no IO, no clock, no randomness."""
    result = StructuredInvoiceParseResult()
    if not raw_text or not raw_text.strip():
        result.warn("INVOICE_TEXT_EMPTY", "No text was recognised, so no field was read.")
        return result
    lines = [line for line in normalize(raw_text).splitlines() if line.strip()]

    number, evidence = _labelled(lines, _LABELS["invoice_number"])
    if number:
        result.invoice_number = ParsedValue(number.split()[0], evidence.strip(), EXACT)

    date_value, date_evidence = None, None
    for line in lines:
        match = _JALALI_DATE.search(line)
        if match and any(label in normalize(line).lower()
                         for label in _LABELS["invoice_date"]):
            date_value, date_evidence = match.group(), line.strip()
            break
    if date_value:
        result.invoice_date = ParsedValue(date_value, date_evidence, EXACT)

    supplier, evidence = _labelled(lines, _LABELS["supplier_name"])
    if supplier:
        result.supplier_name = ParsedValue(supplier, evidence.strip(), EXACT)
    buyer, evidence = _labelled(lines, _LABELS["buyer_name"])
    if buyer:
        result.buyer_name = ParsedValue(buyer, evidence.strip(), EXACT)

    roles, after = _find_header_block(lines)
    if roles:
        result.items = _parse_items(lines, roles, after, result)
    else:
        result.warn("INVOICE_TABLE_NOT_RECOGNISED",
                    "No column header row was found, so no line items were read. The "
                    "recognised text is preserved for review.")

    result.total_amount, total_line = _find_total(lines, result)
    result.currency, other_currencies = _find_currency(lines, total_line)
    for code in other_currencies:
        result.warn("INVOICE_CURRENCY_ALTERNATIVE",
                    "The document also names %s; the total's own currency was used." % code)

    result.validation_status = _validate_total(result)
    return result


def _validate_total(result):
    amounts = [item.amount for item in result.items if item.amount is not None]
    if not result.total_amount.found:
        if amounts:
            result.warn("INVOICE_TOTAL_MISSING",
                        "Items were read but the document states no readable total, so "
                        "the sum could not be checked against one.")
        return TOTAL_UNVERIFIABLE
    if not amounts or len(amounts) != len(result.items):
        result.warn("INVOICE_TOTAL_UNCHECKED",
                    "A total was read but not every item states an amount, so the two "
                    "could not be reconciled.")
        return TOTAL_UNVERIFIABLE
    total = sum(amounts, Decimal(0))
    if total == result.total_amount.value:
        return TOTAL_MATCH
    result.warn("INVOICE_TOTAL_MISMATCH",
                "The items sum to %s but the document states %s. Both are reported as "
                "read; neither was adjusted." % (total, result.total_amount.value),
                evidence=result.total_amount.evidence)
    return TOTAL_MISMATCH
