import test from "node:test";
import assert from "node:assert/strict";
import { describeImportPreview, DUPLICATE_IMPORT_REASON } from "../../src/shared/imports/import-preview-notice.js";
import { mapImportPreview } from "../../src/adapters/api/api-utils.js";

/**
 * ImportPreviewResponse reports a repeated file two ways at once: on
 * `duplicateFile`, and as an issue whose reason is the machine string
 * `duplicate_import_file`. These pin that the reader sees the first and never
 * the second.
 */

function backendPreview(overrides = {}) {
  return {
    previewId: "10000000-0000-4000-8000-000000000001",
    kind: "prices",
    rowCount: 2,
    validCount: 2,
    invalidCount: 0,
    rows: [{ rowNumber: 2, resourceId: "r1", resourceTitle: "میلگرد", resourceCode: "MAT-REBAR", unitPrice: "307000", normalizedUnitPriceIrr: "3070000", currency: "TOMAN", effectiveFrom: "2026-08-24", scope: "project", status: "valid", errors: [] }],
    errors: [],
    canCommit: true,
    ...overrides,
  };
}

test("the adapter carries the Backend's duplicate verdict instead of dropping it", () => {
  const mapped = mapImportPreview(backendPreview({
    canCommit: false,
    errors: [{ row: 0, field: "file", reason: DUPLICATE_IMPORT_REASON }],
    duplicateFile: true,
    duplicateOfImportId: "20000000-0000-4000-8000-000000000009",
    duplicateCommittedAt: "2026-08-11T09:20:00Z",
  }), "prices");

  assert.equal(mapped.duplicateFile, true);
  assert.equal(mapped.duplicateOfImportId, "20000000-0000-4000-8000-000000000009");
  assert.equal(mapped.duplicateCommittedAt, "2026-08-11T09:20:00Z");
});

test("the reason code never reaches the file errors a page prints", () => {
  const mapped = mapImportPreview(backendPreview({
    canCommit: false,
    errors: [{ row: 0, field: "file", reason: DUPLICATE_IMPORT_REASON }],
    duplicateFile: true,
  }), "prices");

  assert.deepEqual(mapped.fileErrors, [], "the raw reason is carried structurally, not as prose");
});

test("the adapter keeps other file-level problems while dropping only the duplicate reason", () => {
  // The wording helper returns from its duplicate branch before it consults
  // fileErrors, so this pins the adapter's filtering, not what is rendered.
  const mapped = mapImportPreview(backendPreview({
    canCommit: false,
    errors: [
      { row: 0, field: "file", reason: DUPLICATE_IMPORT_REASON },
      { row: 0, field: "header", reason: "missing column: unitPrice" },
    ],
    duplicateFile: true,
  }), "prices");

  assert.deepEqual(mapped.fileErrors, ["header: missing column: unitPrice"]);
});

test("a Backend that says nothing about duplication keeps the field closed", () => {
  const mapped = mapImportPreview(backendPreview(), "prices");
  assert.equal(mapped.duplicateFile, false);
  assert.equal(mapped.duplicateOfImportId, null);
  assert.equal(mapped.duplicateCommittedAt, null);
});

test("a repeated file is named as one, with the date it was first committed", () => {
  const verdict = describeImportPreview({
    canCommit: false,
    duplicateFile: true,
    duplicateCommittedAt: "2026-08-11T09:20:00Z",
    fileErrors: [],
  }, { readyText: "آماده", invalidText: "نامعتبر" });

  assert.equal(verdict.tone, "duplicate");
  assert.match(verdict.text, /این فایل قبلاً برای این پروژه ثبت شده است/);
  assert.match(verdict.text, /آخرین ثبت این فایل در/, "the earlier import is dated so the reader can find it");
  assert.doesNotMatch(verdict.text, /duplicate_import_file/);
});

test("a duplicate with no recorded date still reads as a sentence", () => {
  const verdict = describeImportPreview({ canCommit: false, duplicateFile: true, fileErrors: [] }, {});
  assert.equal(verdict.tone, "duplicate");
  assert.doesNotMatch(verdict.text, /undefined|null/);
});

test("duplication outranks the generic invalid wording", () => {
  // Both are true at once on a real response; the specific one is the useful one.
  const verdict = describeImportPreview({
    canCommit: false,
    duplicateFile: true,
    fileErrors: ["file: duplicate_import_file"],
  }, { readyText: "آماده", invalidText: "نامعتبر" });
  assert.equal(verdict.tone, "duplicate");
  assert.doesNotMatch(verdict.text, /duplicate_import_file/);
});

test("a valid preview is still reported as ready", () => {
  const verdict = describeImportPreview({ canCommit: true, duplicateFile: false }, { readyText: "آماده", invalidText: "نامعتبر" });
  assert.deepEqual(verdict, { tone: "ready", text: "آماده" });
});

test("an ordinary invalid file keeps its own page wording", () => {
  const withErrors = describeImportPreview({ canCommit: false, fileErrors: ["header: missing column"] }, { invalidText: "نامعتبر" });
  assert.equal(withErrors.tone, "invalid");
  assert.match(withErrors.text, /missing column/);

  const rowErrorsOnly = describeImportPreview({ canCommit: false, fileErrors: [] }, { invalidText: "نامعتبر" });
  assert.deepEqual(rowErrorsOnly, { tone: "invalid", text: "نامعتبر" });
});

test("even a stray reason code in fileErrors is filtered before printing", () => {
  // Belt and braces: if the adapter ever stops filtering, the page still will.
  const verdict = describeImportPreview({
    canCommit: false,
    duplicateFile: false,
    fileErrors: ["file: duplicate_import_file"],
  }, { invalidText: "نامعتبر" });
  assert.doesNotMatch(verdict.text, /duplicate_import_file/);
});

test("both mock importers reach the duplicate branch, so the demo runtime can show it", async () => {
  const context = { organizationId: "org-1", projectId: "project-1", userId: "user-1" };
  const [{ createMockPricesAdapter }, { createMockFinancialItemsAdapter }] = await Promise.all([
    import("../../src/adapters/mock/prices-adapter.js"),
    import("../../src/adapters/mock/financial-items-adapter.js"),
  ]);

  const prices = createMockPricesAdapter(context);
  const repeated = await prices.previewPriceImport({ name: "قیمت-تکراری.xlsx" });
  assert.equal(repeated.duplicateFile, true);
  assert.equal(repeated.canCommit, false, "the Backend refuses a repeated file, so the mock must too");
  assert.ok(repeated.duplicateCommittedAt, "a date to name in the wording");

  const fresh = await prices.previewPriceImport({ name: "قیمت.xlsx" });
  assert.equal(fresh.duplicateFile, false);
  assert.equal(fresh.canCommit, true);

  const items = createMockFinancialItemsAdapter(context);
  const repeatedEstimate = await items.previewEstimateImport({ name: "estimate-duplicate.xlsx" });
  assert.equal(repeatedEstimate.duplicateFile, true);
  assert.equal(repeatedEstimate.canCommit, false);
});

test("the commit-time refusal is answered in Persian, not with the developer's string", async () => {
  // repositories/imports.py raises DUPLICATE_IMPORT_FILE with an English message,
  // and it reaches the confirm dialog. A preset title alone would not have been
  // enough: the server message outranks a preset fallback unless it is overridden.
  const { formatApiErrorMessage } = await import("../../src/shared/errors/error-presentation.js");
  const message = formatApiErrorMessage({
    status: 409,
    code: "DUPLICATE_IMPORT_FILE",
    message: "this file was already imported into this project",
  });
  assert.doesNotMatch(message, /already imported/);
  assert.match(message, /همین فایل پیش‌تر برای این پروژه ثبت شده است/);
});

test("overriding one code does not silence the server message on any other", async () => {
  const { formatApiErrorMessage } = await import("../../src/shared/errors/error-presentation.js");
  const message = formatApiErrorMessage({ status: 409, code: "STALE_VERSION", message: "نسخه تغییر کرده است." });
  assert.match(message, /نسخه تغییر کرده است/);
});
