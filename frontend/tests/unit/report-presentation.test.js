import test from "node:test";
import assert from "node:assert/strict";
import { buildBulletPresentation, buildOverviewComparisons } from "../../src/shared/reports/report-presentation.js";

test("builds exact overview comparisons without binary financial arithmetic", () => {
  const result = buildOverviewComparisons({
    initialEstimateIrr: "100000000000000001",
    actualCostIrr: "50000000000000000",
    forecastFinalCostIrr: "125000000000000000",
    currentExecutedValueIrr: "25000000000000000",
    remainingPhysicalCostIrr: "75000000000000000",
  });
  assert.deepEqual(result.management.map((entry) => entry.magnitude), [80, 40, 60, 100]);
});

test("an uncomputable metric stays null instead of becoming a zero bar", () => {
  // LiveMetrics declares these nullable: null is "the Backend could not work it
  // out", and a finance screen must not redraw that as ۰ تومان.
  const result = buildOverviewComparisons({
    initialEstimateIrr: "250000000",
    actualCostIrr: "1887800000",
    remainingPhysicalCostIrr: null,
    forecastFinalCostIrr: null,
  });
  const byKey = Object.fromEntries(result.management.map((entry) => [entry.key, entry]));
  assert.equal(byKey.remaining.value, null);
  assert.equal(byKey.forecast.value, null);
  assert.equal(byKey.remaining.magnitude, 0, "nothing to draw for a number nobody computed");
  assert.equal(byKey.actual.value, "1887800000", "the computed ones are untouched");
  assert.equal(byKey.actual.magnitude, 100);
});

test("a metric that is not an exact integer is treated as uncomputable", () => {
  const [initial] = buildOverviewComparisons({ initialEstimateIrr: "12.5" }).management;
  assert.equal(initial.value, null, "money is exact integer IRR or it is nothing");
});

test("the bullet form measures each category against its own estimate", () => {
  const view = buildBulletPresentation([
    { resourceType: "material", initialEstimateIrr: "1000000000", actualCostIrr: "400000000", forecastFinalIrr: "0" },
    { resourceType: "equipment", initialEstimateIrr: "275000000", actualCostIrr: "299256198", forecastFinalIrr: "0" },
  ]);
  const [material, equipment] = view.rows;
  assert.equal(material.consumedPercent, 40);
  assert.equal(material.overBudget, false);
  // The whole point of the form: passing the estimate is a state, not a length
  // the reader has to compare for themselves.
  assert.equal(equipment.overBudget, true);
  assert.equal(equipment.overspendIrr, "24256198");
  assert.equal(Math.round(equipment.consumedPercent), 109);
});

test("the bullet axis ends on a round number above every value", () => {
  const view = buildBulletPresentation([
    { resourceType: "material", initialEstimateIrr: "1106981359", actualCostIrr: "0", forecastFinalIrr: "0" },
  ]);
  assert.equal(view.ceilingIrr, "1500000000");
  assert.deepEqual(view.ticks.map((tick) => tick.valueIrr), ["0", "500000000", "1000000000", "1500000000"]);
  // The last line sits at the end of the track, and a bar of the ceiling's own
  // value would fill it exactly.
  assert.equal(view.ticks.at(-1).magnitude, 100);
  // Nothing may reach the end of the track unless it is the ceiling itself.
  view.rows.forEach((row) => assert.ok(row.estimateMagnitude <= 100));
});

test("a category with no estimate is not a category budgeted at nothing", () => {
  // Its estimate lines carry no estimate price, so the service returns zero and
  // «۰٪ مصرف شده» would be an answer to a question nobody could answer.
  const [row] = buildBulletPresentation([
    { resourceType: "material", initialEstimateIrr: "0", actualCostIrr: "1106981359", forecastFinalIrr: "0" },
  ]).rows;
  assert.equal(row.hasEstimate, false);
  assert.equal(row.consumedPercent, null);
  assert.equal(row.estimateMagnitude, null, "no estimate, no marker");
  assert.equal(row.overBudget, false, "nothing to be over");
  assert.ok(row.actualMagnitude > 0, "the money that was spent is still drawn");
});

test("a category whose reversals outweigh its documents gets no bar", () => {
  const [row] = buildBulletPresentation([
    { resourceType: "general_cost", initialEstimateIrr: "100", actualCostIrr: "-50", forecastFinalIrr: "0" },
  ]).rows;
  assert.equal(row.actualBelowZero, true);
  assert.equal(row.actualMagnitude, 0, "a negative amount must not be drawn from its size");
  assert.equal(row.actualCostIrr, "-50", "the figure itself is untouched");
});

test("the percentage stays exact at magnitudes a float would round", () => {
  const [row] = buildBulletPresentation([
    { resourceType: "material", initialEstimateIrr: "100000000000000000", actualCostIrr: "33333333333333333", forecastFinalIrr: "0" },
  ]).rows;
  assert.equal(row.consumedPercent, 33.3);
  const empty = buildBulletPresentation([]);
  assert.equal(empty.ceilingIrr, "0");
  assert.deepEqual(empty.ticks, []);
  assert.deepEqual(empty.rows, []);
});

/* A SUM OVER NO LINES MUST NOT BECOME A BAR.
 *
 * The module keeps a null null, which covers the figure the service could not work out.
 * It never covered the other one: a sum the service DID publish, as `0`, over none of the
 * project's lines. Measured on terrace, the chart drew «۰ تومان» under «هزینه بروز
 * باقیمانده» while the card beside it read «قابل محاسبه نیست» — one panel, two answers,
 * and the wrong one looked like a number.
 */

test("a withheld metric is drawn as absent even though the service stated it", () => {
  const metrics = { initialEstimateIrr: "360000000000", remainingPhysicalCostIrr: "0" };
  const { management } = buildOverviewComparisons(metrics,
    { withheld: ["remainingPhysicalCostIrr"] });
  const remaining = management.find((bar) => bar.key === "remaining");
  assert.equal(remaining.value, null, "no amount");
  assert.equal(remaining.magnitude, 0, "and therefore no bar to draw");
});

test("withholding one bar does not rescale the others", () => {
  /* The scale comes from the tallest bar, and a withheld bar is worth nothing. A figure
     the reader is still being shown must not change height because another was removed. */
  const metrics = { initialEstimateIrr: "100", actualCostIrr: "50",
                    remainingPhysicalCostIrr: "0" };
  const before = buildOverviewComparisons(metrics).management;
  const after = buildOverviewComparisons(metrics,
    { withheld: ["remainingPhysicalCostIrr"] }).management;
  assert.deepEqual(after.filter((b) => b.key !== "remaining").map((b) => b.magnitude),
                   before.filter((b) => b.key !== "remaining").map((b) => b.magnitude));
});

test("naming no keys leaves every stated figure exactly as it was", () => {
  const metrics = { remainingPhysicalCostIrr: "0", forecastFinalCostIrr: "900" };
  const { management } = buildOverviewComparisons(metrics);
  assert.equal(management.find((bar) => bar.key === "remaining").value, "0",
               "the default is still to draw what the service said");
});

test("each bar carries the metric it draws, so a caller can address one", () => {
  /* Both the withholding above and the coverage mark beside the label are decisions made
     per METRIC by the page; a bar keyed only by «remaining» could not be matched to one. */
  assert.deepEqual(buildOverviewComparisons({}).management.map((bar) => bar.metric),
                   ["initialEstimateIrr", "actualCostIrr",
                    "remainingPhysicalCostIrr", "forecastFinalCostIrr"]);
});
