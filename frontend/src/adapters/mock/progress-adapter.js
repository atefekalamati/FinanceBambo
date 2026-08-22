import { ApiError } from "../../core/api/api-error.js";

function clone(value) {
  return structuredClone(value);
}

function wait(duration = 300) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

export function createMockProgressAdapter(context, { initialState = "success" } = {}) {
  const overrideHistory = [];
  const feeds = initialState === "empty" ? [] : [
    {
      contractMarker: "MOCK DEVELOPMENT CONTRACT — NOT A PRODUCTION BAMBO ENDPOINT",
      snapshot: { organizationId: context.organizationId, projectId: context.projectId, progressSnapshotId: "33333333-3333-4333-8333-333333333331", sourceFileVersionId: "44444444-4444-4444-8444-444444444441", sourceFileNameSafe: "sample-progress-v1.mpp", importedAt: "2026-08-01T08:30:00Z", importedBy: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3", status: "ready", reportingDate: "2026-07-31" },
      assignments: [
        { assignmentExternalId: "asg-foundation-rebar", resourceExternalId: "res-rebar", resourceName: "میلگرد نمونه", resourceType: "material", unit: "kg", plannedQuantity: "10000.0000", actualQuantity: "2500.0000", remainingQuantity: "7500.0000", plannedWork: null, actualWork: null, remainingWork: null, assignmentWorkCompletePercent: null, sourceMethod: "task_progress_fallback", quality: 0.65, task: { taskExternalId: "task-foundation", taskName: "اجرای فونداسیون نمونه", wbsCode: "1.2", activityCode: "ACT-102", parentTaskExternalId: "task-structure", taskProgressPercent: "25.0000", taskStart: "2026-06-01", taskFinish: "2026-08-30" }, manualOverride: null },
        { assignmentExternalId: "asg-permit-general", resourceExternalId: "res-permit", resourceName: "هزینه مجوز نمونه", resourceType: "general_cost", unit: null, plannedQuantity: null, actualQuantity: null, remainingQuantity: null, plannedWork: null, actualWork: null, remainingWork: null, assignmentWorkCompletePercent: null, sourceMethod: "manual_entry", quality: 1, task: { taskExternalId: "task-permit", taskName: "مجوزهای نمونه", wbsCode: "0.2", activityCode: "ACT-002", parentTaskExternalId: null, taskProgressPercent: null, taskStart: null, taskFinish: null }, manualOverride: null },
      ],
    },
    {
      contractMarker: "MOCK DEVELOPMENT CONTRACT — NOT A PRODUCTION BAMBO ENDPOINT",
      snapshot: { organizationId: context.organizationId, projectId: context.projectId, progressSnapshotId: "33333333-3333-4333-8333-333333333332", sourceFileVersionId: "44444444-4444-4444-8444-444444444442", sourceFileNameSafe: "sample-resource-loaded-v2.mpp", importedAt: "2026-08-02T08:30:00Z", importedBy: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3", status: "ready", reportingDate: "2026-08-01" },
      assignments: [
        { assignmentExternalId: "asg-crane-floor1", resourceExternalId: "res-crane", resourceName: "جرثقیل نمونه", resourceType: "equipment", unit: "hour", plannedQuantity: "160.0000", actualQuantity: "48.0000", remainingQuantity: "112.0000", plannedWork: "160.0000", actualWork: "48.0000", remainingWork: "112.0000", assignmentWorkCompletePercent: "30.0000", sourceMethod: "assignment_actual", quality: 0.98, task: { taskExternalId: "task-floor1-slab", taskName: "سقف طبقه اول نمونه", wbsCode: "2.1", activityCode: "ACT-201", parentTaskExternalId: "task-structure", taskProgressPercent: "28.0000", taskStart: "2026-07-01", taskFinish: "2026-09-15" }, manualOverride: null },
      ],
    },
    {
      contractMarker: "MOCK DEVELOPMENT CONTRACT — NOT A PRODUCTION BAMBO ENDPOINT",
      snapshot: { organizationId: context.organizationId, projectId: context.projectId, progressSnapshotId: "33333333-3333-4333-8333-333333333333", sourceFileVersionId: "44444444-4444-4444-8444-444444444443", sourceFileNameSafe: "sample-progress-v3.mpp", importedAt: "2026-08-03T08:30:00Z", importedBy: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3", status: "ready", reportingDate: "2026-08-02" },
      assignments: [
        { assignmentExternalId: "asg-labor-formwork", resourceExternalId: "res-formwork-team", resourceName: "اکیپ قالب‌بندی نمونه", resourceType: "labor", unit: "hour", plannedQuantity: "900.0000", actualQuantity: "315.0000", remainingQuantity: "585.0000", plannedWork: "900.0000", actualWork: null, remainingWork: null, assignmentWorkCompletePercent: null, sourceMethod: "manual_override", quality: 1, task: { taskExternalId: "task-formwork", taskName: "قالب‌بندی نمونه", wbsCode: "2.2", activityCode: "ACT-202", parentTaskExternalId: "task-structure", taskProgressPercent: "30.0000", taskStart: "2026-07-10", taskFinish: "2026-09-20" }, manualOverride: { previousCalculatedValue: "270.0000", newValue: "315.0000", reason: "اصلاح ساختگی بر اساس صورت‌جلسه نمونه", userId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2", occurredAt: "2026-08-03T09:00:00Z", source: "manual_override", progressSnapshotId: "33333333-3333-4333-8333-333333333333" } },
      ],
    },
  ];

  async function getSnapshots() {
    await wait();
    if (initialState === "error") throw new ApiError({ status: 503, code: "PROGRESS_FEED_UNAVAILABLE", message: "دریافت نسخه‌های پیشرفت انجام نشد.", requestId: "mock-progress-001" });
    return clone(feeds.map((feed) => feed.snapshot).sort((left, right) => right.reportingDate.localeCompare(left.reportingDate)));
  }

  async function getFeed(progressSnapshotId) {
    await wait(380);
    const feed = feeds.find((item) => item.snapshot.progressSnapshotId === progressSnapshotId);
    if (!feed) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "نسخه پیشرفت موردنظر پیدا نشد." });
    return clone(feed);
  }

  async function createOverride({ progressSnapshotId, assignmentExternalId, overrideValue, reason }) {
    await wait(420);
    if (!context.permissionCodes?.includes("finance.edit")) {
      throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز ثبت جایگزینی دستی پیشرفت وجود ندارد.", requestId: "mock-progress-override-403" });
    }

    const feed = feeds.find((item) => item.snapshot.progressSnapshotId === progressSnapshotId);
    const assignment = feed?.assignments.find((item) => item.assignmentExternalId === assignmentExternalId);
    if (!feed || !assignment) {
      throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "خط پیشرفت موردنظر پیدا نشد." });
    }
    if (assignment.resourceType === "general_cost" || assignment.actualQuantity === null) {
      throw new ApiError({ status: 422, code: "PROGRESS_OVERRIDE_NOT_APPLICABLE", message: "برای این خط مقدار محاسبه‌شده قابل جایگزینی وجود ندارد." });
    }
    if (!String(reason ?? "").trim()) {
      throw new ApiError({ status: 422, code: "PROGRESS_OVERRIDE_REASON_REQUIRED", message: "دلیل جایگزینی دستی الزامی است." });
    }

    const previousCalculatedValue = assignment.manualOverride?.previousCalculatedValue ?? assignment.actualQuantity;
    const occurredAt = new Date().toISOString();
    const manualOverride = {
      previousCalculatedValue,
      newValue: overrideValue,
      reason: String(reason).trim(),
      userId: context.userId,
      occurredAt,
      source: "manual_override",
      progressSnapshotId,
    };

    overrideHistory.push({ assignmentExternalId, ...manualOverride });
    assignment.actualQuantity = overrideValue;
    assignment.sourceMethod = "manual_override";
    assignment.quality = 1;
    assignment.manualOverride = manualOverride;
    return clone({ feed, override: manualOverride });
  }

  async function getOverrideHistory() {
    await wait(120);
    return clone(overrideHistory);
  }

  return Object.freeze({ getSnapshots, getFeed, createOverride, getOverrideHistory });
}
