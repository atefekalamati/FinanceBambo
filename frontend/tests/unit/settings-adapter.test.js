import test from "node:test";
import assert from "node:assert/strict";
import { createMockSettingsAdapter } from "../../src/adapters/mock/settings-adapter.js";

const context = { userId: "00000000-0000-4000-8000-000000000001", organizationId: "00000000-0000-4000-8000-000000000002", projectId: "project_01" };

test("advances the settings revision and reports the audited reason of the new one", async () => {
  const adapter = createMockSettingsAdapter(context);
  const before = await adapter.getSettings();
  const after = await adapter.updateGrossBuiltArea({ grossBuiltArea: "4300.0000", reason: "اصلاح براساس نقشه مصوب", effectiveDate: "2026-08-08", expectedRevision: before.revision });

  assert.equal(before.grossBuiltArea, "4250.0000", "the fetched snapshot is not mutated in place");
  assert.equal(after.grossBuiltArea, "4300.0000");
  assert.equal(after.revision, before.revision + 1);
  assert.equal(after.effectiveFrom, "2026-08-08");
  assert.equal(after.reason, "اصلاح براساس نقشه مصوب");
  assert.equal(after.createdBy, context.userId);
  assert.ok(after.createdAt, "createdAt stamps the accepted revision");
});

test("exposes exactly the FinanceSettingsResponse fields and no invented history", async () => {
  const settings = await createMockSettingsAdapter(context).getSettings();
  assert.deepEqual(
    Object.keys(settings).sort(),
    ["createdAt", "createdBy", "currency", "displayCurrency", "effectiveFrom", "grossBuiltArea", "grossBuiltAreaUnit", "revision", "reason", "settingsId"].sort(),
  );
  assert.equal(settings.currency, "IRR", "storage currency is always IRR per FR-002");
  assert.equal("revisions" in settings, false, "the Backend exposes no settings history; the mock must not either");
});

test("rejects a stale settings version", async () => {
  const adapter = createMockSettingsAdapter(context);
  await assert.rejects(
    adapter.updateGrossBuiltArea({ grossBuiltArea: "4300", reason: "اصلاح معتبر", effectiveDate: "2026-08-08", expectedRevision: 0 }),
    (error) => error.code === "STALE_VERSION" && error.status === 409,
  );
});
