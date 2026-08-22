import { ApiError } from "../../core/api/api-error.js";
import { financeBase, jsonOptions } from "./api-utils.js";

export function createApiProgressAdapter(context, client) {
  const base = financeBase(context);

  /**
   * GET /progress-snapshots answers with list[ProgressSnapshotResponse], which
   * carries no assignment count. Counting used to mean fetching every feed —
   * one request per snapshot — so the count is now read from the feed of the
   * snapshot actually being viewed instead.
   */
  async function getSnapshots() {
    const snapshots = await client.request(`${base}/progress-snapshots`);
    return [...snapshots].sort((left, right) => right.reportingDate.localeCompare(left.reportingDate));
  }

  async function getFeed(progressSnapshotId) {
    return client.request(`${base}/progress-snapshots/${encodeURIComponent(progressSnapshotId)}/feed`);
  }

  /**
   * The override endpoint is addressed by estimate line, so the line has to be
   * resolved first. The Backend maps an assignment to a line by
   * `assignment_external_id` **or** by `activity_external_id` matching the
   * assignment's `task.activityCode`; matching only on the assignment id here
   * rejected every override, because estimate lines imported from a progress
   * feed carry the activity code and no assignment id.
   */
  async function createOverride({ progressSnapshotId, assignmentExternalId, activityExternalId, overrideValue, reason }) {
    const lines = await client.request(`${base}/estimate-lines`);
    const line = lines.find((item) => assignmentExternalId && item.assignmentExternalId === assignmentExternalId)
      ?? lines.find((item) => activityExternalId && item.activityExternalId === activityExternalId);

    if (!line) {
      throw new ApiError({ status: 422, code: "PROGRESS_LINE_MAPPING_MISSING", message: "خط برآورد متناظر با فعالیت در Backend پیدا نشد." });
    }

    const override = await client.request(
      `${base}/estimate-lines/${encodeURIComponent(line.id)}/progress-override`,
      jsonOptions("POST", { progressSnapshotId, overrideValue, reason }),
    );
    return { feed: await getFeed(progressSnapshotId), override };
  }

  async function getOverrideHistory() {
    return [];
  }

  return Object.freeze({ getSnapshots, getFeed, createOverride, getOverrideHistory });
}
