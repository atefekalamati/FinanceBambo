import test from "node:test";
import assert from "node:assert/strict";
import { buildBreakdownPresentation, buildOverviewComparisons } from "../../src/features/finance-home/report-presentation.js";

test("builds breakdown bars with one exact shared scale", () => {
  const rows = buildBreakdownPresentation([
    { resourceType: "material", initialEstimateIrr: "100000000000000001", actualCostIrr: "50000000000000000", forecastFinalIrr: "75000000000000000" },
    { resourceType: "labor", initialEstimateIrr: "25000000000000000", actualCostIrr: "10000000000000000", forecastFinalIrr: "40000000000000000" },
  ]);
  assert.equal(rows[0].bars.initial, 100);
  assert.equal(rows[0].bars.actual, 49.99);
  assert.equal(rows[1].bars.initial, 24.99);
  assert.equal(rows[0].label, "مصالح");
});

test("uses absolute magnitude for negative financial effects without changing display values", () => {
  const [row] = buildBreakdownPresentation([{ resourceType: "general_cost", initialEstimateIrr: "100", actualCostIrr: "-50", forecastFinalIrr: "25" }]);
  assert.equal(row.actualCostIrr, "-50");
  assert.equal(row.bars.actual, 50);
  assert.equal(row.label, "هزینه‌های عمومی پروژه");
});

test("returns zero-width bars for an all-zero breakdown", () => {
  const [row] = buildBreakdownPresentation([{ resourceType: "equipment", initialEstimateIrr: "0", actualCostIrr: "0", forecastFinalIrr: "0" }]);
  assert.deepEqual(row.bars, { initial: 0, actual: 0 });
});

test("preserves optional revised estimate and remaining breakdown values", () => {
  const [row] = buildBreakdownPresentation([{
    resourceType: "material",
    initialEstimateIrr: "100",
    revisedEstimateIrr: "125",
    actualCostIrr: "40",
    remainingPhysicalCostIrr: "85",
    forecastFinalIrr: "125",
  }]);
  assert.equal(row.revisedEstimateIrr, "125");
  assert.equal(row.remainingPhysicalCostIrr, "85");
});

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
