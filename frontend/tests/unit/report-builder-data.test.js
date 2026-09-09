import test from "node:test";
import assert from "node:assert/strict";
import { loadAllInvoices, loadReportData } from "../../src/features/report-builder/report-data.js";
import { buildCumulativeSeries } from "../../src/features/report-builder/report-analysis.js";
import { createApiReportsAdapter } from "../../src/adapters/api/reports-api-adapter.js";

const month = (persianMonth, actualCostIrr, estimateIrr = null) => ({ persianYear: 1405, persianMonth, actualCostIrr, estimateIrr });

test("cumulative costs stay exact above Number precision and retain reversals", () => {
  const view = buildCumulativeSeries([month(2, "-20", "5"), month(1, "90071992547409931", "10")]);
  assert.equal(view.rows[1].actualCumulativeIrr, "90071992547409911");
  assert.equal(view.rows[1].plannedCumulativeIrr, "15");
  assert.equal(view.hasPlan, true);
  assert.equal(view.incompleteActual, false);
});

test("missing or fractional costs and absent months never become zero", () => {
  for (const value of [null, undefined, "bad", "1.0"]) {
    const view = buildCumulativeSeries([month(1, "10", "5"), month(2, value), month(3, "30", "5")]);
    assert.equal(view.rows[2].actualCumulativeIrr, null);
    assert.equal(view.hasPlan, false);
    assert.equal(view.incompleteActual, true);
  }
  assert.equal(buildCumulativeSeries([month(1, "10"), month(3, "30")]).rows[1].actualCumulativeIrr, null);
  assert.equal(buildCumulativeSeries([month(1, "10"), month(1, "30")]).rows[1].actualCumulativeIrr, null);
});

test("zero is valid; missing or partial plans are not a budget baseline", () => {
  const absent = buildCumulativeSeries([month(1, "0"), month(2, "0")]);
  assert.equal(absent.hasPlan, false);
  assert.equal(absent.rows[1].actualCumulativeIrr, "0");
  const partial = buildCumulativeSeries([month(1, "10", "10"), month(2, "20"), month(3, "30", "20")]);
  assert.equal(partial.hasPlan, false);
  assert.equal(partial.rows[2].plannedCumulativeIrr, null);
  assert.equal(buildCumulativeSeries([]).rows.length, 0);
});

test("invoice report fetches every page beyond 200 without writes", async () => {
  const calls = [];
  const result = await loadAllInvoices({ async getInvoices({ page, pageSize }) {
    calls.push(page);
    assert.equal(pageSize, 200);
    return { page, totalPages: 3, totalItems: 401,
      items: Array.from({ length: page < 3 ? 200 : 1 }, (_, i) => ({ invoiceId: `${page}-${i}` })) };
  } });
  assert.deepEqual(calls, [1, 2, 3]);
  assert.equal(result.items.length, 401);
});

test("an unstable or incomplete register fails instead of printing as complete", async () => {
  await assert.rejects(loadAllInvoices({ async getInvoices({ page }) {
    return { page, totalPages: 2, totalItems: page === 1 ? 2 : 3, items: [{ invoiceId: String(page) }] };
  } }), /تغییر کرد/);
  await assert.rejects(loadAllInvoices({ async getInvoices() {
    return { totalPages: 1, totalItems: 2, items: [{ invoiceId: "1" }] };
  } }), /کامل/);
  await assert.rejects(loadAllInvoices({ async getInvoices({ page }) {
    return { page, totalPages: 2, totalItems: 2, items: [{ invoiceId: "duplicate" }] };
  } }), /کامل/);
});

test("independent invoice and S reports require neither progress nor overview", async () => {
  const calls = [];
  const data = await loadReportData({
    selection: ["invoices", "sCurve"], today: "2026-09-08", period: { from: "2026-08-01", to: "2026-09-08" },
    adapters: {
      invoices: { getInvoices: async () => ({ items: [], totalPages: 1, totalItems: 0 }) },
      reports: { getMonthlyTrend: async (query) => { calls.push(query); return { months: [] }; } },
    },
  });
  assert.deepEqual(calls, [{ reportingDate: "2026-09-08" }]);
  assert.equal(data.snapshot, null);
  assert.equal(data.overview, null);
});

test("overview and WBS share the newest ready snapshot and failed requests propagate", async () => {
  const calls = [];
  const adapters = {
    progress: { getSnapshots: async () => [
      { status: "ready", reportingDate: "2026-08-01", progressSnapshotId: "old" },
      { status: "processing", reportingDate: "2026-09-08" },
      { status: "ready", reportingDate: "2026-09-01", progressSnapshotId: "new" },
    ] },
    reports: {
      getOverview: async (query) => { calls.push(query); return {}; },
      getWbsRollup: async (query) => { calls.push(query); return { available: false }; },
    },
  };
  const data = await loadReportData({ selection: ["overview", "levelOne"], adapters });
  assert.equal(data.snapshot.progressSnapshotId, "new");
  assert.deepEqual(calls, [
    { reportingDate: "2026-09-01", progressSnapshotId: "new" },
    { reportingDate: "2026-09-01", progressSnapshotId: "new", level: 1 },
  ]);
  adapters.progress.getSnapshots = async () => [];
  assert.equal(await loadReportData({ selection: ["levelOne"], adapters }), null);
  for (const status of [403, 500]) {
    adapters.progress.getSnapshots = async () => { throw Object.assign(new Error("server"), { status }); };
    await assert.rejects(loadReportData({ selection: ["levelOne"], adapters }), (error) => error.status === status);
  }
});

test("WBS adapter preserves all quality and allocation details including null money", async () => {
  const response = { items: [{ wbsCode: "1", estimateLineCount: 3, calculationStatus: "incomplete", actualCostIrr: null, forecastFinalIrr: null }],
    unattributedActualIrr: "10", unmappedWbsActualIrr: "20", unmappedEstimateLineCount: 2,
    totals: { actualCostIrr: "30" }, calculationStatus: "incomplete", warnings: [{ code: "MISSING_PRICE" }] };
  const adapter = createApiReportsAdapter({ organizationId: "org", projectId: "project" }, { request: async () => response });
  const view = await adapter.getWbsRollup({ reportingDate: "2026-09-08" });
  assert.equal(view.nodes[0].forecastFinalIrr, null);
  assert.equal(view.nodes[0].actualCostIrr, null);
  assert.equal(view.nodes[0].estimateLineCount, 3);
  assert.equal(view.nodes[0].calculationStatus, "incomplete");
  assert.equal(view.unmappedWbsActualIrr, "20");
  assert.equal(view.unmappedEstimateLineCount, 2);
  assert.deepEqual(view.totals, response.totals);
  assert.deepEqual(view.warnings, response.warnings);
});

test("monthly adapter preserves unavailable actual values for the S report", async () => {
  const adapter = createApiReportsAdapter({ organizationId: "org", projectId: "project" }, { request: async () => ({ months: [month(1, null)] }) });
  assert.equal((await adapter.getMonthlyTrend({ reportingDate: "2026-09-08" })).months[0].actualCostIrr, null);
});
