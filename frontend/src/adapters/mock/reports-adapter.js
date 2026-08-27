import { ApiError } from "../../core/api/api-error.js";
import { aggregateConfirmedInvoicesByMonth } from "../../features/finance-home/monthly-trend.js";
import { buildSeedInvoices } from "./invoices-adapter.js";

/**
 * Synthetic monthly estimate baseline.
 *
 * The Backend has no monthly estimate anywhere in its contract — LiveMetrics
 * and TypeBreakdown carry no time dimension and EstimateLine has no dates — so
 * this exists only to make the overview trend demonstrable while that contract
 * is designed. The API adapter deliberately reports the series as unavailable
 * rather than deriving a lookalike, so nothing here can reach a real project.
 */
const SEED_MONTHLY_ESTIMATE_IRR = Object.freeze([
  "1180000000", "1240000000", "1310000000", "1400000000",
  "1350000000", "1290000000", "1420000000", "1360000000",
]);

function wait(duration = 320) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

/**
 * The Backend rebuilds every figure as of the reporting date — down to
 * `invoice_date <= as_of` — so a mock that answers the same numbers whatever
 * date it is asked about would make a period report show no movement at all,
 * and hide any bug in the comparison behind a row of zeroes.
 *
 * The share below is how much of the seeded project has happened by the date
 * asked for: it is what drives actual cost and everything derived from it.
 */
const AS_OF_START = "2026-01-01";
const AS_OF_END = "2026-08-31";

function elapsedShare(reportingDate) {
  const day = (value) => {
    const [year, month, date] = String(value).split("-").map(Number);
    return Number.isFinite(year) ? Date.UTC(year, month - 1, date) : NaN;
  };
  const asOf = day(reportingDate);
  const start = day(AS_OF_START);
  const end = day(AS_OF_END);
  if (!Number.isFinite(asOf)) return 1;
  if (asOf <= start) return 0;
  if (asOf >= end) return 1;
  return (asOf - start) / (end - start);
}

/** Exact integer IRR, the same contract real money uses. */
function scaleIrr(value, share) {
  return String(BigInt(Math.round(Number(value) * share)));
}

function scaleMetrics(metrics, share) {
  // The estimate baseline is set at the outset and does not accumulate with
  // time; everything else follows the work done by the reporting date.
  const fixed = new Set(["initialEstimateIrr"]);
  return Object.fromEntries(Object.entries(metrics).map(([key, value]) => [
    key,
    fixed.has(key) ? value : scaleIrr(value, share),
  ]));
}

function scaleBreakdown(rows, share) {
  return rows.map((row) => ({
    ...row,
    actualCostIrr: scaleIrr(row.actualCostIrr, share),
    remainingPhysicalCostIrr: scaleIrr(row.remainingPhysicalCostIrr, 1 - share * 0.6),
    forecastFinalIrr: scaleIrr(row.forecastFinalIrr, 0.82 + share * 0.18),
  }));
}

export function createMockReportsAdapter(context, { initialState = "success" } = {}) {
  const snapshots = new Map();

  async function getLiveReport({ reportingDate, progressSnapshotId }) {
    await wait();
    if (initialState === "error") throw new ApiError({ status: 503, code: "LIVE_REPORT_UNAVAILABLE", message: "دریافت خلاصه مالی زنده انجام نشد.", requestId: "mock-live-report-001" });
    if (initialState === "empty") return null;
    const share = elapsedShare(reportingDate);
    const report = {
      reportingDate,
      progressSnapshotId,
      // The same figures the API produces from the seeded database, in rial. They are
      // copied rather than derived on purpose: the mock exists so the interface can be
      // developed without a backend, and a mock that did its own arithmetic would be a
      // second implementation of the report to keep in step. Backend and database remain
      // the source of financial truth.
      metrics: {
        initialEstimateIrr: "680000000000",
        actualCostIrr: "229815320000",
        currentExecutedValueIrr: "219604880000",
        remainingPhysicalCostIrr: "509202120000",
        moneyRequiredToContinueIrr: "485116720000",
        forecastFinalCostIrr: "714932040000",
        actualCostPerSquareMeterIrr: "54074190",
        forecastPerSquareMeterIrr: "168219300",
      },
      breakdown: [
        { resourceType: "material", initialEstimateIrr: "360000000000", revisedEstimateIrr: "384980000000", actualCostIrr: "131815320000", remainingPhysicalCostIrr: "341528860000", forecastFinalIrr: "380758780000" },
        { resourceType: "labor", initialEstimateIrr: "150000000000", revisedEstimateIrr: "158000000000", actualCostIrr: "48000000000", remainingPhysicalCostIrr: "108021800000", forecastFinalIrr: "156021800000" },
        { resourceType: "equipment", initialEstimateIrr: "80000000000", revisedEstimateIrr: "84000000000", actualCostIrr: "23000000000", remainingPhysicalCostIrr: "59651460000", forecastFinalIrr: "82651460000" },
        { resourceType: "general_cost", initialEstimateIrr: "90000000000", revisedEstimateIrr: "95500000000", actualCostIrr: "27000000000", remainingPhysicalCostIrr: "68500000000", forecastFinalIrr: "95500000000" },
      ],
      topPriceVariances: [
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000001", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد آجدار A3", resourceType: "material", varianceIrr: "27509400000" },
        { resourceId: "20000000-0000-4000-8000-000000000005", estimateLineId: "30000000-0000-4000-8000-000000000005", resourceCode: "LAB-FORM", resourceTitle: "اکیپ قالب‌بندی", resourceType: "labor", varianceIrr: "11642400000" },
        { resourceId: "20000000-0000-4000-8000-000000000007", estimateLineId: "30000000-0000-4000-8000-000000000007", resourceCode: "EQ-CRANE", resourceTitle: "جرثقیل برجی", resourceType: "equipment", varianceIrr: "8662500000" },
      ],
      topQuantityVariances: [
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000001", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد آجدار A3", resourceType: "material", varianceQuantity: "45000.0000" },
        { resourceId: "20000000-0000-4000-8000-000000000003", estimateLineId: "30000000-0000-4000-8000-000000000003", resourceCode: "MAT-BLOCK", resourceTitle: "بلوک سفالی دیوارچینی", resourceType: "material", varianceQuantity: "10000.0000" },
      ],
      // No warnings: every line has a current price and a measured progress quantity, which
      // is what the seeded database actually produces. The previous fixture carried a
      // CURRENT_PRICE_MISSING warning beside calculationStatus "complete" -- a combination
      // the real report cannot emit, since a missing price is exactly what makes it
      // incomplete.
      warnings: [],
      calculationStatus: "complete",
      incompleteMetricKeys: [],
      missingPriceCount: 0,
      excludedEstimateLineCount: 0,
      excludedEstimateLineIds: [],
      progressQuality: {
        complete: true,
        manualOverrideCount: 0,
        taskFallbackCount: 0,
        missingCount: 0,
        assignmentActualCount: 2,
        assignmentPercentFallbackCount: 0,
      },
      scope: { organizationId: context.organizationId, projectId: context.projectId },
    };
    return {
      ...report,
      metrics: scaleMetrics(report.metrics, share),
      breakdown: scaleBreakdown(report.breakdown, share),
    };
  }

  async function getOverview(options) {
    return getLiveReport(options);
  }

  async function getVariances({ reportingDate, progressSnapshotId, varianceType = "all", page = 1, pageSize = 200 }) {
    const report = await getLiveReport({ reportingDate, progressSnapshotId });
    if (!report) return { items: [], page, pageSize, totalItems: 0, totalPages: 0 };
    const items = varianceType === "price"
      ? report.topPriceVariances
      : varianceType === "quantity"
        ? report.topQuantityVariances
        : [...report.topPriceVariances, ...report.topQuantityVariances];
    const start = (page - 1) * pageSize;
    return {
      items: items.slice(start, start + pageSize),
      page,
      pageSize,
      totalItems: items.length,
      totalPages: Math.ceil(items.length / pageSize),
    };
  }

  async function issueSnapshot({ reportingDate, progressSnapshotId = null }) {
    await wait();
    if (initialState === "error") throw new ApiError({ status: 503, code: "REPORT_SNAPSHOT_UNAVAILABLE", message: "صدور گزارش انجام نشد.", requestId: "mock-report-issue-001" });
    const live = await getLiveReport({ reportingDate, progressSnapshotId });
    const reportSnapshotId = `00000000-0000-4000-8000-${String(snapshots.size + 1).padStart(12, "0")}`;
    const snapshot = Object.freeze({
      reportSnapshotId,
      organizationId: context.organizationId,
      projectId: context.projectId,
      issuedAt: new Date().toISOString(),
      issuedBy: context.userId,
      progressSnapshotId: live.progressSnapshotId,
      resourceVersionIds: ["00000000-0000-4000-8000-000000000101"],
      priceVersionIds: ["00000000-0000-4000-8000-000000000201"],
      invoiceIds: ["00000000-0000-4000-8000-000000000301"],
      unitConversionIds: [],
      calculatedMetrics: { ...live.metrics },
      immutable: true,
    });
    snapshots.set(reportSnapshotId, snapshot);
    return snapshot;
  }

  async function getSnapshot(reportId) {
    await wait(80);
    const snapshot = snapshots.get(reportId);
    if (!snapshot) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "نسخه گزارش پیدا نشد.", requestId: "mock-report-get-001" });
    return snapshot;
  }

  async function downloadSnapshotCsv(reportId) {
    const snapshot = await getSnapshot(reportId);
    const rows = ["شاخص,مقدار (ریال)", ...Object.entries(snapshot.calculatedMetrics).map(([key, value]) => `${key},${value}`)];
    return Object.freeze({ blob: new Blob([`\uFEFF${rows.join("\r\n")}`], { type: "text/csv;charset=utf-8" }), fileName: `finance-report-${reportId}.csv` });
  }

  async function getMonthlyTrend() {
    await wait(280);
    if (initialState === "error") throw new ApiError({ status: 503, code: "MONTHLY_TREND_UNAVAILABLE", message: "دریافت روند ماهانه هزینه انجام نشد.", requestId: "mock-monthly-trend-001" });
    if (initialState === "empty") return { months: [], estimateSource: "mock_seed" };
    const actualMonths = aggregateConfirmedInvoicesByMonth(buildSeedInvoices(context));
    return {
      estimateSource: "mock_seed",
      months: actualMonths.map((month, index) => ({
        ...month,
        estimateIrr: SEED_MONTHLY_ESTIMATE_IRR[index] ?? null,
      })),
    };
  }

  return Object.freeze({ getOverview, getLiveReport, getVariances, issueSnapshot, getSnapshot, downloadSnapshotCsv, getMonthlyTrend });
}
