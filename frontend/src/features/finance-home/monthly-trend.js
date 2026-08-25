import { gregorianIsoToPersian } from "../../shared/dates/persian-date.js";

/**
 * Monthly cost trend: the exact arithmetic behind the combination chart.
 *
 * Every amount is an integer IRR string (FR-002), so all maths here uses
 * BigInt. Floats appear only as drawing magnitudes — a percentage of the tallest
 * value — never as money, quantity or a reported deviation.
 */

export const PERSIAN_MONTHS = Object.freeze([
  { label: "فروردین", shortLabel: "فرو" },
  { label: "اردیبهشت", shortLabel: "ارد" },
  { label: "خرداد", shortLabel: "خرد" },
  { label: "تیر", shortLabel: "تیر" },
  { label: "مرداد", shortLabel: "مرد" },
  { label: "شهریور", shortLabel: "شهر" },
  { label: "مهر", shortLabel: "مهر" },
  { label: "آبان", shortLabel: "آبا" },
  { label: "آذر", shortLabel: "آذر" },
  { label: "دی", shortLabel: "دی" },
  { label: "بهمن", shortLabel: "بهم" },
  { label: "اسفند", shortLabel: "اسف" },
]);

export const TREND_MODES = Object.freeze({ PERIODIC: "periodic", CUMULATIVE: "cumulative" });

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : 0n;
}

function isExactInteger(value) {
  return /^-?\d+$/.test(String(value ?? ""));
}

function absolute(value) {
  return value < 0n ? -value : value;
}

export function monthKey(persianYear, persianMonth) {
  return `${persianYear}-${String(persianMonth).padStart(2, "0")}`;
}

/**
 * Actual cost is the sum of confirmed invoices (PRD section 9), signed so a
 * reversal subtracts. Anything still in draft, awaiting review or rejected has
 * no financial effect and is skipped.
 */
export function aggregateConfirmedInvoicesByMonth(invoices = []) {
  const buckets = new Map();
  invoices.forEach((invoice) => {
    if (invoice?.invoiceStatus !== "confirmed") return;
    const persian = gregorianIsoToPersian(invoice.invoiceDate);
    if (!persian || !isExactInteger(invoice.finalAmountIRR)) return;
    const sign = invoice.financialEffectSign === -1 ? -1n : 1n;
    const key = monthKey(persian.year, persian.month);
    const current = buckets.get(key) ?? { persianYear: persian.year, persianMonth: persian.month, total: 0n, invoiceCount: 0 };
    current.total += exactInteger(invoice.finalAmountIRR) * sign;
    current.invoiceCount += 1;
    buckets.set(key, current);
  });
  const present = [...buckets.values()]
    .sort((left, right) => left.persianYear - right.persianYear || left.persianMonth - right.persianMonth)
    .map((bucket) => ({
      persianYear: bucket.persianYear,
      persianMonth: bucket.persianMonth,
      actualCostIrr: String(bucket.total),
      invoiceCount: bucket.invoiceCount,
    }));
  return fillMonthGaps(present);
}

/**
 * A month with no confirmed invoice is a real zero, not a missing category.
 * Dropping it would place two non-adjacent months side by side and draw the
 * estimate line straight across a period it never covered.
 */
export function fillMonthGaps(months = []) {
  if (months.length < 2) return months;
  const filled = [];
  let { persianYear: year, persianMonth: month } = months[0];
  const last = months[months.length - 1];
  const byKey = new Map(months.map((entry) => [monthKey(entry.persianYear, entry.persianMonth), entry]));

  // Bounded by the span itself; a malformed range cannot spin here.
  for (let step = 0; step < 240; step += 1) {
    const key = monthKey(year, month);
    filled.push(byKey.get(key) ?? { persianYear: year, persianMonth: month, actualCostIrr: "0", invoiceCount: 0 });
    if (year === last.persianYear && month === last.persianMonth) break;
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return filled;
}

/** Deviation as an exact string percentage, e.g. "12.3" — no floating point. */
function deviationPercentText(deviation, baseline) {
  const base = absolute(baseline);
  if (base === 0n) return null;
  const scaled = (absolute(deviation) * 1000n) / base;
  const whole = scaled / 10n;
  const fraction = scaled % 10n;
  return fraction === 0n ? String(whole) : `${whole}.${fraction}`;
}

/**
 * A point on the value axis, from 0 at the floor to 100 at the ceiling.
 *
 * A month can be negative: a month whose reversals and corrections outweigh its
 * purchases removes more cost than it adds. Scaling on the absolute value would
 * draw that month exactly as tall as a month that spent the same amount, which
 * is the opposite of what happened. So the axis carries its own floor, and zero
 * sits wherever it falls between them.
 */
function magnitude(value, floor, ceiling) {
  const span = ceiling - floor;
  return span === 0n ? 0 : Number(((value - floor) * 10000n) / span) / 100;
}

/**
 * Builds the drawable series for one display mode.
 *
 * periodic   — each month stands alone, so a single overspend is visible.
 * cumulative — running totals from the first month, so drift against the
 *              baseline accumulates the way a spend curve does.
 *
 * A month whose estimate is null keeps a gap in periodic mode; in cumulative
 * mode the running estimate simply does not advance, and `estimatePartial`
 * marks the series so the UI can say the baseline is incomplete.
 */
export function buildMonthlyTrend({ months = [], mode = TREND_MODES.PERIODIC } = {}) {
  const normalizedMode = mode === TREND_MODES.CUMULATIVE ? TREND_MODES.CUMULATIVE : TREND_MODES.PERIODIC;
  const ordered = [...months].sort((left, right) => left.persianYear - right.persianYear || left.persianMonth - right.persianMonth);

  let runningActual = 0n;
  let runningEstimate = 0n;
  let sawEstimate = false;
  let estimatePartial = false;

  const rows = ordered.map((month) => {
    const monthMeta = PERSIAN_MONTHS[month.persianMonth - 1] ?? { label: "ماه نامشخص", shortLabel: "—" };
    const periodActual = exactInteger(month.actualCostIrr);
    const hasEstimate = isExactInteger(month.estimateIrr);
    if (!hasEstimate) estimatePartial = true;
    const periodEstimate = hasEstimate ? exactInteger(month.estimateIrr) : null;

    runningActual += periodActual;
    if (periodEstimate !== null) {
      runningEstimate += periodEstimate;
      sawEstimate = true;
    }

    const actual = normalizedMode === TREND_MODES.CUMULATIVE ? runningActual : periodActual;
    const estimate = normalizedMode === TREND_MODES.CUMULATIVE
      ? (sawEstimate ? runningEstimate : null)
      : periodEstimate;

    const deviation = estimate === null ? null : actual - estimate;
    return {
      key: monthKey(month.persianYear, month.persianMonth),
      persianYear: month.persianYear,
      persianMonth: month.persianMonth,
      label: monthMeta.label,
      shortLabel: monthMeta.shortLabel,
      fullLabel: `${monthMeta.label} ${month.persianYear}`,
      invoiceCount: month.invoiceCount ?? 0,
      actualIrr: String(actual),
      estimateIrr: estimate === null ? null : String(estimate),
      deviationIrr: deviation === null ? null : String(deviation),
      deviationPercent: deviation === null ? null : deviationPercentText(deviation, estimate),
      direction: deviation === null ? null : deviation > 0n ? "over" : deviation < 0n ? "under" : "onTarget",
    };
  });

  const drawn = rows.flatMap((row) => {
    const values = [exactInteger(row.actualIrr)];
    if (row.estimateIrr !== null) values.push(exactInteger(row.estimateIrr));
    return values;
  });
  // Zero is always on the axis, so a chart of only positive months still starts
  // at the baseline and a chart of only negative ones still ends at it.
  const ceiling = drawn.reduce((result, value) => (value > result ? value : result), 0n);
  const floor = drawn.reduce((result, value) => (value < result ? value : result), 0n);

  const points = rows.map((row) => ({
    ...row,
    actualMagnitude: magnitude(exactInteger(row.actualIrr), floor, ceiling),
    estimateMagnitude: row.estimateIrr === null ? null : magnitude(exactInteger(row.estimateIrr), floor, ceiling),
  }));

  return Object.freeze({
    mode: normalizedMode,
    points,
    maximumIrr: String(ceiling),
    minimumIrr: String(floor),
    // Where the value zero falls on the axis. The bars grow from here, up or
    // down, and the axis draws its heavier line across it.
    zeroMagnitude: magnitude(0n, floor, ceiling),
    hasNegative: floor < 0n,
    axisTicks: buildAxisTicks(ceiling, 4, floor),
    hasEstimate: points.some((point) => point.estimateIrr !== null),
    estimatePartial: estimatePartial && points.length > 0,
    isEmpty: points.length === 0,
  });
}

/**
 * Gridlines at exact fractions of the axis, from its floor to its ceiling.
 *
 * The floor is zero unless some month went below it, so an all-positive chart
 * keeps the axis it always had.
 */
export function buildAxisTicks(maximum, steps = 4, minimum = 0n) {
  const top = typeof maximum === "bigint" ? maximum : exactInteger(maximum);
  const bottom = typeof minimum === "bigint" ? minimum : exactInteger(minimum);
  const span = top - bottom;
  if (span <= 0n) return [{ magnitude: 0, valueIrr: String(bottom) }];
  return Array.from({ length: steps + 1 }, (unused, index) => ({
    magnitude: (index * 100) / steps,
    valueIrr: String(bottom + (span * BigInt(index)) / BigInt(steps)),
  }));
}
