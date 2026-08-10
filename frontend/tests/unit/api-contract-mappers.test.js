import test from "node:test";
import assert from "node:assert/strict";
import { mapImportPreview } from "../../src/adapters/api/api-utils.js";
import { createApiFinancialItemsAdapter } from "../../src/adapters/api/financial-items-api-adapter.js";

test("maps canonical backend import preview rows instead of rebuilding only errors", () => {
  const preview = mapImportPreview({
    previewId: "preview-1",
    rowCount: 2,
    validCount: 1,
    invalidCount: 1,
    canCommit: false,
    rows: [
      { rowNumber: 2, status: "valid", errors: [], resourceCode: "MAT-1", resourceTitle: "میلگرد", baseUnit: "kg", activityExternalId: "A-1", activityTitle: "آرماتوربندی", originalQuantity: "12.5" },
      { rowNumber: 3, status: "invalid", errors: [{ row: 3, field: "resourceCode", reason: "resource_not_found" }], resourceCode: "X", originalQuantity: "2" },
    ],
    errors: [],
  }, "estimate");
  assert.equal(preview.validRows, 1);
  assert.equal(preview.rows[0].resourceTitle, "میلگرد");
  assert.equal(preview.rows[0].value, "12.5");
  assert.deepEqual(preview.rows[1].errors, ["resourceCode: resource_not_found"]);
});

test("maps IRR and TOMAN price preview rows without replacing entered currency or amount", () => {
  const preview = mapImportPreview({
    previewId: "preview-price",
    rowCount: 2,
    validCount: 2,
    invalidCount: 0,
    canCommit: true,
    errors: [],
    rows: [
      { rowNumber: 2, status: "valid", errors: [], resourceCode: "MAT-1", resourceTitle: "میلگرد", unitPrice: "125", currency: "TOMAN", normalizedUnitPriceIrr: "1250", effectiveFrom: "2026-08-10", scope: "project" },
      { rowNumber: 3, status: "valid", errors: [], resourceCode: "LAB-1", resourceTitle: "کارگر", unitPrice: "900", currency: "IRR", normalizedUnitPriceIrr: "900", effectiveFrom: "2026-08-10", scope: "organization" },
    ],
  }, "prices");
  assert.deepEqual(preview.rows.map((row) => [row.importedAmount, row.currency, row.unitPriceIRR]), [["125", "TOMAN", "1250"], ["900", "IRR", "900"]]);
});

test("keeps invalid price row details and authoritative preview counters", () => {
  const preview = mapImportPreview({
    previewId: "preview-price-invalid",
    rowCount: 3,
    validCount: 2,
    invalidCount: 1,
    canCommit: false,
    errors: [{ row: 4, field: "currency", reason: "invalid_choice" }],
    rows: [{ rowNumber: 4, status: "invalid", errors: [{ row: 4, field: "currency", reason: "invalid_choice" }], resourceCode: "MAT-1", resourceTitle: "میلگرد", unitPrice: "125", currency: "USD", normalizedUnitPriceIrr: null, effectiveFrom: "2026-08-10", scope: "project" }],
  }, "prices");
  assert.deepEqual([preview.validRows, preview.invalidRows], [2, 1]);
  assert.equal(preview.rows[0].currency, "USD");
  assert.deepEqual(preview.rows[0].errors, ["currency: invalid_choice"]);
  assert.deepEqual(preview.fileErrors, []);
});

test("keeps wrong-template errors at file level and does not synthesize preview rows", () => {
  const preview = mapImportPreview({ previewId: "wrong-template", rowCount: 0, validCount: 0, invalidCount: 0, rows: [], errors: [{ row: 1, field: "unitPrice", reason: "unexpected_column" }], canCommit: false }, "estimate");
  assert.deepEqual(preview.rows, []);
  assert.deepEqual(preview.fileErrors, ["unitPrice: unexpected_column"]);
});

test("maps canonical estimate revision history and general cost amount", async () => {
  const context = { organizationId: "org-1", projectId: "project-1" };
  const client = {
    async request(path) {
      if (path.endsWith("/resources")) return [{ id: "resource-1", type: "general_cost", code: "GEN-1", title: "مجوز", baseUnit: null, dimension: null }];
      if (path.endsWith("/estimate-lines")) return [{ id: "line-1", resourceId: "resource-1", activityExternalId: "A-1", assignmentExternalId: null, originalQuantity: null, revisedQuantity: "1200000", originalUnitPriceIrr: "1000000", source: "manual_entry", revision: 2, revisions: [{ id: "revision-1", revision: 2, previousQuantity: "1000000", newQuantity: "1200000", reason: "اصلاح", createdBy: "user-1", createdAt: "2026-08-10T08:00:00Z" }] }];
      throw new Error(`unexpected path: ${path}`);
    },
  };
  const workspace = await createApiFinancialItemsAdapter(context, client).getWorkspace();
  const line = workspace.estimateLines[0];
  assert.equal(line.originalAmount, "1000000");
  assert.equal(line.revisedAmount, "1200000");
  assert.equal(line.revision, 2);
  assert.equal(line.revisions[0].reason, "اصلاح");
  assert.equal(line.revisions[0].isOverrun, true);
});

test("sends general cost amount only in canonical money field", async () => {
  const calls = [];
  const context = { organizationId: "org-1", projectId: "project-1" };
  const client = {
    async request(path, options) {
      calls.push({ path, options });
      if (path.endsWith("/resources")) return [{ id: "resource-1", type: "general_cost", code: "GEN-1", title: "مجوز", baseUnit: null, dimension: null }];
      if (path.endsWith("/estimate-lines") && !options) return [];
      if (path.endsWith("/estimate-lines") && options?.method === "POST") return {};
      throw new Error(`unexpected path: ${path}`);
    },
  };
  const adapter = createApiFinancialItemsAdapter(context, client);
  await adapter.getWorkspace();
  await adapter.createEstimateLine({ resourceId: "resource-1", activityExternalId: "A-1", assignmentExternalId: null, originalQuantity: "2500000" });
  const body = JSON.parse(calls.find((call) => call.options?.method === "POST").options.body);
  assert.equal(body.originalQuantity, null);
  assert.equal(body.originalUnitPriceIrr, "2500000");
});
