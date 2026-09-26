import test from "node:test";
import assert from "node:assert/strict";

import { RESOURCE_TYPES, canonicalResourceType, foldLegacyTypes, resourceTypeLabel }
  from "../../src/shared/resource-types.js";
import { buildBreakdownComparison } from "../../src/shared/reports/period-comparison.js";

/* THREE KINDS, AND THE TWO OLD NAMES READ AS ONE OF THEM.
 *
 * The service merged `labor` and `equipment` into `work` on 2026-09-26 (migration 0038)
 * and rewrote no row: what was stored keeps its old word, and an issued report snapshot
 * is frozen with it. So the frontend meets both vocabularies, and this is the one place
 * that says what to make of the old one.
 */

test("the kinds are exactly three", () => {
  assert.deepEqual([...RESOURCE_TYPES], ["material", "work", "general_cost"]);
});

test("labor and equipment are work; everything else passes through", () => {
  assert.equal(canonicalResourceType("labor"), "work");
  assert.equal(canonicalResourceType("equipment"), "work");
  assert.equal(canonicalResourceType("material"), "material");
  assert.equal(canonicalResourceType(null), null, "an unclassified resource is not quietly work");
});

test("the old names get the new label, not a blank", () => {
  assert.equal(resourceTypeLabel("labor"), "نیرو و تجهیزات");
  assert.equal(resourceTypeLabel("equipment"), "نیرو و تجهیزات");
  assert.equal(resourceTypeLabel("work"), "نیرو و تجهیزات");
  assert.equal(resourceTypeLabel("budget"), null);
});

test("two old rows fold into one work row, summed exactly", () => {
  const folded = foldLegacyTypes([
    { resourceType: "material", actualCostIrr: "10" },
    { resourceType: "labor", actualCostIrr: "9007199254740993", forecastFinalIrr: null },
    { resourceType: "equipment", actualCostIrr: "1", forecastFinalIrr: "5" },
  ], ["actualCostIrr", "forecastFinalIrr"]);
  assert.deepEqual(folded, [
    { resourceType: "material", actualCostIrr: "10" },
    /* Past 2^53, so a float would have rounded it: the sum is exact. A null beside a
       number is the number, and two nulls stay null. */
    { resourceType: "work", actualCostIrr: "9007199254740994", forecastFinalIrr: "5" },
  ]);
});

/* THE COMPARISON ACROSS THE MERGE.
 *
 * Opening: a snapshot issued before 0038, with a labour row and an equipment row.
 * Closing: today's live report, with one work row. Without folding, the table would show
 * «نیروی انسانی» and «تجهیزات» vanishing and «نیرو و تجهیزات» appearing from nothing.
 */
test("an old snapshot compares against a new report kind for kind", () => {
  const rows = buildBreakdownComparison({
    opening: [{ resourceType: "labor", actualCostIrr: "300" },
              { resourceType: "equipment", actualCostIrr: "200" },
              { resourceType: "material", actualCostIrr: "1000" }],
    closing: [{ resourceType: "work", actualCostIrr: "900" },
              { resourceType: "material", actualCostIrr: "1000" }],
  });
  const work = rows.find((row) => row.resourceType === "work");
  assert.ok(work, "one work row, not three rows");
  assert.equal(work.label, "نیرو و تجهیزات");
  /* Exact integer rials travel as strings, as everywhere in the reports. */
  assert.equal(work.measures.actualCostIrr.openingIrr, "500");
  assert.equal(work.measures.actualCostIrr.closingIrr, "900");
  assert.equal(work.measures.actualCostIrr.changeIrr, "400");
  assert.deepEqual(rows.map((row) => row.resourceType).sort(), ["material", "work"]);
});
