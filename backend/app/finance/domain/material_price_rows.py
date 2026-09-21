# -*- coding: utf-8 -*-
"""One row of the material price sheet, turned into a decided record -- or into a refusal.

Pure: no network, no database, no clock. Everything it needs arrives as arguments, so every
rule below can be stated as a test without a sheet or a server in the room.

THE RULES THIS FILE EXISTS TO HOLD

  * A blank price is not zero. A price that cannot be parsed is not zero. Neither becomes a
    number at all -- the row comes back REJECTED with the reason attached, and the caller
    stores it as an invalid observation rather than dropping it.
  * Money is Decimal, never float, and Toman -> IRR is a multiplication by ten applied once.
    The sheet's 1993 prices are all integers, so the result is always an integer and the
    repository's integer-IRR rule holds without any rounding decision being made here.
  * The category comes from the productId PREFIX, not from the worksheet title. A worksheet
    can be renamed; the prefix is part of the data.
  * A date that cannot be read stays unread. Eight spellings of the workflow date were
    measured in the real sheet, including cells Google had already turned into Gregorian
    datetimes; anything outside those shapes is `None`, never today.
  * The sheet's unit is recorded as what the sheet said. It is never promoted to the unit a
    price is displayed in -- that is a decision an authorised person makes elsewhere.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .persian_calendar import persian_to_gregorian

#: The commercial unit a price is PER, under both spellings the workbook uses for it.
#:
#: This is one concept with two headings, and reading only one of them is why six of the
#: seven worksheets imported with no pricing unit at all. Counted on the live workbook:
#: `واحد` heads the column on I-beam, Angle, Channel, Hollow, Pipe and brick;
#: `واحد - وزن` heads it on Rebar alone. The importer asked for the second name only,
#: so Rebar was the only worksheet whose unit survived -- 1,244 listings out of 6,579.
#:
#: The Rebar heading is also the misleading one: `واحد - وزن` reads as "unit - weight",
#: but the column holds `عدد` on Pipe and on brick. It is not a weight. It is what one
#: unit of price buys, which is exactly what `source_unit` means.
#:
#: It lives in the domain because the row decision is what needs it; the sheet service
#: imports it from here to require the column, rather than the other way round.
SOURCE_UNIT_HEADERS = ('واحد', 'واحد - وزن')

#: Toman -> IRR. One place, applied once, and never mixed with a unit conversion.
TOMAN_TO_IRR = Decimal(10)

#: Persian and Arabic-Indic digits, to their ASCII counterparts. The sheet is written by
#: people and both families appear in it; API payloads and stored values use ASCII only.
_DIGITS = {ord(c): str(i % 10) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")}

#: What each productId prefix means. Measured from the sheet: every one of the 1993 rows
#: carries one of these. The worksheet a row came from is recorded separately and is not
#: what decides this.
CATEGORY_BY_PREFIX = {
    # Two spellings of one category. The sheet used to emit `IBEAM-...` and now emits
    # `I_BEAM-...`; both are listed because the older identifiers are what 601 already
    # imported listings are keyed on, and dropping the old name would orphan every one of
    # them while the new one would still be refused. Measured on the live workbook:
    # 104 of 104 I-beam rows carry `I_BEAM`, and every one was being rejected as an
    # unknown category -- the whole worksheet, for a missing underscore.
    "IBEAM": "ibeam",
    "I_BEAM": "ibeam",
    "ANGLE": "angle",
    "CHANNEL": "channel",
    "PROFILE": "profile",
    "PIPE": "pipe",
    "REBAR": "rebar",
    "BRICK": "brick",
}

#: Inside the pipe worksheet, 992 of 1072 rows are pipes and 80 are not. The split is by
#: the first word of the product name, and it is exact: those eleven words cover every row.
#: Listed as what a pipe IS rather than what it is not, so a new kind of fitting appearing
#: in the sheet is excluded by default instead of silently joining the pipe list.
PIPE_NAME_PREFIX = "لوله"

#: The category a non-pipe row in the pipe worksheet is given. It is imported and kept --
#: the raw history is never edited -- and it is not part of the active pipe list.
PIPE_FITTING_CATEGORY = "pipe_fitting"


class RowStatus:
    """What became of one row. `REJECTED` still gets stored; it is not a dropped row."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MaterialPriceRow:
    """A sheet row after the rules have been applied to it.

    `price_irr` is `None` whenever the price could not be read. That is the whole point of
    the type: there is no code path here that produces a zero for a missing number.
    """

    status: str
    worksheet: str
    row_number: int
    source: str | None
    product_id: str | None
    product_name: str | None
    category: str | None
    raw_price: str | None
    price_irr: Decimal | None
    source_unit: str | None
    workflow_date_raw: str | None
    workflow_date_jalali: str | None
    workflow_date_gregorian: date | None
    secondary_price_irr: Decimal | None = None
    secondary_price_basis: str | None = None
    attributes: dict = field(default_factory=dict)
    reasons: tuple = ()

    @property
    def accepted(self) -> bool:
        return self.status == RowStatus.ACCEPTED


def normalize_digits(value) -> str:
    """Persian and Arabic digits to ASCII. Everything else is left exactly as it is."""
    return str(value).translate(_DIGITS)


def parse_price_toman(value) -> tuple[Decimal | None, str | None]:
    """`(amount, reason_it_failed)`. Never both, and never a zero standing in for a blank.

    Decimal throughout, and built from a STRING even when openpyxl hands over a float: a
    float already carries whatever the binary representation made of the number, and
    `Decimal(str(x))` is the only way to get back what was written rather than what was
    stored.
    """
    if value is None:
        return None, "price is blank"
    text = normalize_digits(value).strip()
    if not text:
        return None, "price is blank"
    # Thousands separators, both the ASCII and the Persian one, and a stray currency word.
    text = text.replace(",", "").replace("٬", "").replace("،", "")
    text = text.replace("تومان", "").replace("ریال", "").strip()
    if not text:
        return None, "price is blank"
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "price is not a number: %r" % str(value)[:40]
    if not amount.is_finite():
        return None, "price is not a finite number"
    if amount <= 0:
        return None, "price is not positive: %s" % amount
    return amount, None


def to_irr(toman: Decimal) -> Decimal:
    """Toman -> IRR, once. Kept apart from every unit conversion on purpose.

    The result must be a whole number of rials: the repository stores money as integer IRR
    and rejects a fractional form, so a source price with sub-rial precision is a refusal
    here rather than a rounding decision made quietly.
    """
    amount = toman * TOMAN_TO_IRR
    if amount != amount.to_integral_value():
        raise ValueError("a price of %s Toman is not a whole number of rials" % toman)
    return amount.to_integral_value()


def category_for(product_id: str | None, worksheet: str, product_name: str | None):
    """`(category, reason_it_failed)` -- from the identifier, then narrowed by the name.

    The prefix decides the category. The product NAME is consulted for one thing only: a row
    in the pipe worksheet whose name does not begin with «لوله» is a fitting, not a pipe.
    That is not fuzzy matching to a Finance resource -- it is reading which list of the
    sheet's own a row belongs on, and the sheet offers nothing else to read it from.
    """
    if not product_id or not str(product_id).strip():
        return None, "productId is blank"
    prefix = str(product_id).strip().split("-", 1)[0].upper()
    category = CATEGORY_BY_PREFIX.get(prefix)
    if category is None:
        return None, "productId prefix %r is not a known category" % prefix
    if category == "pipe":
        name = (product_name or "").strip()
        if not name.startswith(PIPE_NAME_PREFIX):
            return PIPE_FITTING_CATEGORY, None
    return category, None


def parse_workflow_date(value):
    """`(raw, jalali_text, gregorian_date)`. Any of the last two may be `None`.

    Eight spellings were measured in the real sheet. Rather than a regular expression that
    would quietly accept a ninth, this accepts exactly what was seen:

      * a real datetime, which Google produced for 279 rows -- already Gregorian;
      * three numbers separated by `/` or `-`, in Persian or ASCII digits, padded or not,
        read as Jalali when the year is a plausible Jalali year.

    Anything else keeps its raw text and reports no date. A date this cannot read is not
    today, and is not the date of the row above it.
    """
    if value is None:
        return None, None, None
    if isinstance(value, datetime):
        return value.isoformat(sep=" "), None, value.date()
    if isinstance(value, date):
        return value.isoformat(), None, value
    raw = str(value).strip()
    if not raw:
        return None, None, None
    text = normalize_digits(raw).replace("-", "/")
    parts = [p for p in text.split("/") if p != ""]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return raw, None, None
    year, month, day = (int(p) for p in parts)
    # A Jalali year in this system is four digits and in the 1300-1500 range. A Gregorian
    # year would be 19xx/20xx; treating one as the other silently is exactly the mistake
    # this refuses to make.
    if not (1300 <= year <= 1500):
        return raw, None, None
    jalali = "%04d/%02d/%02d" % (year, month, day)
    try:
        gregorian = persian_to_gregorian(year, month, day)
    except (ValueError, OverflowError):
        return raw, jalali, None
    return raw, jalali, gregorian


def decide_row(*, worksheet: str, row_number: int, cells: dict,
               attribute_columns=()) -> MaterialPriceRow:
    """One sheet row in, one decided record out.

    `cells` is the row keyed by the sheet's own header text. Nothing here reaches for a
    column that was not handed over, and a missing optional column is simply absent rather
    than an error -- the header check that decides whether a worksheet is importable at all
    happens before this, against the contract, not row by row.
    """
    reasons = []
    source = _text(cells.get("source"))
    product_id = _text(cells.get("productId"))
    product_name = _text(cells.get("محصول"))

    category, category_reason = category_for(product_id, worksheet, product_name)
    if category_reason:
        reasons.append(category_reason)
    if not product_name:
        reasons.append("product name is blank")
    if not source:
        reasons.append("source is blank")

    toman, price_reason = parse_price_toman(cells.get("قیمت"))
    price_irr = None
    if price_reason:
        reasons.append(price_reason)
    else:
        try:
            price_irr = to_irr(toman)
        except ValueError as exc:
            reasons.append(str(exc))

    secondary_irr = None
    secondary_basis = None
    if "قیمت در هر مترمربع" in cells:
        secondary_toman, secondary_reason = parse_price_toman(cells.get("قیمت در هر مترمربع"))
        if secondary_toman is not None and secondary_reason is None:
            try:
                secondary_irr = to_irr(secondary_toman)
                secondary_basis = "square_meter"
            except ValueError:
                # The secondary price failing does not reject the row. It is a second
                # figure, and losing it must not cost the primary price its record.
                secondary_irr = None

    raw_date, jalali, gregorian = parse_workflow_date(cells.get("تاریخ آپدیت ورک فلو"))
    if raw_date is None:
        reasons.append("workflow date is blank")
    elif gregorian is None:
        # THE CELL SAID SOMETHING AND IT WAS NOT A DATE.
        #
        # «1405/13/40», «فردا», «1405-07-31» (month 7 has 30 days) and «1405-12-30» (1405
        # is not a leap year) all reach here: `parse_workflow_date` hands back the raw text
        # so it survives as evidence, and no Gregorian date, because there is none to give.
        #
        # This used to be ACCEPTED, and the row was then written with `validation_status =
        # 'valid'` and a null `workflow_date_gregorian`. Two things were wrong with that.
        # A price that cannot say which day it is for is not a price anybody may use, and
        # since 0027 the database agrees: `price_observations_valid_row_has_business_date`
        # refuses exactly that row -- so a single unreadable cell in a sheet of two
        # thousand would abort the whole import instead of costing one row.
        #
        # Rejecting is the honest answer and the working one. The raw text is kept, the
        # reason names it, and the row is findable on `/invalid-rows`. What must NEVER
        # happen is the alternative that makes the constraint pass: substituting
        # `fetched_at` or today, which would state a business date nobody quoted.
        reasons.append("workflow date is not a date: %s" % raw_date)

    # The pricing unit, under whichever heading this worksheet gives it. Read here rather
    # than by one hard-coded name: the two spellings are one column, and asking for the
    # Rebar one alone left six worksheets priced per nothing.
    source_unit = None
    for heading in SOURCE_UNIT_HEADERS:
        if heading in cells:
            source_unit = _text(cells.get(heading))
            if source_unit:
                break
    # An omitted unit is retained as unknown source evidence. Unit-sensitive project
    # calculations remain unresolved until the commercial pricing basis is known.

    attributes = {}
    for column in attribute_columns:
        if column in cells:
            attributes[column] = _text(cells.get(column))

    return MaterialPriceRow(
        status=RowStatus.REJECTED if reasons else RowStatus.ACCEPTED,
        worksheet=worksheet,
        row_number=row_number,
        source=source,
        product_id=product_id,
        product_name=product_name,
        category=category,
        raw_price=None if cells.get("قیمت") is None else normalize_digits(cells["قیمت"]).strip(),
        price_irr=price_irr,
        source_unit=source_unit,
        workflow_date_raw=raw_date,
        workflow_date_jalali=jalali,
        workflow_date_gregorian=gregorian,
        secondary_price_irr=secondary_irr,
        secondary_price_basis=secondary_basis,
        attributes=attributes,
        reasons=tuple(reasons),
    )


def _text(value):
    """A trimmed string, or `None`. An empty cell is absent, not an empty string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
