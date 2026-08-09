import { ApiError } from "../../core/api/api-error.js";
import { financeBase, jsonOptions } from "./api-utils.js";

export function createApiProgressAdapter(context, client) {
  const base = financeBase(context);
  async function getSnapshots() {
    const snapshots = await client.request(`${base}/progress-snapshots`);
    const ordered = snapshots.sort((left, right) => right.reportingDate.localeCompare(left.reportingDate));
    return Promise.all(ordered.map(async (snapshot) => {
      const feed = await getFeed(snapshot.progressSnapshotId);
      return { snapshot, assignmentCount: feed.assignments.length };
    }));
  }
  async function getFeed(progressSnapshotId) {
    return client.request(`${base}/progress-snapshots/${encodeURIComponent(progressSnapshotId)}/feed`);
  }
  async function createOverride({ progressSnapshotId, assignmentExternalId, overrideValue, reason }) {
    const [lines, feed] = await Promise.all([client.request(`${base}/estimate-lines`), getFeed(progressSnapshotId)]);
    const line = lines.find((item) => item.assignmentExternalId === assignmentExternalId);
    const assignment = feed.assignments.find((item) => item.assignmentExternalId === assignmentExternalId);
    if (!line || !assignment) throw new ApiError({ status: 422, code: "PROGRESS_LINE_MAPPING_MISSING", message: "اتصال Assignment پیشرفت به خط برآورد در Backend پیدا نشد." });
    const computedValue = assignment.manualOverride?.previousCalculatedValue ?? assignment.actualQuantity;
    const override = await client.request(`${base}/estimate-lines/${encodeURIComponent(line.id)}/progress-override`, jsonOptions("POST", { progressSnapshotId, computedValue, overrideValue, reason }));
    return { feed: await getFeed(progressSnapshotId), override };
  }
  async function getOverrideHistory() {
    return [];
  }
  return Object.freeze({ getSnapshots, getFeed, createOverride, getOverrideHistory });
}
