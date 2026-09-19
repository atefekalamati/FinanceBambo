import { normalizeDecimalInput, validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";

export function validateInvoiceHeader(values) {
  // No invoiceNumber. The project allocates it when the invoice is written, so
  // there is nothing here to require, normalise or reject -- and carrying it in
  // `values` would put it back in the payload the API refuses.
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

/* HOW A LINE SAYS WHAT IT COST.
 *
 * `computed` is a quantity and a rate, and the site multiplies them: twelve tonnes at
 * eight hundred thousand. `total` is the figure off the document and nothing else.
 *
 * Both are ordinary for an estimate line. A delivery note states quantity and rate; a
 * contractor's bill for the same activity states one number and no breakdown, and the
 * person holding it should not have to invent a rate so the form will accept it. The
 * service has always taken either -- `InvoiceLineCreate` refuses only the COMBINATION,
 * and `services/invoices.py` reads a stated amount as the raw amount -- so this is a
 * question the interface was not asking, not a capability it lacked.
 *
 * A general cost has no quantity to state, so it is always `total`. */
export const AMOUNT_MODES = Object.freeze({ COMPUTED: "computed", TOTAL: "total" });

/**
 * Whether this line states its amount outright, rather than a quantity to multiply.
 *
 * Read from the LINE, never from the target's type. A general cost always states a total
 * and an estimate line may, and asking the type instead is how one of them ends up sent
 * with both shapes or neither -- which the service refuses, correctly, at the end of a
 * form somebody has already filled in.
 */
export function statesTotal(line) {
  const amount = String(line?.lineAmountIRR ?? "").trim();
  return amount !== "" && amount !== "0";
}

/** Which shape a target may use, and which it must. */
export function amountModesFor(target) {
  return target?.targetType === "general_cost"
    ? [AMOUNT_MODES.TOTAL]
    : [AMOUNT_MODES.COMPUTED, AMOUNT_MODES.TOTAL];
}

export function validateInvoiceLine(values, target, amountMode = null) {
  const errors = {};
  const description = String(values.description ?? "").trim();
  if (!target) errors.targetId = "اتصال مالی خط را انتخاب کنید.";
  const allowed = amountModesFor(target);
  const mode = allowed.includes(amountMode) ? amountMode : allowed[0];
  if (mode === AMOUNT_MODES.TOTAL) {
    const amountIRR = normalizeDecimalInput(values.amountIRR);
    if (!/^\d+$/.test(amountIRR) || !/[1-9]/.test(amountIRR)) errors.amountIRR = `مبلغ خط باید مقدار مثبت و معتبر ${getDisplayCurrencyLabel()} باشد.`;
    /* Nothing but the figure. The other three are explicitly null rather than absent: the
       service refuses an amount sent beside a quantity, and «I left it out» and «I sent
       nothing» must not be two different requests. */
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
