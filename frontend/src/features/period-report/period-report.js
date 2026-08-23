import { getPersianMonthDays, gregorianIsoToPersian, persianToGregorianIso } from "../../shared/dates/persian-date.js";

/**
 * The arithmetic behind the period report, kept apart from the DOM so the rules
 * that matter — which measures may be subtracted, and what a missing one means
 * — can be tested directly.
 *
 * The Backend rebuilds the whole financial picture at any past date: every
 * input is bound by the reporting date, down to `invoice_date <= as_of`. A
 * period is therefore two of those pictures, one at the day before the period
 * opens and one at the day it closes.
 */

/**
 * Money is exact integer IRR or it is nothing. A metric the Backend could not
 * compute arrives as null, and null is not zero — subtracting it would invent a
 * change the project never had.
 */
function exactOrNull(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? String(value) : null;
}

function difference(opening, closing) {
  if (opening === null || closing === null) return null;
  return (BigInt(closing) - BigInt(opening)).toString();
}

function directionOf(change) {
  if (change === null) return null;
  const value = BigInt(change);
  return value > 0n ? "up" : value < 0n ? "down" : "flat";
}

/**
 * Two kinds of measure, and the difference between them is the whole reason a
 * period report can mislead:
 *
 *   cumulative — grows as the project records more. Subtracting two dates gives
 *                what the period itself added: "this period cost X".
 *   state      — where the project stands right now. Subtracting gives how far
 *                the figure moved, never a total for the period. A forecast that
 *                went up by X did not *cost* X.
 *
 * The UI reads `kind` to choose its wording, so a state measure is never
 * captioned as if it were spending.
 */
export const PERIOD_METRICS = Object.freeze([
  { key: "actualCostIrr", label: "هزینه واقعی ثبت‌شده", kind: "cumulative" },
  { key: "initialEstimateIrr", label: "برآورد اولیه", kind: "cumulative" },
  { key: "currentExecutedValueIrr", label: "ارزش روز کار انجام‌شده", kind: "state" },
  { key: "remainingPhysicalCostIrr", label: "هزینه کار باقی‌مانده", kind: "state" },
  { key: "moneyRequiredToContinueIrr", label: "بودجه موردنیاز تا تکمیل", kind: "state" },
  { key: "forecastFinalCostIrr", label: "پیش‌بینی هزینه نهایی", kind: "state" },
  { key: "actualCostPerSquareMeterIrr", label: "هزینه واقعی هر مترمربع", kind: "state" },
  { key: "forecastPerSquareMeterIrr", label: "پیش‌بینی هزینه هر مترمربع", kind: "state" },
]);

const BREAKDOWN_LABELS = Object.freeze({
  material: "مصالح",
  labor: "نیروی انسانی",
  equipment: "تجهیزات",
  general_cost: "هزینه‌های عمومی پروژه",
});

const BREAKDOWN_MEASURES = Object.freeze([
  { key: "initialEstimateIrr", kind: "cumulative" },
  { key: "actualCostIrr", kind: "cumulative" },
  { key: "remainingPhysicalCostIrr", kind: "state" },
  { key: "forecastFinalIrr", kind: "state" },
]);

export function buildPeriodComparison({ opening, closing } = {}) {
  return PERIOD_METRICS.map(({ key, label, kind }) => {
    const openingIrr = exactOrNull(opening?.[key]);
    const closingIrr = exactOrNull(closing?.[key]);
    const changeIrr = difference(openingIrr, closingIrr);
    return {
      key,
      label,
      kind,
      openingIrr,
      closingIrr,
      changeIrr,
      direction: directionOf(changeIrr),
      // Only a measure whose two ends are both computable can be compared, and
      // the reader is told which ones those are rather than being shown a dash
      // that could mean zero.
      comparable: changeIrr !== null,
    };
  });
}

export function buildBreakdownComparison({ opening = [], closing = [] } = {}) {
  const openingByType = new Map((opening ?? []).map((row) => [row.resourceType, row]));
  const types = [...new Set([...(closing ?? []).map((row) => row.resourceType), ...openingByType.keys()])];

  return types.map((resourceType) => {
    const closingRow = (closing ?? []).find((row) => row.resourceType === resourceType) ?? {};
    const openingRow = openingByType.get(resourceType) ?? {};
    const measures = {};
    BREAKDOWN_MEASURES.forEach(({ key, kind }) => {
      const openingIrr = exactOrNull(openingRow[key]);
      const closingIrr = exactOrNull(closingRow[key]);
      const changeIrr = difference(openingIrr, closingIrr);
      measures[key] = { kind, openingIrr, closingIrr, changeIrr, direction: directionOf(changeIrr) };
    });
    return { resourceType, label: BREAKDOWN_LABELS[resourceType] ?? "نوع تعریف‌نشده", measures };
  });
}

/** Groups the period's audit trail by what happened, most frequent first. */
export function summarizeEvents(events = []) {
  const counts = new Map();
  events.forEach((event) => {
    const action = event?.action ?? "unknown";
    counts.set(action, (counts.get(action) ?? 0) + 1);
  });
  return [...counts.entries()]
    .map(([action, count]) => ({ action, count }))
    .sort((left, right) => right.count - left.count || left.action.localeCompare(right.action));
}

/**
 * Confirmed money the period actually recorded. Voided and corrective documents
 * carry a financial effect sign, so they subtract rather than being ignored —
 * the same rule the Backend applies when it totals actual cost.
 */
export function totalInvoicedIrr(invoices = []) {
  return invoices.reduce((total, invoice) => {
    const amount = exactOrNull(invoice?.finalAmountIRR ?? invoice?.finalAmountIrr);
    if (amount === null) return total;
    const sign = Number(invoice?.financialEffectSign ?? 1) < 0 ? -1n : 1n;
    return total + BigInt(amount) * sign;
  }, 0n).toString();
}

/* ── Dates ──────────────────────────────────────────────────────────────── */

const DAY_MS = 86400000;

function isIsoDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value ?? ""));
}

function isoToUtc(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

function utcToIso(value) {
  const date = new Date(value);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

/**
 * The opening picture is taken the day *before* the period starts, so anything
 * recorded on the first day of the period counts inside it rather than being
 * swallowed by the baseline.
 */
export function openingDateFor(from) {
  return isIsoDate(from) ? utcToIso(isoToUtc(from) - DAY_MS) : null;
}

export function isWithinPeriod(value, { from, to }) {
  if (!isIsoDate(value)) return false;
  const day = isoToUtc(value);
  if (isIsoDate(from) && day < isoToUtc(from)) return false;
  if (isIsoDate(to) && day > isoToUtc(to)) return false;
  return true;
}

export function validatePeriod({ from, to } = {}) {
  const errors = {};
  if (!isIsoDate(from)) errors.from = "تاریخ شروع دوره را انتخاب کنید.";
  if (!isIsoDate(to)) errors.to = "تاریخ پایان دوره را انتخاب کنید.";
  if (!errors.from && !errors.to && isoToUtc(from) > isoToUtc(to)) {
    errors.to = "پایان دوره نمی‌تواند پیش از شروع آن باشد.";
  }
  return { valid: Object.keys(errors).length === 0, errors };
}

export function periodDayCount({ from, to } = {}) {
  if (!isIsoDate(from) || !isIsoDate(to)) return 0;
  return Math.floor((isoToUtc(to) - isoToUtc(from)) / DAY_MS) + 1;
}

function persianMonthRange(year, month) {
  // getPersianMonthDays answers with the month's shape, not a count: its
  // `firstIso` is the first day already resolved and `length` is how many days
  // the month actually has, which is what decides the last one.
  const shape = getPersianMonthDays(year, month);
  if (!shape?.firstIso || !shape.length) return null;
  const to = persianToGregorianIso(year, month, shape.length);
  return to ? { from: shape.firstIso, to } : null;
}

function previousPersianMonth(year, month) {
  return month === 1 ? { year: year - 1, month: 12 } : { year, month: month - 1 };
}

/**
 * Ready-made periods, in the calendar the reader actually works in. Every one
 * ends today at the latest, because a report cannot be run into the future.
 */
export function buildPeriodPresets(todayIso) {
  const today = gregorianIsoToPersian(todayIso);
  if (!today) return [];

  const clampToToday = (range) => range && { from: range.from, to: range.to > todayIso ? todayIso : range.to };
  const thisMonth = clampToToday(persianMonthRange(today.year, today.month));
  const previous = previousPersianMonth(today.year, today.month);
  const lastMonth = persianMonthRange(previous.year, previous.month);
  const quarterStartMonth = today.month - ((today.month - 1) % 3);
  const quarter = clampToToday({
    from: persianToGregorianIso(today.year, quarterStartMonth, 1),
    to: todayIso,
  });
  const yearToDate = { from: persianToGregorianIso(today.year, 1, 1), to: todayIso };

  return [
    { key: "thisMonth", label: "ماه جاری", range: thisMonth },
    { key: "lastMonth", label: "ماه گذشته", range: lastMonth },
    { key: "quarter", label: "سه‌ماهه جاری", range: quarter },
    { key: "yearToDate", label: "از ابتدای سال", range: yearToDate },
  ].filter((preset) => preset.range?.from && preset.range?.to);
}

export function matchPreset(presets, { from, to }) {
  return presets.find((preset) => preset.range.from === from && preset.range.to === to)?.key ?? null;
}
