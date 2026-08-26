import { getPersianMonthDays, gregorianIsoToPersian, persianToGregorianIso } from "./persian-date.js";

/**
 * Reporting periods, in the calendar the reader actually works in.
 *
 * Two features ask a report to cover a range — the period report and the report
 * builder — and a range means the same thing to both: which days are inside it,
 * where its opening picture is taken, and whether it makes sense at all. Kept
 * here rather than inside either one, because a rule that lives in a feature is
 * a rule the next feature copies slightly differently.
 */

const DAY_MS = 86400000;

export function isIsoDate(value) {
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

export function isWithinPeriod(value, { from, to } = {}) {
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
 * Ready-made periods. Every one ends today at the latest, because a report
 * cannot be run into the future.
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
