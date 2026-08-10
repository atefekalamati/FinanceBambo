import test from "node:test";
import assert from "node:assert/strict";

import { mapImportPreview } from "../../src/adapters/api/api-utils.js";

test("maps every real estimate preview row without synthesizing mock data", () => {
  const result = mapImportPreview({
    previewId: "preview-1", rowCount: 2, validCount: 1, invalidCount: 1, canCommit: false,
    rows: [
      { rowNumber: 2, status: "valid", errors: [], resourceCode: "M1", resourceId: "resource-1", resourceTitle: "میلگرد", baseUnit: "kg", activityExternalId: "A1", activityTitle: null, assignmentExternalId: "AS1", originalQuantity: "2.5000", source: "excel_import" },
      { rowNumber: 3, status: "invalid", errors: [{ row: 3, field: "resourceCode", reason: "resource_not_found" }], resourceCode: "UNKNOWN", resourceId: null, resourceTitle: null, baseUnit: null, activityExternalId: "A2", activityTitle: null, assignmentExternalId: "AS2", originalQuantity: "1", source: "excel_import" },
    ],
  }, "estimate");
  assert.equal(result.rows.length, 2);
  assert.deepEqual([result.validRows, result.invalidRows, result.canCommit], [1, 1, false]);
  assert.deepEqual([result.rows[0].resourceTitle, result.rows[0].value, result.rows[0].unit], ["میلگرد", "2.5000", "kg"]);
  assert.deepEqual(result.rows[1].errors, ["resourceCode: resource_not_found"]);
});

test("maps row-specific price currency and normalized IRR", () => {
  const result = mapImportPreview({
    previewId: "preview-2", rowCount: 1, validCount: 1, invalidCount: 0, canCommit: true,
    rows: [{ rowNumber: 2, status: "valid", errors: [], resourceCode: "M1", resourceId: "resource-1", resourceTitle: "میلگرد", unitPrice: "197500", currency: "TOMAN", normalizedUnitPriceIrr: "1975000", effectiveFrom: "2026-08-10", scope: "project" }],
  }, "prices");
  assert.deepEqual([result.rows[0].importedAmount, result.rows[0].currency, result.rows[0].unitPriceIRR], ["197500", "TOMAN", "1975000"]);
  assert.deepEqual([result.validRows, result.invalidRows, result.canCommit], [1, 0, true]);
});
