import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  describeFeedWarning,
  describeReportWarning,
  feedWarningText,
  FEED_WARNING_CODES,
  REPORT_WARNING_CODES,
  reportWarningText,
} from "../../src/shared/warnings/finance-warning-labels.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

test("every warning code the Backend can emit has Persian wording", () => {
  // The finance domain emits these seven on the report; the feed adds its own.
  assert.deepEqual([...REPORT_WARNING_CODES].sort(), [
    "CURRENT_PRICE_MISSING",
    "GENERAL_COST_OVERRUN",
    "GROSS_AREA_MISSING",
    "MONTHLY_ESTIMATE_UNAVAILABLE",
    "PROGRESS_MISSING",
    "QUANTITY_OVERRUN",
    "UNIT_CONVERSION_MISSING",
  ]);
  assert.deepEqual([...FEED_WARNING_CODES].sort(), ["PROGRESS_MISSING", "TASK_PROGRESS_FALLBACK"]);
  [...REPORT_WARNING_CODES, ...FEED_WARNING_CODES].forEach((code) => {
    const text = describeReportWarning(code) ?? describeFeedWarning(code);
    assert.match(text, /[؀-ۿ]/, `${code} has no Persian wording`);
    assert.doesNotMatch(text, /[A-Z_]{6,}/, `${code} leaks a machine string into its wording`);
  });
});

test("PROGRESS_MISSING does not claim which of the two causes it is", () => {
  // The Backend cannot tell "not mapped to an activity" from "mapped but with no
  // usable quantity" — both arrive as this one code — so the wording must not
  // assert either. Claiming the wrong one sends the reader to the wrong fix.
  const text = describeReportWarning("PROGRESS_MISSING");
  assert.match(text, /متصل نشده/);
  assert.match(text, /یا/, "both causes are offered, not one asserted");
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
    "../../src/features/reports/reports-page.js",
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
