import test from "node:test";
import assert from "node:assert/strict";
import { createApiReportsAdapter } from "../../src/adapters/api/reports-api-adapter.js";
import { buildMonthlyTrend, TREND_MODES } from "../../src/shared/reports/monthly-trend.js";

const context = { organizationId: "org-1", projectId: "project-1" };

function stubClient(payload) {
  const calls = [];
  return {
    calls,
    async request(path) {
      calls.push(path);
      return payload;
    },
  };
}

const PAYLOAD = Object.freeze({
  months: [
    { persianYear: 1404, persianMonth: 12, actualCostIrr: "0", estimateIrr: null, invoiceCount: 0, reversalCount: 0, breakdown: { material: "0", labor: "0", equipment: "0", general_cost: "0" } },
    { persianYear: 1405, persianMonth: 1, actualCostIrr: "1344500000", estimateIrr: null, invoiceCount: 17, reversalCount: 9, breakdown: { material: "1000000000", labor: "344500000", equipment: "0", general_cost: "0" } },
  ],
  windowStart: "2025-09-23",
  windowEnd: "2026-08-25",
  reportingDate: "2026-08-25",
  actualDataThroughDate: "2026-08-20",
  progressSnapshotId: "snapshot-1",
  estimateSource: "unavailable",
  actualSource: "confirmed_financial_documents",
  warnings: [{ code: "MONTHLY_ESTIMATE_UNAVAILABLE", message: "برآورد ماهانه در دسترس نیست." }],
});

test("the monthly series is asked for as an anchor and a month count", async () => {
  const client = stubClient(PAYLOAD);
  await createApiReportsAdapter(context, client).getMonthlyTrend({ reportingDate: "2026-08-25" });
  // A from/to pair would open and close on half a Persian month, and the chart
  // would draw those two stubs as real dips.
  assert.match(client.calls[0], /\/reports\/monthly\?/);
  assert.match(client.calls[0], /reportingDate=2026-08-25/);
  assert.match(client.calls[0], /monthCount=12/);
  const pinned = stubClient(PAYLOAD);
  await createApiReportsAdapter(context, pinned).getMonthlyTrend({
    reportingDate: "2026-08-25",
    progressSnapshotId: "snapshot-1",
  });
  assert.match(pinned.calls[0], /progressSnapshotId=snapshot-1/);
  const custom = stubClient(PAYLOAD);
  await createApiReportsAdapter(context, custom).getMonthlyTrend({ reportingDate: "2026-08-25", monthCount: 24 });
  assert.match(custom.calls[0], /monthCount=24/);
});

test("money arrives as exact strings and a missing estimate stays missing", async () => {
  const result = await createApiReportsAdapter(context, stubClient(PAYLOAD)).getMonthlyTrend({ reportingDate: "2026-08-25" });
  assert.equal(result.months.length, 2);
  assert.equal(result.months[1].actualCostIrr, "1344500000");
  assert.equal(typeof result.months[1].actualCostIrr, "string", "money must never become a number");
  // No estimate line carries a planned date, so there is no monthly baseline.
  // Zero would assert that nothing was budgeted for the month and would put a
  // floor on the chart that turns every month into an overrun.
  result.months.forEach((month) => assert.equal(month.estimateIrr, null));
  assert.equal(result.estimateSource, "unavailable");
  assert.equal(result.actualSource, "confirmed_financial_documents");
  assert.equal(result.windowStart, "2025-09-23");
  assert.equal(result.reportingDate, "2026-08-25");
  assert.equal(result.actualDataThroughDate, "2026-08-20");
  assert.equal(result.progressSnapshotId, "snapshot-1");
  assert.equal(result.warnings[0].code, "MONTHLY_ESTIMATE_UNAVAILABLE");
});

test("a month with no invoices is a real zero, not a gap", async () => {
  // The service sends every month in the window, including the empty ones, so
  // the chart keeps a continuous axis rather than closing up the quiet months.
  const result = await createApiReportsAdapter(context, stubClient(PAYLOAD)).getMonthlyTrend({ reportingDate: "2026-08-25" });
  assert.equal(result.months[0].actualCostIrr, "0");
  assert.equal(result.months[0].invoiceCount, 0);
});

test("the chart draws bars from the series and no baseline when there is none", () => {
  const view = buildMonthlyTrend({ months: PAYLOAD.months.map((month) => ({ ...month })), mode: TREND_MODES.PERIODIC });
  assert.equal(view.points.length, 2);
  assert.equal(view.points[1].actualIrr, "1344500000");
  assert.equal(view.points[1].actualMagnitude, 100, "the tallest bar is the month that spent the most");
  assert.equal(view.points[0].actualMagnitude, 0, "an empty month is a real zero, drawn flat");
  // Every estimate is null, so no point may claim a line height and the chart
  // must know it has no baseline to draw.
  view.points.forEach((point) => assert.equal(point.estimateMagnitude, null));
  assert.equal(view.hasEstimate, false);
  assert.equal(view.estimatePartial, true);
  // A month with no baseline cannot be over or under one.
  view.points.forEach((point) => assert.equal(point.direction, null));
});

test("a reversal is counted apart from a purchase", async () => {
  // A voided document removes cost. Counting it as new purchasing activity
  // would make a month of corrections look like a month of spending.
  const result = await createApiReportsAdapter(context, stubClient(PAYLOAD)).getMonthlyTrend({ reportingDate: "2026-08-25" });
  assert.equal(result.months[1].invoiceCount, 17);
  assert.equal(result.months[1].reversalCount, 9);
});
