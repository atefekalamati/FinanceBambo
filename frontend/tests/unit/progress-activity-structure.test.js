import test from "node:test";
import assert from "node:assert/strict";
import { activityStructureLabel } from "../../src/features/progress/progress-page.js";

/**
 * The structure line under an activity's name on #/progress.
 *
 * `wbsCode` and `activityCode` are two different task fields — the breakdown code and the
 * outline number — and on the current file they hold the same string. Printing both read
 * as "1.11.1.12 · 1.11.1.12", which says one thing twice. They are joined only when they
 * genuinely differ, because that is the only case where the second adds anything.
 *
 * Nothing here is about identity: the task, parent, resource and assignment identifiers
 * still travel on every row and still key the override request. They are simply not
 * printed at the reader any more.
 */

test("one code is shown once, not twice", () => {
  assert.equal(activityStructureLabel({ wbsCode: "1.11.1.12", activityCode: "1.11.1.12" }),
    "1.11.1.12");
});

test("two different codes are both shown, because they are two facts", () => {
  assert.equal(activityStructureLabel({ wbsCode: "1.5.2", activityCode: "A-1420" }),
    "1.5.2 · A-1420");
});

test("whichever one the task states is the one shown", () => {
  assert.equal(activityStructureLabel({ wbsCode: "1.4", activityCode: null }), "1.4");
  assert.equal(activityStructureLabel({ wbsCode: null, activityCode: "1.4" }), "1.4");
});

test("a task that states neither says so, and invents no code", () => {
  assert.equal(activityStructureLabel({ wbsCode: null, activityCode: null }),
    "ساختار شکست موجود نیست");
  assert.equal(activityStructureLabel({}), "ساختار شکست موجود نیست");
});

test("an empty string is not a code either", () => {
  // `??` would have let "" through as a value; the row would then show a blank line
  // where a code belongs, which reads as "there is one and it is nothing".
  assert.equal(activityStructureLabel({ wbsCode: "", activityCode: "" }),
    "ساختار شکست موجود نیست");
});
