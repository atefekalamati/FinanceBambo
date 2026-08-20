import test from "node:test";
import assert from "node:assert/strict";
import { createMockProgressAdapter } from "../../src/adapters/mock/progress-adapter.js";

const context = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "11111111-1111-4111-8111-111111111111",
  projectId: "sample_site_01",
};

test("lists immutable snapshot metadata in newest reporting-date order", async () => {
  const adapter = createMockProgressAdapter(context);
  const snapshots = await adapter.getSnapshots();
  assert.equal(snapshots.length, 3);
  assert.equal(snapshots[0].reportingDate, "2026-08-02");
  assert.equal(snapshots[0].organizationId, context.organizationId);
  assert.equal(snapshots[0].projectId, context.projectId);
  assert.ok(snapshots.every((snapshot) => snapshot.progressSnapshotId && snapshot.sourceFileVersionId));
  assert.ok(
    snapshots.every((snapshot) => !("assignmentCount" in snapshot) && !("assignments" in snapshot)),
    "ProgressSnapshotResponse carries no assignment data; counting it here would mean one feed request per snapshot",
  );
});

test("returns assignment-level, task-fallback and manual-override source methods", async () => {
  const adapter = createMockProgressAdapter(context);
  const snapshots = await adapter.getSnapshots();
  const feeds = await Promise.all(snapshots.map((snapshot) => adapter.getFeed(snapshot.progressSnapshotId)));
  const methods = feeds.flatMap((feed) => feed.assignments.map((assignment) => assignment.sourceMethod));
  assert.ok(methods.includes("assignment_actual"));
  assert.ok(methods.includes("task_progress_fallback"));
  assert.ok(methods.includes("manual_override"));
});

test("preserves null as missing and keeps general cost quantity fields nullable", async () => {
  const adapter = createMockProgressAdapter(context);
  const snapshots = await adapter.getSnapshots();
  const oldest = snapshots.at(-1);
  const feed = await adapter.getFeed(oldest.progressSnapshotId);
  const generalCost = feed.assignments.find((assignment) => assignment.resourceType === "general_cost");
  assert.equal(generalCost.unit, null);
  assert.equal(generalCost.plannedQuantity, null);
  assert.equal(generalCost.actualQuantity, null);
  assert.equal(generalCost.remainingQuantity, null);
});

test("keeps manual override linked to its snapshot and original calculated value", async () => {
  const adapter = createMockProgressAdapter(context);
  const snapshots = await adapter.getSnapshots();
  const latest = snapshots[0];
  const feed = await adapter.getFeed(latest.progressSnapshotId);
  const assignment = feed.assignments[0];
  assert.equal(assignment.manualOverride.progressSnapshotId, latest.progressSnapshotId);
  assert.equal(assignment.manualOverride.previousCalculatedValue, "270.0000");
  assert.equal(assignment.actualQuantity, assignment.manualOverride.newValue);
  assert.equal("updateFeed" in adapter, false);
});

test("returns empty/error states and rejects an unknown snapshot", async () => {
  const emptyAdapter = createMockProgressAdapter(context, { initialState: "empty" });
  assert.deepEqual(await emptyAdapter.getSnapshots(), []);
  await assert.rejects(emptyAdapter.getFeed("missing"), (error) => error.code === "FINANCE_NOT_FOUND");
  const errorAdapter = createMockProgressAdapter(context, { initialState: "error" });
  await assert.rejects(errorAdapter.getSnapshots(), (error) => error.code === "PROGRESS_FEED_UNAVAILABLE");
});

test("appends an audited manual override and preserves the computed value", async () => {
  const adapter = createMockProgressAdapter({ ...context, permissionCodes: ["finance.view", "finance.edit"] });
  const snapshots = await adapter.getSnapshots();
  const oldest = snapshots.at(-1);
  const feed = await adapter.getFeed(oldest.progressSnapshotId);
  const assignment = feed.assignments[0];
  const response = await adapter.createOverride({
    progressSnapshotId: oldest.progressSnapshotId,
    assignmentExternalId: assignment.assignmentExternalId,
    overrideValue: "2600.5000",
    reason: "اصلاح براساس صورت‌جلسه کارگاه",
  });

  assert.equal(response.override.previousCalculatedValue, "2500.0000");
  assert.equal(response.override.newValue, "2600.5000");
  assert.equal(response.override.progressSnapshotId, oldest.progressSnapshotId);
  assert.equal(response.override.userId, context.userId);
  assert.equal(response.override.source, "manual_override");
  assert.equal(response.feed.assignments[0].sourceMethod, "manual_override");
  assert.equal((await adapter.getOverrideHistory()).length, 1);
});

test("rejects a manual override without edit permission or reason", async () => {
  const deniedAdapter = createMockProgressAdapter({ ...context, permissionCodes: ["finance.view"] });
  const deniedSnapshot = (await deniedAdapter.getSnapshots()).at(-1);
  await assert.rejects(
    deniedAdapter.createOverride({ progressSnapshotId: deniedSnapshot.progressSnapshotId, assignmentExternalId: "asg-foundation-rebar", overrideValue: "2600", reason: "اصلاح معتبر" }),
    (error) => error.status === 403,
  );

  const adapter = createMockProgressAdapter({ ...context, permissionCodes: ["finance.edit"] });
  const snapshot = (await adapter.getSnapshots()).at(-1);
  await assert.rejects(
    adapter.createOverride({ progressSnapshotId: snapshot.progressSnapshotId, assignmentExternalId: "asg-foundation-rebar", overrideValue: "2600", reason: "" }),
    (error) => error.status === 422,
  );
});
