import test from "node:test";
import assert from "node:assert/strict";
import { createApiFinancialItemsAdapter } from "../../src/adapters/api/financial-items-api-adapter.js";
import { buildEstimateLinesCsv } from "../../src/features/financial-items/financial-items-csv.js";
import {
  isScheduleBackedLine, scheduleCostOf, selectEstimateRows,
} from "../../src/features/financial-items/financial-items-presentation.js";

/**
 * Which rows are the current schedule's, and the three money columns that are
 * not each other.
 *
 * The schedule's cost, the price the estimate was fixed at, and the price in
 * force today are three different numbers about one item. The page shows all
 * three and derives none of them from another — which is the only way an empty
 * price column can be read as "nobody has priced this" rather than "free".
 */

const context = { organizationId: "org-1", projectId: "terrace" };

const scheduleResource = {
  id: "r-mpp", type: "material", code: "MPP-R98", title: "بتن 400", baseUnit: "m3",
  dimension: "volume", externalResourceId: null, sourceResourceUid: 98,
  createdBy: "u", createdAt: "2026-01-01",
};
const legacyResource = {
  id: "r-legacy", type: "material", code: "MSP-T1951", title: "اجرای دیوارچینی داخلی",
  baseUnit: "unit", dimension: "count", externalResourceId: "1951", sourceResourceUid: null,
  createdBy: "u", createdAt: "2026-01-01",
};
const manualResource = {
  id: "r-manual", type: "equipment", code: "123", title: "جرثقیل", baseUnit: "day",
  dimension: "equipment_time", externalResourceId: null, sourceResourceUid: null,
  createdBy: "u", createdAt: "2026-01-01",
};

const scheduleLine = (id, activity, resourceId, assignment) => ({
  id, resourceId, activityExternalId: activity, assignmentExternalId: String(assignment),
  sourceAssignmentUid: assignment, sourceTaskUid: 500, originalQuantity: null,
  revisedQuantity: null, originalUnitPriceIrr: null, source: "progress_feed",
  revision: 0, revisions: [],
});
const legacyLine = {
  id: "l-legacy", resourceId: "r-legacy", activityExternalId: "1.9.5.4",
  assignmentExternalId: "1951", sourceAssignmentUid: null, sourceTaskUid: null,
  originalQuantity: "9.0000", revisedQuantity: "9.0000", originalUnitPriceIrr: "1000000",
  source: "manual_entry", revision: 0, revisions: [],
};
const manualLine = {
  id: "l-manual", resourceId: "r-manual", activityExternalId: "1.6",
  assignmentExternalId: null, sourceAssignmentUid: null, sourceTaskUid: null,
  originalQuantity: "4.0000", revisedQuantity: "4.0000", originalUnitPriceIrr: "8000000",
  source: "manual_entry", revision: 0, revisions: [],
};

function stub({ resources, lines, activities = [], prices = [] }) {
  const seen = [];
  return {
    seen,
    request(path) {
      seen.push(path);
      if (path.endsWith("/resources")) return Promise.resolve(resources);
      if (path.endsWith("/estimate-lines")) return Promise.resolve(lines);
      if (path.includes("/activities?")) {
        return Promise.resolve({ items: activities, page: 1, pageSize: 200,
          totalItems: activities.length, totalPages: 1 });
      }
      if (path.includes("/prices/current?")) return Promise.resolve(prices);
      if (path.endsWith("/unit-registry")) return Promise.resolve({ items: [] });
      throw new Error(`unexpected request ${path}`);
    },
  };
}

const activities = [
  { activityExternalId: "1.6", taskExternalId: "500", title: "اصلاح هندسی بلوار شاهنامه",
    wbsCode: "1.6", mppTaskCostIrr: "365730884784", status: "active" },
  { activityExternalId: "1.9.5.4", taskExternalId: "900", title: "دیوارچینی",
    wbsCode: "1.9.5.4", mppTaskCostIrr: "12000000", status: "active" },
];

async function workspaceOf(options) {
  return createApiFinancialItemsAdapter(context, stub(options)).getWorkspace();
}

test("shows a row for a real activity paired with a real cost item", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)], activities,
  });
  const selected = selectEstimateRows(workspace.estimateLines, workspace.resources);
  assert.equal(selected.rows.length, 1);
  assert.equal(selected.scheduleBackedCount, 1);
  const [only] = selected.rows;
  assert.equal(only.activityTitle, "اصلاح هندسی بلوار شاهنامه");
  assert.equal(workspace.resources[0].title, "بتن 400");
});

test("an activity with no cost item produces no financial item row", () => {
  // The line names a resource the catalogue does not have — there is nothing to
  // put in «قلم هزینه», and the activity's own name must never fill that in.
  const selected = selectEstimateRows(
    [{ lineId: "l-x", resourceId: "gone", activityTitle: "اجرای سابگرید" }], []);
  assert.deepEqual(selected.rows, []);
  assert.equal(selected.orphanCount, 1);
});

test("requires both halves of the schedule identity before calling a line schedule-backed", () => {
  assert.equal(isScheduleBackedLine({ sourceAssignmentUid: 3001 }, { sourceResourceUid: 98 }), true);
  assert.equal(isScheduleBackedLine({ sourceAssignmentUid: null }, { sourceResourceUid: 98 }), false);
  assert.equal(isScheduleBackedLine({ sourceAssignmentUid: 3001 }, { sourceResourceUid: null }), false);
  // assignmentExternalId is free text and must not stand in for the uid.
  assert.equal(isScheduleBackedLine({ assignmentExternalId: "3001" }, { sourceResourceUid: 98 }), false);
});

test("keeps a hand-entered item and its line while withholding the legacy one", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource, legacyResource, manualResource],
    lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001), legacyLine, manualLine],
    activities,
  });
  const selected = selectEstimateRows(workspace.estimateLines, workspace.resources);
  assert.deepEqual(selected.rows.map((line) => line.lineId), ["l-1", "l-manual"]);
  assert.equal(selected.hiddenLegacyCount, 1);
  assert.equal(selected.scheduleBackedCount, 1);
  assert.equal(selected.manualCount, 1, "a genuine manual item is not a legacy one");
});

test("one cost item used by two activities is two rows, not one", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource],
    lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001), scheduleLine("l-2", "1.9.5.4", "r-mpp", 3002)],
    activities,
  });
  const selected = selectEstimateRows(workspace.estimateLines, workspace.resources);
  assert.equal(selected.rows.length, 2);
  assert.notEqual(selected.rows[0].activityExternalId, selected.rows[1].activityExternalId);
  assert.equal(selected.rows[0].resourceId, selected.rows[1].resourceId);
});

test("labels a schedule line by the source the database stored, not by a guess", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource, manualResource],
    lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001), manualLine],
    activities,
  });
  assert.equal(workspace.estimateLines[0].source, "progress_feed");
  assert.equal(workspace.estimateLines[1].source, "manual_entry");
  const csv = buildEstimateLinesCsv({ lines: workspace.estimateLines, resources: workspace.resources });
  assert.ok(csv.includes("برنامه زمان‌بندی"), "the export names the source too");
  assert.ok(!csv.includes("progress_feed"), "and never leaks the machine value");
});

test("carries the schedule's cost from the activity, not from the item", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource],
    lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001), scheduleLine("l-2", "1.6", "r-mpp", 3002)],
    activities,
  });
  const [first, second] = workspace.estimateLines;
  assert.equal(scheduleCostOf(first), "365730884784");
  assert.equal(scheduleCostOf(second), "365730884784", "both items of one activity read one figure");
  assert.equal(scheduleCostOf({ mppTaskCostIrr: null }), null);
});

test("the schedule's cost never becomes the price the estimate was fixed at", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)], activities,
  });
  const [only] = workspace.estimateLines;
  assert.equal(only.mppTaskCostIrr, "365730884784");
  assert.equal(only.originalUnitPriceIRR, null, "an MPP cost is not a Finance unit price");
});

test("the schedule's cost never becomes today's price", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)],
    activities, prices: [],
  });
  const [only] = workspace.estimateLines;
  assert.equal(only.mppTaskCostIrr, "365730884784");
  assert.equal(only.currentUnitPriceIRR, null, "no price version means no price, whatever the schedule cost");
});

test("today's price is unavailable, not zero, when nobody has priced the item", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)],
    activities, prices: [{ resourceId: "r-mpp", currentPriceIrr: null, scopeKind: null }],
  });
  assert.equal(workspace.estimateLines[0].currentUnitPriceIRR, null);
  assert.notEqual(workspace.estimateLines[0].currentUnitPriceIRR, 0);
  assert.notEqual(workspace.estimateLines[0].currentUnitPriceIRR, "0");
});

test("reads today's price from the price endpoint when one exists", async () => {
  const client = stub({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)],
    activities, prices: [{ resourceId: "r-mpp", currentPriceIrr: "4200000", scopeKind: "project" }],
  });
  const workspace = await createApiFinancialItemsAdapter(context, client).getWorkspace();
  assert.equal(workspace.estimateLines[0].currentUnitPriceIRR, "4200000");
  assert.ok(client.seen.some((path) => path.includes("/prices/current?asOf=")),
    "the same endpoint the قیمت روز page reads, so the two cannot disagree");
});

test("an unknown quantity stays unknown and never becomes zero", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)], activities,
  });
  const [only] = workspace.estimateLines;
  assert.equal(only.originalQuantity, null);
  assert.equal(only.revisedQuantity, null);
  for (const value of [only.originalQuantity, only.revisedQuantity, only.originalUnitPriceIRR]) {
    assert.notEqual(value, 0);
    assert.notEqual(value, "0");
  }
});

test("a revision is not an overrun against an estimate that was never set", async () => {
  const line = scheduleLine("l-1", "1.6", "r-mpp", 3001);
  line.revisions = [{ id: "rev-1", revision: 1, previousQuantity: null, newQuantity: "12.0000",
    reason: "اصلاح", createdBy: "u", createdAt: "2026-02-01" }];
  const workspace = await workspaceOf({ resources: [scheduleResource], lines: [line], activities });
  assert.equal(workspace.estimateLines[0].revisions[0].isOverrun, false,
    "there is no baseline to exceed; reading null as zero made every revision an overrun");
});

test("the schedule's identity reaches the page as its own fields", async () => {
  const workspace = await workspaceOf({
    resources: [scheduleResource], lines: [scheduleLine("l-1", "1.6", "r-mpp", 3001)], activities,
  });
  const [only] = workspace.estimateLines;
  assert.equal(only.sourceAssignmentUid, 3001);
  assert.equal(only.sourceTaskUid, 500);
  assert.equal(only.taskExternalId, "500", "from the catalogue, not from the WBS code");
});
