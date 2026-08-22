import test from "node:test";
import assert from "node:assert/strict";
import { buildPriceVariancePresentation, buildQuantityVariancePresentation } from "../../src/features/reports/report-analysis.js";

test("builds exact price-impact bars and preserves increase or decrease direction", () => {
  const rows = buildPriceVariancePresentation([
    { resourceType: "material", resourceTitle: "میلگرد", varianceIrr: "100000000000000001" },
    { resourceType: "equipment", resourceTitle: "جرثقیل", varianceIrr: "-50000000000000000" },
  ]);
  assert.equal(rows[0].magnitude, 100);
  assert.equal(rows[1].magnitude, 49.99);
  assert.equal(rows[0].direction, "increase");
  assert.equal(rows[1].direction, "decrease");
  assert.equal(rows[1].varianceIrr, "-50000000000000000");
});

test("keeps quantity deviations exact and labels their resource type", () => {
  const [row] = buildQuantityVariancePresentation([
    { resourceType: "labor", resourceTitle: "قالب‌بندی", varianceQuantity: "125.7500" },
  ]);
  assert.equal(row.varianceQuantity, "125.7500");
  assert.equal(row.resourceTypeLabel, "نیروی انسانی");
});
