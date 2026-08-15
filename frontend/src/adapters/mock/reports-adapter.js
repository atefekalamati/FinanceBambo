import { ApiError } from "../../core/api/api-error.js";

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
      scope: { organizationId: context.organizationId, projectId: context.projectId },
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

  return Object.freeze({ getLiveReport, issueSnapshot, getSnapshot, downloadSnapshotCsv });
}
