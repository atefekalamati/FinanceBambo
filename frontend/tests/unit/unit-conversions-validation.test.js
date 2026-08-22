import test from "node:test";
import assert from "node:assert/strict";
import {
  getCompatibleTargetUnits,
  getConversionDimension,
  getUnitDefinition,
  getUnitOptions,
  setUnitRegistry,
  validateUnitConversion,
} from "../../src/features/prices/unit-conversions-validation.js";

/**
 * The unit codes here are the ones the Backend UNIT_REGISTRY defines. The
 * Frontend previously invented `person_hour` and `equipment_day`, which the API
 * rejects with UNIT_NOT_FOUND, so these tests pin the shared vocabulary.
 */

test("the default vocabulary matches the Backend registry", () => {
  assert.deepEqual(
    getUnitOptions().map((unit) => unit.value).sort(),
    ["day", "each", "hour", "kg", "m", "m2", "m3", "ton"],
  );
  assert.equal(getUnitDefinition("hour").dimension, "time");
  assert.equal(getUnitDefinition("day").dimension, "equipment_time");
  assert.equal(getUnitDefinition("person_hour"), null, "an invented code must not resolve");
  assert.equal(getUnitDefinition("equipment_day"), null);
});

test("offers only the destination units the Backend will accept", () => {
  assert.deepEqual(getCompatibleTargetUnits("ton").map((unit) => unit.value), ["kg"]);
  assert.deepEqual(getCompatibleTargetUnits("day").map((unit) => unit.value), ["hour"]);
  assert.deepEqual(getCompatibleTargetUnits("kg"), []);
  assert.deepEqual(getCompatibleTargetUnits("hour"), []);
  assert.deepEqual(getCompatibleTargetUnits("unknown"), []);
});

test("sends the dimension the pair needs, not just the source unit's own", () => {
  // units_are_compatible allows ("day","hour","equipment_time") even though
  // hour's own dimension is time; sending "time" here is refused as a mismatch.
  assert.equal(getConversionDimension("day", "hour"), "equipment_time");
  assert.equal(getConversionDimension("ton", "kg"), "mass");
});

test("rejects reverse conversions", () => {
  const mass = validateUnitConversion({ sourceUnit: "kg", targetUnit: "ton", factor: "1000", scope: "organization", effectiveDate: "2026-08-08" });
  const workingTime = validateUnitConversion({ sourceUnit: "hour", targetUnit: "day", factor: "8", scope: "project", effectiveDate: "2026-08-08" });
  assert.equal(mass.valid, false);
  assert.match(mass.errors.direction, /جهت تبدیل مجاز نیست/);
  assert.equal(workingTime.valid, false);
  assert.match(workingTime.errors.direction, /جهت تبدیل مجاز نیست/);
});

test("accepts an exact configurable working-time conversion factor", () => {
  const result = validateUnitConversion({ sourceUnit: "day", targetUnit: "hour", factor: "۸٫۵۰۰۰۰۰", scope: "organization", effectiveDate: "2026-08-08" });
  assert.equal(result.valid, true);
  assert.equal(result.values.factor, "8.500000");
});

test("rejects changing a fixed physical conversion", () => {
  const result = validateUnitConversion({ sourceUnit: "ton", targetUnit: "kg", factor: "1500", scope: "project", effectiveDate: "2026-08-08" });
  assert.equal(result.valid, false);
  assert.match(result.errors.policy, /ثابت است و قابل تغییر نیست/);
});

test("rejects conversions between genuinely incompatible dimensions", () => {
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

test("the live registry from the service replaces the defaults", () => {
  const before = getUnitOptions();
  setUnitRegistry([
    { code: "kg", label: "کیلوگرم", dimension: "mass", dimensionLabel: "جرم" },
    { code: "litre", label: "لیتر", dimension: "volume", dimensionLabel: "حجم" },
  ]);
  assert.deepEqual(getUnitOptions().map((unit) => unit.value), ["kg", "litre"]);
  assert.equal(getUnitDefinition("litre").dimension, "volume");

  setUnitRegistry([]);
  assert.deepEqual(getUnitOptions().map((unit) => unit.value), ["kg", "litre"], "an empty payload must not blank the vocabulary");

  setUnitRegistry(before.map((unit) => ({ code: unit.value, label: unit.label, dimension: unit.dimension, dimensionLabel: unit.dimensionLabel })));
  assert.deepEqual(getUnitOptions().map((unit) => unit.value), before.map((unit) => unit.value));
});
