import test from "node:test";
import assert from "node:assert/strict";
import { createMockPricesAdapter } from "../../src/adapters/mock/prices-adapter.js";

const context = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  projectId: "project_01",
};

test("prefers a valid project price over the organization base price", async () => {
  const adapter = createMockPricesAdapter(context);
  const workspace = await adapter.getPrices();
  const rebar = workspace.currentPrices.find((item) => item.resource.code === "MAT-REBAR");
  assert.equal(rebar.organizationPrice.scope, "organization");
  assert.equal(rebar.projectPrice.scope, "project");
  assert.equal(rebar.currentPrice.priceId, rebar.projectPrice.priceId);
  assert.equal(rebar.trend.scopeKind, "project");
  assert.equal(rebar.trend.trendDirection, "up");
  assert.equal(rebar.trend.previousPriceIrr, "295000");
  assert.equal(rebar.trend.currentPriceIrr, "302000");
  assert.equal(rebar.trend.latestChangePercent, "2.372881");
  assert.deepEqual(rebar.trend.trendPoints.map((point) => point.effectiveFrom), ["2026-07-15", "2026-08-01"]);
});

test("returns none when the resolved price scope has no previous version", async () => {
  const workspace = await createMockPricesAdapter(context).getPrices();
  const labor = workspace.currentPrices.find((item) => item.resource.code === "LAB-FORM");
  assert.equal(labor.trend.scopeKind, "organization");
  assert.equal(labor.trend.trendDirection, "none");
  assert.equal(labor.trend.previousPriceIrr, null);
  assert.equal(labor.trend.latestChangePercent, null);
});

test("appends a price version without rewriting history", async () => {
  const adapter = createMockPricesAdapter(context);
  const before = await adapter.getPrices();
  const labor = before.currentPrices.find((item) => item.resource.code === "LAB-FORM");
  const existing = labor.organizationPrice;
  const after = await adapter.createPriceVersion({ resourceId: labor.resource.resourceId, scope: "project", unitPriceIRR: "1950000", effectiveFrom: "2026-08-08" });
  assert.equal(after.history.length, before.history.length + 1);
  assert.ok(after.history.some((price) => price.priceId === existing.priceId && price.unitPriceIRR === existing.unitPriceIRR));
  assert.equal(after.currentPrices.find((item) => item.resource.code === "LAB-FORM").currentPrice.unitPriceIRR, "1950000");
});

test("allows same-date price corrections and deterministically selects the newest version", async () => {
  const adapter = createMockPricesAdapter(context);
  const workspace = await adapter.getPrices();
  const rebar = workspace.currentPrices.find((item) => item.resource.code === "MAT-REBAR");
  const previousId = rebar.projectPrice.priceId;
  const after = await adapter.createPriceVersion({ resourceId: rebar.resource.resourceId, scope: "project", unitPriceIRR: "310000", effectiveFrom: "2026-08-01" });
  const current = after.currentPrices.find((item) => item.resource.code === "MAT-REBAR");
  assert.equal(current.projectPrice.unitPriceIRR, "310000");
  assert.notEqual(current.projectPrice.priceId, previousId);
  assert.ok(after.history.some((price) => price.priceId === previousId && price.unitPriceIRR === "302000"));
});

test("previews and commits valid price rows as append-only versions", async () => {
  const adapter = createMockPricesAdapter(context);
  const before = await adapter.getPrices();
  const preview = await adapter.previewPriceImport({ name: "prices.xlsx" });
  assert.equal(preview.canCommit, true);
  assert.equal(preview.validRows, 2);
  assert.deepEqual(preview.rows.map((row) => row.currency), ["IRR", "TOMAN"]);

  const result = await adapter.commitPriceImport({ previewId: preview.previewId });
  assert.equal(result.importedCount, 2);
  assert.equal(result.workspace.history.length, before.history.length + 2);
  assert.equal(result.workspace.history.filter((price) => price.source === "excel_import").length, 2);
});

test("blocks price import commit when preview contains row errors", async () => {
  const adapter = createMockPricesAdapter(context);
  const preview = await adapter.previewPriceImport({ name: "prices-invalid.xlsx" });
  assert.equal(preview.canCommit, false);
  assert.equal(preview.invalidRows, 1);
  await assert.rejects(
    adapter.commitPriceImport({ previewId: preview.previewId }),
    (error) => error.code === "IMPORT_PREVIEW_INVALID",
  );
});

test("rejects unsupported price files and repeated import commits", async () => {
  const adapter = createMockPricesAdapter(context);
  await assert.rejects(adapter.previewPriceImport({ name: "prices.csv" }), (error) => error.code === "IMPORT_FILE_TYPE_INVALID");
  const preview = await adapter.previewPriceImport({ name: "prices.xls" });
  await adapter.commitPriceImport({ previewId: preview.previewId });
  await assert.rejects(
    adapter.commitPriceImport({ previewId: preview.previewId }),
    (error) => error.code === "IMPORT_ALREADY_COMMITTED",
  );
});

test("prefers a project unit conversion over the organization conversion", async () => {
  const adapter = createMockPricesAdapter(context);
  const workspace = await adapter.getPrices();
  const equipmentTime = workspace.currentConversions.find((item) => item.sourceUnit === "equipment_day" && item.targetUnit === "hour");
  assert.equal(equipmentTime.organizationConversion.factor, "8.000000");
  assert.equal(equipmentTime.projectConversion.factor, "10.000000");
  assert.equal(equipmentTime.currentConversion.factor, "10.000000");
});

test("appends a unit conversion version and preserves previous records", async () => {
  const adapter = createMockPricesAdapter(context);
  const before = await adapter.getPrices();
  const oldIds = before.conversionHistory.map((conversion) => conversion.conversionId);
  const after = await adapter.createUnitConversion({ sourceUnit: "ton", targetUnit: "kg", factor: "1020.000000", scope: "project", effectiveDate: "2026-08-08" });
  assert.equal(after.conversionHistory.length, before.conversionHistory.length + 1);
  assert.ok(oldIds.every((id) => after.conversionHistory.some((conversion) => conversion.conversionId === id)));
  const current = after.currentConversions.find((item) => item.sourceUnit === "ton" && item.targetUnit === "kg");
  assert.equal(current.currentConversion.factor, "1020.000000");
  assert.equal(current.currentConversion.projectId, context.projectId);
});

test("returns UNIT_MISMATCH for incompatible unit dimensions", async () => {
  const adapter = createMockPricesAdapter(context);
  await assert.rejects(
    adapter.createUnitConversion({ sourceUnit: "ton", targetUnit: "hour", factor: "1", scope: "organization", effectiveDate: "2026-08-08" }),
    (error) => error.code === "UNIT_MISMATCH",
  );
});
