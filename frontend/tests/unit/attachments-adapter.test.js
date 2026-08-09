import test from "node:test";
import assert from "node:assert/strict";
import { createMockAttachmentsAdapter } from "../../src/adapters/mock/attachments-adapter.js";

const context = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  projectId: "project_01",
  permissionCodes: ["finance.view", "finance.edit"],
};

test("uploads a scoped attachment without creating financial effect", async () => {
  const adapter = createMockAttachmentsAdapter(context);
  const result = await adapter.uploadFile({ file: { name: "فاکتور:نمونه.png", type: "image/png", size: 4096 }, logicalType: "invoice_image" });
  assert.equal(result.organizationId, context.organizationId);
  assert.equal(result.projectId, context.projectId);
  assert.equal(result.processingStatus, "uploaded");
  assert.equal(result.originalNameSafe.includes(":"), false);
  assert.equal(Object.hasOwn(result, "financialEffectIRR"), false);
  assert.equal((await adapter.getFiles()).length, 1);
});

test("blocks upload without finance edit permission", async () => {
  const adapter = createMockAttachmentsAdapter({ ...context, permissionCodes: ["finance.view"] });
  await assert.rejects(
    adapter.uploadFile({ file: { name: "invoice.png", type: "image/png", size: 4096 }, logicalType: "invoice_image" }),
    (error) => error.status === 403 && error.code === "FINANCE_PERMISSION_DENIED",
  );
});

test("surfaces the simulated file workspace failure", async () => {
  const adapter = createMockAttachmentsAdapter(context, { initialState: "error" });
  await assert.rejects(adapter.getFiles(), (error) => error.status === 503 && Boolean(error.requestId));
});
