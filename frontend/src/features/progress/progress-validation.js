import {
  compareDecimalStrings,
  validatePositiveDecimal,
} from "../../shared/validation/decimal-validation.js";

export function validateProgressOverride({ value, reason, plannedQuantity }) {
  const quantity = validatePositiveDecimal(value, {
    precision: 4,
    requiredMessage: "مقدار جایگزین الزامی است.",
    invalidMessage: "مقدار جایگزین باید عددی مثبت با حداکثر چهار رقم اعشار باشد.",
  });
  const normalizedReason = String(reason ?? "").trim();
  const errors = {};

  if (!quantity.valid) errors.value = quantity.message;
  if (normalizedReason.length < 3) errors.reason = "دلیل ممیزی باید حداقل سه نویسه داشته باشد.";

  const exceedsPlan = quantity.valid
    && plannedQuantity !== null
    && plannedQuantity !== undefined
    && compareDecimalStrings(quantity.value, plannedQuantity) > 0;

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    value: quantity.value,
    reason: normalizedReason,
    exceedsPlan,
  };
}
