import test from "node:test";
import assert from "node:assert/strict";
import { validateUnitConversion } from "../../src/features/prices/unit-conversions-validation.js";

test("accepts an exact same-dimension conversion factor", () => {
  const result = validateUnitConversion({ sourceUnit: "ton", targetUnit: "kg", factor: "۱٬۰۰۰٫۰۰۰۰۰۰", scope: "organization", effectiveDate: "2026-08-08" });
  assert.equal(result.valid, true);
  assert.equal(result.values.factor, "1000.000000");
});

test("rejects conversions between incompatible dimensions", () => {
  const result = validateUnitConversion({ sourceUnit: "ton", targetUnit: "hour", factor: "1", scope: "project", effectiveDate: "2026-08-08" });
  assert.equal(result.valid, false);
  assert.match(result.errors.dimension, /ناسازگار/);
});

test("rejects identical units and factor precision over six decimals", () => {
  const result = validateUnitConversion({ sourceUnit: "kg", targetUnit: "kg", factor: "1.0000001", scope: "organization", effectiveDate: "2026-08-08" });
  assert.equal(result.valid, false);
  assert.ok(result.errors.targetUnit);
  assert.ok(result.errors.factor);
});
