import test from "node:test";
import assert from "node:assert/strict";
import {
  ABSENT, activityLabel, canonicalWbs, isLegacyTaskResource, resourceLabel,
  selectEstimateRows, selectVisibleResources, withheldRowsNotice,
} from "../../src/features/financial-items/financial-items-presentation.js";
import { buildEstimateLinesCsv } from "../../src/features/financial-items/financial-items-csv.js";

/**
 * An activity is not a cost item.
 *
 * The page showed a task name in the قلم هزینه column and a WBS code twice in
 * the فعالیت column. Both came from a value standing in for a different value,
 * so these tests are all one assertion in different clothes: a field is printed
 * from its own source or not at all.
 */

const scheduleResource = {
  resourceId: "r-mpp", code: "MPP-R157", title: "آبپاش", type: "equipment",
  baseUnit: "hour", externalResourceId: null, sourceResourceUid: 157,
};
const legacyResource = {
  resourceId: "r-legacy", code: "MSP-T253", title: "برآورد مصالح مورد نیاز", type: "material",
  baseUnit: "kg", externalResourceId: "253", sourceResourceUid: null,
};
const manualResource = {
  resourceId: "r-manual", code: "MAT-REBAR", title: "میلگرد آجدار", type: "material",
  baseUnit: "kg", externalResourceId: null, sourceResourceUid: null,
};
const line = (resourceId, extra = {}) => ({
  lineId: `line-${resourceId}`, resourceId, activityExternalId: "1.8.2.3",
  activityTitle: "اجرای فونداسیون", wbsCode: "1.8.2.3",
  originalQuantity: "10", revisedQuantity: "10", source: "progress_feed", ...extra,
});

test("prints one WBS value where the row previously printed the same code twice", () => {
  assert.equal(canonicalWbs({ wbsCode: "1.8.2.3", activityExternalId: "1.8.2.3" }), "1.8.2.3");
});

test("prints one WBS value where the row previously printed a placeholder beside a code", () => {
  const rendered = canonicalWbs({ wbsCode: null, activityExternalId: "1.8.2.3" });
  assert.equal(rendered, "1.8.2.3");
  assert.ok(!rendered.includes(ABSENT), "a code is a code; nothing is joined to it");
});

test("prefers the catalogue WBS code over the activity identity when they differ", () => {
  assert.equal(canonicalWbs({ wbsCode: "2.1", activityExternalId: "1.8.2.3" }), "2.1");
});

test("reads the activity identity as a WBS code only when it is shaped like one", () => {
  assert.equal(canonicalWbs({ wbsCode: null, activityExternalId: "ACT-102" }), ABSENT);
  assert.equal(canonicalWbs({ wbsCode: null, activityExternalId: "MSP-T253" }), ABSENT);
});

test("states the absence when the line carries no WBS code at all", () => {
  assert.equal(canonicalWbs({}), ABSENT);
  assert.equal(canonicalWbs(null), ABSENT);
});

test("never names a cost item from the activity it belongs to", () => {
  // The mission's rule, as a rule: resourceLabel reads the resource and nothing
  // else, so a missing cost item can only ever render as missing.
  assert.equal(resourceLabel(undefined), ABSENT);
  assert.equal(resourceLabel({ title: "" }), ABSENT);
  assert.equal(resourceLabel(scheduleResource), "آبپاش");
  assert.equal(activityLabel({ activityTitle: null, activityExternalId: "1.8.2.3" }), "فعالیت بدون عنوان");
});

test("never names an activity from its identity or its WBS code", () => {
  const label = activityLabel({ activityTitle: null, activityExternalId: "1.8.2.3", wbsCode: "1.8.2.3" });
  assert.ok(!label.includes("1.8.2.3"), "a code printed as a title is the reported bug");
});

test("recognises a legacy task-derived resource by its source, not by its title", () => {
  assert.equal(isLegacyTaskResource(legacyResource), true);
  assert.equal(isLegacyTaskResource(scheduleResource), false);
  assert.equal(isLegacyTaskResource(manualResource), false);
  // A resource read from the current file stays visible whatever it is coded.
  assert.equal(isLegacyTaskResource({ code: "MSP-T99", sourceResourceUid: 99 }), false);
});

test("withholds legacy task rows from the estimate table", () => {
  const lines = [line("r-mpp"), line("r-legacy"), line("r-manual")];
  const selected = selectEstimateRows(lines, [scheduleResource, legacyResource, manualResource]);
  assert.deepEqual(selected.rows.map((row) => row.resourceId), ["r-mpp", "r-manual"]);
  assert.equal(selected.hiddenLegacyCount, 1);
});

test("withholds a line whose cost item is not in the catalogue instead of labelling it", () => {
  const selected = selectEstimateRows([line("r-mpp"), line("r-gone")], [scheduleResource]);
  assert.deepEqual(selected.rows.map((row) => row.resourceId), ["r-mpp"]);
  assert.equal(selected.orphanCount, 1);
});

test("keeps hand-entered cost items visible", () => {
  const visible = selectVisibleResources([scheduleResource, legacyResource, manualResource]);
  assert.deepEqual(visible.rows.map((row) => row.code), ["MPP-R157", "MAT-REBAR"]);
  assert.equal(visible.hiddenLegacyCount, 1);
});

test("withholds legacy rows without removing them from the data it was given", () => {
  const resources = [scheduleResource, legacyResource, manualResource];
  const lines = [line("r-mpp"), line("r-legacy")];
  selectVisibleResources(resources);
  selectEstimateRows(lines, resources);
  assert.equal(resources.length, 3, "hiding is not deleting");
  assert.equal(lines.length, 2);
  assert.ok(resources.includes(legacyResource));
});

test("tells the reader what the table is not showing", () => {
  assert.equal(withheldRowsNotice({ hiddenLegacyCount: 0, orphanCount: 0 }), null);
  const notice = withheldRowsNotice({ hiddenLegacyCount: 120, orphanCount: 3 });
  assert.match(notice, /MSP-T/);
  assert.match(notice, /حذف هم نشده/, "a reader must not think the rows were deleted");
  assert.match(notice, /بدون قلم هزینه معتبر/);
});

test("exports the one WBS value the table shows", () => {
  const csv = buildEstimateLinesCsv({
    lines: [line("r-mpp", { wbsCode: null }), line("r-manual", { activityTitle: null })],
    resources: [scheduleResource, manualResource],
  });
  assert.ok(!csv.includes("null"), "a missing value is not the word null");
  assert.ok(csv.includes("1.8.2.3"), "the WBS code still reaches the spreadsheet");
});
