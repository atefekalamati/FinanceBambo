import test from "node:test";
import assert from "node:assert/strict";
import { compactMoneyFromIrr, formatCompactMoneyFromIrr, formatTomanFromIrr, irrToDisplayValue, irrToToman, tomanInputToIrr } from "../../src/shared/formatters/money.js";

const rtlMoney = (text) => `\u2067${text}\u2069`;

test("converts canonical IRR to exact Toman without floating point", () => {
  assert.equal(irrToToman("12345678901234567891"), "1234567890123456789.1");
  assert.equal(formatTomanFromIrr("1250"), rtlMoney("۱۲۵ تومان"));
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
    assert.equal(formatTomanFromIrr("1250"), rtlMoney("۱٬۲۵۰ ریال"));
    assert.equal(tomanInputToIrr("۱٬۲۵۰"), "1250");
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test("compacts large Toman values without floating point and keeps the exact value", () => {
  const result = compactMoneyFromIrr("189000000000");
  assert.deepEqual(result, {
    amount: "۱۸٫۹",
    unit: "میلیارد تومان",
    exact: rtlMoney("۱۸٬۹۰۰٬۰۰۰٬۰۰۰ تومان"),
    compact: true,
  });
  assert.equal(formatCompactMoneyFromIrr("12500000"), rtlMoney("۱٫۲۵ میلیون تومان"));
});

test("keeps small values exact and compacts according to the selected IRR display", () => {
  assert.equal(formatCompactMoneyFromIrr("1250"), rtlMoney("۱۲۵ تومان"));
  const previousWindow = globalThis.window;
  globalThis.window = { localStorage: { getItem: () => "IRR" } };
  try {
    assert.equal(formatCompactMoneyFromIrr("189000000000"), rtlMoney("۱۸۹ میلیارد ریال"));
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test("a shared compact scale keeps every axis tick in one unit", async () => {
  const { compactMoneyScale } = await import("../../src/shared/formatters/money.js");
  const scale = compactMoneyScale("1250000000");
  assert.equal(scale.unit, "میلیون تومان");
  assert.deepEqual(
    ["0", "312500000", "625000000", "937500000", "1250000000"].map((tick) => scale.format(tick)),
    ["۰", "۳۱٫۲۵", "۶۲٫۵", "۹۳٫۷۵", "۱۲۵"],
    "a per-value formatter would label the low ticks in a smaller unit and silently mix scales on one axis",
  );
});

test("the compact scale follows the maximum into a larger unit", async () => {
  const { compactMoneyScale } = await import("../../src/shared/formatters/money.js");
  const scale = compactMoneyScale("125000000000");
  assert.equal(scale.unit, "میلیارد تومان");
  assert.equal(scale.format("125000000000"), "۱۲٫۵");
  assert.equal(scale.format("0"), "۰");
});

test("the compact scale rejects a non-integer maximum instead of guessing", async () => {
  const { compactMoneyScale } = await import("../../src/shared/formatters/money.js");
  assert.equal(compactMoneyScale("12.5"), null);
  assert.equal(compactMoneyScale(null), null);
  assert.equal(compactMoneyScale("1000000").format("12.5"), null);
});
