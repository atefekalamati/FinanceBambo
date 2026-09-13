import { normalizeDecimalInput, validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";

/**
 * The header a person fills in. No invoice number: the service allocates it per project
 * when the invoice is written, and a number typed here would be discarded by the Backend
 * -- which refuses the field outright rather than accepting and ignoring it.
 */
export function validateInvoiceHeader(values) {
  const normalized = {
    invoiceDate: String(values.invoiceDate ?? ""),
    vendorName: String(values.vendorName ?? "").trim(),
    description: String(values.description ?? "").trim(),
  };
  const errors = {};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized.invoiceDate)) errors.invoiceDate = "تاریخ فاکتور را انتخاب کنید.";
  if (normalized.vendorName.length < 2) errors.vendorName = "نام فروشنده یا ارائه‌دهنده الزامی است.";
  return { valid: Object.keys(errors).length === 0, errors, values: normalized };
}

export function validateInvoiceLine(values, target) {
  const errors = {};
  const description = String(values.description ?? "").trim();
  if (!target) errors.targetId = "اتصال مالی خط را انتخاب کنید.";
  if (target?.targetType === "general_cost") {
    const amountIRR = normalizeDecimalInput(values.amountIRR);
    if (!/^\d+$/.test(amountIRR) || !/[1-9]/.test(amountIRR)) errors.amountIRR = `مبلغ خط باید مقدار مثبت و معتبر ${getDisplayCurrencyLabel()} باشد.`;
    return { valid: Object.keys(errors).length === 0, errors, values: { targetId: target?.targetId ?? "", targetType: target?.targetType ?? "", targetLabel: target?.label ?? "", quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: amountIRR, description } };
  }
  const quantity = validatePositiveDecimal(values.quantity, { precision: 4, requiredMessage: "مقدار خط الزامی است.", invalidMessage: "مقدار باید مثبت و حداکثر چهار رقم اعشار باشد." });
  const unitPriceIRR = normalizeDecimalInput(values.unitPriceIRR);
  if (!quantity.valid) errors.quantity = quantity.message;
  if (!/^\d+$/.test(unitPriceIRR) || !/[1-9]/.test(unitPriceIRR)) errors.unitPriceIRR = `قیمت واحد باید مقدار مثبت و معتبر ${getDisplayCurrencyLabel()} باشد.`;
  return { valid: Object.keys(errors).length === 0, errors, values: { targetId: target?.targetId ?? "", targetType: target?.targetType ?? "", targetLabel: target?.label ?? "", quantity: quantity.value, unit: target?.unit ?? null, unitPriceIRR, lineAmountIRR: "", description } };
}

export function validateInvoiceAdjustments(values) {
  const errors = {};
  const normalized = {};
  for (const key of ["discountIRR", "taxIRR", "shippingIRR", "otherCostsIRR"]) {
    const value = normalizeDecimalInput(values[key] || "0");
    if (!/^\d+$/.test(value)) errors[key] = `مبلغ تعدیل باید مقدار نامنفی و معتبر ${getDisplayCurrencyLabel()} باشد.`;
    normalized[key] = value;
  }
  return { valid: Object.keys(errors).length === 0, errors, values: normalized };
}
