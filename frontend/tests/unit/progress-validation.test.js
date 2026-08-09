import test from "node:test";
import assert from "node:assert/strict";
import { calculateProgressDeviation, validateProgressOverride } from "../../src/features/progress/progress-validation.js";

test("validates and normalizes a progress override without floating point", () => {
  const result = validateProgressOverride({ value: "۲٬۶۰۰٫۵۰۰۰", reason: " اصلاح صورت‌جلسه ", plannedQuantity: "10000.0000" });
  assert.equal(result.valid, true);
  assert.equal(result.value, "2600.5000");
  assert.equal(result.reason, "اصلاح صورت‌جلسه");
  assert.equal(result.exceedsPlan, false);
});

test("requires a positive value and audited reason", () => {
  const result = validateProgressOverride({ value: "0", reason: " ", plannedQuantity: "100" });
  assert.equal(result.valid, false);
  assert.ok(result.errors.value);
  assert.ok(result.errors.reason);
});

test("allows an override above plan and returns an explicit warning flag", () => {
  const result = validateProgressOverride({ value: "100.0001", reason: "مقدار تاییدشده کارگاه", plannedQuantity: "100.0000" });
  assert.equal(result.valid, true);
  assert.equal(result.exceedsPlan, true);
  assert.deepEqual(result.deviation, { amount: "0.0001", percent: "0.0001" });
});

test("calculates deviation amount and rounded percentage with exact integers", () => {
  assert.deepEqual(calculateProgressDeviation("125.5000", "100.0000"), { amount: "25.5", percent: "25.5" });
  assert.deepEqual(calculateProgressDeviation("1.0001", "1.0000"), { amount: "0.0001", percent: "0.01" });
  assert.equal(calculateProgressDeviation("99.9999", "100.0000"), null);
});

test("marks deviation percentage unavailable when planned quantity is zero", () => {
  assert.deepEqual(calculateProgressDeviation("5.0000", "0.0000"), { amount: "5", percent: null });
});
