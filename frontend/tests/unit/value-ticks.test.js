import test from "node:test";
import assert from "node:assert/strict";
import { buildValueTicks, chooseTickStep } from "../../src/shared/charts/value-ticks.js";
import { compactMoneyScale } from "../../src/shared/formatters/money.js";

/**
 * The point of these is readability, so most of them assert what a reader would
 * actually see rather than an internal number.
 */

const render = (maximumIrr, options) => {
  const scale = compactMoneyScale(maximumIrr);
  return buildValueTicks(maximumIrr, options).map((tick) => scale.format(tick.valueIrr));
};

test("the lines land on round numbers, not on equal divisions of the tallest bar", () => {
  // The old helper divided the maximum into equal parts, which for this project
  // produced 1,956,325,000 IRR and its multiples.
  assert.deepEqual(render("7825300000"), ["۰", "۲۰۰", "۴۰۰", "۶۰۰"]);
});

test("the amounts follow the size of the project", () => {
  assert.deepEqual(render("47000"), ["۰", "۱٬۰۰۰", "۲٬۰۰۰", "۳٬۰۰۰", "۴٬۰۰۰"]);
  assert.deepEqual(render("8960654000"), ["۰", "۲۰۰", "۴۰۰", "۶۰۰", "۸۰۰"]);
  assert.deepEqual(render("9900000000000"), ["۰", "۲۰۰", "۴۰۰", "۶۰۰", "۸۰۰"]);
});

test("two projects three orders of magnitude apart each get a readable axis", () => {
  const small = compactMoneyScale("12000000");
  const large = compactMoneyScale("12000000000");
  assert.equal(small.unit === large.unit, false, "the unit itself adapts");
  assert.ok(buildValueTicks("12000000").length >= 3);
  assert.ok(buildValueTicks("12000000000").length >= 3);
});

test("every step is a 1, 2 or 5 followed by zeros", () => {
  const maxima = ["47000", "999999999", "1250000000", "3300000000", "7825300000", "8960654000", "9900000000000"];
  maxima.forEach((maximum) => {
    const step = chooseTickStep(maximum);
    const digits = step.toString();
    assert.match(digits, /^[125]0*$/, `step ${digits} for maximum ${maximum} is not a round number`);
  });
});

test("the axis never rises above the tallest bar, so no column is rescaled", () => {
  const maximum = 7825300000n;
  buildValueTicks(maximum).forEach((tick) => {
    assert.ok(BigInt(tick.valueIrr) <= maximum, `${tick.valueIrr} sits above the tallest bar`);
    assert.ok(tick.magnitude >= 0 && tick.magnitude <= 100);
  });
});

test("a line and a bar of the same value sit at the same height", () => {
  // The bars are positioned as a hundredth-of-a-percent share of the largest
  // value, so a gridline has to be placed by the same arithmetic or it will
  // float above or below the bar top it is supposed to explain.
  const maximum = 7825300000n;
  buildValueTicks(maximum).forEach((tick) => {
    const expected = Number((BigInt(tick.valueIrr) * 10000n) / maximum) / 100;
    assert.equal(tick.magnitude, expected, `${tick.valueIrr} is placed at the wrong height`);
  });
  assert.equal(buildValueTicks(maximum)[0].magnitude, 0, "zero sits on the floor the bars stand on");
});

test("the number of lines stays within what a short chart can carry", () => {
  const maxima = ["47000", "999999999", "1250000000", "3300000000", "7825300000", "8960654000", "9900000000000", "1000000000000000"];
  maxima.forEach((maximum) => {
    const count = buildValueTicks(maximum).length;
    assert.ok(count >= 2 && count <= 6, `maximum ${maximum} produced ${count} lines`);
  });
});

test("nothing is drawn when there is nothing to measure", () => {
  assert.deepEqual(buildValueTicks("0"), []);
  assert.deepEqual(buildValueTicks(null), []);
  assert.deepEqual(buildValueTicks("-500"), [], "a negative ceiling is not an axis");
  assert.deepEqual(buildValueTicks("12.5"), [], "money is exact integer IRR or it is nothing");
  assert.equal(chooseTickStep("0"), null);
});

test("a single value still produces an axis", () => {
  const ticks = buildValueTicks("5000000000");
  assert.ok(ticks.length >= 2);
  assert.equal(ticks[0].valueIrr, "0");
});

test("the arithmetic stays exact at magnitudes that would break a float", () => {
  const maximum = "9007199254740993000"; // past Number.MAX_SAFE_INTEGER
  const ticks = buildValueTicks(maximum);
  ticks.forEach((tick) => assert.match(tick.valueIrr, /^\d+$/));
  assert.ok(BigInt(ticks.at(-1).valueIrr) <= BigInt(maximum));
});

test("zero can be dropped when the chart already draws its own floor", () => {
  const ticks = buildValueTicks("8000000000", { includeZero: false });
  assert.notEqual(ticks[0].valueIrr, "0");
});
