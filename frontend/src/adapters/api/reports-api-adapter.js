import { financeBase } from "./api-utils.js";

export function createApiReportsAdapter(context, client) {
  const base = financeBase(context);

  async function getLiveReport({ reportingDate, progressSnapshotId }) {
    const query = new URLSearchParams({ reportingDate });
    if (progressSnapshotId) query.set("progressSnapshotId", progressSnapshotId);
    return client.request(`${base}/reports/live?${query.toString()}`);
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

  return Object.freeze({ getLiveReport, issueSnapshot, getSnapshot, downloadSnapshotCsv });
}
