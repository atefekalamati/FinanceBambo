import test from "node:test";
import assert from "node:assert/strict";
import { addExactDecimal, rollupPriceVariances, rollupQuantityVariances } from "../../src/shared/variances/variance-rollup.js";
import { buildPriceVariancePresentation, buildQuantityVariancePresentation } from "../../src/features/reports/report-analysis.js";

// The shape the service actually answers with: one row per estimate line, and
// the same item appearing on two activities.
const PRICE_ROWS = Object.freeze([
  { varianceKind: "price", estimateLineId: "line-1", resourceId: "rebar", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", activityExternalId: "ACT-102", baseUnit: "kg", varianceIrr: "2642500000", currentUnitPriceIrr: "302000", priceAvailable: true },
  { varianceKind: "price", estimateLineId: "line-2", resourceId: "rebar", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", activityExternalId: "ACT-201", baseUnit: "kg", varianceIrr: "2552504000", currentUnitPriceIrr: "302000", priceAvailable: true },
  { varianceKind: "price", estimateLineId: "line-4", resourceId: "crane", resourceCode: "EQ-CRANE", resourceTitle: "جرثقیل", resourceType: "equipment", activityExternalId: "ACT-201", baseUnit: "hour", varianceIrr: "1400000000", priceAvailable: true },
]);

const QUANTITY_ROWS = Object.freeze([
  { estimateLineId: "line-1", resourceId: "rebar", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", baseUnit: "kg", initialQuantity: "10000.0000", revisedQuantity: "11250.0000", varianceQuantity: "1250.0000" },
  { estimateLineId: "line-2", resourceId: "rebar", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", baseUnit: "kg", initialQuantity: "8500.0000", revisedQuantity: "8500.0000", varianceQuantity: "0.0000" },
  { estimateLineId: "line-3", resourceId: "form", resourceCode: "LAB-FORM", resourceTitle: "اکیپ قالب‌بندی", resourceType: "labor", baseUnit: "person_hour", initialQuantity: "900.0000", revisedQuantity: "980.0000", varianceQuantity: "80.0000" },
  { estimateLineId: "line-4", resourceId: "crane", resourceCode: "EQ-CRANE", resourceTitle: "جرثقیل", resourceType: "equipment", baseUnit: "hour", initialQuantity: "160.0000", revisedQuantity: "160.0000", varianceQuantity: "0.0000" },
]);

test("an item used on two activities is one row, not two", () => {
  const rolled = rollupPriceVariances(PRICE_ROWS);
  assert.deepEqual(rolled.map((row) => row.resourceCode), ["MAT-REBAR", "EQ-CRANE"]);
  const rebar = rolled[0];
  // 2642500000 + 2552504000, added as integers.
  assert.equal(rebar.varianceIrr, "5195004000");
  assert.equal(rebar.lineCount, 2);
  // A folded row is not a line and must not claim to be one: a link built from
  // it would otherwise deep-link to whichever line happened to arrive first.
  assert.equal(rebar.estimateLineId, null);
  assert.equal(rebar.activityExternalId, null);
  assert.equal(rebar.resourceId, "rebar");
});

test("an item whose figures never moved is not a deviation", () => {
  const rolled = rollupQuantityVariances(QUANTITY_ROWS);
  // میلگرد keeps its +1250 from one line and 0 from the other; جرثقیل is 0 on
  // its only line and drops out of a card that lists the largest deviations.
  assert.deepEqual(rolled.map((row) => [row.resourceCode, row.varianceQuantity]), [
    ["MAT-REBAR", "1250.0000"],
    ["LAB-FORM", "80.0000"],
  ]);
  assert.equal(rollupQuantityVariances([{ resourceId: "a", varianceQuantity: "0" }]).length, 0);
  assert.equal(rollupQuantityVariances([]).length, 0);
  assert.equal(rollupQuantityVariances(undefined).length, 0);
});

test("rows are ordered by how far they moved, whichever way", () => {
  const rolled = rollupPriceVariances([
    { resourceId: "a", resourceCode: "A", varianceIrr: "100" },
    { resourceId: "b", resourceCode: "B", varianceIrr: "-900" },
    { resourceId: "c", resourceCode: "C", varianceIrr: "400" },
  ]);
  // A saving of 900 is a bigger deviation than an overrun of 400.
  assert.deepEqual(rolled.map((row) => row.resourceCode), ["B", "C", "A"]);
});

test("two lines of one item cancelling out drop the item entirely", () => {
  const rolled = rollupPriceVariances([
    { resourceId: "a", resourceCode: "A", varianceIrr: "500000" },
    { resourceId: "a", resourceCode: "A", varianceIrr: "-500000" },
  ]);
  assert.deepEqual(rolled, []);
});

test("quantities in different units are never added together", () => {
  // Summing hours into kilograms would produce a number that means nothing, so
  // the two stay visible as two rows rather than being silently merged.
  const rolled = rollupQuantityVariances([
    { resourceId: "a", resourceCode: "A", baseUnit: "kg", varianceQuantity: "10.0000" },
    { resourceId: "a", resourceCode: "A", baseUnit: "hour", varianceQuantity: "4.0000" },
  ]);
  assert.equal(rolled.length, 2);
  assert.deepEqual(rolled.map((row) => [row.baseUnit, row.varianceQuantity]), [["kg", "10.0000"], ["hour", "4.0000"]]);
});

test("the arithmetic is exact at magnitudes and precisions a float would lose", () => {
  // Nine hundred trillion rial: Number.MAX_SAFE_INTEGER is nine quadrillion, and
  // a float starts skipping integers long before a sum of these does.
  const rolled = rollupPriceVariances([
    { resourceId: "a", varianceIrr: "9007199254740993" },
    { resourceId: "a", varianceIrr: "1" },
  ]);
  assert.equal(rolled[0].varianceIrr, "9007199254740994");
  // 0.1 + 0.2 is famously not 0.3 in binary floating point.
  assert.equal(addExactDecimal("0.1", "0.2"), "0.3");
  assert.equal(addExactDecimal("1250.0000", "0.5"), "1250.5000");
  assert.equal(addExactDecimal("-2642500000", "2552504000"), "-89996000");
  // A value that is not a number at all contributes nothing rather than NaN.
  assert.equal(addExactDecimal("۱۲۳", "1"), "1");
  assert.equal(addExactDecimal(null, null), null);
});

test("the totals that travel with a folded row are the item's, not one line's", () => {
  const rolled = rollupQuantityVariances([
    { resourceId: "a", baseUnit: "kg", varianceQuantity: "10.0000", initialQuantity: "100.0000", revisedQuantity: "110.0000", remainingPhysicalCostIrr: "500" },
    { resourceId: "a", baseUnit: "kg", varianceQuantity: "5.0000", initialQuantity: "50.0000", revisedQuantity: "55.0000", remainingPhysicalCostIrr: "250" },
  ]);
  assert.equal(rolled[0].varianceQuantity, "15.0000");
  assert.equal(rolled[0].initialQuantity, "150.0000");
  assert.equal(rolled[0].revisedQuantity, "165.0000");
  assert.equal(rolled[0].remainingPhysicalCostIrr, "750");
});

test("both report tables show the folded rows, and scale their bars to them", () => {
  const priced = buildPriceVariancePresentation(PRICE_ROWS);
  assert.deepEqual(priced.map((row) => row.resourceCode), ["MAT-REBAR", "EQ-CRANE"]);
  // The tallest bar is the item's total, not the largest single line — otherwise
  // the folded leader would overflow the track it is scaled against.
  assert.equal(priced[0].magnitude, 100);
  assert.ok(priced[1].magnitude < 100);
  assert.equal(priced[0].direction, "increase");
  const quantities = buildQuantityVariancePresentation(QUANTITY_ROWS);
  assert.deepEqual(quantities.map((row) => row.resourceCode), ["MAT-REBAR", "LAB-FORM"]);
  quantities.forEach((row) => assert.notEqual(Number(row.varianceQuantity), 0, "a zero deviation reached a table of largest deviations"));
});
