import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { changedEstimateRows, supplierDocumentRows } from "../../src/features/report-builder/report-followups.js";
import { REPORTS, featuredReports, datasetsFor } from "../../src/features/report-builder/report-catalog.js";

test("the catalogue keeps the featured shortcuts and shares existing datasets", () => {
  assert.equal(REPORTS.length, 21);
  assert.equal(featuredReports().length, 6);
  assert.deepEqual(datasetsFor(["supplierDocuments", "pendingDocuments", "correctiveDocuments"]), ["invoices"]);
  assert.deepEqual(datasetsFor(["completionBudget", "areaCosts"]), ["overview"]);
  // The two that replaced the period report read the project at two dates, and
  // are the only entries that do. They share one dataset with each other and
  // with nothing else, so choosing either does not drag the rest of the module
  // into the request.
  assert.deepEqual(datasetsFor(["periodMetrics", "periodBreakdown"]), ["periodOverview"]);
  assert.deepEqual(datasetsFor(["overview", "periodMetrics"]), ["overview", "periodOverview"]);
});

test("supplier register separates statuses and sources and sums exact nominal amounts", () => {
  const invoice = { vendorName: "فروشنده", invoiceStatus: "confirmed", source: "manual", invoiceDate: "2026-09-01", finalAmountIRR: "90071992547409931" };
  const rows = supplierDocumentRows([invoice, { ...invoice, finalAmountIRR: "9" }, { ...invoice, invoiceStatus: "draft" }, { ...invoice, source: "reversal" }, { ...invoice, invoiceDate: "2026-08-01" }], { from: "2026-09-01", to: "2026-09-30" });
  assert.equal(rows.length, 3);
  assert.equal(rows[0].amount, "90071992547409940");
  assert.equal(rows[0].count, 2);
  assert.equal(supplierDocumentRows([{ ...invoice, finalAmountIRR: null }])[0].amount, null);
});

test("estimate comparisons ignore decimal formatting but keep changed and unknown rows", () => {
  const workspace = { resources: [{ resourceId: "m", type: "material" }, { resourceId: "g", type: "general_cost" }], estimateLines: [
    { resourceId: "m", originalQuantity: "01.0000", revisedQuantity: "1" },
    { resourceId: "m", originalQuantity: "1.0001", revisedQuantity: "1" },
    { resourceId: "g", originalAmount: "100000000000000001", revisedAmount: "100000000000000002" },
    { resourceId: "m", originalQuantity: null, revisedQuantity: "1" },
  ] };
  const rows = changedEstimateRows(workspace);
  assert.equal(rows.length, 3);
  assert.equal(rows[1].general, true);
  assert.equal(rows[2].known, false);
});

test("category viewport has a finite responsive cap and keyboard access", () => {
  const css = readFileSync(new URL("../../src/features/report-builder/report-builder.css", import.meta.url), "utf8");
  assert.match(css, /max-block-size: min\(24rem, 48dvh\)/);
  assert.match(css, /overscroll-behavior-y: contain/);
  const dialog = readFileSync(new URL("../../src/features/report-builder/report-builder-dialog.js", import.meta.url), "utf8");
  assert.match(dialog, /cats.tabIndex = 0/);
  assert.match(dialog, /activeCategory.*focus\(\)/);
});
