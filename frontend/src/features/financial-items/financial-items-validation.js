import { validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { isResourceType } from "./financial-items-model.js";

function requiredText(value, label) {
  const normalized = String(value ?? "").trim();
  return normalized ? { valid: true, value: normalized, message: "" } : { valid: false, value: normalized, message: `${label} الزامی است.` };
}

export function validateResource(values) {
  const title = requiredText(values.title, "عنوان قلم");
  const code = requiredText(values.code, "کد قلم");
  const typeValid = isResourceType(values.type);
  const isGeneralCost = values.type === "general_cost";
  const baseUnit = isGeneralCost ? { valid: true, value: null, message: "" } : requiredText(values.baseUnit, "واحد پایه");
  const dimension = isGeneralCost ? { valid: true, value: null, message: "" } : requiredText(values.dimension, "بُعد");

  return {
    valid: title.valid && code.valid && typeValid && baseUnit.valid && dimension.valid,
    values: { title: title.value, code: code.value, type: values.type, baseUnit: baseUnit.value, dimension: dimension.value },
    errors: {
      title: title.message,
      code: code.message,
      type: typeValid ? "" : "نوع قلم مالی معتبر نیست.",
      baseUnit: baseUnit.message,
      dimension: dimension.message,
    },
  };
}

export function validateEstimateLine(values) {
  const activityExternalId = requiredText(values.activityExternalId, "فعالیت");
  const resourceId = requiredText(values.resourceId, "قلم مالی");
  const originalQuantity = validatePositiveDecimal(values.originalQuantity, {
    precision: 4,
    requiredMessage: "مقدار اولیه الزامی است.",
    invalidMessage: "مقدار اولیه باید بزرگ‌تر از صفر و حداکثر چهار رقم اعشار باشد.",
  });

  return {
    valid: activityExternalId.valid && resourceId.valid && originalQuantity.valid,
    values: {
      activityExternalId: activityExternalId.value,
      resourceId: resourceId.value,
      originalQuantity: originalQuantity.value,
    },
    errors: {
      activityExternalId: activityExternalId.message,
      resourceId: resourceId.message,
      originalQuantity: originalQuantity.message,
    },
  };
}

export function validateEstimateRevision(values, { isGeneralCost = false } = {}) {
  const revisedValue = validatePositiveDecimal(values.revisedValue, {
    precision: isGeneralCost ? 2 : 4,
    requiredMessage: isGeneralCost ? "مبلغ اصلاح‌شده الزامی است." : "مقدار اصلاح‌شده الزامی است.",
    invalidMessage: isGeneralCost ? `مبلغ اصلاح‌شده باید عدد مثبت به ${CURRENCY_LABELS.IRR} باشد.` : "مقدار اصلاح‌شده باید مثبت و حداکثر چهار رقم اعشار باشد.",
  });
  if (isGeneralCost && revisedValue.valid) {
    if (revisedValue.value.includes(".")) {
      revisedValue.valid = false;
      revisedValue.message = `مبلغ باید عدد صحیح ${CURRENCY_LABELS.IRR} باشد.`;
    }
  }
  const reason = requiredText(values.reason, "دلیل بازنگری");
  if (reason.valid && reason.value.length < 3) {
    reason.valid = false;
    reason.message = "دلیل بازنگری باید حداقل سه نویسه داشته باشد.";
  }

  return {
    valid: revisedValue.valid && reason.valid,
    values: { revisedValue: revisedValue.value, reason: reason.value },
    errors: { revisedValue: revisedValue.message, reason: reason.message },
  };
}
