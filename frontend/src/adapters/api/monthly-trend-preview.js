/**
 * TEMPORARY PREVIEW DATA — DELETE WHEN THE BACKEND SHIPS A MONTHLY REPORT.
 *
 * The finance API has no monthly series: LiveMetrics and TypeBreakdown carry no
 * time dimension and EstimateLine has no dates, so `getMonthlyTrend` in
 * `reports-api-adapter.js` honestly reports the series as unavailable. That
 * leaves the trend chart with nothing to draw and no way to review its output.
 *
 * This module fabricates a series so the chart can be looked at. It is opt-in
 * and never runs unless a developer asks for it, because placeholder money on a
 * finance screen is indistinguishable from real money once it is on screen.
 *
 * ── How to turn it on ────────────────────────────────────────────────────────
 *   http://127.0.0.1:43129/?monthlyTrendPreview=1#/finance
 * or, from the console:
 *   window.__BAMBO_MONTHLY_TREND_PREVIEW__ = true
 *
 * ── How to remove it, once GET /reports/monthly (or equivalent) exists ───────
 *   1. Delete this file.
 *   2. In `src/adapters/api/reports-api-adapter.js`, drop the import and the
 *      `monthlyTrendPreview()` branch inside `getMonthlyTrend`, and call the
 *      real endpoint there instead.
 *   3. In `src/features/finance-home/finance-home-page.js`, drop the
 *      `estimateSource === "preview"` notice.
 *   4. Delete `tests/unit/monthly-trend-preview.test.js`.
 * Nothing else references it; `grep -r monthlyTrendPreview src tests` should
 * come back empty afterwards.
 */

import { gregorianIsoToPersian, persianToGregorianIso } from "../../shared/dates/persian-date.js";

export const PREVIEW_FLAG = "monthlyTrendPreview";

/**
 * Opt-in only, from the query string or an explicit global. Checked on both the
 * search string and the hash, because the app routes on the hash.
 */
export function isMonthlyTrendPreviewEnabled(location = globalThis.location, globals = globalThis) {
  if (globals?.__BAMBO_MONTHLY_TREND_PREVIEW__ === true) return true;
  const search = String(location?.search ?? "");
  const hash = String(location?.hash ?? "");
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?")) : "";
  return new URLSearchParams(search).get(PREVIEW_FLAG) === "1"
    || new URLSearchParams(query).get(PREVIEW_FLAG) === "1";
}

/**
 * Twelve months ending on the reporting month, shaped like a build that starts
 * slowly, peaks through the structural phase and tapers — with two months over
 * the baseline and the rest under it, so every state the chart can draw
 * (over, under, on target, and a month with no estimate) is visible.
 *
 * Amounts are exact integer IRR strings, the same contract real money uses, so
 * nothing downstream has to special-case this data.
 */
const ESTIMATE_PATTERN = Object.freeze([
  "9200000000", "11800000000", "14500000000", "18900000000",
  "24600000000", "27300000000", "26100000000", "22400000000",
  "18700000000", "15200000000", null, "10400000000",
]);

const ACTUAL_PATTERN = Object.freeze([
  "7600000000", "10900000000", "15800000000", "18900000000",
  "22100000000", "29800000000", "24700000000", "20100000000",
  "19900000000", "13600000000", "9800000000", "6200000000",
]);

function previousPersianMonth(year, month) {
  return month === 1 ? { year: year - 1, month: 12 } : { year, month: month - 1 };
}

export function buildMonthlyTrendPreview({ reportingDate } = {}) {
  const anchor = gregorianIsoToPersian(reportingDate) ?? gregorianIsoToPersian(todayIso());
  if (!anchor) return { months: [], estimateSource: "preview" };

  const months = [];
  let cursor = { year: anchor.year, month: anchor.month };
  for (let index = 0; index < ESTIMATE_PATTERN.length; index += 1) {
    months.unshift({
      persianYear: cursor.year,
      persianMonth: cursor.month,
      actualCostIrr: ACTUAL_PATTERN[index],
      estimateIrr: ESTIMATE_PATTERN[index],
      invoiceCount: 0,
    });
    cursor = previousPersianMonth(cursor.year, cursor.month);
  }

  return {
    months,
    estimateSource: "preview",
    previewNotice: "داده این نمودار نمایشی و موقت است؛ سرویس مالی هنوز سری زمانی ماهانه ارائه نمی‌دهد.",
  };
}

function todayIso() {
  // persianToGregorianIso round-trips through the same calendar the app uses,
  // so the anchor stays consistent with every other Persian date on screen.
  const now = new Date();
  const iso = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
  const persian = gregorianIsoToPersian(iso);
  return persian ? persianToGregorianIso(persian.year, persian.month, persian.day) ?? iso : iso;
}
