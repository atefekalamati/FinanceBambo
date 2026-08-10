import { normalizeDecimalInput, validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";

export function validateInvoiceHeader(values) {
  const normalized = {
    invoiceNumber: String(values.invoiceNumber ?? "").trim(),
    invoiceDate: String(values.invoiceDate ?? ""),
    vendorName: String(values.vendorName ?? "").trim(),
    description: String(values.description ?? "").trim(),
  };
  const errors = {};
  if (!normalized.invoiceNumber) errors.invoiceNumber = "شماره فاکتور الزامی است.";
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
    if (!/^\d+$/.test(amountIRR) || !/[1-9]/.test(amountIRR)) errors.amountIRR = `مبلغ خط باید عدد صحیح و مثبت ${CURRENCY_LABELS.IRR} باشد.`;
    return { valid: Object.keys(errors).length === 0, errors, values: { targetId: target?.targetId ?? "", targetType: target?.targetType ?? "", targetLabel: target?.label ?? "", quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: amountIRR, description } };
  }
  const quantity = validatePositiveDecimal(values.quantity, { precision: 4, requiredMessage: "مقدار خط الزامی است.", invalidMessage: "مقدار باید مثبت و حداکثر چهار رقم اعشار باشد." });
  const unitPriceIRR = normalizeDecimalInput(values.unitPriceIRR);
  if (!quantity.valid) errors.quantity = quantity.message;
  if (!/^\d+$/.test(unitPriceIRR) || !/[1-9]/.test(unitPriceIRR)) errors.unitPriceIRR = `قیمت واحد باید عدد صحیح و مثبت ${CURRENCY_LABELS.IRR} باشد.`;
  return { valid: Object.keys(errors).length === 0, errors, values: { targetId: target?.targetId ?? "", targetType: target?.targetType ?? "", targetLabel: target?.label ?? "", quantity: quantity.value, unit: target?.unit ?? null, unitPriceIRR, lineAmountIRR: "", description } };
}

export function validateInvoiceAdjustments(values) {
  const errors = {};
  const normalized = {};
  for (const key of ["discountIRR", "taxIRR", "shippingIRR", "otherCostsIRR"]) {
    const value = normalizeDecimalInput(values[key] || "0");
    if (!/^\d+$/.test(value)) errors[key] = `مبلغ تعدیل باید عدد صحیح و نامنفی ${CURRENCY_LABELS.IRR} باشد.`;
    normalized[key] = value;
  }
  return { valid: Object.keys(errors).length === 0, errors, values: normalized };
}
