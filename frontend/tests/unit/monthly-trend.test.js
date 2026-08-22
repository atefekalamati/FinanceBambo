import test from "node:test";
import assert from "node:assert/strict";
import { aggregateConfirmedInvoicesByMonth, buildAxisTicks, buildMonthlyTrend, fillMonthGaps, monthKey, TREND_MODES } from "../../src/features/finance-home/monthly-trend.js";
import { createMockReportsAdapter } from "../../src/adapters/mock/reports-adapter.js";

const context = { userId: "user-1", organizationId: "org-1", projectId: "project_01" };

function month(persianMonth, actual, estimate = null, persianYear = 1405) {
  return { persianYear, persianMonth, actualCostIrr: String(actual), estimateIrr: estimate === null ? null : String(estimate) };
}

test("only confirmed invoices reach the actual-cost series, and reversals subtract", () => {
  const months = aggregateConfirmedInvoicesByMonth([
    // All three sit inside فروردین ۱۴۰۵ (2026-03-21 .. 2026-04-20).
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-10", finalAmountIRR: "1000", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-15", finalAmountIRR: "500", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-18", finalAmountIRR: "200", financialEffectSign: -1 },
    { invoiceStatus: "draft", invoiceDate: "2026-04-11", finalAmountIRR: "9999", financialEffectSign: 1 },
    { invoiceStatus: "awaitingConfirmation", invoiceDate: "2026-04-12", finalAmountIRR: "9999", financialEffectSign: 1 },
  ]);

  assert.equal(months.length, 1);
  assert.equal(months[0].actualCostIrr, "1300", "1000 + 500 - 200, exact integers only");
  assert.equal(months[0].invoiceCount, 3);
});

test("invoices are bucketed by Persian month and returned oldest first", () => {
  const months = aggregateConfirmedInvoicesByMonth([
    { invoiceStatus: "confirmed", invoiceDate: "2026-07-05", finalAmountIRR: "300", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-05", finalAmountIRR: "100", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-05-05", finalAmountIRR: "200", financialEffectSign: 1 },
  ]);
  assert.deepEqual(
    months.map((item) => [monthKey(item.persianYear, item.persianMonth), item.actualCostIrr]),
    [["1405-01", "100"], ["1405-02", "200"], ["1405-03", "0"], ["1405-04", "300"]],
    "خرداد has no confirmed invoice but must still appear as zero, or the axis would put اردیبهشت next to تیر",
  );
});

test("a month with no confirmed invoice becomes a zero bar, not a missing category", () => {
  const months = aggregateConfirmedInvoicesByMonth([
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-05", finalAmountIRR: "100", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-09-05", finalAmountIRR: "500", financialEffectSign: 1 },
  ]);
  assert.deepEqual(months.map((item) => monthKey(item.persianYear, item.persianMonth)), ["1405-01", "1405-02", "1405-03", "1405-04", "1405-05", "1405-06"]);
  assert.deepEqual(months.map((item) => item.actualCostIrr), ["100", "0", "0", "0", "0", "500"]);
  assert.deepEqual(months.map((item) => item.invoiceCount), [1, 0, 0, 0, 0, 1]);
});

test("gap filling rolls the Persian year over", () => {
  const months = fillMonthGaps([
    { persianYear: 1405, persianMonth: 11, actualCostIrr: "10", invoiceCount: 1 },
    { persianYear: 1406, persianMonth: 2, actualCostIrr: "20", invoiceCount: 1 },
  ]);
  assert.deepEqual(months.map((item) => monthKey(item.persianYear, item.persianMonth)), ["1405-11", "1405-12", "1406-01", "1406-02"]);
});

test("malformed dates and amounts are dropped rather than coerced to zero rows", () => {
  const months = aggregateConfirmedInvoicesByMonth([
    { invoiceStatus: "confirmed", invoiceDate: "not-a-date", finalAmountIRR: "100", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-05", finalAmountIRR: "12.5", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-06", finalAmountIRR: "100", financialEffectSign: 1 },
  ]);
  assert.equal(months.length, 1);
  assert.equal(months[0].actualCostIrr, "100");
});

test("periodic mode keeps each month independent and reports exact deviation", () => {
  const view = buildMonthlyTrend({ months: [month(4, "1230000000", "1400000000")], mode: TREND_MODES.PERIODIC });
  const [point] = view.points;
  assert.equal(point.fullLabel, "تیر 1405");
  assert.equal(point.actualIrr, "1230000000");
  assert.equal(point.estimateIrr, "1400000000");
  assert.equal(point.deviationIrr, "-170000000");
  assert.equal(point.deviationPercent, "12.1");
  assert.equal(point.direction, "under");
});

test("cumulative mode sums both series from the first month", () => {
  const months = [month(1, 100, 120), month(2, 300, 200), month(3, 50, 100)];
  const view = buildMonthlyTrend({ months, mode: TREND_MODES.CUMULATIVE });
  assert.deepEqual(view.points.map((point) => point.actualIrr), ["100", "400", "450"]);
  assert.deepEqual(view.points.map((point) => point.estimateIrr), ["120", "320", "420"]);
  assert.deepEqual(view.points.map((point) => point.direction), ["under", "over", "over"]);
});

test("a month with no estimate leaves a gap in periodic mode and stalls the cumulative baseline", () => {
  const months = [month(1, 100, 120), month(2, 300, null), month(3, 50, 100)];

  const periodic = buildMonthlyTrend({ months, mode: TREND_MODES.PERIODIC });
  assert.deepEqual(periodic.points.map((point) => point.estimateIrr), ["120", null, "100"]);
  assert.deepEqual(periodic.points.map((point) => point.estimateMagnitude === null), [false, true, false]);
  assert.equal(periodic.estimatePartial, true);

  const cumulative = buildMonthlyTrend({ months, mode: TREND_MODES.CUMULATIVE });
  assert.deepEqual(cumulative.points.map((point) => point.estimateIrr), ["120", "120", "220"], "the baseline does not advance for a month it has no value for");
});

test("a series with no estimate at all still draws the actual bars", () => {
  const view = buildMonthlyTrend({ months: [month(1, 100), month(2, 200)], mode: TREND_MODES.PERIODIC });
  assert.equal(view.hasEstimate, false);
  assert.equal(view.isEmpty, false);
  assert.deepEqual(view.points.map((point) => point.actualMagnitude), [50, 100]);
});

test("all-zero and empty inputs stay finite instead of dividing by zero", () => {
  const zeros = buildMonthlyTrend({ months: [month(1, 0, 0), month(2, 0, 0)], mode: TREND_MODES.PERIODIC });
  assert.deepEqual(zeros.points.map((point) => point.actualMagnitude), [0, 0]);
  assert.deepEqual(zeros.points.map((point) => point.deviationPercent), [null, null], "0 vs 0 has no percentage, and must not be Infinity or NaN");
  assert.equal(zeros.points[0].direction, "onTarget");

  const empty = buildMonthlyTrend({ months: [], mode: TREND_MODES.PERIODIC });
  assert.equal(empty.isEmpty, true);
  assert.deepEqual(empty.axisTicks, [{ magnitude: 0, valueIrr: "0" }]);
});

test("axis ticks divide the tallest value exactly", () => {
  assert.deepEqual(buildAxisTicks(1000n), [
    { magnitude: 0, valueIrr: "0" },
    { magnitude: 25, valueIrr: "250" },
    { magnitude: 50, valueIrr: "500" },
    { magnitude: 75, valueIrr: "750" },
    { magnitude: 100, valueIrr: "1000" },
  ]);
});

test("an unknown mode falls back to periodic rather than rendering nothing", () => {
  const view = buildMonthlyTrend({ months: [month(1, 100, 50), month(2, 100, 50)], mode: "sideways" });
  assert.equal(view.mode, TREND_MODES.PERIODIC);
  assert.deepEqual(view.points.map((point) => point.actualIrr), ["100", "100"]);
});

test("the mock reports adapter derives its trend from the seeded invoices across several months", async () => {
  const trend = await createMockReportsAdapter(context).getMonthlyTrend({ reportingDate: "2026-08-20" });
  assert.ok(trend.months.length > 1, "the seed must span more than one month or the chart has nothing to compare");
  assert.equal(trend.estimateSource, "mock_seed");
  assert.ok(trend.months.every((month) => /^-?\d+$/.test(month.actualCostIrr)), "amounts stay exact IRR strings");

  const view = buildMonthlyTrend({ months: trend.months, mode: TREND_MODES.CUMULATIVE });
  assert.equal(view.hasEstimate, true);
  const totals = view.points.map((point) => BigInt(point.actualIrr));
  assert.deepEqual(totals, [...totals].sort((left, right) => (left < right ? -1 : left > right ? 1 : 0)), "a cumulative actual series never decreases while no reversal outweighs a month");
});

test("mock trend reports empty and error states like every other adapter", async () => {
  assert.deepEqual((await createMockReportsAdapter(context, { initialState: "empty" }).getMonthlyTrend({})).months, []);
  await assert.rejects(
    createMockReportsAdapter(context, { initialState: "error" }).getMonthlyTrend({}),
    (error) => error.status === 503 && Boolean(error.requestId),
  );
});

test("the Persian month boundary decides the bucket, not the Gregorian one", () => {
  const months = aggregateConfirmedInvoicesByMonth([
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-20", finalAmountIRR: "100", financialEffectSign: 1 },
    { invoiceStatus: "confirmed", invoiceDate: "2026-04-21", finalAmountIRR: "200", financialEffectSign: 1 },
  ]);
  assert.deepEqual(
    months.map((item) => [monthKey(item.persianYear, item.persianMonth), item.actualCostIrr]),
    [["1405-01", "100"], ["1405-02", "200"]],
    "فروردین ends on 2026-04-20; the next day belongs to اردیبهشت even though both are April",
  );
});
