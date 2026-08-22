import test from "node:test";
import assert from "node:assert/strict";
import { createMockFinancialItemsAdapter } from "../../src/adapters/mock/financial-items-adapter.js";

const context = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  projectId: "project_01",
};

test("keeps repeated resource use as independent activity lines", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const workspace = await adapter.getWorkspace();
  const rebar = workspace.resources.find((resource) => resource.code === "MAT-REBAR");
  const rebarLines = workspace.estimateLines.filter((line) => line.resourceId === rebar.resourceId);
  assert.equal(rebarLines.length, 2);
  assert.notEqual(rebarLines[0].lineId, rebarLines[1].lineId);
  assert.notEqual(rebarLines[0].activityExternalId, rebarLines[1].activityExternalId);
});

test("creates an estimate line with immutable original and initial revised quantity", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const workspace = await adapter.getWorkspace();
  const material = workspace.resources.find((resource) => resource.type === "material");
  const next = await adapter.createEstimateLine({ activityExternalId: "ACT-202", resourceId: material.resourceId, originalQuantity: "120.5000", originalUnitPriceIRR: "285000" });
  const created = next.estimateLines.at(-1);
  assert.equal(created.originalQuantity, "120.5000");
  assert.equal(created.revisedQuantity, "120.5000");
  assert.equal(created.originalUnitPriceIRR, "285000", "the initial estimate is quantity x this price, so it must be recorded");
  assert.notEqual(created.lineId, next.estimateLines[0].lineId);
});

test("stores general cost as integer IRR amount without a physical quantity", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const workspace = await adapter.getWorkspace();
  const generalCost = workspace.resources.find((resource) => resource.type === "general_cost");
  const next = await adapter.createEstimateLine({ activityExternalId: "ACT-002", resourceId: generalCost.resourceId, originalQuantity: "5000000" });
  const created = next.estimateLines.at(-1);
  assert.equal(created.originalQuantity, null);
  assert.equal(created.originalAmount, "5000000");
});

test("appends revision history while keeping original quantity immutable", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const before = await adapter.getWorkspace();
  const line = before.estimateLines.find((item) => item.originalQuantity === "8500.0000");
  const after = await adapter.reviseEstimateLine({ lineId: line.lineId, revisedValue: "9000.0000", reason: "اصلاح براساس نقشه اجرایی", expectedRevision: line.revision });
  const revised = after.estimateLines.find((item) => item.lineId === line.lineId);
  assert.equal(revised.originalQuantity, "8500.0000");
  assert.equal(revised.revisedQuantity, "9000.0000");
  assert.equal(revised.revisions[0].previousValue, "8500.0000");
  assert.equal(revised.revisions[0].newValue, "9000.0000");
  assert.equal(revised.revisions[0].reason, "اصلاح براساس نقشه اجرایی");
  assert.equal(revised.revisions[0].isOverrun, true);
});

test("rejects stale or no-change estimate revisions", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const workspace = await adapter.getWorkspace();
  const line = workspace.estimateLines.find((item) => item.originalQuantity === "8500.0000");
  await assert.rejects(
    adapter.reviseEstimateLine({ lineId: line.lineId, revisedValue: "9000", reason: "اصلاح معتبر", expectedRevision: 999 }),
    (error) => error.code === "STALE_VERSION",
  );
  await assert.rejects(
    adapter.reviseEstimateLine({ lineId: line.lineId, revisedValue: line.revisedQuantity, reason: "اصلاح معتبر", expectedRevision: line.revision }),
    (error) => error.code === "REVISION_NO_CHANGE",
  );
});

test("previews and commits a valid estimate import without changing original values", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const before = await adapter.getWorkspace();
  const preview = await adapter.previewEstimateImport({ name: "estimate.xlsx" });

  assert.equal(preview.canCommit, true);
  assert.equal(preview.invalidRows, 0);
  assert.equal(preview.validRows, 2);

  const result = await adapter.commitEstimateImport({ previewId: preview.previewId });
  assert.equal(result.importedCount, 2);
  assert.equal(result.workspace.estimateLines.length, before.estimateLines.length + 2);
  for (const line of result.workspace.estimateLines.slice(-2)) {
    assert.equal(line.source, "excel_import");
    assert.equal(line.originalQuantity, line.revisedQuantity);
    assert.equal(line.revision, 1);
    assert.deepEqual(line.revisions, []);
  }
});

test("blocks commit when estimate import preview has row errors", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const preview = await adapter.previewEstimateImport({ name: "estimate-invalid.xlsx" });

  assert.equal(preview.canCommit, false);
  assert.equal(preview.invalidRows, 1);
  assert.ok(preview.rows.some((row) => row.errors.length > 0));
  await assert.rejects(
    adapter.commitEstimateImport({ previewId: preview.previewId }),
    (error) => error.code === "IMPORT_PREVIEW_INVALID",
  );
});

test("rejects unsupported estimate import files and repeated commits", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  await assert.rejects(
    adapter.previewEstimateImport({ name: "estimate.csv" }),
    (error) => error.code === "IMPORT_FILE_TYPE_INVALID",
  );

  const preview = await adapter.previewEstimateImport({ name: "estimate.xls" });
  await adapter.commitEstimateImport({ previewId: preview.previewId });
  await assert.rejects(
    adapter.commitEstimateImport({ previewId: preview.previewId }),
    (error) => error.code === "IMPORT_ALREADY_COMMITTED",
  );
});

test("a quantified estimate line cannot be created without the price it was fixed at", async () => {
  const adapter = createMockFinancialItemsAdapter(context);
  const workspace = await adapter.getWorkspace();
  const material = workspace.resources.find((resource) => resource.type === "material");
  await assert.rejects(
    adapter.createEstimateLine({ activityExternalId: "ACT-202", resourceId: material.resourceId, originalQuantity: "10.0000" }),
    (error) => error.status === 422,
    "without originalUnitPriceIrr the Backend computes an initial estimate of zero",
  );
});
