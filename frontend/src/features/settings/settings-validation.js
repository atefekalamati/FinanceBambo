import { normalizeDecimalInput, validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";

export { normalizeDecimalInput };

export function validateGrossBuiltArea(value) {
  return validatePositiveDecimal(value, {
    precision: 4,
    requiredMessage: "زیربنای کل الزامی است.",
    invalidMessage: "زیربنا باید عددی بزرگ‌تر از صفر با حداکثر چهار رقم اعشار باشد.",
  });
}

export function validateRevisionReason(value) {
  const normalized = String(value ?? "").trim();
  if (normalized.length < 3) return { valid: false, value: normalized, message: "دلیل تغییر باید حداقل سه نویسه داشته باشد." };
  return { valid: true, value: normalized, message: "" };
}

export function validateEffectiveDate(value) {
  const normalized = String(value ?? "").trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalized);
  const date = match ? new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))) : null;
  const valid = Boolean(date) && date.getUTCFullYear() === Number(match[1]) && date.getUTCMonth() === Number(match[2]) - 1 && date.getUTCDate() === Number(match[3]);
  if (!valid) {
    return { valid: false, value: normalized, message: "تاریخ اعمال تغییر معتبر نیست." };
  }
  return { valid: true, value: normalized, message: "" };
}

export function validateSettingsRevision(values) {
  const grossBuiltArea = validateGrossBuiltArea(values.grossBuiltArea);
  const reason = validateRevisionReason(values.reason);
  const effectiveDate = validateEffectiveDate(values.effectiveDate);
  return {
    valid: grossBuiltArea.valid && reason.valid && effectiveDate.valid,
    values: { grossBuiltArea: grossBuiltArea.value, reason: reason.value, effectiveDate: effectiveDate.value },
    errors: { grossBuiltArea: grossBuiltArea.message, reason: reason.message, effectiveDate: effectiveDate.message },
  };
}
