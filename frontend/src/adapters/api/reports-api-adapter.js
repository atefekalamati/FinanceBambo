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

  return Object.freeze({ getOverview, getLiveReport, getVariances, issueSnapshot, getSnapshot, downloadSnapshotCsv });
}
