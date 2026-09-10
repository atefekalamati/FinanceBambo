import test from "node:test";
import assert from "node:assert/strict";
import { projectFacts } from "../../src/shared/reports/report-header.js";

/**
 * One document, two dates, one word.
 *
 * A built report can put two chapters side by side: a cumulative one, whose figures are as
 * of the progress snapshot they were computed from, and a period one, whose figures are as
 * of the period's close. Those are genuinely different dates -- the snapshot's is the
 * schedule's own Status Date and on the current data sits a year earlier -- and both
 * letterheads used to call it «تاریخ گزارش».
 *
 * A reader who asked for 1405-01-01 تا 1405-06-19 and read «تاریخ گزارش: ۱۰ مهر ۱۴۰۴» on
 * page one could only conclude the range had been ignored. It had not: the request behind
 * that chapter really does carry reportingDate=2025-10-02, and the one behind the next
 * chapter really does carry 2026-09-10. The document was right and the label was not.
 */

const PROJECT = { name: "پروژه نمونه", code: "BMB-1405-01" };

function labelled(facts, value) {
  const found = facts.find(([, printed]) => printed === value);
  return found ? found[0] : null;
}

test("a date taken from a progress version is named as one", () => {
  const facts = projectFacts({
    project: PROJECT, snapshot: "test_progress.mpp", reportingDate: "2025-10-02",
  });
  const printed = facts.find(([label]) => label.includes("نسخه پیشرفت") && label.includes("تاریخ"));
  assert.ok(printed, "the snapshot's date is not labelled as coming from the version");
  assert.notEqual(printed[0], "تاریخ گزارش", "it still wears the ambiguous word");
  // The version it belongs to is named right beside it, so the pair reads together.
  assert.ok(facts.some(([label, value]) => label === "نسخه پیشرفت" && value === "test_progress.mpp"));
});

test("a date that is the report's own keeps the plain word", () => {
  const facts = projectFacts({ project: PROJECT, reportingDate: "2026-09-10" });
  const label = labelled(facts, facts.find(([l]) => l.includes("تاریخ"))[1]);
  assert.equal(label, "تاریخ گزارش");
  assert.ok(!facts.some(([l]) => l === "نسخه پیشرفت" && l !== null && facts.find(([k, v]) => k === "نسخه پیشرفت" && v)),
    "no version line is printed when there is no version");
});

test("the two chapters of one document no longer share a label", () => {
  // Exactly the shape the report builder produces for `sections=overview,periodMetrics`.
  const cumulative = projectFacts({
    project: PROJECT, snapshot: "test_progress.mpp", reportingDate: "2025-10-02",
  });
  const period = projectFacts({
    project: PROJECT, reportingDate: "2026-09-10",
    period: { from: "2026-03-21", to: "2026-09-10" },
  });
  const dateLabel = (facts) => facts.find(([label]) => label.includes("تاریخ"))[0];
  assert.notEqual(dateLabel(cumulative), dateLabel(period),
    "both chapters name their date the same way again");
  // And the period chapter still states its interval, which is the other half of the answer.
  assert.ok(period.some(([label, value]) => label === "بازه" && value && value.includes("تا")));
});

test("a missing date is dropped rather than printed empty", () => {
  const facts = projectFacts({ project: PROJECT, snapshot: "x.mpp" });
  const dated = facts.find(([label]) => label.includes("تاریخ"));
  assert.equal(dated[1], null, "an absent date must stay null for the renderer to drop it");
});
