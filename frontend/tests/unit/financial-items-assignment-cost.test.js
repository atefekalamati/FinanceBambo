import test from "node:test";
import assert from "node:assert/strict";
import { createApiFinancialItemsAdapter } from "../../src/adapters/api/financial-items-api-adapter.js";
import {
  assignmentCostOf, scheduleCostOf,
} from "../../src/features/financial-items/financial-items-presentation.js";

/**
 * The schedule's cost, on the right row.
 *
 * An activity's cost is the sum of its items' costs, so writing it on every item
 * would count it once per item — which is why the activity's row carries it and
 * the items' rows carry their own. The file states both; the adapter had been
 * dropping the item's, and the cell was hard-coded empty.
 *
 * These pin the two apart: each item shows ITS assignment's cost, no item shows
 * another's, the activity row is untouched, a real zero survives as zero and an
 * absent figure stays absent.
 */

const context = { organizationId: "org-1", projectId: "terrace" };

// One activity, «اجرای بتن پیش ساخته دال» in the reference file: two items that
// cost something and one the schedule prices at zero.
const activities = [
  { activityExternalId: "1.9.2", taskExternalId: "1227", title: "اجرای بتن پیش ساخته دال",
    wbsCode: "1.9.2", mppTaskCostIrr: "65477773715", status: "active" },
];

const resources = [
  { id: "r-rebar", type: "material", code: "MPP-R98", title: "آرماتور", baseUnit: "kg",
    dimension: "mass", externalResourceId: null, sourceResourceUid: 98,
    createdBy: "u", createdAt: "2026-01-01" },
  { id: "r-concrete", type: "material", code: "MPP-R99", title: "بتن 300", baseUnit: "m3",
    dimension: "volume", externalResourceId: null, sourceResourceUid: 99,
    createdBy: "u", createdAt: "2026-01-01" },
  { id: "r-crane", type: "equipment", code: "MPP-R100", title: "جرثقیل 10 تن", baseUnit: "hour",
    dimension: "time", externalResourceId: null, sourceResourceUid: 100,
    createdBy: "u", createdAt: "2026-01-01" },
];

function line(id, resourceId, assignmentUid, mppCostIrr) {
  return {
    id, activityExternalId: "1.9.2", assignmentExternalId: String(assignmentUid),
    sourceAssignmentUid: assignmentUid, sourceTaskUid: 1227,
    resourceId, originalQuantity: null, revisedQuantity: null,
    originalUnitPriceIrr: null, mppCostIrr, source: "progress_feed",
    revision: 1, revisions: [], createdBy: "u", createdAt: "2026-01-01",
  };
}

const lines = [
  line("l-rebar", "r-rebar", 9455, "65445773715"),
  line("l-concrete", "r-concrete", 9814, "32000000"),
  line("l-crane", "r-crane", 9829, "0"),
];

function stub() {
  return {
    async request(path) {
      if (path.includes("/activities")) {
        return { items: activities, page: 1, pageSize: 200, totalItems: 1, totalPages: 1 };
      }
      if (path.includes("/estimate-lines")) return lines;
      if (path.includes("/unit-registry")) return { items: [] };
      if (path.includes("/prices/current")) return [];
      if (path.includes("/resources")) return resources;
      throw new Error(`unexpected path ${path}`);
    },
  };
}

test("each item carries its own assignment cost, and no other item's", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub()).getWorkspace();
  const byId = new Map(workspace.estimateLines.map((item) => [item.lineId, item]));
  assert.equal(assignmentCostOf(byId.get("l-rebar")), "65445773715");
  assert.equal(assignmentCostOf(byId.get("l-concrete")), "32000000");
  // The expensive item's figure did not leak onto the cheap one, or the reverse.
  assert.notEqual(assignmentCostOf(byId.get("l-rebar")), assignmentCostOf(byId.get("l-concrete")));
});

test("the activity's own figure stays the activity's on every one of its items", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub()).getWorkspace();
  for (const item of workspace.estimateLines) {
    assert.equal(scheduleCostOf(item), "65477773715");
    assert.notEqual(assignmentCostOf(item), scheduleCostOf(item),
      "an item is not its activity: the two figures are read from different fields");
  }
});

test("a schedule zero is a zero and not an absence", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub()).getWorkspace();
  const crane = workspace.estimateLines.find((item) => item.lineId === "l-crane");
  assert.equal(assignmentCostOf(crane), "0");
});

test("a line the schedule states no cost for reports none, not zero", () => {
  assert.equal(assignmentCostOf({ mppAssignmentCostIrr: null }), null);
  assert.equal(assignmentCostOf({ mppAssignmentCostIrr: undefined }), null);
  assert.equal(assignmentCostOf({ mppAssignmentCostIrr: "" }), null);
  assert.equal(assignmentCostOf({}), null);
  assert.equal(assignmentCostOf(null), null);
});

test("a line that came from no schedule at all carries neither figure", async () => {
  const manual = {
    id: "l-manual", activityExternalId: null, assignmentExternalId: null,
    sourceAssignmentUid: null, sourceTaskUid: null, resourceId: "r-rebar",
    originalQuantity: "5", revisedQuantity: "5", originalUnitPriceIrr: "1000",
    mppCostIrr: null, source: "manual", revision: 1, revisions: [],
    createdBy: "u", createdAt: "2026-01-01",
  };
  const adapter = createApiFinancialItemsAdapter(context, {
    async request(path) {
      if (path.includes("/activities")) {
        return { items: [], page: 1, pageSize: 200, totalItems: 0, totalPages: 0 };
      }
      if (path.includes("/estimate-lines")) return [manual];
      if (path.includes("/unit-registry")) return { items: [] };
      if (path.includes("/prices/current")) return [];
      if (path.includes("/resources")) return resources;
      throw new Error(`unexpected path ${path}`);
    },
  });
  const [only] = (await adapter.getWorkspace()).estimateLines;
  assert.equal(assignmentCostOf(only), null);
  assert.equal(scheduleCostOf(only), null);
});
