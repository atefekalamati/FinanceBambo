import { ApiError } from "../../core/api/api-error.js";
import { aggregateConfirmedInvoicesByMonth } from "../../shared/reports/monthly-trend.js";
import { buildSeedInvoices } from "./invoices-adapter.js";
import { buildWbsNodes, unattributedActualIrr } from "./wbs-fixture.js";

/**
 * The per-period plan, for the reference dataset only.
 *
 * The real figures come from the host platform's periodic files: each period
 * carries its own estimated quantities, this module prices them, and the
 * cumulative curve is the running sum. That pipe does not exist yet, so the
 * reference dataset models its shape — a construction ramp, slow at the start,
 * heaviest through the structural months, tapering at handover.
 *
 * The API adapter still reports the series as unavailable rather than deriving
 * a lookalike, so none of this can reach a real project. It exists so the
 * cumulative chart can be judged before the pipe is built, and it is labelled
 * `demo_period_plan` at the boundary rather than dressed up as a real source.
 */
const PLAN_SHAPE = Object.freeze([2, 3, 5, 8, 11, 13, 14, 13, 11, 8, 7, 5]);

function planWeights(count) {
  if (count <= 0) return [];
  return Array.from({ length: count }, (unused, index) => PLAN_SHAPE[Math.floor((index * PLAN_SHAPE.length) / count)]);
}

/**
 * Splits a total across periods without losing a rial: every period takes its
 * whole share and the last one absorbs the remainder, so the periods always sum
 * to exactly the figure they were divided from.
 */
function distributePlan(count, totalIrr) {
  const total = BigInt(totalIrr);
  const weights = planWeights(count);
  const sum = BigInt(weights.reduce((result, weight) => result + weight, 0));
  if (sum === 0n) return weights.map(() => "0");
  let allocated = 0n;
  return weights.map((weight, index) => {
    if (index === weights.length - 1) return String(total - allocated);
    const share = (total * BigInt(weight)) / sum;
    allocated += share;
    return String(share);
  });
}
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
        // Deliberately over its estimate. A reference dataset in which nothing
        // ever exceeds its budget cannot show the one state the comparison
        // exists to reveal.
        { resourceType: "equipment", initialEstimateIrr: "2750000000", revisedEstimateIrr: "2680000000", actualCostIrr: "3400000000", remainingPhysicalCostIrr: "1930000000", forecastFinalIrr: "4100000000" },
        { resourceType: "general_cost", initialEstimateIrr: "2000000000", revisedEstimateIrr: "2050000000", actualCostIrr: "330000000", remainingPhysicalCostIrr: "1640000000", forecastFinalIrr: "1970000000" },
      ],
      // One row per estimate line, the way the service answers: میلگرد is used on
      // two activities and arrives twice, and a line whose quantity was never
      // revised arrives with a deviation of zero. Both are what the presentation
      // has to fold away, so the mock has to contain them.
      topPriceVariances: [
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000001", activityExternalId: "ACT-102", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", baseUnit: "kg", varianceIrr: "460000000", priceAvailable: true },
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000002", activityExternalId: "ACT-201", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", baseUnit: "kg", varianceIrr: "312000000", priceAvailable: true },
        { resourceId: "20000000-0000-4000-8000-000000000003", estimateLineId: "30000000-0000-4000-8000-000000000004", activityExternalId: "ACT-201", resourceCode: "EQ-CRANE", resourceTitle: "جرثقیل", resourceType: "equipment", baseUnit: "hour", varianceIrr: "185000000", priceAvailable: true },
      ],
      topQuantityVariances: [
        { resourceId: "20000000-0000-4000-8000-000000000002", estimateLineId: "30000000-0000-4000-8000-000000000003", activityExternalId: "ACT-202", resourceCode: "LAB-FORM", resourceTitle: "اکیپ قالب‌بندی", resourceType: "labor", baseUnit: "person_hour", initialQuantity: "900.0000", revisedQuantity: "1025.7500", varianceQuantity: "125.7500" },
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000001", activityExternalId: "ACT-102", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", baseUnit: "kg", initialQuantity: "10000.0000", revisedQuantity: "10042.5000", varianceQuantity: "42.5000" },
        { resourceId: "20000000-0000-4000-8000-000000000001", estimateLineId: "30000000-0000-4000-8000-000000000002", activityExternalId: "ACT-201", resourceCode: "MAT-REBAR", resourceTitle: "میلگرد", resourceType: "material", baseUnit: "kg", initialQuantity: "8500.0000", revisedQuantity: "8500.0000", varianceQuantity: "0.0000" },
        { resourceId: "20000000-0000-4000-8000-000000000003", estimateLineId: "30000000-0000-4000-8000-000000000004", activityExternalId: "ACT-201", resourceCode: "EQ-CRANE", resourceTitle: "جرثقیل", resourceType: "equipment", baseUnit: "hour", initialQuantity: "160.0000", revisedQuantity: "160.0000", varianceQuantity: "0.0000" },
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
    if (initialState === "empty") return { months: [], estimateSource: "unavailable" };
    // The periodic plan the cumulative curve compares against. The real one
    // arrives with the host's period files; this is the reference dataset's
    // stand-in, named as such at the boundary so nothing downstream mistakes it
    // for a figure the service produced.
    const actualMonths = aggregateConfirmedInvoicesByMonth(buildSeedInvoices(context));
    const plan = distributePlan(actualMonths.length, "18650000000");
    return {
      estimateSource: "demo_period_plan",
      actualSource: "confirmed_financial_documents",
      months: actualMonths.map((month, index) => ({
        ...month,
        estimateIrr: plan[index] ?? null,
      })),
    };
  }

  /**
   * Cost rolled up the breakdown structure. The service has no such endpoint
   * yet; this answers the shape it is specified to answer so the report can be
   * built and reviewed before it ships.
   */
  async function getWbsRollup({ parentWbsCode = null } = {}) {
    await wait(240);
    if (initialState === "error") throw new ApiError({ status: 503, code: "WBS_ROLLUP_UNAVAILABLE", message: "دریافت گزارش سطح‌بندی هزینه انجام نشد.", requestId: "mock-wbs-001" });
    if (initialState === "empty") return { available: true, nodes: [], unattributedActualIrr: null, source: "demo_wbs_rollup" };
    const all = buildWbsNodes();
    const nodes = parentWbsCode
      ? all.filter((node) => node.parentWbsCode === parentWbsCode)
      : all.filter((node) => node.parentWbsCode === null);
    return {
      available: true,
      nodes,
      // Only claimed at the top level: a phase's own children account for all of
      // that phase, so an unattributed figure there would be double-counted.
      unattributedActualIrr: parentWbsCode ? null : unattributedActualIrr(all),
      source: "demo_wbs_rollup",
    };
  }

  return Object.freeze({ getOverview, getLiveReport, getVariances, issueSnapshot, getSnapshot, downloadSnapshotCsv, getMonthlyTrend, getWbsRollup });
}
