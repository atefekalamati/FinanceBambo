import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  REPORTS,
  REPORT_CATEGORIES,
  datasetsFor,
  featuredReports,
  findReport,
  normalizeSelection,
  reportsByCategory,
  selectionUsesPeriod,
} from "../../src/features/report-builder/report-catalog.js";
import { REPORT_SECTIONS } from "../../src/features/report-builder/report-sections.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

test("every report belongs to a declared category and says what it needs", () => {
  const categories = new Set(REPORT_CATEGORIES.map((category) => category.key));
  const keys = new Set();
  REPORTS.forEach((report) => {
    assert.ok(categories.has(report.category), `${report.key} is in no declared category`);
    assert.ok(report.needs?.length, `${report.key} names no dataset`);
    assert.match(report.title, /[؀-ۿ]/, `${report.key} has no Persian title`);
    assert.match(report.summary, /[؀-ۿ]/, `${report.key} has no Persian summary`);
    assert.ok(!keys.has(report.key), `${report.key} is declared twice`);
    keys.add(report.key);
  });
  // Every category the chooser draws has something in it.
  REPORT_CATEGORIES.forEach((category) => {
    assert.ok(reportsByCategory(category.key).length, `${category.key} has no reports`);
  });
});

test("a report that can be chosen is a report that can be drawn", () => {
  // The catalogue and the renderers are two lists, and a document that offered
  // something it cannot draw would produce a numbered heading over nothing.
  REPORTS.filter((report) => !report.unavailable).forEach((report) => {
    assert.equal(typeof REPORT_SECTIONS[report.key], "function", `${report.key} has no renderer`);
  });
  Object.keys(REPORT_SECTIONS).forEach((key) => {
    assert.ok(findReport(key), `${key} is drawn but not declared`);
  });
});

test("a report that is not yet producible says why, and cannot be chosen", () => {
  const pending = REPORTS.filter((report) => report.unavailable);
  assert.ok(pending.length, "the catalogue should still name what is coming");
  pending.forEach((report) => {
    assert.match(report.unavailable, /[؀-ۿ]/, `${report.key} gives no reason`);
    // Neither by ticking it, nor by typing its key into the address.
    assert.deepEqual(normalizeSelection([report.key]), []);
    assert.ok(!featuredReports().some((featured) => featured.key === report.key));
  });
});

test("a selection is cleaned up before anything is built from it", () => {
  assert.deepEqual(normalizeSelection(["breakdown", "nope", "breakdown", "overview"]), ["overview", "breakdown"]);
  assert.deepEqual(normalizeSelection([]), []);
  assert.deepEqual(normalizeSelection(), []);
  // Catalogue order, not the order they were ticked: the document's chapters
  // read the same way however the reader arrived at them.
  const reversed = normalizeSelection(["warnings", "overview"]);
  assert.deepEqual(reversed, ["overview", "warnings"]);
});

test("only the datasets the chosen reports need are asked for", () => {
  // A document of two summaries must not make the reader wait on the price list
  // it does not contain.
  assert.deepEqual(datasetsFor(["overview", "deviation"]), ["overview"]);
  assert.deepEqual(datasetsFor(["prices"]), ["prices"]);
  assert.deepEqual(datasetsFor(["invoices", "auditEvents"]).sort(), ["audit", "invoices"]);
  assert.deepEqual(datasetsFor([]), []);
  assert.deepEqual(datasetsFor(["sCurve"]), [], "a report that cannot be built fetches nothing");
});

test("the chosen range is only claimed when something in the document uses it", () => {
  // The cover carries the range. Printing one over a document of state figures
  // would say the whole thing covers a window it does not.
  assert.equal(selectionUsesPeriod(["invoices"]), true);
  assert.equal(selectionUsesPeriod(["auditEvents", "overview"]), true);
  assert.equal(selectionUsesPeriod(["overview", "breakdown", "prices"]), false);
  assert.equal(selectionUsesPeriod([]), false);
});

test("the document is addressable, so it can be reopened rather than rebuilt", () => {
  const bootstrap = read("../../src/app/bootstrap.js");
  assert.match(bootstrap, /route\.key === "report-builder"/);
  assert.match(bootstrap, /routeQuery\.get\("sections"\)/);
  assert.match(bootstrap, /routeQuery\.get\("from"\)/);
  const section = read("../../src/features/report-builder/report-builder-section.js");
  assert.match(section, /openReportBuilder/);
});

test("the chooser refuses to build nothing", () => {
  const dialog = read("../../src/features/report-builder/report-builder-dialog.js");
  assert.match(dialog, /build\.disabled = count === 0/);
  assert.match(dialog, /حداقل یک گزارش/);
  // And the range is read back at the moment it is used, because the picker it
  // comes from writes into a read-only input and announces nothing.
  assert.match(dialog, /const validation = readPeriod\(\)/);
});

test("the document carries the same chrome the project's other reports do", () => {
  const doc = read("../../src/features/report-builder/report-document.js");
  ["reportCover", "reportSection", "reportFooter", "reportTable", "reportFigures"].forEach((name) => {
    assert.ok(doc.includes(`export function ${name}(`), `${name} is missing`);
  });
  // Numbered chapters and a footer that says when it was made, as the control
  // documents have.
  assert.match(doc, /report-doc__section-number/);
  assert.match(doc, /بامبو — گزارش مالی پروژه · تولیدشده در/);
});
