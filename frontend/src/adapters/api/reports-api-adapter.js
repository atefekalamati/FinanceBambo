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
        actualCostIrr: String(month.actualCostIrr ?? "0"),
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

  return Object.freeze({ getOverview, getLiveReport, getVariances, issueSnapshot, getSnapshot, downloadSnapshotCsv, getMonthlyTrend });
}
