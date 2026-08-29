import test from "node:test";
import assert from "node:assert/strict";

import { buildCostCurve, chooseCurveCeiling, curvePath } from "../../src/shared/charts/cost-curve.js";
import { buildMonthlyTrend, TREND_MODES } from "../../src/shared/reports/monthly-trend.js";

const months = (values) => values.map(([actual, estimate], index) => ({
  persianYear: 1405,
  persianMonth: index + 1,
  actualCostIrr: String(actual),
  estimateIrr: estimate === null ? null : String(estimate),
  invoiceCount: 1,
}));

const cumulative = (values) => buildMonthlyTrend({ months: months(values), mode: TREND_MODES.CUMULATIVE }).points;

test("the axis leaves room above the data for an overrun", () => {
  // Without headroom a project sitting exactly on a round number would draw its
  // curve along the top edge, and the next rial spent would have nowhere to go.
  const axis = chooseCurveCeiling("10000000000", { headroomPercent: 15 });
  assert.ok(BigInt(axis.ceiling) > 10000000000n, "ceiling must clear the data");
  assert.equal(BigInt(axis.ceiling) % BigInt(axis.step), 0n, "ceiling sits on a whole step");
});

test("the ceiling stays a number a person would have chosen", () => {
  const axis = chooseCurveCeiling("8960654000");
  const step = BigInt(axis.step);
  const decade = 10n ** BigInt(String(step).length - 1);
  assert.ok([1n, 2n, 5n, 10n].includes(step / decade), `step ${step} is off the 1-2-5 ladder`);
});

test("no headroom is added when none is asked for", () => {
  const withRoom = chooseCurveCeiling("1000000", { headroomPercent: 15 });
  const without = chooseCurveCeiling("1000000", { headroomPercent: 0 });
  assert.ok(BigInt(withRoom.ceiling) > BigInt(without.ceiling));
});

test("both series climb period by period and never fall back", () => {
  const view = buildCostCurve({ points: cumulative([[100, 200], [300, 250], [50, 300]]) });
  const climbs = (series) => series.every((point, index) => index === 0 || point.y >= series[index - 1].y);
  assert.ok(climbs(view.actual), "actual must be monotone");
  assert.ok(climbs(view.plan), "plan must be monotone");
  assert.equal(view.actual.at(-1).valueIrr, "450", "last actual is the running total");
  assert.equal(view.plan.at(-1).valueIrr, "750", "last plan is the running total");
});

test("the smoothing never dips below a segment it connects", () => {
  // A cardinal spline overshoots here and draws spending going backwards before
  // the steep month. Monotone interpolation is the reason this passes.
  const series = [{ x: 0, y: 0 }, { x: 25, y: 1 }, { x: 50, y: 2 }, { x: 75, y: 60 }, { x: 100, y: 62 }];
  const path = curvePath(series);
  const controlYs = [...path.matchAll(/C ([\d.-]+) ([\d.-]+), ([\d.-]+) ([\d.-]+)/g)]
    .flatMap((match) => [Number(match[2]), Number(match[4])]);
  assert.ok(controlYs.every((y) => y >= -0.01), `a control point dipped below the baseline: ${Math.min(...controlYs)}`);
  assert.ok(controlYs.every((y) => y <= 62.01), "a control point overshot the peak");
});

test("a period the project has not reached yet stops the actual curve, not the plan", () => {
  const points = cumulative([[100, 200], [300, 250]]).concat([
    { key: "1405-03", label: "خرداد", shortLabel: "خرد", fullLabel: "خرداد ۱۴۰۵", actualIrr: null, estimateIrr: "900" },
  ]);
  const view = buildCostCurve({ points });
  assert.equal(view.actual.length, 2, "actual stops where the record stops");
  assert.equal(view.plan.length, 3, "plan carries on alone");
  assert.equal(view.marker.valueIrr, "400", "the marker sits on the last recorded total");
});

test("a missing plan is reported rather than drawn as zero", () => {
  const view = buildCostCurve({ points: cumulative([[100, null], [300, null]]) });
  assert.equal(view.hasPlan, false);
  assert.equal(view.planPath, "");
  assert.ok(view.hasActual, "the actual is still drawn");
});

test("the filled area closes onto the baseline, not onto the plan", () => {
  const view = buildCostCurve({ points: cumulative([[100, 200], [300, 250]]) });
  assert.ok(view.areaPath.startsWith(view.actualPath), "the area's top edge is the curve itself");
  assert.ok(/ L [\d.]+ 0 L [\d.]+ 0 Z$/.test(view.areaPath), "the area closes at zero");
});

test("an empty series produces nothing to draw rather than a broken axis", () => {
  const view = buildCostCurve({ points: [] });
  assert.equal(view.isEmpty, true);
  assert.deepEqual(view.ticks, []);
  assert.equal(view.marker, null);
});

test("every drawn point stays inside the plot", () => {
  const view = buildCostCurve({ points: cumulative([[900, 100], [900, 100], [900, 100]]) });
  const inside = (point) => point.x >= 0 && point.x <= 100 && point.y >= 0 && point.y <= 100;
  assert.ok(view.actual.every(inside), "an overrun must stay under the ceiling");
  assert.ok(view.plan.every(inside));
});

test("money is never rounded on its way to the chart", () => {
  const view = buildCostCurve({ points: cumulative([["123456789", "987654321"]]) });
  assert.equal(view.actual[0].valueIrr, "123456789");
  assert.equal(view.plan[0].valueIrr, "987654321");
});
