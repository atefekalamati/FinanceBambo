import { validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";

export const UNIT_OPTIONS = Object.freeze([
  { value: "ton", label: "تن", dimension: "mass", dimensionLabel: "جرم" },
  { value: "kg", label: "کیلوگرم", dimension: "mass", dimensionLabel: "جرم" },
  { value: "equipment_day", label: "روز دستگاه", dimension: "equipment_time", dimensionLabel: "زمان دستگاه" },
  { value: "hour", label: "ساعت", dimension: "equipment_time", dimensionLabel: "زمان دستگاه" },
  { value: "person_hour", label: "نفر-ساعت", dimension: "labor_time", dimensionLabel: "زمان نیروی انسانی" },
]);

const UNIT_MAP = new Map(UNIT_OPTIONS.map((unit) => [unit.value, unit]));
const SCOPES = new Set(["organization", "project"]);
const ALLOWED_CONVERSION_DIRECTIONS = new Map([
  ["ton", new Set(["kg"])],
  ["equipment_day", new Set(["hour"])],
]);
const CONFIGURABLE_CONVERSION_DIRECTIONS = new Map([
  ["equipment_day", new Set(["hour"])],
]);

function validateDate(value) {
  const normalized = String(value ?? "").trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalized);
  const date = match ? new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))) : null;
  const valid = Boolean(date)
    && date.getUTCFullYear() === Number(match[1])
    && date.getUTCMonth() === Number(match[2]) - 1
    && date.getUTCDate() === Number(match[3]);
  return { value: normalized, message: valid ? "" : "تاریخ اعتبار معتبر نیست." };
}

export function getUnitDefinition(value) {
  return UNIT_MAP.get(value) ?? null;
}

export function getCompatibleTargetUnits(sourceUnit) {
  const source = getUnitDefinition(sourceUnit);
  if (!source) return [];
  const allowedTargets = ALLOWED_CONVERSION_DIRECTIONS.get(source.value) ?? new Set();
  return UNIT_OPTIONS.filter((unit) => unit.dimension === source.dimension && allowedTargets.has(unit.value));
}

export function isSupportedConversionDirection(sourceUnit, targetUnit) {
  return ALLOWED_CONVERSION_DIRECTIONS.get(sourceUnit)?.has(targetUnit) ?? false;
}

export function isConfigurableConversionDirection(sourceUnit, targetUnit) {
  return CONFIGURABLE_CONVERSION_DIRECTIONS.get(sourceUnit)?.has(targetUnit) ?? false;
}

export function getConfigurableSourceUnits() {
  return UNIT_OPTIONS.filter((unit) => CONFIGURABLE_CONVERSION_DIRECTIONS.has(unit.value));
}

export function validateUnitConversion(values) {
  const sourceUnit = String(values.sourceUnit ?? "").trim();
  const targetUnit = String(values.targetUnit ?? "").trim();
  const scope = String(values.scope ?? "").trim();
  const source = getUnitDefinition(sourceUnit);
  const target = getUnitDefinition(targetUnit);
  const factor = validatePositiveDecimal(values.factor, {
    precision: 6,
    requiredMessage: "ضریب تبدیل الزامی است.",
    invalidMessage: "ضریب باید مثبت و حداکثر شش رقم اعشار باشد.",
  });
  const effectiveDate = validateDate(values.effectiveDate);
  const errors = {
    sourceUnit: source ? "" : "واحد مبدأ معتبر نیست.",
    targetUnit: target ? "" : "واحد مقصد معتبر نیست.",
    factor: factor.message,
    scope: SCOPES.has(scope) ? "" : "سطح تبدیل معتبر نیست.",
    effectiveDate: effectiveDate.message,
    dimension: source && target && source.dimension !== target.dimension ? "تبدیل بین دو بُعد ناسازگار مجاز نیست." : "",
    direction: source && target && source.dimension === target.dimension && !isSupportedConversionDirection(sourceUnit, targetUnit)
      ? "جهت تبدیل مجاز نیست؛ تبدیل فقط از واحد بزرگ‌تر به واحد پایه کوچک‌تر ثبت می‌شود."
      : "",
    policy: source && target && isSupportedConversionDirection(sourceUnit, targetUnit) && !isConfigurableConversionDirection(sourceUnit, targetUnit)
      ? "این تبدیل یک رابطه استاندارد و ثابت است و قابل تغییر نیست."
      : "",
  };
  if (sourceUnit && sourceUnit === targetUnit) errors.targetUnit = "واحد مبدأ و مقصد باید متفاوت باشند.";
  return {
    valid: Object.values(errors).every((message) => !message),
    values: { sourceUnit, targetUnit, factor: factor.value, scope, effectiveDate: effectiveDate.value },
    errors,
  };
}
