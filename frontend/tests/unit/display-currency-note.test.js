import test from "node:test";
import assert from "node:assert/strict";
import { displayCurrencyNote, formatTomanFromIrr } from "../../src/shared/formatters/money.js";
import { CURRENCY_LABELS } from "../../src/shared/constants/currency.js";

/**
 * A column of bare numbers has to say somewhere which currency it is in.
 *
 * `#/financial-items` formats «هزینه MSP فعالیت», «قیمت اولیه» and «قیمت روز» with
 * `withCurrency: false`, which keeps the column readable and leaves the reader unable to
 * tell ۱۲٬۵۶۵٬۱۱۵٬۳۹۱ rials from ۱۲٬۵۶۵٬۱۱۵٬۳۹۱ tomans — a factor of ten.
 *
 * What matters is not that a label exists; it is that the label and the numbers under it
 * describe the SAME currency. Writing «مبالغ به تومان» by hand would satisfy an
 * existence check and then be wrong the moment somebody switched the display currency, so
 * these tests compare the note against what the formatter itself appends, in both
 * currencies the preference supports.
 */

function withDisplayCurrency(code, body) {
  const previous = globalThis.window;
  globalThis.window = { localStorage: { getItem: () => code } };
  try {
    return body();
  } finally {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  }
}

/** The currency word `formatTomanFromIrr` puts beside an amount, whatever it is. */
function labelTheFormatterUses() {
  const withWord = formatTomanFromIrr("125651153910");
  const bare = formatTomanFromIrr("125651153910", { withCurrency: false });
  return withWord.replace(/[⁦-⁩]/g, "").replace(bare, "").trim();
}

for (const code of ["TOMAN", "IRR"]) {
  test(`the note names the same currency the amounts are formatted in (${code})`, () => {
    withDisplayCurrency(code, () => {
      const note = displayCurrencyNote();
      const label = labelTheFormatterUses();
      assert.equal(label, CURRENCY_LABELS[code], "the formatter changed currency unexpectedly");
      assert.ok(note.includes(label),
        `the note ${JSON.stringify(note)} does not name ${label}`);
      // And it must not name the other one, which is what a hard-coded label would do.
      const other = CURRENCY_LABELS[code === "TOMAN" ? "IRR" : "TOMAN"];
      assert.ok(!note.includes(other), `the note also names ${other}`);
    });
  });
}

test("the amounts themselves are unchanged by having a label", () => {
  // Assignment 9703's real rate, as the API reports it. The label is presentation; the
  // arithmetic underneath must be exactly what it was: one division by ten, no rounding.
  withDisplayCurrency("TOMAN", () => {
    assert.equal(formatTomanFromIrr("125651153910", { withCurrency: false }), "۱۲٬۵۶۵٬۱۱۵٬۳۹۱");
  });
  withDisplayCurrency("IRR", () => {
    assert.equal(formatTomanFromIrr("125651153910", { withCurrency: false }), "۱۲۵٬۶۵۱٬۱۵۳٬۹۱۰");
  });
});

test("a missing amount stays “—” and a real zero stays zero", () => {
  withDisplayCurrency("TOMAN", () => {
    // The label says what the numbers mean; it must not turn an absent number into one.
    assert.equal(formatTomanFromIrr(null, { withCurrency: false }), "—");
    assert.equal(formatTomanFromIrr(undefined, { withCurrency: false }), "—");
    assert.equal(formatTomanFromIrr("0", { withCurrency: false }), "۰");
  });
});
