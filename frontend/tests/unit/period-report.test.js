import test from "node:test";
import assert from "node:assert/strict";
import {
  buildBreakdownComparison,
  buildPeriodComparison,
  buildPeriodPresets,
  isWithinPeriod,
  matchPreset,
  openingDateFor,
  periodDayCount,
  PERIOD_METRICS,
  summarizeEvents,
  totalInvoicedIrr,
  validatePeriod,
} from "../../src/features/period-report/period-report.js";
import { buildPeriodReportCsv, periodReportFileName } from "../../src/features/period-report/period-report-csv.js";

const opening = {
  initialEstimateIrr: "18650000000",
  actualCostIrr: "2000000000",
  remainingPhysicalCostIrr: "14000000000",
  forecastFinalCostIrr: "17000000000",
};

const closing = {
  initialEstimateIrr: "18650000000",
  actualCostIrr: "6240000000",
  remainingPhysicalCostIrr: "12840000000",
  forecastFinalCostIrr: "17850000000",
};

test("the period change is the exact difference between the two ends", () => {
  const rows = buildPeriodComparison({ opening, closing });
  const actual = rows.find((row) => row.key === "actualCostIrr");
  assert.equal(actual.changeIrr, "4240000000", "money stays exact integer IRR through the subtraction");
  assert.equal(actual.direction, "up");
  assert.equal(actual.kind, "cumulative", "spending accumulates, so its difference is the period's own cost");
});

test("a figure that fell is reported as falling, not as a negative to be read as spending", () => {
  const remaining = buildPeriodComparison({ opening, closing }).find((row) => row.key === "remainingPhysicalCostIrr");
  assert.equal(remaining.changeIrr, "-1160000000");
  assert.equal(remaining.direction, "down");
  assert.equal(remaining.kind, "state", "remaining work is where the project stands, never a period total");
});

test("an unchanged baseline reads as flat rather than as a missing value", () => {
  const estimate = buildPeriodComparison({ opening, closing }).find((row) => row.key === "initialEstimateIrr");
  assert.equal(estimate.changeIrr, "0");
  assert.equal(estimate.direction, "flat");
  assert.equal(estimate.comparable, true);
});

test("a metric the Backend could not compute is never subtracted into a number", () => {
  // LiveMetrics declares these nullable; null means "not computable", and
  // treating it as zero would invent a change the project never had.
  const rows = buildPeriodComparison({
    opening: { ...opening, forecastFinalCostIrr: null },
    closing,
  });
  const forecast = rows.find((row) => row.key === "forecastFinalCostIrr");
  assert.equal(forecast.openingIrr, null);
  assert.equal(forecast.changeIrr, null);
  assert.equal(forecast.direction, null);
  assert.equal(forecast.comparable, false, "the reader is told it cannot be compared, not shown a dash");
});

test("every metric declares whether its difference is a period total", () => {
  const kinds = new Set(PERIOD_METRICS.map((metric) => metric.kind));
  assert.deepEqual([...kinds].sort(), ["cumulative", "state"]);
  assert.deepEqual(
    PERIOD_METRICS.filter((metric) => metric.kind === "cumulative").map((metric) => metric.key),
    ["actualCostIrr", "initialEstimateIrr"],
    "only what accumulates may be captioned as the period's own money",
  );
});

test("the breakdown compares each resource type on both ends", () => {
  const rows = buildBreakdownComparison({
    opening: [{ resourceType: "material", initialEstimateIrr: "100", actualCostIrr: "40", remainingPhysicalCostIrr: "60", forecastFinalIrr: "100" }],
    closing: [{ resourceType: "material", initialEstimateIrr: "100", actualCostIrr: "70", remainingPhysicalCostIrr: "30", forecastFinalIrr: "100" }],
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].label, "مصالح");
  assert.equal(rows[0].measures.actualCostIrr.changeIrr, "30");
  assert.equal(rows[0].measures.remainingPhysicalCostIrr.changeIrr, "-30");
});

test("a resource type that only appears at one end still gets a row", () => {
  const rows = buildBreakdownComparison({
    opening: [],
    closing: [{ resourceType: "labor", initialEstimateIrr: "500", actualCostIrr: "120", remainingPhysicalCostIrr: "380", forecastFinalIrr: "500" }],
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].measures.actualCostIrr.openingIrr, null, "nothing at the opening is unknown, not zero");
  assert.equal(rows[0].measures.actualCostIrr.changeIrr, null);
});

test("the opening reading is taken the day before the period starts", () => {
  // Otherwise everything recorded on the first day would be swallowed by the
  // baseline and vanish from the period it belongs to.
  assert.equal(openingDateFor("2026-08-01"), "2026-07-31");
  assert.equal(openingDateFor("2026-01-01"), "2025-12-31");
  assert.equal(openingDateFor("not-a-date"), null);
});

test("period membership includes both end days", () => {
  const period = { from: "2026-08-01", to: "2026-08-31" };
  assert.equal(isWithinPeriod("2026-08-01", period), true);
  assert.equal(isWithinPeriod("2026-08-31", period), true);
  assert.equal(isWithinPeriod("2026-07-31", period), false);
  assert.equal(isWithinPeriod("2026-09-01", period), false);
  assert.equal(isWithinPeriod(null, period), false);
});

test("a period must be a real range before a report is built from it", () => {
  assert.equal(validatePeriod({ from: "2026-08-01", to: "2026-08-31" }).valid, true);
  assert.equal(validatePeriod({ from: "2026-08-31", to: "2026-08-01" }).valid, false);
  assert.match(validatePeriod({ from: "2026-08-31", to: "2026-08-01" }).errors.to, /پیش از شروع/);
  assert.equal(validatePeriod({ from: "", to: "2026-08-01" }).valid, false);
  assert.equal(validatePeriod({}).valid, false);
});

test("the day count counts both ends", () => {
  assert.equal(periodDayCount({ from: "2026-08-01", to: "2026-08-31" }), 31);
  assert.equal(periodDayCount({ from: "2026-08-01", to: "2026-08-01" }), 1);
  assert.equal(periodDayCount({ from: "", to: "" }), 0);
});

test("the ready-made periods are real Persian months and never run past today", () => {
  const presets = buildPeriodPresets("2026-08-22");
  const byKey = Object.fromEntries(presets.map((preset) => [preset.key, preset.range]));
  assert.ok(byKey.thisMonth.to <= "2026-08-22", "a report cannot be run into the future");
  assert.ok(byKey.lastMonth.to < byKey.thisMonth.from, "last month ends before this one starts");
  assert.equal(matchPreset(presets, byKey.lastMonth), "lastMonth");
  assert.equal(matchPreset(presets, { from: "2026-01-01", to: "2026-01-31" }), null);
});

test("events are grouped by what happened, most frequent first", () => {
  const summary = summarizeEvents([
    { action: "invoice.confirmed" },
    { action: "price_version.created" },
    { action: "invoice.confirmed" },
    { action: "invoice.confirmed" },
    { action: "price_version.created" },
  ]);
  assert.deepEqual(summary, [
    { action: "invoice.confirmed", count: 3 },
    { action: "price_version.created", count: 2 },
  ]);
  assert.deepEqual(summarizeEvents([]), []);
});

test("a voiding document subtracts from the period's money instead of being ignored", () => {
  const total = totalInvoicedIrr([
    { finalAmountIRR: "1000000", financialEffectSign: 1 },
    { finalAmountIRR: "400000", financialEffectSign: -1 },
    { finalAmountIRR: null, financialEffectSign: 1 },
  ]);
  assert.equal(total, "600000", "the same sign rule the Backend applies to actual cost");
});

test("the CSV carries exact IRR, not the compacted figures on screen", () => {
  const csv = buildPeriodReportCsv({
    project: { name: "برج نمونه", code: "PRJ-1" },
    period: { from: "2026-08-01", to: "2026-08-31", opening: "2026-07-31" },
    generatedAt: "2026-08-22T09:00:00Z",
    metrics: buildPeriodComparison({ opening, closing }),
    breakdown: [],
    events: [{ action: "invoice.confirmed", count: 2 }],
    invoices: [],
  });
  assert.ok(csv.startsWith("﻿"), "Excel needs the byte order mark to read UTF-8");
  assert.ok(csv.includes("4240000000"), "the exact integer, not «۴٫۲۴ میلیارد»");
  assert.ok(csv.includes("\r\n"), "CRLF, the line ending the format specifies");
  assert.ok(csv.includes("2026-07-31"), "the opening date is stated so the reader can reproduce the figures");
});

test("a field containing a comma or a quote cannot break the CSV apart", () => {
  const csv = buildPeriodReportCsv({
    project: { name: 'شرکت "الف", شعبه دو', code: "PRJ-1" },
    period: { from: "2026-08-01", to: "2026-08-31", opening: "2026-07-31" },
    generatedAt: "2026-08-22T09:00:00Z",
  });
  assert.ok(csv.includes('"شرکت ""الف"", شعبه دو"'), "quotes are doubled and the field is wrapped");
});

test("the export file name says which project and which period it holds", () => {
  const name = periodReportFileName({ project: { code: "PRJ-1" }, period: { from: "2026-08-01", to: "2026-08-31" } });
  assert.equal(name, "finance-period-report-PRJ-1-2026-08-01_2026-08-31.csv");
});
