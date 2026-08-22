import { normalizeDecimalInput } from "../../shared/validation/decimal-validation.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";

const PRICE_SCOPES = new Set(["organization", "project"]);

function validateDate(value) {
  const normalized = String(value ?? "").trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalized);
  const date = match ? new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))) : null;
  const valid = Boolean(date)
    && date.getUTCFullYear() === Number(match[1])
    && date.getUTCMonth() === Number(match[2]) - 1
    && date.getUTCDate() === Number(match[3]);
  return { valid, value: normalized, message: valid ? "" : "تاریخ اعتبار معتبر نیست." };
}

export function validatePriceVersion(values) {
  const resourceId = String(values.resourceId ?? "").trim();
  const scope = String(values.scope ?? "").trim();
  const unitPriceIRR = normalizeDecimalInput(values.unitPriceIRR);
  const effectiveFrom = validateDate(values.effectiveFrom);
  const errors = {
    resourceId: resourceId ? "" : "انتخاب قلم هزینه الزامی است.",
    scope: PRICE_SCOPES.has(scope) ? "" : "سطح قیمت معتبر نیست.",
    unitPriceIRR: /^\d+$/.test(unitPriceIRR) && /[1-9]/.test(unitPriceIRR) ? "" : `قیمت باید مبلغ مثبت و معتبر به ${getDisplayCurrencyLabel()} باشد.`,
    effectiveFrom: effectiveFrom.message,
  };
  return {
    valid: Object.values(errors).every((message) => !message),
    values: { resourceId, scope, unitPriceIRR, effectiveFrom: effectiveFrom.value },
    errors,
  };
}
