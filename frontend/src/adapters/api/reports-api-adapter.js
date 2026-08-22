import { financeBase } from "./api-utils.js";
import { buildMonthlyTrendPreview, isMonthlyTrendPreviewEnabled } from "./monthly-trend-preview.js";

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
   * No route returns a monthly series. LiveMetrics and TypeBreakdown have no
   * time dimension, EstimateLine has no dates, and the only date-bearing money
   * is the invoice list — which would give actual cost but never an estimate
   * baseline, and only by paging the whole project.
   *
   * Reporting the series as unavailable is the honest answer: half a chart
   * labelled as a comparison would read as "no overspend" when it is really
   * "no baseline". Replace this once the Backend exposes the monthly report.
   */
  async function getMonthlyTrend({ reportingDate } = {}) {
    // TEMPORARY: opt-in preview data so the chart can be reviewed before the
    // Backend has a monthly report. See monthly-trend-preview.js for how to
    // remove it. Off unless a developer asks for it.
    if (isMonthlyTrendPreviewEnabled()) return buildMonthlyTrendPreview({ reportingDate });
    return {
      months: [],
      estimateSource: "unavailable",
      unavailableReason: "سرویس گزارش مالی هنوز سری زمانی ماهانه ارائه نمی‌دهد.",
    };
  }

  return Object.freeze({ getOverview, getLiveReport, getVariances, issueSnapshot, getSnapshot, downloadSnapshotCsv, getMonthlyTrend });
}
