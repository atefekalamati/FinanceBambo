import test from "node:test";
import assert from "node:assert/strict";

import { buildWbsView } from "../../src/shared/reports/wbs-rollup.js";
import { buildBulletPresentation } from "../../src/shared/reports/report-presentation.js";

/**
 * A figure the Backend could not work out is not a figure of nothing.
 *
 * The live report reports `null` for a phase or a cost type whose lines carry no estimate
 * basis — this project's 426 equipment lines state neither a quantity nor a rate — and
 * `0` for one that really came to nothing. Both builders used to flatten the first into
 * the second before it reached a chart, so an unanswerable phase was drawn exactly like a
 * phase budgeted at nil, and the phase totals published a subtotal under the word "total".
 *
 * These pin the distinction at the only place both charts read from.
 */

const phase = (wbsCode, estimate, actual) => ({
  wbsCode, title: `مرحله ${wbsCode}`, parentWbsCode: null, activityCount: 1, childCount: 0,
  initialEstimateIrr: estimate, actualCostIrr: actual, forecastFinalIrr: actual,
});

test("a phase whose estimate is unavailable keeps saying so", () => {
  const view = buildWbsView({ nodes: [phase("1.1", "1000", "400"), phase("1.5", null, "250")] });
  const [first, second] = view.rows;
  assert.equal(first.initialEstimateIrr, "1000");
  assert.equal(second.initialEstimateIrr, null, "null must not arrive at the chart as \"0\"");
  assert.equal(second.estimateMagnitude, null, "and it must not be drawn as a bar of no height");
  assert.equal(second.hasEstimate, false);
  assert.equal(second.consumedPercent, null);
});

test("a phase estimated at nothing still says nothing, not unavailable", () => {
  const [row] = buildWbsView({ nodes: [phase("1.2", "0", "0")] }).rows;
  assert.equal(row.initialEstimateIrr, "0", "a real zero is a fact and is kept");
  assert.equal(row.estimateMagnitude, 0);
  assert.equal(row.hasEstimate, false, "nothing to consume, so no percentage");
});

test("the actual cost of a phase is drawn even when its estimate is unavailable", () => {
  // The two series are independent: an unanswerable estimate must not take a real cost
  // off the chart with it.
  const [row] = buildWbsView({ nodes: [phase("1.7", null, "9000")] }).rows;
  assert.equal(row.actualCostIrr, "9000");
  assert.ok(row.actualMagnitude > 0, "the actual bar still has a height");
  assert.equal(row.initialEstimateIrr, null);
});

test("phase totals refuse to publish a subtotal as a total", () => {
  const partial = buildWbsView({ nodes: [phase("1.1", "1000", "400"), phase("1.5", null, "250")] });
  assert.equal(partial.totals.initialEstimateIrr, null,
    "one unavailable phase makes the estimate total unavailable, not 1000");
  assert.equal(partial.totals.consumedPercent, null, "and no percentage of an unknown whole");
  assert.equal(partial.totals.actualCostIrr, "650", "the actual total is known and is published");

  const whole = buildWbsView({ nodes: [phase("1.1", "1000", "400"), phase("1.5", "500", "250")] });
  assert.equal(whole.totals.initialEstimateIrr, "1500");
  assert.equal(whole.totals.consumedPercent, "43.3");
});

test("a cost type with no estimate is not a type budgeted at nothing", () => {
  const view = buildBulletPresentation([
    { resourceType: "material", initialEstimateIrr: "1000", actualCostIrr: "600", forecastFinalIrr: "1000" },
    { resourceType: "equipment", initialEstimateIrr: null, actualCostIrr: "0", forecastFinalIrr: null },
  ]);
  const [material, equipment] = view.rows;
  assert.equal(material.initialEstimateIrr, "1000");
  assert.equal(equipment.initialEstimateIrr, null);
  assert.equal(equipment.estimateMagnitude, null);
  assert.equal(equipment.forecastFinalIrr, null);
  assert.equal(equipment.hasEstimate, false);
  assert.equal(equipment.consumedPercent, null);
  // A real zero on the actual side is still a fact, and still gets its (empty) bar.
  assert.equal(equipment.actualCostIrr, "0");
  assert.equal(equipment.actualMagnitude, 0);
});

test("an unavailable actual has no bar at all, unlike a zero one", () => {
  const [row] = buildBulletPresentation([
    { resourceType: "labor", initialEstimateIrr: "500", actualCostIrr: null, forecastFinalIrr: null },
  ]).rows;
  assert.equal(row.actualCostIrr, null);
  assert.equal(row.actualMagnitude, null, "nothing to draw, rather than a bar of height zero");
  assert.equal(row.consumedPercent, null);
  assert.equal(row.overBudget, false);
});

test("a negative actual is preserved, not clamped", () => {
  const [row] = buildBulletPresentation([
    { resourceType: "material", initialEstimateIrr: "500", actualCostIrr: "-200", forecastFinalIrr: "300" },
  ]).rows;
  assert.equal(row.actualCostIrr, "-200");
  assert.equal(row.actualBelowZero, true);
});
