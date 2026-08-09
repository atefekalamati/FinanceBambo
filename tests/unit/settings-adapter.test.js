import test from "node:test";
import assert from "node:assert/strict";
import { createMockSettingsAdapter } from "../../src/adapters/mock/settings-adapter.js";

const context = { userId: "00000000-0000-4000-8000-000000000001", organizationId: "00000000-0000-4000-8000-000000000002", projectId: "project_01" };

test("appends a gross-built-area revision instead of replacing history", async () => {
  const adapter = createMockSettingsAdapter(context);
  const before = await adapter.getSettings();
  const after = await adapter.updateGrossBuiltArea({ grossBuiltArea: "4300.0000", reason: "اصلاح براساس نقشه مصوب", effectiveDate: "2026-08-08", expectedRevision: before.revision });
  assert.equal(after.grossBuiltArea, "4300.0000");
  assert.equal(after.revision, 2);
  assert.equal(after.revisions.length, before.revisions.length + 1);
  assert.equal(after.revisions[0].previousValue, "4250.0000");
  assert.equal(before.grossBuiltArea, "4250.0000");
});

test("rejects a stale settings version", async () => {
  const adapter = createMockSettingsAdapter(context);
  await assert.rejects(
    adapter.updateGrossBuiltArea({ grossBuiltArea: "4300", reason: "اصلاح معتبر", effectiveDate: "2026-08-08", expectedRevision: 0 }),
    (error) => error.code === "STALE_VERSION" && error.status === 409,
  );
});
