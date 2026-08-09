import {
  compareDecimalStrings,
  normalizeDecimalInput,
  validatePositiveDecimal,
} from "../../shared/validation/decimal-validation.js";

const QUANTITY_SCALE = 4;

function toScaledInteger(value) {
  const normalized = normalizeDecimalInput(value);
  if (!/^\d+(?:\.\d{1,4})?$/.test(normalized)) return null;
  const [integer, fraction = ""] = normalized.split(".");
  return BigInt(`${integer}${fraction.padEnd(QUANTITY_SCALE, "0")}`);
}

function formatScaledInteger(value) {
  const digits = value.toString().padStart(QUANTITY_SCALE + 1, "0");
  const integer = digits.slice(0, -QUANTITY_SCALE);
  const fraction = digits.slice(-QUANTITY_SCALE).replace(/0+$/, "");
  return fraction ? `${integer}.${fraction}` : integer;
}

export function calculateProgressDeviation(actualQuantity, plannedQuantity) {
  const actual = toScaledInteger(actualQuantity);
  const planned = toScaledInteger(plannedQuantity);
  if (actual === null || planned === null || actual <= planned) return null;

  const difference = actual - planned;
  if (planned === 0n) {
    return { amount: formatScaledInteger(difference), percent: null };
  }

  const percentTenThousandths = ((difference * 1000000n) + (planned / 2n)) / planned;
  const percentInteger = percentTenThousandths / 10000n;
  const percentFraction = (percentTenThousandths % 10000n).toString().padStart(4, "0").replace(/0+$/, "");
  return {
    amount: formatScaledInteger(difference),
    percent: percentFraction ? `${percentInteger}.${percentFraction}` : percentInteger.toString(),
  };
}

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
  const deviation = exceedsPlan
    ? calculateProgressDeviation(quantity.value, plannedQuantity)
    : null;

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    value: quantity.value,
    reason: normalizedReason,
    exceedsPlan,
    deviation,
  };
}
