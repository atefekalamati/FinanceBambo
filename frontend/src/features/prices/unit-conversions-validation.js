import { validatePositiveDecimal } from "../../shared/validation/decimal-validation.js";

/**
 * Unit vocabulary.
 *
 * `GET /api/projects/{projectId}/finance/unit-registry` is the source of truth
 * and `setUnitRegistry` replaces these defaults as soon as a page loads it.
 * The defaults mirror the Backend registry exactly so validation still works
 * before the first fetch — an invented code (the previous `person_hour` and
 * `equipment_day`) is rejected by the API with UNIT_NOT_FOUND.
 */
const DEFAULT_UNITS = Object.freeze([
  { value: "kg", label: "کیلوگرم", dimension: "mass", dimensionLabel: "جرم" },
  { value: "ton", label: "تن", dimension: "mass", dimensionLabel: "جرم" },
  { value: "m", label: "متر", dimension: "length", dimensionLabel: "طول" },
  { value: "m2", label: "مترمربع", dimension: "area", dimensionLabel: "مساحت" },
  { value: "m3", label: "مترمکعب", dimension: "volume", dimensionLabel: "حجم" },
  { value: "each", label: "عدد", dimension: "count", dimensionLabel: "تعداد" },
  { value: "hour", label: "ساعت", dimension: "time", dimensionLabel: "زمان" },
  { value: "day", label: "روز دستگاه", dimension: "equipment_time", dimensionLabel: "زمان تجهیز" },
]);

let unitOptions = DEFAULT_UNITS;
let unitMap = new Map(DEFAULT_UNITS.map((unit) => [unit.value, unit]));

/** Replaces the defaults with the registry the Backend actually serves. */
export function setUnitRegistry(units) {
  const normalized = (units ?? [])
    .filter((unit) => unit && unit.code)
    .map((unit) => ({
      value: unit.code,
      label: unit.label ?? unit.labelFa ?? unit.code,
      dimension: unit.dimension,
      dimensionLabel: unit.dimensionLabel ?? unit.dimensionLabelFa ?? unit.dimension,
    }));
  if (!normalized.length) return unitOptions;
  unitOptions = Object.freeze(normalized);
  unitMap = new Map(normalized.map((unit) => [unit.value, unit]));
  return unitOptions;
}

export function getUnitOptions() {
  return unitOptions;
}

/**
 * The conversions the Backend will accept, mirroring `units_are_compatible`:
 * pairs inside one dimension, plus the sanctioned day↔hour crossing.
 * `configurable` marks the working-time rule an operator may actually change;
 * a fixed physical relationship like ton→kg is not editable.
 */
const CONVERSION_RULES = Object.freeze([
  { sourceUnit: "ton", targetUnit: "kg", dimension: "mass", configurable: false },
  { sourceUnit: "day", targetUnit: "hour", dimension: "equipment_time", configurable: true },
]);

const SCOPES = new Set(["organization", "project"]);

function findRule(sourceUnit, targetUnit) {
  return CONVERSION_RULES.find((rule) => rule.sourceUnit === sourceUnit && rule.targetUnit === targetUnit) ?? null;
}

/** The dimension the API expects for this pair, not just the source's own. */
export function getConversionDimension(sourceUnit, targetUnit) {
  return findRule(sourceUnit, targetUnit)?.dimension ?? getUnitDefinition(sourceUnit)?.dimension ?? null;
}

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
  return unitMap.get(value) ?? null;
}

export function getCompatibleTargetUnits(sourceUnit) {
  if (!getUnitDefinition(sourceUnit)) return [];
  return CONVERSION_RULES
    .filter((rule) => rule.sourceUnit === sourceUnit)
    .map((rule) => getUnitDefinition(rule.targetUnit))
    .filter(Boolean);
}

export function isSupportedConversionDirection(sourceUnit, targetUnit) {
  return findRule(sourceUnit, targetUnit) !== null;
}

export function isConfigurableConversionDirection(sourceUnit, targetUnit) {
  return findRule(sourceUnit, targetUnit)?.configurable === true;
}

export function getConfigurableSourceUnits() {
  const sources = new Set(CONVERSION_RULES.filter((rule) => rule.configurable).map((rule) => rule.sourceUnit));
  return unitOptions.filter((unit) => sources.has(unit.value));
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
    // day→hour crosses dimensions on purpose, exactly as units_are_compatible allows.
    dimension: source && target && source.dimension !== target.dimension && !isSupportedConversionDirection(sourceUnit, targetUnit) && !isSupportedConversionDirection(targetUnit, sourceUnit)
      ? "تبدیل بین دو بُعد ناسازگار مجاز نیست."
      : "",
    direction: source && target && !isSupportedConversionDirection(sourceUnit, targetUnit) && isSupportedConversionDirection(targetUnit, sourceUnit)
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
