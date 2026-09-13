import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  PROGRESS_STATUS,
  describeFeedWarning,
  describeReportWarning,
  feedWarningText,
  FEED_WARNING_CODES,
  REPORT_WARNING_CODES,
  reportWarningText,
} from "../../src/shared/warnings/finance-warning-labels.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

test("every warning code the Backend can emit has Persian wording", () => {
  // The finance domain emits these nine on the report; the feed adds its own.
  assert.deepEqual([...REPORT_WARNING_CODES].sort(), [
    "CURRENT_PRICE_MISSING",
    "GENERAL_COST_OVERRUN",
    "GROSS_AREA_MISSING",
    "MONTHLY_ESTIMATE_UNAVAILABLE",
    "PROGRESS_MISSING",
    "PROGRESS_UNMAPPED",
    "PROGRESS_WORK_NOT_QUANTITY",
    "QUANTITY_OVERRUN",
    "UNIT_CONVERSION_MISSING",
  ]);
  assert.deepEqual([...FEED_WARNING_CODES].sort(), ["PROGRESS_MISSING", "PROGRESS_WORK_NOT_QUANTITY", "TASK_PROGRESS_FALLBACK"]);
  [...REPORT_WARNING_CODES, ...FEED_WARNING_CODES].forEach((code) => {
    const text = describeReportWarning(code) ?? describeFeedWarning(code);
    assert.match(text, /[؀-ۿ]/, `${code} has no Persian wording`);
    assert.doesNotMatch(text, /[A-Z_]{6,}/, `${code} leaks a machine string into its wording`);
  });
});

test("the three progress situations each get their own sentence", () => {
  // They used to arrive as one PROGRESS_MISSING and the wording had to hedge.
  // The Backend now separates them, and each is fixed by a different person: a
  // broken reference on the line, a missing activity, or a silent assignment.
  const brokenReference = describeReportWarning("PROGRESS_UNMAPPED", PROGRESS_STATUS.UNMAPPED_ASSIGNMENT);
  const missingActivity = describeReportWarning("PROGRESS_UNMAPPED", PROGRESS_STATUS.UNMAPPED_ACTIVITY);
  const silentAssignment = describeReportWarning("PROGRESS_MISSING");

  assert.equal(new Set([brokenReference, missingActivity, silentAssignment]).size, 3, "three situations, three sentences");
  assert.match(brokenReference, /تخصیصی را نام می‌برد/);
  assert.match(missingActivity, /فعالیتش/);
  assert.match(silentAssignment, /هیچ مقداری گزارش نکرده/);
  // The hedge the old wording needed must be gone: none of them offers a choice.
  assert.doesNotMatch(silentAssignment, /متصل نشده/);
});

test("an unmapped warning with no status still says something true", () => {
  const text = describeReportWarning("PROGRESS_UNMAPPED");
  assert.match(text, /به هیچ تخصیصی/);
  assert.doesNotMatch(text, /undefined/);
});

test("the feed wording speaks about the one row it belongs to", () => {
  const feed = describeFeedWarning("PROGRESS_MISSING");
  const report = describeReportWarning("PROGRESS_MISSING");
  assert.notEqual(feed, report, "a per-assignment warning is not phrased like a project-wide one");
  assert.match(feed, /این تخصیص/);
});

test("an unknown code is still surfaced rather than swallowed", () => {
  assert.match(feedWarningText({ code: "SOMETHING_NEW" }), /SOMETHING_NEW/);
  assert.equal(feedWarningText({ code: "" }), null);
  assert.equal(feedWarningText(null), null);
});

test("a report warning with no known code falls back to what the service said", () => {
  assert.equal(reportWarningText({ code: "NEW_CODE", message: "service text" }), "service text");
  assert.match(reportWarningText({ code: "NEW_CODE" }), /هشدار بدون توضیح/);
  assert.equal(reportWarningText({ code: "GROSS_AREA_MISSING", message: "ignored" }), describeReportWarning("GROSS_AREA_MISSING"));
});

test("no surface keeps a private copy of the wording any more", () => {
  // The overview said «خطوط برآورد» and the report page said «ردیف‌های برآورد»
  // for the same code before this was shared.
  const surfaces = [
    "../../src/features/finance-home/finance-home-page.js",
    "../../src/features/progress/progress-page.js",
  ];
  surfaces.forEach((path) => {
    const source = read(path);
    assert.doesNotMatch(source, /WARNING_LABELS\s*=\s*Object\.freeze/, `${path} still declares its own warning map`);
    assert.match(source, /finance-warning-labels\.js/, `${path} does not read the shared wording`);
  });
});

test("the progress page renders the Backend's own feed warnings", () => {
  const source = read("../../src/features/progress/progress-page.js");
  assert.match(source, /assignment\.warnings \?\? \[\]/, "the feed's warnings array must be read, not ignored");
  assert.match(source, /feedWarningText/);
  // The two notes that remain are not Backend warnings and must stay local.
  assert.match(source, /sourceMethod === "manual_override"/);
  assert.match(source, /LOW_QUALITY_THRESHOLD/);
});

test("a refused progress request reads as a permission answer, not a fault", () => {
  const source = read("../../src/features/progress/progress-page.js");
  assert.match(source, /error\.status === 403 \? REQUEST_STATUS\.DENIED/);
});

test("nothing invents a snapshot's source from its file name", () => {
  // The strip that carried these facts came off the board, and the console log
  // that replaced it was dropped too -- the progress page shows them, in the
  // interface, where a reader can act on them. What the strip must never have
  // done, nothing else may start doing: a filename extension is not evidence of
  // the tool that produced a schedule, and sourceType is null for rows imported
  // before the Backend began recording it.
  const source = read("../../src/features/finance-home/finance-home-page.js");
  assert.doesNotMatch(source, /sourceFileNameSafe.{0,60}?(endsWith|includes\(|match\()/,
    "the page must not read a tool out of a file name");
  // And the one thing the log still says is the one thing not visible anywhere
  // else: the figures would be right numbers from the wrong version.
  assert.match(source, /answered !== asked/);
});


test("the page never works out the snapshot pairing for itself", () => {
  // The mapped/unmapped counts are no longer shown, and if they come back they
  // come from the service: repeating its pairing rule here would drift from it.
  const source = read("../../src/features/finance-home/finance-home-page.js");
  assert.doesNotMatch(source, /assignmentExternalId === /, "the page must not redo the pairing itself");
});
