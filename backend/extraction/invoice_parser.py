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
#: Both thousands separators an Iranian invoice actually uses, not just the one that has
#: "thousands separator" in its Unicode name. See `strict_amount`.
_NUMBER_TOKEN = re.compile(r"\d[\d,٬،]*")

#: Column headers as Iranian invoices write them, mapped to the role each column plays.
#: Matched by containment because OCR glues neighbours together ("مبلغ كلريال").
_HEADERS = (
    ("قیمت واحد", "unit_price"),
    ("بهای واحد", "unit_price"),
    ("قیمت", "unit_price"),
    ("مبلغ کل", "amount"),
    ("جمع مبلغ", "amount"),
    ("مبلغ", "amount"),
    ("جمع", "amount"),
    ("شرح کالا", "name"),
    ("شرح", "name"),
    ("کالا", "name"),
    ("محصول", "name"),
    ("تعداد", "quantity"),
    ("مقدار", "quantity"),
    ("واحد", "unit"),
)

#: Labels, by role. Two rules govern what may go in here.
#:
#: FIRST: no variant that differs only in Arabic vs Persian ي/ك. `normalize` folds those
#: before any comparison, so "تاريخ" and "تاریخ" are the same string by the time a label is
#: tried. The pairs that used to be listed here were dead weight that read as coverage.
#:
#: SECOND: no label so short that it names something else on the same document. A bare
#: "شماره" was asked for and is NOT here: the real invoice this was tested against
#: carries "شماره تماس", "شماره حساب" and "شماره شبا", and the bare label lifts a
#: PHONE NUMBER into `invoiceNumber` -- a wrong value that looks exactly like a right one
#: once it is sitting in a review form. The specific wordings are listed instead.
#:
#: Order does not matter here: `_label_value` tries the longest first, so "تاریخ فاکتور"
#: is never shadowed by "تاریخ".
_LABELS = {
    "invoice_number": ("invoice no", "invoice number", "invoice #", "شماره فاکتور",
                       "شماره صورتحساب", "شماره صورت حساب", "سریال فاکتور",
                       "شماره سند"),
    "invoice_date": ("تاریخ فاکتور", "تاریخ صدور", "تاریخ صورتحساب", "invoice date",
                     "date", "تاریخ"),
    # A bare "شرکت" was asked for here and is NOT included, for the same reason a bare
    # "شماره" is not included above, and this one was measured rather than guessed at:
    # adding it made the letterhead invoice report "شرکت توسعه بنا کیان" as the SUPPLIER,
    # and that company is the BUYER -- the parser's own `buyer_name` reads it from a real
    # label two lines away. "شرکت" heads the letterhead, the bank block and the signature
    # block, so it names whichever company printed the page rather than the one that sold
    # anything. A supplier nobody labelled stays empty; see
    # `test_a_seller_with_no_label_is_a_miss_not_a_guess`.
    "supplier_name": ("نام فروشنده", "نام تامین کننده", "تامین کننده", "تأمین کننده",
                      "فروشنده", "فروشگاه", "seller", "supplier", "vendor"),
    "buyer_name": ("نام خریدار", "طرف حساب", "خریدار", "مشتری", "buyer", "customer"),
    "total": ("مبلغ قابل پرداخت", "جمع قابل پرداخت", "قابل پرداخت",
              "جمع کل پس از تخفیف", "مبلغ نهایی", "grand total", "total",
              "جمع کل", "مبلغ کل", "جمع مبلغ", "جمع"),
    # New roles. The document states them and the contract names them; until now they were
    # read by nobody, so a reviewer retyped a tax figure that was sitting in the text.
    "tax": ("مالیات بر ارزش افزوده", "ارزش افزوده", "مالیات و عوارض", "مالیات",
            "vat", "tax"),
    "discount": ("تخفیف", "discount"),
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
    #: Stated on the document and, until now, read by nobody -- so a reviewer retyped a
    #: figure that was already in the text. Read by the same strict rule as every other
    #: money field: a malformed group is refused rather than repaired.
    tax_amount: ParsedValue = field(default_factory=ParsedValue)
    discount_amount: ParsedValue = field(default_factory=ParsedValue)
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
    cleaned = normalize(str(token)).strip().rstrip(".,،")
    # U+060C ARABIC COMMA and U+066C ARABIC THOUSANDS SEPARATOR both group digits on an
    # Iranian invoice and look identical in most fonts. Only the second was mapped, and the
    # recogniser emits the first -- so every grouped figure on a real invoice reached
    # `_WELL_GROUPED` still carrying a character it does not accept and was rejected as
    # malformed. Mapping happens BEFORE the grouping rule, never instead of it: `135,00,0`
    # is still refused, which is the whole reason this function is not `to_decimal`.
    cleaned = cleaned.replace("٬", ",").replace("،", ",").replace(" ", "")
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
    # Longest first. "تاریخ" is a prefix of "تاریخ فاکتور", and trying the short one first
    # matched it and handed back "فاکتور: 1404/06/22" -- the rest of the LABEL, read as the
    # value. Sorting here rather than asking every caller to order its own tuple correctly:
    # the requirement belongs to the matching, not to the vocabulary.
    for label in sorted(labels, key=len, reverse=True):
        position = lowered.find(label.lower())
        if position < 0:
            continue
        rest = normalize(line)[position + len(label):]
        rest = rest.lstrip(" :：-–—\t")
        if rest.strip():
            return rest.strip()
    return None


#: A line that is nothing but a number -- the shape a table cell has once OCR has put it
#: on a line of its own. Deliberately strict: a line with any other word on it is not a
#: bare value and must not be read as one.
_BARE_NUMBER_LINE = re.compile(r"^[\d][\d,٬،.‏ ]*$")


def _labelled(lines, labels):
    """The value a label introduces, from its own line or from the line below it.

    WHY THE LINE BELOW COUNTS

    OCR flattens a ruled table into reading order, so a label and its amount sitting in
    two cells of one visual row arrive as two lines:

        مبلغ کل قابل پرداخت      <- the label, alone
        566,500,000              <- its value, on the next line

    Reading only the label's own line loses that field entirely. On the audited
    letterhead invoice it lost the payable total -- the one number the whole document is
    about -- and reported INVOICE_TOTAL_MISSING while 566,500,000 sat one line away.

    WHY IT IS STILL NARROW

    The next line is read ONLY when the label's own line offers nothing after the label,
    and ONLY when that next line is nothing but a number. Both halves matter: a label
    followed by more prose is a sentence, not a table row, and a next line carrying words
    belongs to something else on the page. Anything looser starts attaching whatever
    happens to follow a label, which is how a parser that never invented a value begins
    inventing them.

    The evidence returned names BOTH lines, so a reviewer sees why the two were joined.
    """
    for index, line in enumerate(lines):
        # The label-only test comes FIRST, and it has to. `_label_value` returns whatever
        # follows the first label it finds, and on «مبلغ کل قابل پرداخت» that is
        # «قابل پرداخت» -- the rest of the heading, handed back as though it were a value.
        # Checking the same line first would therefore "succeed" with label text and never
        # look at the number underneath.
        if _line_is_only_a_label(line, labels):
            following = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if following and _BARE_NUMBER_LINE.match(normalize(following)):
                return following, "%s | %s" % (line.strip(), following)
            continue
        value = _label_value(line, labels)
        if value:
            return value, line
    return None, None


def _line_is_only_a_label(line, labels):
    """Whether this line is label text and nothing else.

    EVERY matching label is removed, not just the first. Real headings stack them:
    «مبلغ کل قابل پرداخت» is «مبلغ کل» AND «قابل پرداخت» end to end, and taking one away
    leaves the other -- so a check that stops at the first match decides the line still
    holds a value and declines to look at the row below it. That is what kept the payable
    total unread on the audited invoice.

    At least one label must match, so a line of ordinary prose is never mistaken for a
    heading waiting on a value.
    """
    text = normalize(line).strip()
    matched = False
    for label in sorted(labels, key=len, reverse=True):
        needle = label.lower()
        while needle in text.lower():
            position = text.lower().find(needle)
            text = text[:position] + text[position + len(label):]
            matched = True
    return matched and not text.strip(" :：-–—	")


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
    for index, line in enumerate(lines):
        if not any(label in normalize(line).lower() for label in _LABELS["total"]):
            continue
        token = _first_number_token(line)
        evidence = line.strip()
        if token is None:
            # The label is in a cell of its own and its amount is in the next one, which
            # OCR delivers as the following line. Same narrow rule as `_labelled`: the
            # label line must hold nothing but label text, and the next line nothing but
            # a number. On the audited letterhead invoice this is the difference between
            # reading the payable total and reporting INVOICE_TOTAL_MISSING with
            # 566,500,000 one line away.
            if not _line_is_only_a_label(line, _LABELS["total"]):
                continue
            following = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if not (following and _BARE_NUMBER_LINE.match(normalize(following))):
                continue
            token = _first_number_token(following)
            if token is None:
                continue
            evidence = "%s | %s" % (line.strip(), following)
        value, problem = strict_amount(token)
        candidates.append((value, problem, evidence))
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


def _labelled_amount(lines, labels, result, code):
    """One labelled money figure, or nothing. Never a repaired number.

    Deliberately simpler than `_find_total`: a tax line is not cross-checked against
    anything, so an unreadable one is reported and dropped rather than argued about. What
    it shares with the total is the rule that matters -- `strict_amount`, so a group the
    recogniser mangled into `20،55،000` is refused instead of becoming 20,550,000.

    More than one candidate means the document says it twice and this does not guess which:
    a tax figure chosen by position is a tax figure chosen by luck.
    """
    found = []
    for index, line in enumerate(lines):
        lowered = normalize(line).lower()
        if not any(label in lowered for label in labels):
            continue
        token = _first_number_token(line)
        evidence = line.strip()
        if token is None:
            if not _line_is_only_a_label(line, labels):
                continue
            following = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if not (following and _BARE_NUMBER_LINE.match(normalize(following))):
                continue
            token = _first_number_token(following)
            if token is None:
                continue
            evidence = "%s | %s" % (line.strip(), following)
        value, problem = strict_amount(token)
        if value is None:
            result.warn(code + "_UNREADABLE",
                        "A %s line was found but its digits do not form a number (%s); "
                        "it was not used." % (code.lower().replace("invoice_", ""), problem),
                        evidence=evidence)
            continue
        found.append((value, evidence))
    if not found:
        return ParsedValue()
    if len({value for value, _ in found}) > 1:
        result.warn(code + "_AMBIGUOUS",
                    "The document states more than one such amount; none was chosen.",
                    evidence=" | ".join(line for _v, line in found))
        return ParsedValue(None, " | ".join(line for _v, line in found), AMBIGUOUS)
    return ParsedValue(found[0][0], found[0][1], EXACT)


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
    result.tax_amount = _labelled_amount(lines, _LABELS["tax"], result, "INVOICE_TAX")
    result.discount_amount = _labelled_amount(lines, _LABELS["discount"], result,
                                              "INVOICE_DISCOUNT")
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
