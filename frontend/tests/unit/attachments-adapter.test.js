import test from "node:test";
import assert from "node:assert/strict";
import { createMockAttachmentsAdapter } from "../../src/adapters/mock/attachments-adapter.js";
import { createMockInvoicesAdapter } from "../../src/adapters/mock/invoices-adapter.js";

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

test("keeps file, extraction review and invoice lifecycles independent", async () => {
  const adapter = createMockAttachmentsAdapter(context);
  const file = await adapter.uploadFile({ file: { name: "invoice.png", type: "image/png", size: 4096 }, logicalType: "invoice_image" });
  const draft = await adapter.startExtraction(file.fileId);
  assert.equal(draft.file.processingStatus, "ready");
  assert.equal(draft.reviewStatus, "awaitingReview");
  assert.equal(draft.invoiceStatus, "draft");
  assert.equal(draft.financialEffectIRR, "0");
  assert.ok(draft.fields.some((field) => field.confidence < 0.8));
});

test("retries extraction as a new version without replacing the previous review", async () => {
  const adapter = createMockAttachmentsAdapter(context);
  const file = await adapter.uploadFile({ file: { name: "invoice.mp3", type: "audio/mpeg", size: 4096 }, logicalType: "invoice_voice" });
  const first = await adapter.startExtraction(file.fileId);
  const second = await adapter.retryExtraction(first.draftId);
  assert.equal(first.version, 1);
  assert.equal(second.version, 2);
  assert.equal((await adapter.getExtractions()).length, 2);
});

test("rejects an extraction without deleting its uploaded file", async () => {
  const adapter = createMockAttachmentsAdapter(context);
  const file = await adapter.uploadFile({ file: { name: "invoice.png", type: "image/png", size: 4096 }, logicalType: "invoice_image" });
  const draft = await adapter.startExtraction(file.fileId);
  const rejected = await adapter.rejectExtraction({ draftId: draft.draftId, expectedVersion: 1 });
  assert.equal(rejected.reviewStatus, "rejected");
  assert.equal(rejected.financialEffectIRR, "0");
  assert.equal((await adapter.getFiles()).length, 1);
});

test("confirms human edits only for the uploader and current version", async () => {
  const invoiceAdapter = createMockInvoicesAdapter(context);
  const adapter = createMockAttachmentsAdapter(context, { invoiceAdapter });
  const file = await adapter.uploadFile({ file: { name: "invoice.png", type: "image/png", size: 4096 }, logicalType: "invoice_image" });
  const draft = await adapter.startExtraction(file.fileId);
  const invoice = await adapter.confirmExtraction({
    draftId: draft.draftId,
    expectedVersion: 1,
    idempotencyKey: "ai-confirm-1",
    fieldConfirmations: [{ key: "vendorName", confirmedValue: "فروشنده اصلاح‌شده" }],
    invoice: { invoiceNumber: "۱۲", invoiceDate: "2026-08-09", vendorName: "فروشنده اصلاح‌شده", resourceId: "general-permit", totalIRR: "248500000" },
  });
  assert.equal(invoice.invoiceStatus, "confirmed");
  assert.equal(invoice.source, "image");
  assert.equal(invoice.finalAmountIRR, "248500000");
  const accepted = (await adapter.getExtractions()).find((item) => item.draftId === draft.draftId);
  assert.equal(accepted.reviewStatus, "accepted");
  assert.equal(accepted.fields.find((field) => field.key === "vendorName").editedByUser, true);
  const repeated = await adapter.confirmExtraction({
    draftId: draft.draftId,
    expectedVersion: 1,
    idempotencyKey: "ai-confirm-1",
    fieldConfirmations: [],
    invoice: { invoiceDate: "2026-08-09", vendorName: "نادیده‌گرفته‌شده", resourceId: "general-permit", totalIRR: "1" },
  });
  assert.equal(repeated.finalAmountIRR, "248500000");
  assert.ok((await invoiceAdapter.getInvoices({ source: "image" })).items.some((item) => item.invoiceId === invoice.invoiceId));
  await assert.rejects(
    adapter.rejectExtraction({ draftId: draft.draftId, expectedVersion: 1 }),
    (error) => error.code === "STALE_VERSION",
  );
});

test("preserves a failed provider upload for retry and manual fallback", async () => {
  const adapter = createMockAttachmentsAdapter(context);
  const file = await adapter.uploadFile({ file: { name: "invoice.png", type: "image/png", size: 4096 }, logicalType: "invoice_image" });
  await assert.rejects(adapter.startExtraction(file.fileId, { simulateFailure: true }), (error) => error.code === "AI_EXTRACTION_FAILED" && error.status === 503);
  const failed = (await adapter.getFiles()).find((item) => item.fileId === file.fileId);
  assert.equal(failed.processingStatus, "failed");
  assert.match(failed.processingError, /حفظ/);
  const retried = await adapter.startExtraction(file.fileId);
  assert.equal(retried.reviewStatus, "awaitingReview");
});
