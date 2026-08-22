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

export function createMockReportsAdapter(context, { initialState = "success" } = {}) {
  const snapshots = new Map();

  async function getLiveReport({ reportingDate, progressSnapshotId }) {
    await wait();
    if (initialState === "error") throw new ApiError({ status: 503, code: "LIVE_REPORT_UNAVAILABLE", message: "دریافت خلاصه مالی زنده انجام نشد.", requestId: "mock-live-report-001" });
    if (initialState === "empty") return null;
    return {
      reportingDate,
      progressSnapshotId,
      metrics: {
        initialEstimateIrr: "18650000000",
        actualCostIrr: "6240000000",
        currentExecutedValueIrr: "7150000000",
        remainingPhysicalCostIrr: "12840000000",
        moneyRequiredToContinueIrr: "11610000000",
        forecastFinalCostIrr: "17850000000",
        actualCostPerSquareMeterIrr: "1468235",
        forecastPerSquareMeterIrr: "4200000",
      },
      breakdown: [
        { resourceType: "material", initialEstimateIrr: "9800000000", revisedEstimateIrr: "10200000000", actualCostIrr: "3920000000", remainingPhysicalCostIrr: "5440000000", forecastFinalIrr: "9360000000" },
        { resourceType: "labor", initialEstimateIrr: "4100000000", revisedEstimateIrr: "4250000000", actualCostIrr: "1380000000", remainingPhysicalCostIrr: "2600000000", forecastFinalIrr: "3980000000" },
        { resourceType: "equipment", initialEstimateIrr: "2750000000", revisedEstimateIrr: "2680000000", actualCostIrr: "610000000", remainingPhysicalCostIrr: "1930000000", forecastFinalIrr: "2540000000" },
        { resourceType: "general_cost", initialEstimateIrr: "2000000000", revisedEstimateIrr: "2050000000", actualCostIrr: "330000000", remainingPhysicalCostIrr: "1640000000", forecastFinalIrr: "1970000000" },
      ],
      topPriceVariances: [
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000001", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", varianceIrr: "460000000" },
        { resourceId: "20000000-0000-4000-8000-000000000003", estimateLineId: "30000000-0000-4000-8000-000000000004", resourceCode: "EQ-CRANE", resourceTitle: "جرثقیل", resourceType: "equipment", varianceIrr: "185000000" },
      ],
      topQuantityVariances: [
        { resourceId: "20000000-0000-4000-8000-000000000002", estimateLineId: "30000000-0000-4000-8000-000000000003", resourceCode: "LAB-FORM", resourceTitle: "اکیپ قالب‌بندی", resourceType: "labor", varianceQuantity: "125.75" },
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000002", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", varianceQuantity: "42.5" },
      ],
      warnings: [{ code: "CURRENT_PRICE_MISSING", message: "Current price is missing.", estimateLineId: null }],
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
