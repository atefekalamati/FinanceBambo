import { financeBase } from "./api-utils.js";

export function createApiReportsAdapter(context, client) {
  const base = financeBase(context);

  async function getLiveReport({ reportingDate, progressSnapshotId }) {
    const query = new URLSearchParams({ reportingDate });
    if (progressSnapshotId) query.set("progressSnapshotId", progressSnapshotId);
    return client.request(`${base}/reports/live?${query.toString()}`);
  }

  return Object.freeze({ getLiveReport });
}
