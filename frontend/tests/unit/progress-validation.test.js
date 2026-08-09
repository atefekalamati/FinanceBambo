import test from "node:test";
import assert from "node:assert/strict";
import { validateProgressOverride } from "../../src/features/progress/progress-validation.js";

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
});
