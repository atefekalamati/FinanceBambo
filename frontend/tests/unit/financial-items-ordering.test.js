import test from "node:test";
import assert from "node:assert/strict";
import {
  ABSENT, activityBlockStarts, compareWbs, sortEstimateRows,
} from "../../src/features/financial-items/financial-items-presentation.js";

/**
 * A project reads `1.9.2` before `1.9.10`, and expects the five items it priced
 * for one activity to be in one place. Alphabetic order gives neither.
 */

const resources = [
  { resourceId: "r-1", title: "خاکبرداری", code: "MPP-R1", sourceResourceUid: 1 },
  { resourceId: "r-2", title: "زیر اساس", code: "MPP-R2", sourceResourceUid: 2 },
  { resourceId: "r-3", title: "آسفالت توپکا", code: "MPP-R3", sourceResourceUid: 3 },
];
const row = (wbs, resourceId, assignment) => ({
  lineId: `${wbs}-${resourceId}`, resourceId, wbsCode: wbs, activityExternalId: wbs,
  taskExternalId: "10", sourceAssignmentUid: assignment,
});

test("orders WBS by its numbers, not by its characters", () => {
  const codes = ["1.9.10", "1.9.2", "1.10", "1.2", "1.9"];
  assert.deepEqual([...codes].sort(compareWbs), ["1.2", "1.9", "1.9.2", "1.9.10", "1.10"]);
});

test("puts a code before the longer code it is a prefix of", () => {
  assert.ok(compareWbs("1.8", "1.8.1") < 0);
  assert.ok(compareWbs("1.8.1", "1.8") > 0);
});

test("sorts rows with no WBS code to the end rather than the top", () => {
  assert.ok(compareWbs(ABSENT, "1.1") > 0);
  assert.ok(compareWbs("1.1", ABSENT) < 0);
  assert.equal(compareWbs(ABSENT, ABSENT), 0);
});

test("keeps a lettered numbering scheme in one stable order", () => {
  const codes = ["A.2", "1.2", "A.1"];
  assert.deepEqual([...codes].sort(compareWbs), ["1.2", "A.1", "A.2"]);
});

test("keeps every item of one activity consecutive", () => {
  const scattered = [
    row("1.6", "r-3", 30), row("1.2", "r-1", 10), row("1.6", "r-1", 31),
    row("1.10", "r-2", 40), row("1.6", "r-2", 32), row("1.2", "r-2", 11),
  ];
  const ordered = sortEstimateRows(scattered, resources);
  const codes = ordered.map((line) => line.wbsCode);
  assert.deepEqual(codes, ["1.2", "1.2", "1.6", "1.6", "1.6", "1.10"]);
  // One run per activity is the definition of "not scattered".
  const runs = codes.filter((code, index) => code !== codes[index - 1]).length;
  assert.equal(runs, new Set(codes).size);
});

test("orders the items inside one activity by the schedule, not by their titles", () => {
  const ordered = sortEstimateRows(
    [row("1.6", "r-3", 32), row("1.6", "r-1", 30), row("1.6", "r-2", 31)], resources);
  assert.deepEqual(ordered.map((line) => line.sourceAssignmentUid), [30, 31, 32]);
});

test("marks the first row of each activity block and no other", () => {
  const ordered = sortEstimateRows(
    [row("1.2", "r-1", 10), row("1.6", "r-1", 30), row("1.6", "r-2", 31)], resources);
  assert.deepEqual(activityBlockStarts(ordered), [true, true, false]);
});

test("sorting does not add, drop or duplicate a row", () => {
  const given = [row("1.6", "r-3", 30), row("1.2", "r-1", 10), row("1.6", "r-1", 31)];
  const ordered = sortEstimateRows(given, resources);
  assert.equal(ordered.length, given.length);
  assert.deepEqual(new Set(ordered.map((line) => line.lineId)), new Set(given.map((line) => line.lineId)));
  assert.equal(given[0].wbsCode, "1.6", "the caller's array is left alone");
});
