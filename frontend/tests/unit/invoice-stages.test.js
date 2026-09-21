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

test("a stage is what the level-one chart draws, not the whole path", () => {
  /* Measured on the audited project: the chart's stages are «۱.۱» … «۱.۱۸» and an
     activity's code is the full path beneath one of them, four to six segments deep.
     Reading only the FIRST segment made every one of 835 lines «۱» -- one group, which is
     the flat list this module exists to break up, wearing a stage's name. */
  assert.equal(stageCodeOf("1.11.1.2"), "1.11");
  assert.equal(stageCodeOf("1.5.3.7.2"), "1.5");
  assert.equal(stageCodeOf("1.5"), "1.5");
  /* Shallower than a stage IS its own stage. «۱.۳» carries one real estimate line, and a
     rule about depth must not drop a row that exists. */
  assert.equal(stageCodeOf("1"), "1");
  assert.equal(stageCodeOf(" 1.6 "), "1.6");
  assert.equal(stageCodeOf(""), null);
  assert.equal(stageCodeOf(null), null);
});

test("the stages read in structural order, not string order", () => {
  /* "1.10" sorts before "1.2" as text, which would put the tenth stage second. The chart
     orders them structurally and this picker has to agree with it, or the same project
     reads in two different orders on two screens. */
  const stages = buildStageIndex([
    estimateTarget("a", "1.10.2"),
    estimateTarget("b", "1.2.1"),
    estimateTarget("c", "1.9.4"),
  ]);
  assert.deepEqual(stages.map((stage) => stage.value), ["1.2", "1.9", "1.10"],
                   "«۱.۱۰» after «۱.۹», which string order would reverse");
});

test("the two groups that are not stages come last, and in that order", () => {
  const stages = buildStageIndex([GENERAL, estimateTarget("a", null), estimateTarget("b", "1.4.1")]);
  assert.deepEqual(stages.map((stage) => stage.value), ["1.4", UNSTAGED, GENERAL_COST_STAGE]);
});

test("only stages that have something to bill against are offered", () => {
  /* A stage with no estimate line is a choice that leads to an empty list. The picker is
     built from the targets themselves, so such a stage cannot appear. */
  const stages = buildStageIndex([estimateTarget("a", "1.7.1")]);
  assert.deepEqual(stages.map((stage) => stage.value), ["1.7"]);
});

test("each stage carries its name and how many rows it holds", () => {
  const stages = buildStageIndex([
    estimateTarget("a", "1.5.1", "اجرای عملیات سیویل"),
    estimateTarget("b", "1.5.2", "اجرای عملیات سیویل"),
    estimateTarget("c", "1.6.1"),
  ]);
  assert.deepEqual(stages[0], { value: "1.5", title: "اجرای عملیات سیویل", count: 2, kind: "stage" });
  assert.equal(stages[1].title, null, "a stage the catalogue did not name still appears");
  assert.equal(stages[1].count, 1);
});

test("every target lands in exactly one group", () => {
  const targets = [estimateTarget("a", "1.5.1"), estimateTarget("b", "1.5.9"), estimateTarget("c", null), GENERAL];
  const counted = buildStageIndex(targets).reduce((sum, stage) => sum + stage.count, 0);
  assert.equal(counted, targets.length);
  assert.equal(stageOf(GENERAL), GENERAL_COST_STAGE);
  assert.equal(stageOf(estimateTarget("c", null)), UNSTAGED);
});

test("choosing a stage narrows the list to that stage alone", () => {
  const targets = [estimateTarget("a", "1.5.1"), estimateTarget("b", "1.6.1"), GENERAL];
  assert.deepEqual(targetsInStage(targets, "1.5").map((target) => target.targetId), ["a"]);
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

test("a stage code reads as a code, so «۱.۱۰» is not «۱.۱»", async () => {
  /* `formatDisplayNumber` reads «1.10» as one and a tenth: it strips the trailing zero and
     writes the decimal separator. Stage «۱.۱ شروع» and stage «۱.۱۰ اجرای خط کشی» both came
     out «۱٫۱» -- two different stages of the project wearing one label, in the menu where
     somebody chooses which one an invoice is for. Caught by driving the real picker against
     the real project, not by reading the code. */
  const { toPersianCode } = await import("../../src/shared/formatters/display.js");
  const { formatDisplayNumber } = await import("../../src/shared/formatters/display.js");
  assert.equal(toPersianCode("1.10"), "۱.۱۰");
  assert.equal(toPersianCode("1.1"), "۱.۱");
  assert.notEqual(toPersianCode("1.10"), toPersianCode("1.1"));
  assert.equal(formatDisplayNumber("1.10"), formatDisplayNumber("1.1"),
               "which is exactly why the code may not go through the number formatter");
});
