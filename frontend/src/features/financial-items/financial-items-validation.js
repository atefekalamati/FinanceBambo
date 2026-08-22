import { validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";
import { getDisplayCurrencyCode, getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { isResourceType } from "./financial-items-model.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";

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

  return {
    valid: title.valid && code.valid && typeValid && baseUnit.valid,
    values: { title: title.value, code: code.value, type: values.type, baseUnit: baseUnit.value },
    errors: {
      title: title.message,
      code: code.message,
      type: typeValid ? "" : "نوع قلم هزینه معتبر نیست.",
      baseUnit: baseUnit.message,
    },
  };
}

export function validateActivity(values) {
  const title = requiredText(values.title, "عنوان فعالیت");
  const wbsCode = String(values.wbsCode ?? "").trim();
  const parentTaskExternalId = String(values.parentTaskExternalId ?? "").trim();

  return {
    valid: title.valid,
    values: {
      title: title.value,
      wbsCode: wbsCode || null,
      parentTaskExternalId: parentTaskExternalId || null,
    },
    errors: { title: title.message },
  };
}

/**
 * A quantified line needs the price the estimate was fixed at: PRD section 9
 * computes the initial estimate as originalQuantity x originalUnitPrice, so
 * without it the Backend reports an initial estimate of zero. A general-cost
 * line carries an amount instead and takes no unit price.
 */
export function validateEstimateLine(values, { isGeneralCost = false } = {}) {
  const activityExternalId = requiredText(values.activityExternalId, "فعالیت");
  const resourceId = requiredText(values.resourceId, "قلم هزینه");
  const originalQuantity = validatePositiveDecimal(values.originalQuantity, {
    precision: 4,
    requiredMessage: "مقدار برآورد اولیه الزامی است.",
    invalidMessage: "مقدار برآورد اولیه باید بزرگ‌تر از صفر و حداکثر چهار رقم اعشار باشد.",
  });
  const originalUnitPriceIRR = isGeneralCost
    ? { valid: true, value: null, message: "" }
    : validatePositiveDecimal(values.originalUnitPriceIRR, {
      precision: 2,
      requiredMessage: "قیمت واحد اولیه الزامی است؛ برآورد اولیه بدون آن صفر محاسبه می‌شود.",
      invalidMessage: "قیمت واحد اولیه باید عددی مثبت باشد.",
    });
  // Money is stored as whole IRR (FR-002), so a fractional value is rejected
  // the same way a general-cost revision is.
  if (!isGeneralCost && originalUnitPriceIRR.valid && originalUnitPriceIRR.value.includes(".")) {
    originalUnitPriceIRR.valid = false;
    originalUnitPriceIRR.message = `قیمت واحد اولیه باید عدد صحیح ${CURRENCY_LABELS.IRR} باشد.`;
  }

  return {
    valid: activityExternalId.valid && resourceId.valid && originalQuantity.valid && originalUnitPriceIRR.valid,
    values: {
      activityExternalId: activityExternalId.value,
      resourceId: resourceId.value,
      originalQuantity: originalQuantity.value,
      originalUnitPriceIRR: originalUnitPriceIRR.value,
    },
    errors: {
      activityExternalId: activityExternalId.message,
      resourceId: resourceId.message,
      originalQuantity: originalQuantity.message,
      originalUnitPriceIRR: originalUnitPriceIRR.message,
    },
  };
}

export function validateEstimateRevision(values, { isGeneralCost = false } = {}) {
  const revisedValue = validatePositiveDecimal(values.revisedValue, {
    precision: isGeneralCost ? 2 : 4,
    requiredMessage: isGeneralCost ? "آخرین مبلغ برآورد الزامی است." : "آخرین مقدار برآورد الزامی است.",
    invalidMessage: isGeneralCost ? `آخرین مبلغ برآورد باید عدد مثبت به ${getDisplayCurrencyLabel()} باشد.` : "آخرین مقدار برآورد باید مثبت و حداکثر چهار رقم اعشار باشد.",
  });
  if (isGeneralCost && revisedValue.valid) {
    if (revisedValue.value.includes(".")) {
      revisedValue.valid = false;
      revisedValue.message = getDisplayCurrencyCode() === "TOMAN"
        ? `مبلغ ${getDisplayCurrencyLabel()} باید حداکثر یک رقم اعشار داشته باشد.`
        : `مبلغ ${getDisplayCurrencyLabel()} باید عدد صحیح باشد.`;
    }
  }
  const reason = requiredText(values.reason, "دلیل اصلاح");
  if (reason.valid && reason.value.length < 3) {
    reason.valid = false;
    reason.message = "دلیل اصلاح باید حداقل سه نویسه داشته باشد.";
  }

  return {
    valid: revisedValue.valid && reason.valid,
    values: { revisedValue: revisedValue.value, reason: reason.value },
    errors: { revisedValue: revisedValue.message, reason: reason.message },
  };
}
