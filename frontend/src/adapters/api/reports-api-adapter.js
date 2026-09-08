import { financeBase } from "./api-utils.js";

export function createApiReportsAdapter(context, client) {
  const base = financeBase(context);

  function createReportQuery({ reportingDate, progressSnapshotId }) {
    const query = new URLSearchParams({ reportingDate });
    if (progressSnapshotId) query.set("progressSnapshotId", progressSnapshotId);
    return query;
  }

  async function getOverview({ reportingDate, progressSnapshotId }) {
    const query = createReportQuery({ reportingDate, progressSnapshotId });
    return client.request(`${base}/overview?${query.toString()}`);
  }

  async function getLiveReport({ reportingDate, progressSnapshotId }) {
    const query = createReportQuery({ reportingDate, progressSnapshotId });
    return client.request(`${base}/reports/live?${query.toString()}`);
  }

  async function getVariances({
    reportingDate,
    progressSnapshotId,
    varianceType = "all",
    resourceType,
    query: searchQuery,
    page = 1,
    pageSize = 200,
    sortBy,
    sortDirection = "desc",
  }) {
    const query = createReportQuery({ reportingDate, progressSnapshotId });
    query.set("varianceType", varianceType);
    query.set("page", String(page));
    query.set("pageSize", String(pageSize));
    query.set("sortDirection", sortDirection);
    if (resourceType) query.set("resourceType", resourceType);
    if (searchQuery) query.set("query", searchQuery);
    if (sortBy) query.set("sortBy", sortBy);
    return client.request(`${base}/reports/live/variances?${query.toString()}`);
  }

  async function issueSnapshot({ reportingDate, progressSnapshotId = null }) {
    return client.request(`${base}/report-snapshots`, {
      method: "POST",
      body: JSON.stringify({ reportingDate, progressSnapshotId }),
    });
  }

  async function getSnapshot(reportId) {
    return client.request(`${base}/report-snapshots/${encodeURIComponent(reportId)}`);
  }

  async function downloadSnapshotCsv(reportId) {
    return client.download(`${base}/report-snapshots/${encodeURIComponent(reportId)}/csv`);
  }

  /**
   * The service aggregates the series itself, by Persian month.
   *
   * The window is an anchor date plus a month count rather than a from/to pair,
   * because Persian months do not line up with Gregorian dates: an arbitrary
   * range would open and close on half a month, and the chart would draw those
   * two stubs as real dips.
   *
   * `estimateIrr` comes back null on every point and stays null. No estimate
   * line carries a planned date, so there is no monthly baseline to report, and
   * the service says so in a MONTHLY_ESTIMATE_UNAVAILABLE warning rather than
   * sending zero — zero would assert that nothing was budgeted for that month.
   * Coercing it here would put a floor on the chart and turn every month into an
   * overrun.
   */
  async function getMonthlyTrend({ reportingDate, monthCount = 12 } = {}) {
    const query = new URLSearchParams({ reportingDate, monthCount: String(monthCount) });
    const payload = await client.request(`${base}/reports/monthly?${query.toString()}`);
    return {
      months: (payload.months ?? []).map((month) => ({
        persianYear: month.persianYear,
        persianMonth: month.persianMonth,
        actualCostIrr: month.actualCostIrr == null ? null : String(month.actualCostIrr),
        estimateIrr: month.estimateIrr == null ? null : String(month.estimateIrr),
        invoiceCount: month.invoiceCount ?? 0,
        reversalCount: month.reversalCount ?? 0,
        breakdown: month.breakdown ?? null,
      })),
      estimateSource: payload.estimateSource ?? "unavailable",
      actualSource: payload.actualSource ?? "confirmed_financial_documents",
      windowStart: payload.windowStart ?? null,
      windowEnd: payload.windowEnd ?? null,
      warnings: payload.warnings ?? [],
    };
  }

  /**
   * Cost rolled up the project's breakdown structure.
   *
   * Older deployments may not have the endpoint. A 404 is
   * this project's answer to "is that report available", so it comes back as an
   * empty result carrying `available: false` and the page says what is missing.
   * Every other status still raises: a 500 here is a real fault and hiding it
   * behind "not available yet" would keep it hidden after the endpoint lands.
   */
  async function getWbsRollup({ reportingDate, progressSnapshotId, parentWbsCode = null, level = 1 } = {}) {
    const query = new URLSearchParams({ reportingDate });
    if (progressSnapshotId) query.set("progressSnapshotId", progressSnapshotId);
    if (parentWbsCode) query.set("parentWbsCode", parentWbsCode);
    else query.set("level", String(level));
    try {
      const payload = await client.request(`${base}/reports/live/by-wbs?${query.toString()}`);
      return {
        available: true,
        nodes: (payload.nodes ?? payload.items ?? []).map((node) => ({
          wbsCode: node.wbsCode,
          title: node.title ?? null,
          parentWbsCode: node.parentWbsCode ?? null,
          activityCount: node.activityCount ?? 0,
          childCount: node.childCount ?? 0,
          estimateLineCount: node.estimateLineCount ?? null,
          calculationStatus: node.calculationStatus ?? null,
          weight: node.weight == null ? null : String(node.weight),
          progressPercent: node.progressPercent == null ? null : String(node.progressPercent),
          initialEstimateIrr: node.initialEstimateIrr == null ? null : String(node.initialEstimateIrr),
          revisedEstimateIrr: node.revisedEstimateIrr == null ? null : String(node.revisedEstimateIrr),
          actualCostIrr: node.actualCostIrr == null ? null : String(node.actualCostIrr),
          remainingPhysicalCostIrr: node.remainingPhysicalCostIrr == null ? null : String(node.remainingPhysicalCostIrr),
          moneyRequiredIrr: node.moneyRequiredIrr == null ? null : String(node.moneyRequiredIrr),
          forecastFinalIrr: node.forecastFinalIrr == null ? null : String(node.forecastFinalIrr),
          breakdown: node.breakdown ?? null,
        })),
        unattributedActualIrr: payload.unattributedActualIrr == null ? null : String(payload.unattributedActualIrr),
        unmappedWbsActualIrr: payload.unmappedWbsActualIrr == null ? null : String(payload.unmappedWbsActualIrr),
        unmappedEstimateLineCount: payload.unmappedEstimateLineCount ?? null,
        totals: payload.totals ?? null,
        calculationStatus: payload.calculationStatus ?? null,
        warnings: payload.warnings ?? [],
        source: payload.source ?? "service",
      };
    } catch (error) {
      if (error?.status === 404) return { available: false, nodes: [], unattributedActualIrr: null, source: "unavailable" };
      throw error;
    }
  }

  return Object.freeze({ getOverview, getLiveReport, getVariances, issueSnapshot, getSnapshot, downloadSnapshotCsv, getMonthlyTrend, getWbsRollup });
}
