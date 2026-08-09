import test from "node:test";
import assert from "node:assert/strict";
import { validateEstimateLine, validateEstimateRevision, validateResource } from "../../src/features/financial-items/financial-items-validation.js";

test("supports the four PRD financial item types", () => {
  for (const type of ["material", "labor", "equipment", "general_cost"]) {
    const result = validateResource({ type, title: "قلم نمونه", code: `CODE-${type}`, baseUnit: "kg", dimension: "جرم" });
    assert.equal(result.valid, true, type);
  }
});

test("allows general cost without a physical unit or dimension", () => {
  const result = validateResource({ type: "general_cost", title: "هزینه مجوز", code: "GEN-01", baseUnit: "", dimension: "" });
  assert.equal(result.valid, true);
  assert.equal(result.values.baseUnit, null);
  assert.equal(result.values.dimension, null);
});

test("requires unit and dimension for quantity-based resources", () => {
  const result = validateResource({ type: "material", title: "میلگرد", code: "MAT-01", baseUnit: "", dimension: "" });
  assert.equal(result.valid, false);
  assert.match(result.errors.baseUnit, /واحد/);
  assert.match(result.errors.dimension, /بُعد/);
});

test("keeps estimate quantity as an exact decimal string", () => {
  const result = validateEstimateLine({ activityExternalId: "ACT-01", resourceId: "resource-01", originalQuantity: "۱٬۲۵۰٫۵۰۰۰" });
  assert.equal(result.valid, true);
  assert.equal(result.values.originalQuantity, "1250.5000");
});

test("requires an audited reason for estimate revisions", () => {
  const result = validateEstimateRevision({ revisedValue: "1200.0000", reason: "" });
  assert.equal(result.valid, false);
  assert.match(result.errors.reason, /دلیل/);
});

test("rejects fractional IRR general-cost revisions", () => {
  const result = validateEstimateRevision({ revisedValue: "1000.50", reason: "اصلاح مبلغ" }, { isGeneralCost: true });
  assert.equal(result.valid, false);
  assert.match(result.errors.revisedValue, /عدد صحیح/);
});

test("rejects a zero fractional part for integer IRR general costs", () => {
  const result = validateEstimateRevision({ revisedValue: "100.0", reason: "اصلاح مبلغ" }, { isGeneralCost: true });
  assert.equal(result.valid, false);
  assert.match(result.errors.revisedValue, /عدد صحیح ریال/);
});
