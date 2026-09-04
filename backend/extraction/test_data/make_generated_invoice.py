# -*- coding: utf-8 -*-
"""Build `generated_invoice.png`, the fixture the end-to-end extraction test uploads.

LOCAL TEST FIXTURE ONLY. Every name and number here is invented; nothing is real financial
data and nothing is inserted into a database by this script.

    ../ai-extraction-env/Scripts/python extraction/test_data/make_generated_invoice.py

WHY THE SHAPING STEP EXISTS
Pillow in this environment is built without raqm, so it draws Persian letters in isolated
form and in logical order -- `فاکتور` comes out as five disconnected glyphs, left to right.
An OCR test against that would measure nothing about Persian: no invoice ever looks like it.
`arabic_reshaper` joins the letters and `python-bidi` puts them in visual order, which is
what a real document contains.
"""

from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "generated_invoice.png"
FONT = "C:/Windows/Fonts/tahoma.ttf"
WIDTH, HEIGHT = 1240, 900

#: The invoice's own numbers. Kept here as one block so the expected OCR result can be read
#: off the fixture rather than guessed from the picture.
SELLER = "شرکت تست بامبو"
BUYER = "پروژه تراس پلاس"
NUMBER = "INV-1405-001"
DATE = "1405/06/12"
ITEMS = (
    ("بتن آماده", "10", "مترمکعب", "5,000,000", "50,000,000"),
    ("میلگرد", "1000", "کیلوگرم", "85,000", "85,000,000"),
)
TOTAL = "135,000,000"


def fa(text):
    """Persian as it must be drawn: glyphs joined, then reordered right to left."""
    return get_display(arabic_reshaper.reshape(text))


def main():
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype(FONT, 34)
    head = ImageFont.truetype(FONT, 24)
    body = ImageFont.truetype(FONT, 21)

    def right(text, y, font=body, x=WIDTH - 50):
        line = fa(text)
        draw.text((x - draw.textlength(line, font=font), y), line, font=font, fill="black")

    def left(text, y, font=body, x=50):
        draw.text((x, y), text, font=font, fill="black")

    draw.rectangle([25, 25, WIDTH - 25, HEIGHT - 25], outline="black", width=3)

    right("فاکتور فروش", 55, title)
    right("فروشنده: %s" % SELLER, 120, head)
    right("خریدار: %s" % BUYER, 165, head)
    right("شماره فاکتور: %s" % NUMBER, 215)
    right("تاریخ: %s" % DATE, 250)
    left("INVOICE NO: %s" % NUMBER, 215)
    left("DATE: %s" % DATE, 250)

    # A ruled table. Real invoices have lines, and a table that OCR can segment is part of
    # what this fixture is meant to exercise.
    top, row_height = 305, 62
    bottom = top + row_height * (len(ITEMS) + 1)
    columns = (WIDTH - 50, 830, 660, 470, 250)
    draw.line([50, top, WIDTH - 50, top], fill="black", width=2)
    for header, x in zip(("شرح کالا", "تعداد", "واحد", "قیمت واحد (ریال)",
                          "مبلغ کل (ریال)"), columns):
        right(header, top + 16, head, x)
    draw.line([50, top + row_height, WIDTH - 50, top + row_height], fill="black", width=2)

    y = top + row_height
    for name, quantity, unit, price, amount in ITEMS:
        right(name, y + 18, body, columns[0])
        right(quantity, y + 18, body, columns[1])
        right(unit, y + 18, body, columns[2])
        right(price, y + 18, body, columns[3])
        right(amount, y + 18, body, columns[4])
        y += row_height
        draw.line([50, y, WIDTH - 50, y], fill="black", width=1)

    draw.rectangle([50, top, WIDTH - 50, bottom], outline="black", width=2)
    for x in columns[1:]:
        draw.line([x + 20, top, x + 20, bottom], fill="black", width=1)

    right("جمع کل: %s ریال" % TOTAL, bottom + 35, head)
    left("TOTAL: %s IRR" % TOTAL, bottom + 38)
    right("مهر و امضای فروشنده", bottom + 130)
    left("TEST FIXTURE - NOT A REAL INVOICE", HEIGHT - 70, body)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT)
    print("wrote %s (%d bytes)" % (OUT, OUT.stat().st_size))


if __name__ == "__main__":
    main()
