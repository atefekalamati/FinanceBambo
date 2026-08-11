import test from "node:test";
import assert from "node:assert/strict";
import { formatTomanFromIrr, irrToDisplayValue, irrToToman, tomanInputToIrr } from "../../src/shared/formatters/money.js";

test("converts canonical IRR to exact Toman without floating point", () => {
  assert.equal(irrToToman("12345678901234567891"), "1234567890123456789.1");
  assert.equal(formatTomanFromIrr("1250"), "۱۲۵ تومان");
});

test("converts Persian Toman input to canonical integer IRR", () => {
  assert.equal(tomanInputToIrr("۱۲٬۳۴۵٫۶"), "123456");
  assert.equal(tomanInputToIrr("12.55"), "");
});

test("uses the selected IRR display without changing the canonical backend amount", () => {
  const previousWindow = globalThis.window;
  globalThis.window = { localStorage: { getItem: () => "IRR" } };
  try {
    assert.equal(irrToDisplayValue("1250"), "1250");
    assert.equal(formatTomanFromIrr("1250"), "۱٬۲۵۰ ریال");
    assert.equal(tomanInputToIrr("۱٬۲۵۰"), "1250");
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
