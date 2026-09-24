import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { createScheduleSyncSection, provenanceLine, remapSummary, scheduleSummary } =
  await import("../../src/features/settings/schedule-sync-section.js");

/* The one control that turns an imported schedule into estimate lines.
 *
 * Reading the file and turning it into money are two steps, and only the first ran on its
 * own. A schedule could sit fully imported and produce nothing — which is what happened
 * here: the file stated 5,148,488,006 toman of task-level fixed costs and the project
 * total was short by precisely that.
 */

const STATUS = {
  sourceVersionId: "b889bc98-98e3-4654-8c49-e1141790e58a",
  sourceFileName: "test_progress.mpp",
  importedAt: "2026-09-14T15:15:51+03:30",
  reportingDate: "2025-10-02",
  rowCount: 789,
  total: 789, assignmentMapped: 715, activityOnly: 74, unclassified: 0,
  stageLabelRows: 62, assignmentsWithoutResource: 12,
};

const RESULT = {
  resourcesCreated: 1, resourcesMatched: 68,
  linesCreated: 0, linesMatched: 715,
  fixedCostLinesCreated: 4, fixedCostLinesMatched: 0,
  fixedCostIrr: "51484880064",
  fixedCostResidueRows: 21, fixedCostResidueFileUnits: "5.9099993896484375",
  unmappedRows: 0,
};

const adapterFor = (over = {}) => ({
  getMppStatus: async () => STATUS,
  remapMpp: async () => RESULT,
  ...over,
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/* ─────────────────────────── the counts, on their own ─────────────────────────── */

test("the counts read as what the file has, then what became of it", () => {
  assert.deepEqual(scheduleSummary(STATUS).map((item) => [item.key, item.value]),
                   [["total", "۷۸۹"], ["assignmentMapped", "۷۱۵"],
                    ["activityOnly", "۷۴"], ["unclassified", "۰"]]);
});

test("a count of zero is still stated, because it is an answer", () => {
  /* «۰ منبع طبقه‌بندی‌نشده» tells a reader there is nothing waiting for them. A blank
     tells them the panel could not find out. */
  const zero = scheduleSummary({ ...STATUS, unclassified: 0 })
    .find((item) => item.key === "unclassified");
  assert.equal(zero.value, "۰");
});

test("an absent status counts nothing rather than throwing", () => {
  assert.deepEqual(scheduleSummary(null), []);
  assert.deepEqual(scheduleSummary(undefined), []);
});

/* ─────────────────────────── where the numbers came from ─────────────────────────── */

test("the file is named beside its own numbers", () => {
  const line = provenanceLine(STATUS);
  assert.match(line, /test_progress\.mpp/);
  assert.match(line, /شهریور ۱۴۰۵/, "the date it was imported");
});

test("the import date and the file's own reporting date are told apart", () => {
  /* Two different facts. A panel that showed one as the other would date the project's
     progress by when somebody uploaded a file. */
  const line = provenanceLine(STATUS);
  assert.match(line, /تاریخ گزارش فایل/);
  assert.doesNotMatch(provenanceLine({ ...STATUS, reportingDate: null }), /تاریخ گزارش فایل/);
});

test("a project that imported nothing says so instead of naming a file", () => {
  assert.match(provenanceLine({ sourceVersionId: null }), /هنوز هیچ برنامهٔ زمان‌بندی/);
  assert.match(provenanceLine(null), /هنوز هیچ برنامهٔ زمان‌بندی/);
});

/* ─────────────────────────── what a run did ─────────────────────────── */

test("a run that created things names each kind", () => {
  const text = remapSummary(RESULT);
  assert.match(text, /۱ منبع/);
  assert.match(text, /۴ ردیف هزینه عمومی/);
  assert.match(text, /۷۱۵ ردیف از قبل موجود بود/);
  assert.match(text, /۲۱ ته‌مانده/, "and says the rounding residue was not dropped");
});

test("a second press is answered, not met with silence", () => {
  /* The normal result of pressing twice. A panel that said nothing would read as a
     button that did nothing. */
  const again = remapSummary({ ...RESULT, resourcesCreated: 0, linesCreated: 0,
                               fixedCostLinesCreated: 0, fixedCostLinesMatched: 4 });
  assert.match(again, /چیزی برای ساختن نبود/);
  assert.match(again, /۷۱۹ ردیف از قبل موجود بود/, "715 lines and 4 fixed-cost lines");
});

test("a run with no residue does not invent a sentence about one", () => {
  assert.doesNotMatch(remapSummary({ ...RESULT, fixedCostResidueRows: 0 }), /ته‌مانده/);
});

test("no answer from the service is not reported as a successful run", () => {
  assert.match(remapSummary(null), /پاسخی از سرویس دریافت نشد/);
});

/* ─────────────────────────── the panel ─────────────────────────── */

test("the panel names the file and draws its counts once the status arrives", async () => {
  const section = createScheduleSyncSection({ adapter: adapterFor(), canEdit: true });
  await settle();
  assert.match(section.textContent, /test_progress\.mpp/);
  assert.equal(section.querySelectorAll(".schedule-sync__count").length, 4);
  assert.match(section.textContent, /۷۱۵/);
});

test("without the edit permission the panel reads and offers no button", async () => {
  /* The service serves the status to anyone who may view finance and asks for the edit
     permission only on the run. Hiding the whole section would tell a reader the feature
     does not exist; naming the permission tells them whose to ask for. */
  const section = createScheduleSyncSection({ adapter: adapterFor(), canEdit: false });
  await settle();
  assert.match(section.textContent, /test_progress\.mpp/, "reading still happens");
  assert.equal(section.querySelectorAll("button").length, 0);
  assert.match(section.textContent, /دسترسی ویرایش امور مالی لازم است/);
});

test("pressing it runs the mapping, says what happened, and re-reads the counts", async () => {
  let statusReads = 0;
  let runs = 0;
  const section = createScheduleSyncSection({
    adapter: { getMppStatus: async () => { statusReads += 1; return STATUS; },
               remapMpp: async () => { runs += 1; return RESULT; } },
    canEdit: true,
  });
  await settle();
  assert.equal(statusReads, 1, "read once on open");
  section.querySelector("button").click();
  await settle();
  await settle();
  assert.equal(runs, 1);
  assert.equal(statusReads, 2, "and read again afterwards, never derived from the result");
  assert.match(section.querySelector(".schedule-sync__feedback").textContent,
               /۴ ردیف هزینه عمومی/);
});

test("a failed run says why and leaves the panel standing", async () => {
  const section = createScheduleSyncSection({
    adapter: adapterFor({ remapMpp: async () => { throw new Error("boom"); } }),
    canEdit: true,
  });
  await settle();
  section.querySelector("button").click();
  await settle();
  await settle();
  const feedback = section.querySelector(".schedule-sync__feedback");
  assert.ok(feedback.className.includes("--failed"));
  assert.ok(feedback.textContent.length > 0, "a reason, not a blank");
  assert.ok(section.querySelector("button"), "and the button is still there to retry");
});

test("a project with no schedule cannot run the mapping", async () => {
  const empty = { sourceVersionId: null, total: 0, assignmentMapped: 0,
                  activityOnly: 0, unclassified: 0 };
  const section = createScheduleSyncSection({
    adapter: adapterFor({ getMppStatus: async () => empty }), canEdit: true });
  await settle();
  assert.equal(section.querySelector("button").disabled, true);
  assert.match(section.textContent, /چیزی برای بازخوانی نیست/);
});

test("a status that cannot be read leaves the section saying so, not gone", async () => {
  /* A panel that vanishes when a request fails teaches a reader that the feature is not
     there. */
  const section = createScheduleSyncSection({
    adapter: adapterFor({ getMppStatus: async () => { throw new Error("nope"); } }),
    canEdit: true });
  await settle();
  assert.ok(section.querySelector(".schedule-sync__feedback").textContent.length > 0);
  assert.ok(section.textContent.includes("همگام‌سازی با برنامهٔ زمان‌بندی"));
});

test("the result survives whatever the page does next", async () => {
  /* The regression this pins. The page used to reload after a run, which rebuilt this
     section and threw away the sentence it had just been given: the reader pressed a
     button, the service did the work, and the panel came back blank. Measured in the
     browser before it was fixed. */
  let repaints = 0;
  const section = createScheduleSyncSection({
    adapter: adapterFor(), canEdit: true,
    onRemapped: () => { repaints += 1; },
  });
  await settle();
  section.querySelector("button").click();
  await settle();
  await settle();
  assert.equal(repaints, 1, "the page is still told a run happened");
  assert.match(section.querySelector(".schedule-sync__feedback").textContent,
               /۴ ردیف هزینه عمومی/, "and the sentence is still on screen");
});

test("a run that created a resource says the lists elsewhere moved", async () => {
  /* This section cannot repaint the equipment list beside it, so it says so instead of
     repainting the page under a reader mid-sentence. */
  const section = createScheduleSyncSection({ adapter: adapterFor(), canEdit: true });
  await settle();
  section.querySelector("button").click();
  await settle();
  await settle();
  assert.match(section.querySelector(".schedule-sync__feedback").textContent,
               /فهرست منابع تغییر کرده/);
});

test("a run that created no resource adds no such sentence", async () => {
  const section = createScheduleSyncSection({
    adapter: adapterFor({ remapMpp: async () => ({ ...RESULT, resourcesCreated: 0 }) }),
    canEdit: true });
  await settle();
  section.querySelector("button").click();
  await settle();
  await settle();
  assert.doesNotMatch(section.querySelector(".schedule-sync__feedback").textContent,
                      /فهرست منابع تغییر کرده/);
});
