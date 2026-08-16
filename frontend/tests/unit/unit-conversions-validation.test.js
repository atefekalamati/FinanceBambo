import test from "node:test";
import assert from "node:assert/strict";
import { getCompatibleTargetUnits, validateUnitConversion } from "../../src/features/prices/unit-conversions-validation.js";

test("offers only same-dimension destination units and excludes the source", () => {
  assert.deepEqual(getCompatibleTargetUnits("ton").map((unit) => unit.value), ["kg"]);
  assert.deepEqual(getCompatibleTargetUnits("equipment_day").map((unit) => unit.value), ["hour"]);
  assert.deepEqual(getCompatibleTargetUnits("kg"), []);
  assert.deepEqual(getCompatibleTargetUnits("hour"), []);
  assert.deepEqual(getCompatibleTargetUnits("unknown"), []);
});

test("rejects reverse conversions even when both units share a dimension", () => {
  const mass = validateUnitConversion({ sourceUnit: "kg", targetUnit: "ton", factor: "1000", scope: "organization", effectiveDate: "2026-08-08" });
  const equipmentTime = validateUnitConversion({ sourceUnit: "hour", targetUnit: "equipment_day", factor: "8", scope: "project", effectiveDate: "2026-08-08" });
  assert.equal(mass.valid, false);
  assert.match(mass.errors.direction, /جهت تبدیل مجاز نیست/);
  assert.equal(equipmentTime.valid, false);
  assert.match(equipmentTime.errors.direction, /جهت تبدیل مجاز نیست/);
});

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
