import test from "node:test";
import assert from "node:assert/strict";
import { validateInvoiceAdjustments, validateInvoiceHeader, validateInvoiceLine } from "../../src/features/invoices/invoices-validation.js";

test("validates a complete manual invoice header", () => {
  const result = validateInvoiceHeader({ invoiceNumber: " ف-۱۰۰ ", invoiceDate: "2026-08-09", vendorName: " فروشنده نمونه ", description: " خرید نمونه " });
  assert.equal(result.valid, true);
  assert.equal(result.values.vendorName, "فروشنده نمونه");
});

test("validates estimate and general-cost invoice lines independently", () => {
  const estimate = validateInvoiceLine({ quantity: "۱٫۲۵", unitPriceIRR: "۸۰۰۰۰", description: "" }, { targetId: "e1", targetType: "estimate_line", label: "میلگرد", unit: "kg" });
  const general = validateInvoiceLine({ amountIRR: "۱۲٬۰۰۰٬۰۰۰", description: "مجوز" }, { targetId: "g1", targetType: "general_cost", label: "مجوز", unit: null });
  assert.equal(estimate.valid, true);
  assert.equal(estimate.values.quantity, "1.25");
  assert.equal(estimate.values.unitPriceIRR, "80000");
  assert.equal(general.valid, true);
  assert.equal(general.values.lineAmountIRR, "12000000");
});

test("rejects fractional IRR adjustments", () => {
  const result = validateInvoiceAdjustments({ discountIRR: "100.5", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" });
  assert.equal(result.valid, false);
  assert.ok(result.errors.discountIRR);
});
