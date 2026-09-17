import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  GENERAL_COST_STAGE,
  UNSTAGED,
  buildStageIndex,
  stageCodeOf,
  stageOf,
  targetsInStage,
} from "../../src/features/invoices/invoice-stages.js";

function estimateTarget(id, wbsCode, stageTitle = null) {
  return { targetId: id, targetType: "estimate_line", label: id, wbsCode, stageTitle };
}

const GENERAL = { targetId: "general-permit", targetType: "general_cost", label: "مجوز", wbsCode: null };

test("a stage is the first segment of the activity's code, not the whole path", () => {
  assert.equal(stageCodeOf("3.2.1"), "3");
  assert.equal(stageCodeOf("3"), "3");
  assert.equal(stageCodeOf(" 12.4 "), "12");
  assert.equal(stageCodeOf(""), null);
  assert.equal(stageCodeOf(null), null);
});

test("the stages read in structural order, not string order", () => {
  /* "1.10" sorts before "1.2" as text, which would put the tenth stage second. The chart
     orders them structurally and this picker has to agree with it, or the same project
     reads in two different orders on two screens. */
  const stages = buildStageIndex([
    estimateTarget("a", "10.1"),
    estimateTarget("b", "2.1"),
    estimateTarget("c", "1.4"),
  ]);
  assert.deepEqual(stages.map((stage) => stage.value), ["1", "2", "10"]);
});

test("the two groups that are not stages come last, and in that order", () => {
  const stages = buildStageIndex([GENERAL, estimateTarget("a", null), estimateTarget("b", "4.1")]);
  assert.deepEqual(stages.map((stage) => stage.value), ["4", UNSTAGED, GENERAL_COST_STAGE]);
});

test("only stages that have something to bill against are offered", () => {
  /* A stage with no estimate line is a choice that leads to an empty list. The picker is
     built from the targets themselves, so such a stage cannot appear. */
  const stages = buildStageIndex([estimateTarget("a", "7.1")]);
  assert.deepEqual(stages.map((stage) => stage.value), ["7"]);
});

test("each stage carries its name and how many rows it holds", () => {
  const stages = buildStageIndex([
    estimateTarget("a", "3.1", "سفت‌کاری"),
    estimateTarget("b", "3.2", "سفت‌کاری"),
    estimateTarget("c", "4.1"),
  ]);
  assert.deepEqual(stages[0], { value: "3", title: "سفت‌کاری", count: 2, kind: "stage" });
  assert.equal(stages[1].title, null, "a stage the catalogue did not name still appears");
  assert.equal(stages[1].count, 1);
});

test("every target lands in exactly one group", () => {
  const targets = [estimateTarget("a", "3.1"), estimateTarget("b", "3.9"), estimateTarget("c", null), GENERAL];
  const counted = buildStageIndex(targets).reduce((sum, stage) => sum + stage.count, 0);
  assert.equal(counted, targets.length);
  assert.equal(stageOf(GENERAL), GENERAL_COST_STAGE);
  assert.equal(stageOf(estimateTarget("c", null)), UNSTAGED);
});

test("choosing a stage narrows the list to that stage alone", () => {
  const targets = [estimateTarget("a", "3.1"), estimateTarget("b", "4.1"), GENERAL];
  assert.deepEqual(targetsInStage(targets, "3").map((target) => target.targetId), ["a"]);
  assert.deepEqual(targetsInStage(targets, GENERAL_COST_STAGE).map((target) => target.targetId),
                   ["general-permit"]);
  assert.deepEqual(targetsInStage(targets, ""), [], "nothing chosen offers nothing");
});

test("the stage never becomes part of what is saved", () => {
  /* The guard on the whole design: this module reads targets and returns groups. If it
     ever gained a writer, the same fact would be stored twice -- on the invoice line and
     on the estimate line's activity -- and the day a re-imported schedule moved an
     activity, the report would have two answers and no rule for choosing. */
  const source = new URL("../../src/features/invoices/invoice-stages.js", import.meta.url);
  const text = readFileSync(source, "utf8");
  assert.ok(!/\bfetch\b|client\.request|createDraft|POST/.test(text),
            "invoice-stages.js must stay a pure filter over targets already in hand");
});
