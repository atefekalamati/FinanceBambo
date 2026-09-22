# -*- coding: utf-8 -*-
"""Arithmetic a reader would do, done before the reader has to.

These checks never CORRECT anything. They compare numbers that a document states against
each other and report where the statement is internally inconsistent. Correcting would
mean deciding which of two stated numbers is the mistake, and that decision belongs to
whoever is reviewing the draft -- the document may be wrong, or the reading may be, and
this module cannot tell those apart.

WHAT IT CATCHES, AND WHY EACH ONE IS HERE

  * `quantity x unitPrice != totalPrice`. On the audited invoices this identity holds
    exactly -- row 13 is 511,727,000 x 3 = 1,535,181,000, row 15 is 25,000,000 x 8.7 =
    217,500,000 -- so a row that breaks it was misread. It is the single strongest signal
    available, because it needs no ground truth: the page checks itself.

  * a stated total that is not the sum of the stated rows. Weaker, and deliberately only
    a warning: real invoices carry tax, installation, discounts and rounding. The audited
    summary page adds 7% consumables and 6% installation and subtracts 15%, so a bare sum
    would be wrong there by design.

  * impossible dates. A Jalali year outside 1380..1410 is not a date on a construction
    invoice; a model produced 1442, which is 2063.

  * amounts far outside any plausible range, which is how a digit-insertion error
    presents: 317,453,000 read as 3,174,535,000.
"""

from decimal import Decimal, InvalidOperation

from .fusion import as_number, ascii_digits

#: Jalali years a real invoice can carry. 1380 is 2001, 1410 is 2031.
JALALI_MIN_YEAR = 1380
JALALI_MAX_YEAR = 1410

#: Absolute slack on the row identity, in rials -- deliberately sub-rial.
#:
#: It was a RELATIVE tolerance of 0.01%, and its own test caught what that meant: against
#: a row of 1,535,181,000 it silently accepted a discrepancy of 999 rial, because 999 is
#: 0.000065 of a billion. A percentage tolerance grows with the invoice, so the larger the
#: line the more it forgives -- precisely backwards for money.
#:
#: The audited invoices reconcile EXACTLY: 511,727,000 x 3 = 1,535,181,000, and
#: 25,000,000 x 8.7 = 217,500,000. Rials are whole, so anything from one rial upward is a
#: difference and not a rounding. The allowance that remains covers only the fractional
#: residue a decimal quantity can leave behind.
ARITHMETIC_TOLERANCE_IRR = Decimal("1")

#: A single line on a construction invoice above this is more likely a misread than a
#: purchase. The audited rows top out near 1.5 billion rial; a tenfold margin above that
#: flags digit insertion without flagging a genuinely large order.
IMPLAUSIBLE_LINE_IRR = 100_000_000_000


def _decimal(value):
    number = as_number(value)
    if number is None:
        return None
    try:
        return Decimal(str(number))
    except InvalidOperation:
        return None


def check_row_arithmetic(row):
    """`quantity x unitPrice == totalPrice`, when the row states all three.

    Returns None when it cannot be checked. That is not a pass -- it is the absence of a
    test, and saying so beats reporting a success nothing verified.
    """
    quantity = _decimal(row.get("quantity"))
    unit_price = _decimal(row.get("unitPrice"))
    total = _decimal(row.get("totalPrice"))
    if quantity is None or unit_price is None or total is None:
        return None
    expected = quantity * unit_price
    if expected == total:
        return {"check": "row_arithmetic", "ok": True,
                "expected": str(expected), "stated": str(total)}
    difference = abs(expected - total)
    within = difference < ARITHMETIC_TOLERANCE_IRR
    return {
        "check": "row_arithmetic",
        "ok": bool(within),
        "expected": str(expected),
        "stated": str(total),
        "difference": str(difference),
        # Rounding is tolerated and reported; a real mismatch demands a person.
        "requiresReview": not within,
        "message": ("مقدار × قیمت واحد با مبلغ کل این ردیف نمی‌خواند"
                    if not within else None),
    }


def check_total_against_rows(total_amount, rows):
    """The stated total against the sum of the stated rows.

    A warning, never a verdict. Invoices legitimately add tax and installation and
    subtract discounts -- the audited summary page does all three -- so a difference here
    means "worth a look", not "wrong".
    """
    stated = _decimal(total_amount)
    if stated is None:
        return None
    amounts = [_decimal(row.get("totalPrice")) for row in rows or []]
    amounts = [value for value in amounts if value is not None]
    if not amounts:
        return None
    summed = sum(amounts, Decimal(0))
    return {
        "check": "total_against_rows",
        "ok": summed == stated,
        "sumOfRows": str(summed),
        "statedTotal": str(stated),
        "difference": str(stated - summed),
        "requiresReview": summed != stated,
        "message": ("جمع ردیف‌ها با مبلغ کل اعلام‌شده برابر نیست؛ ممکن است مالیات، "
                    "نصب یا تخفیف در میان باشد" if summed != stated else None),
    }


def check_date(value):
    """A Jalali date that could belong to an invoice."""
    text = ascii_digits(value)
    if not text:
        return None
    digits = "".join(character if character.isdigit() else " " for character in text).split()
    if not digits or len(digits[0]) != 4:
        return None
    year = int(digits[0])
    plausible = JALALI_MIN_YEAR <= year <= JALALI_MAX_YEAR
    return {
        "check": "invoice_date",
        "ok": plausible,
        "year": year,
        "requiresReview": not plausible,
        "message": (None if plausible else
                    "سال %s برای یک فاکتور ممکن نیست" % year),
    }


def check_amount_plausible(value, label="amount"):
    """An amount large enough to be a misread rather than a purchase."""
    number = _decimal(value)
    if number is None:
        return None
    implausible = number < 0 or number > IMPLAUSIBLE_LINE_IRR
    return {
        "check": "amount_plausible",
        "field": label,
        "ok": not implausible,
        "value": str(number),
        "requiresReview": implausible,
        "message": (None if not implausible else
                    "مبلغ %s خارج از محدودهٔ باورپذیر است" % number),
    }


def validate(invoice, rows):
    """Every check this module can make about one reading, gathered.

    `invoice` is the header mapping and `rows` the line items. Nothing is modified; the
    return value is a report.
    """
    rows = list(rows or [])
    results = []

    for index, row in enumerate(rows):
        arithmetic = check_row_arithmetic(row)
        if arithmetic is not None:
            results.append(dict(arithmetic, row=index))
        plausible = check_amount_plausible(row.get("totalPrice"), "totalPrice")
        if plausible is not None and not plausible["ok"]:
            results.append(dict(plausible, row=index))

    total = check_total_against_rows((invoice or {}).get("totalAmount"), rows)
    if total is not None:
        results.append(total)

    date = check_date((invoice or {}).get("invoiceDate"))
    if date is not None and not date["ok"]:
        results.append(date)

    failed = [entry for entry in results if entry.get("requiresReview")]
    return {
        "checks": results,
        "checksRun": len(results),
        "failed": len(failed),
        "requiresReview": bool(failed),
    }
