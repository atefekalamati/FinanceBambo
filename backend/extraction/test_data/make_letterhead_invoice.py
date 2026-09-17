# -*- coding: utf-8 -*-
"""Build `letterhead_invoice.png` -- a SECOND layout, to test whether the rules generalise.

LOCAL TEST FIXTURE ONLY. Every name and number is invented; nothing here is real financial
data and nothing is written to a database.

WHY A SECOND FIXTURE EXISTS

`generated_invoice.png` was drawn to match the labels the parser already knows, so it
proves the parser reads ITS OWN template. It cannot show whether the rules generalise --
a test built from the same assumptions as the code always passes.

This one follows the conventions of a real supplier invoice instead, and every difference
is deliberate:

    the seller is in the LETTERHEAD      no «فروشنده:» label anywhere on the page
    «شماره:» not «شماره فاکتور:»          the word فاکتور appears only in the title
    a three-line money block              subtotal, then tax, then the payable total
    «جمع مبلغ کالاها» for the SUBTOTAL     which contains the word «جمع»
    «مبلغ کل قابل پرداخت» for the TOTAL    which contains «مبلغ کل» AND «قابل پرداخت»
    «مالیات بر ارزش افزوده»                a field the parser has no rule for at all
    a «ردیف» row-number column             an extra leading column in the table

The last three are the interesting ones. Two labels both contain a word the total rule
matches, and they sit on different lines with different numbers -- so the fixture can show
whether the parser takes the subtotal for the total, which is a 51,500,000 rial error that
looks entirely reasonable on screen.
"""

from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "letterhead_invoice.png"
FONT = "C:/Windows/Fonts/tahoma.ttf"
WIDTH, HEIGHT = 1300, 1000

SELLER = "فراز سازه پارس"
SELLER_TRADE = "تامین مصالح ساختمانی"
BUYER = "شرکت توسعه بنا کیان"
NUMBER = "1403/1125"
DATE = "1403/08/15"
ITEMS = (
    ("1", "سیمان تیپ 2 - پاکتی", "پاکت", "100", "1,200,000", "120,000,000"),
    ("2", "میلگرد آجدار 14", "کیلوگرم", "5,000", "72,000", "360,000,000"),
    ("3", "ماسه شسته", "متر مکعب", "20", "550,000", "11,000,000"),
    ("4", "شن نخودی", "متر مکعب", "20", "450,000", "9,000,000"),
    ("5", "آجر سفال 20x20x20", "عدد", "5,000", "3,000", "15,000,000"),
)
SUBTOTAL = "515,000,000"
TAX = "51,500,000"
TOTAL = "566,500,000"


def fa(text):
    """Persian as it must be drawn: glyphs joined, then reordered right to left."""
    return get_display(arabic_reshaper.reshape(text))


def main():
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype(FONT, 32)
    head = ImageFont.truetype(FONT, 23)
    body = ImageFont.truetype(FONT, 19)
    small = ImageFont.truetype(FONT, 16)

    def right(text, y, font=body, x=WIDTH - 45):
        line = fa(text)
        draw.text((x - draw.textlength(line, font=font), y), line, font=font, fill="black")

    def left(text, y, font=body, x=45):
        draw.text((x, y), fa(text), font=font, fill="black")

    draw.rectangle([20, 20, WIDTH - 20, HEIGHT - 20], outline="black", width=2)

    # ---- letterhead: the seller's name with NO label in front of it ------------------
    left(SELLER, 45, title)
    left(SELLER_TRADE, 88, small)
    left("تهران، بزرگراه فتح، خیابان صنایع، پلاک 123", 118, small)
    left("تلفن: 021-55234678", 145, small)

    # ---- the title block, boxed, as these invoices print it -------------------------
    draw.rectangle([WIDTH // 2 - 150, 40, WIDTH // 2 + 150, 150], outline="black", width=2)
    right("فاکتور فروش", 52, title, WIDTH // 2 + 135)
    right("شماره: %s" % NUMBER, 100, body, WIDTH // 2 + 135)
    right("تاریخ: %s" % DATE, 125, body, WIDTH // 2 + 135)

    # ---- the buyer, labelled ---------------------------------------------------------
    right("خریدار: %s" % BUYER, 190, head)
    right("شماره اقتصادی: 411234567", 222, small)
    right("نشانی: تهران، منطقه 22، بلوار پژوهش، پلاک 45", 248, small)

    # ---- a six-column table, the first column being the row number -------------------
    top, row_height = 300, 52
    columns = (WIDTH - 45, 1080, 880, 740, 560, 300)
    headers = ("ردیف", "شرح کالا", "واحد", "تعداد", "قیمت واحد (ریال)", "مبلغ کل (ریال)")
    draw.line([45, top, WIDTH - 45, top], fill="black", width=2)
    for header, x in zip(headers, columns):
        right(header, top + 14, body, x)
    draw.line([45, top + row_height, WIDTH - 45, top + row_height], fill="black", width=2)

    y = top + row_height
    for row in ITEMS:
        for value, x in zip(row, columns):
            right(value, y + 15, body, x)
        y += row_height
        draw.line([45, y, WIDTH - 45, y], fill="black", width=1)

    bottom = y
    draw.rectangle([45, top, WIDTH - 45, bottom], outline="black", width=2)
    for x in columns[1:]:
        draw.line([x + 18, top, x + 18, bottom], fill="black", width=1)

    # ---- the money block: THREE lines, two of which the total rule can match ---------
    money_top = bottom
    for index, (label, value) in enumerate((("جمع مبلغ کالاها", SUBTOTAL),
                                            ("مالیات بر ارزش افزوده (1%)", TAX),
                                            ("مبلغ کل قابل پرداخت", TOTAL))):
        row_y = money_top + index * 44
        draw.rectangle([300, row_y, WIDTH - 45, row_y + 44], outline="black", width=1)
        right(label, row_y + 12, body, 880)
        right(value, row_y + 12, body, WIDTH - 60)

    right("مبلغ به حروف: پانصد و شصت و شش میلیون و پانصد هزار ریال",
          money_top + 160, body)
    left("TEST FIXTURE - NOT A REAL INVOICE", HEIGHT - 55, small)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT)
    print("wrote %s (%d bytes)" % (OUT, OUT.stat().st_size))


if __name__ == "__main__":
    main()
