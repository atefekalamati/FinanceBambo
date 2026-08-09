import test from "node:test";
import assert from "node:assert/strict";
import { validatePriceVersion } from "../../src/features/prices/prices-validation.js";

test("accepts an exact positive integer IRR price", () => {
  const result = validatePriceVersion({ resourceId: "resource-1", scope: "project", unitPriceIRR: "۱۲۵٬۰۰۰", effectiveFrom: "2026-08-08" });
  assert.equal(result.valid, true);
  assert.equal(result.values.unitPriceIRR, "125000");
});

test("rejects fractional prices, invalid scope and impossible dates", () => {
  const result = validatePriceVersion({ resourceId: "", scope: "other", unitPriceIRR: "12.5", effectiveFrom: "2026-02-30" });
  assert.equal(result.valid, false);
  assert.ok(result.errors.resourceId);
  assert.ok(result.errors.scope);
  assert.ok(result.errors.unitPriceIRR);
  assert.ok(result.errors.effectiveFrom);
});
