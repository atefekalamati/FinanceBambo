import test from "node:test";
import assert from "node:assert/strict";
import { CURRENCY_LABELS } from "../../src/shared/constants/currency.js";
import { validateEstimateLine, validateEstimateRevision, validateResource } from "../../src/features/financial-items/financial-items-validation.js";

test("supports the three financial item types", () => {
  // Three since 0038: `work` is what the PRD's labour and equipment became.
  for (const type of ["material", "work", "general_cost"]) {
    const result = validateResource({ type, title: "قلم نمونه", code: `CODE-${type}`, baseUnit: "kg" });
    assert.equal(result.valid, true, type);
  }
});

test("allows general cost without a physical unit", () => {
  const result = validateResource({ type: "general_cost", title: "هزینه مجوز", code: "GEN-01", baseUnit: "" });
  assert.equal(result.valid, true);
  assert.equal(result.values.baseUnit, null);
  assert.equal("dimension" in result.values, false);
});

test("requires only a registry unit for quantity-based resources", () => {
  const result = validateResource({ type: "material", title: "میلگرد", code: "MAT-01", baseUnit: "" });
  assert.equal(result.valid, false);
  assert.match(result.errors.baseUnit, /واحد/);
  assert.equal("dimension" in result.errors, false);
});

test("keeps estimate quantity as an exact decimal string", () => {
  const result = validateEstimateLine({ activityExternalId: "ACT-01", resourceId: "resource-01", originalQuantity: "۱٬۲۵۰٫۵۰۰۰", originalUnitPriceIRR: "285000" });
  assert.equal(result.valid, true);
  assert.equal(result.values.originalQuantity, "1250.5000");
  assert.equal(result.values.originalUnitPriceIRR, "285000");
});

test("a quantified line requires the unit price its estimate was fixed at", () => {
  const missing = validateEstimateLine({ activityExternalId: "ACT-01", resourceId: "resource-01", originalQuantity: "10.0000" });
  assert.equal(missing.valid, false);
  assert.match(missing.errors.originalUnitPriceIRR, /قیمت واحد اولیه/);

  const general = validateEstimateLine({ activityExternalId: "ACT-01", resourceId: "resource-01", originalQuantity: "250000000" }, { isGeneralCost: true });
  assert.equal(general.valid, true, "a general-cost line carries an amount, not a unit price");
  assert.equal(general.values.originalUnitPriceIRR, null);
});

test("requires an audited reason for estimate revisions", () => {
  const result = validateEstimateRevision({ revisedValue: "1200.0000", reason: "" });
  assert.equal(result.valid, false);
  assert.match(result.errors.reason, /دلیل/);
});

test("rejects fractional IRR general-cost revisions", () => {
  const result = validateEstimateRevision({ revisedValue: "1000.50", reason: "اصلاح مبلغ" }, { isGeneralCost: true });
  assert.equal(result.valid, false);
  assert.match(result.errors.revisedValue, /حداکثر یک رقم اعشار/);
});

test("rejects a zero fractional part for integer IRR general costs", () => {
  const result = validateEstimateRevision({ revisedValue: "100.0", reason: "اصلاح مبلغ" }, { isGeneralCost: true });
  assert.equal(result.valid, false);
  assert.match(result.errors.revisedValue, new RegExp(CURRENCY_LABELS.TOMAN));
});
