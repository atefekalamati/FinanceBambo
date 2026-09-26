// The period arithmetic below needs to know which days fall inside a range;
// the range itself is a shared idea, and lives with the other reporting dates.
import { isWithinPeriod, openingDateFor } from "../../shared/dates/reporting-periods.js";
import { RESOURCE_TYPE_LABELS, foldLegacyTypes } from "../resource-types.js";
export { buildPeriodPresets, isWithinPeriod, matchPreset, openingDateFor, periodDayCount, validatePeriod } from "../../shared/dates/reporting-periods.js";

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

const BREAKDOWN_LABELS = RESOURCE_TYPE_LABELS;

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
  /* A snapshot issued before 0038 is frozen with `labor` and `equipment` rows; the live
     report beside it has one `work` row. Folded here, exactly, so the two sides of the
     comparison describe the same three kinds and «نیرو و تجهیزات» is not shown as having
     appeared from nowhere. */
  const measureKeys = BREAKDOWN_MEASURES.map(({ key }) => key);
  const openingRows = foldLegacyTypes(opening ?? [], measureKeys);
  const closingRows = foldLegacyTypes(closing ?? [], measureKeys);
  const openingByType = new Map(openingRows.map((row) => [row.resourceType, row]));
  const types = [...new Set([...closingRows.map((row) => row.resourceType), ...openingByType.keys()])];

  return types.map((resourceType) => {
    const closingRow = closingRows.find((row) => row.resourceType === resourceType) ?? {};
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

