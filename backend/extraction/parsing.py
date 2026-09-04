# -*- coding: utf-8 -*-
"""Turning recognised Persian text into candidate invoice fields.

Everything here is a *candidate*. A human confirms each field before it becomes money, and
this module is written on the assumption that it will sometimes be wrong -- so it is wrong in
the visible direction. It reports what it found and stays silent about what it did not.

THREE THINGS IT WILL NOT DO
  * derive a missing value from the ones it has. Given a quantity and a total but no unit
    price, it reports the quantity and the total. Dividing would produce a confident number
    nobody wrote down, and a reviewer has no way to tell a read price from a computed one;
  * pick between two readings. Two plausible totals means neither is reported as *the* total;
    both are reported, and the reviewer chooses;
  * convert a currency. A number written next to ریال and a number written next to تومان
    differ by a factor of ten, and guessing which the writer meant is how an invoice becomes
    wrong by an order of magnitude. The unit is reported as read.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

#: Persian and Arabic-Indic digits, mapped to ASCII. OCR returns whichever the document used.
_DIGITS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})

#: Unit words as they are actually written on Iranian construction invoices, mapped to the
#: unit codes the finance module uses. Spelling variants are listed rather than stemmed:
#: a stemmer that turned "متر" into "m" would also turn "مترمربع" into "m".
UNITS = {
    "کیلوگرم": "kg", "کيلوگرم": "kg", "کیلو": "kg", "کgr": "kg", "kg": "kg",
    "تن": "ton", "ton": "ton",
    "مترمکعب": "m3", "متر مکعب": "m3", "مترمكعب": "m3", "m3": "m3",
    "مترمربع": "m2", "متر مربع": "m2", "مترمربع.": "m2", "m2": "m2",
    "مترطول": "m", "متر طول": "m", "متر": "m", "m": "m",
    "عدد": "each", "دستگاه": "each", "اصله": "each", "حلقه": "each", "each": "each",
    "کیسه": "bag", "پاکت": "bag",
    "لیتر": "litre", "ليتر": "litre",
    "ساعت": "hour", "نفرساعت": "person_hour", "نفر ساعت": "person_hour",
}

CURRENCIES = {"ریال": "IRR", "ريال": "IRR", "تومان": "IRT", "تومن": "IRT"}

_QUANTITY_WORDS = ("مقدار", "تعداد", "حجم", "وزن", "کمیت")
_TOTAL_WORDS = ("جمع کل", "جمع", "مبلغ کل", "قابل پرداخت", "مبلغ نهایی", "جمع مبلغ")
_UNIT_PRICE_WORDS = ("قیمت واحد", "فی", "بهای واحد", "نرخ واحد", "قيمت واحد")
_VENDOR_WORDS = ("فروشنده", "تامین کننده", "تأمین کننده", "شرکت", "فروشگاه")
_DATE_WORDS = ("تاریخ", "تاريخ")
_NUMBER_WORDS = ("شماره فاکتور", "شماره", "سریال")

_NUMBER = re.compile(r"\d[\d,٬\.٫]*")
_JALALI = re.compile(r"\b(1[34]\d{2})[/\-](\d{1,2})[/\-](\d{1,2})\b")


def normalize(text: str) -> str:
    """Persian text in one shape, so a match does not depend on which keyboard typed it.

    Arabic ي and ك are folded to Persian ی and ک: the two look identical in most fonts and
    an invoice is as likely to contain one as the other, so matching only one would depend on
    the vendor's keyboard layout.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("‌", " ").replace("‏", "").replace("‎", "")
    return re.sub(r"[ \t]+", " ", text)


def to_decimal(token: str):
    """A number as written on an invoice, or None. Never a float.

    Handles both thousands conventions -- `1,250,000` and `1٬250٬000` -- and the Persian
    decimal separator. A trailing `.` or `,` is dropped: OCR frequently reads the end of a
    ruled cell as punctuation.
    """
    if token is None:
        return None
    cleaned = normalize(str(token)).strip().rstrip(".,")
    cleaned = cleaned.replace(",", "").replace("٬", "").replace("٫", ".")
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _numbers_near(line: str):
    return [value for value in (to_decimal(match.group())
                                for match in _NUMBER.finditer(line)) if value is not None]


def find_unit(line: str):
    """The unit named on a line, or None. Longest match wins.

    Longest-first matters: "متر" is a prefix of "مترمکعب", and matching the short one first
    would report cubic metres of concrete as linear metres.
    """
    text = normalize(line)
    for word in sorted(UNITS, key=len, reverse=True):
        if word in text:
            return UNITS[word], word
    return None, None


def find_currency(text: str):
    normalized = normalize(text)
    for word, code in CURRENCIES.items():
        if word in normalized:
            return code, word
    return None, None


def parse_invoice_text(text: str, base_confidence=Decimal("0.5")):
    """Candidate fields from recognised text.

    The confidence attached to each field is the recogniser's own, lowered where the parse
    itself is uncertain -- a number found on a line that names no field is reported at half
    the recogniser's confidence, because reading it correctly and understanding it correctly
    are different claims.

    Returns `(fields, warnings)`. A field the text does not support is simply absent; the
    warnings say what was ambiguous, so the reviewer knows where to look.
    """
    normalized = normalize(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    found, warnings = {}, []
    confidence = Decimal(base_confidence)
    lowered = (confidence / 2).quantize(Decimal("0.01"))

    def claim(key, value, at):
        """Record a candidate. A second, different value for a key is a conflict, not a fix."""
        if key in found and found[key][0] != value:
            warnings.append("چند مقدار برای «%s» پیدا شد؛ هیچ‌کدام قطعی نیست." % key)
            found[key] = (found[key][0], lowered)
            return
        found[key] = (value, at)

    for line in lines:
        numbers = _numbers_near(line)
        unit, unit_word = find_unit(line)

        if unit and numbers:
            claim("quantity", format(numbers[0], "f"), confidence)
            claim("unit", unit, confidence)
        elif any(word in line for word in _QUANTITY_WORDS) and numbers:
            claim("quantity", format(numbers[0], "f"), lowered)

        if any(word in line for word in _TOTAL_WORDS) and numbers:
            claim("totalAmount", format(max(numbers), "f"), confidence)
        if any(word in line for word in _UNIT_PRICE_WORDS) and numbers:
            claim("unitPrice", format(numbers[0], "f"), confidence)

        code, word = find_currency(line)
        if code:
            claim("currency", code, confidence)

        jalali = _JALALI.search(line)
        if jalali and any(word in line for word in _DATE_WORDS):
            claim("invoiceDate", "%s-%02d-%02d" % (jalali.group(1), int(jalali.group(2)),
                                                   int(jalali.group(3))), confidence)
        elif jalali:
            claim("invoiceDate", "%s-%02d-%02d" % (jalali.group(1), int(jalali.group(2)),
                                                   int(jalali.group(3))), lowered)

        for word in _VENDOR_WORDS:
            if word in line:
                rest = line.split(word, 1)[1].strip(" :،-")
                if rest:
                    claim("vendorName", rest[:120], lowered)
                break

        for word in _NUMBER_WORDS:
            if word in line:
                rest = line.split(word, 1)[1].strip(" :،-")
                token = rest.split(" ")[0] if rest else ""
                if token:
                    claim("invoiceNumber", token[:60], lowered)
                break

    # Deliberately absent: any attempt to complete the set. With a quantity and a total but
    # no unit price, dividing would produce a number nobody wrote, indistinguishable to the
    # reviewer from one that was read off the page.
    if "quantity" in found and "unitPrice" not in found and "totalAmount" in found:
        warnings.append("قیمت واحد در متن نبود و محاسبه نشد؛ خودتان وارد کنید.")
    if "quantity" in found and "unit" not in found:
        warnings.append("مقدار پیدا شد ولی واحدش مشخص نیست.")
    if not found:
        warnings.append("هیچ فیلد مالی قابل تشخیصی در متن پیدا نشد.")

    fields = tuple((key, value, at) for key, (value, at) in sorted(found.items()))
    return fields, tuple(warnings)
