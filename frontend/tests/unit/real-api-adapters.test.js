import test from "node:test";
import assert from "node:assert/strict";
import { createApiAttachmentsAdapter } from "../../src/adapters/api/attachments-api-adapter.js";
import { createApiInvoicesAdapter } from "../../src/adapters/api/invoices-api-adapter.js";
import { createApiProgressAdapter } from "../../src/adapters/api/progress-api-adapter.js";
import { createApiSettingsAdapter } from "../../src/adapters/api/settings-api-adapter.js";

const context = { organizationId: "org-1", projectId: "project-1", locale: "fa-IR" };

function invoice(id = "invoice-1") {
  return { id, invoiceNumber: "F-1", invoiceDate: "2026-08-10", vendorName: "فروشنده", description: null, source: "manual", status: "draft", discountIrr: "0", taxIrr: "0", shippingIrr: "0", otherCostsIrr: "0", finalAmountIrr: "1000", financialEffectSign: 1, originalInvoiceId: null, idempotencyKey: "key", version: 1, submittedBy: "user-1", confirmedBy: null, confirmedAt: null, createdAt: "2026-08-10T08:00:00Z", lines: [{ estimateLineId: "line-1", resourceId: "resource-1", quantity: "1", unit: "kg", unitPriceIrr: "1000", rawAmountIrr: "1000", finalLineAmountIrr: "1000", description: null }] };
}

test("uses backend invoice list items, metadata, search and filters without client pagination", async () => {
  const calls = [];
  const client = { async request(path) { calls.push(path); return { items: [invoice()], page: 2, pageSize: 25, totalItems: 51, totalPages: 3 }; } };
  const result = await createApiInvoicesAdapter(context, client).getInvoices({ query: "فروشنده خاص", status: "draft", source: "manual", page: 2, pageSize: 25 });
  assert.equal(result.items.length, 1);
  assert.deepEqual([result.page, result.pageSize, result.totalItems, result.totalPages], [2, 25, 51, 3]);
  const url = new URL(calls[0], "https://example.test");
  assert.deepEqual(Object.fromEntries(url.searchParams), { page: "2", pageSize: "25", query: "فروشنده خاص", status: "draft", source: "manual" });
});

test("sends general-cost invoice line as direct IRR amount without quantity semantics", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); if (path.endsWith("/resources")) return [{ id: "resource-general", type: "general_cost", code: "GEN", title: "مجوز", baseUnit: null }]; if (path.endsWith("/estimate-lines")) return []; if (path.endsWith("/invoices") && options?.method === "POST") return invoice(); throw new Error(path); } };
  const adapter = createApiInvoicesAdapter(context, client);
  const targets = await adapter.getInvoiceTargets();
  await adapter.createDraft({ header: { invoiceNumber: "F-G", invoiceDate: "2026-08-10", vendorName: "فروشنده", description: "" }, lines: [{ targetId: targets[0].targetId, targetType: "general_cost", lineAmountIRR: "7000", description: "" }], adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" }, duplicateOverrideReason: null, idempotencyKey: "draft-general" });
  const body = JSON.parse(calls.find((call) => call.path.endsWith("/invoices") && call.options?.method === "POST").options.body);
  assert.equal(body.lines[0].lineAmountIrr, "7000");
  assert.equal(body.lines[0].quantity, null);
  assert.equal(body.lines[0].unitPriceIrr, null);
});

test("uses real file and extraction routes for list, start, get, retry and reject", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); if (path.includes("/files?")) return { items: [{ fileId: "file-1" }] }; if (path.includes("/extractions?")) return { items: [{ draftId: "draft-1" }] }; return { draftId: "draft-1" }; } };
  const adapter = createApiAttachmentsAdapter(context, client, { getInvoiceTargets: async () => [] });
  assert.equal((await adapter.getFiles())[0].fileId, "file-1");
  assert.equal((await adapter.getExtractions())[0].draftId, "draft-1");
  await adapter.startExtraction("file-1");
  await adapter.getExtraction("draft-1");
  await adapter.retryExtraction("draft-1");
  await adapter.rejectExtraction({ draftId: "draft-1", expectedVersion: 3 });
  // `/extractions/async`: starting an extraction answers 202 and the page polls the
  // attachment status. The blocking route held the request open for the whole OCR run.
  assert.ok(calls.some((call) => call.path.endsWith("/files/file-1/extractions/async") && call.options.method === "POST"));
  assert.ok(calls.some((call) => call.path.endsWith("/extractions/draft-1") && !call.options));
  assert.ok(calls.some((call) => call.path.endsWith("/extractions/draft-1/retry")));
  const reject = calls.find((call) => call.path.endsWith("/extractions/draft-1/reject"));
  assert.deepEqual(JSON.parse(reject.options.body), { expectedVersion: 3, reason: null });
});

test("forwards supported file and extraction filters to Backend pagination", async () => {
  const calls = [];
  const client = { async request(path) { calls.push(path); return { items: [] }; } };
  const adapter = createApiAttachmentsAdapter(context, client, { getInvoiceTargets: async () => [] });
  await adapter.getFiles({ page: 2, pageSize: 25, logicalType: "invoice_image", processingStatus: "ready", uploaderId: "user-1" });
  await adapter.getExtractions({ page: 3, pageSize: 10, reviewStatus: "awaitingReview", source: "image", fileId: "file-1", linkedInvoiceId: "invoice-1" });
  assert.deepEqual(Object.fromEntries(new URL(calls[0], "https://example.test").searchParams), { page: "2", pageSize: "25", logicalType: "invoice_image", processingStatus: "ready", uploaderId: "user-1" });
  assert.deepEqual(Object.fromEntries(new URL(calls[1], "https://example.test").searchParams), { page: "3", pageSize: "10", reviewStatus: "awaitingReview", source: "image", fileId: "file-1", linkedInvoiceId: "invoice-1" });
});

test("maps reviewed extraction confirmation to canonical invoice DTO", async () => {
  let request;
  const client = { async request(path, options) { request = { path, options }; return invoice(); } };
  const targets = [{ targetId: "target-1", targetType: "general_cost", estimateLineId: null, resourceId: "resource-1" }];
  const adapter = createApiAttachmentsAdapter(context, client, { getInvoiceTargets: async () => targets });
  await adapter.confirmExtraction({ draftId: "draft-1", expectedVersion: 2, idempotencyKey: "confirm-1", fieldConfirmations: [], invoice: { invoiceNumber: "F-2", invoiceDate: "2026-08-10", vendorName: "فروشنده", resourceId: "target-1", totalIRR: "5000" } });
  const body = JSON.parse(request.options.body);
  assert.equal(body.invoice.lines[0].lineAmountIrr, "5000");
  assert.equal(body.invoice.lines[0].quantity, null);
  assert.equal(body.expectedVersion, 2);
});

test("does not invent quantity truth when extracted total targets a quantified line", async () => {
  const adapter = createApiAttachmentsAdapter(context, { request: async () => { throw new Error("request must not be sent"); } }, { getInvoiceTargets: async () => [{ targetId: "target-1", targetType: "estimate_line", estimateLineId: "line-1", resourceId: "resource-1" }] });
  await assert.rejects(adapter.confirmExtraction({ draftId: "draft-1", expectedVersion: 1, idempotencyKey: "confirm-quantified", fieldConfirmations: [], invoice: { invoiceDate: "2026-08-10", vendorName: "فروشنده", resourceId: "target-1", totalIRR: "5000" } }), (error) => error.code === "EXTRACTION_QUANTIFIED_LINE_DATA_MISSING");
});

test("lists progress snapshots with a single request and no per-snapshot feed fan-out", async () => {
  const calls = [];
  const client = {
    async request(path) {
      calls.push(path);
      if (path.endsWith("/progress-snapshots")) {
        return [
          { progressSnapshotId: "snapshot-old", reportingDate: "2026-07-02", status: "superseded" },
          { progressSnapshotId: "snapshot-new", reportingDate: "2026-08-02", status: "ready" },
        ];
      }
      throw new Error(`unexpected request: ${path}`);
    },
  };

  const snapshots = await createApiProgressAdapter(context, client).getSnapshots();

  assert.deepEqual(calls, ["/api/projects/project-1/finance/progress-snapshots"], "one list request, never one feed per snapshot");
  assert.deepEqual(snapshots.map((snapshot) => snapshot.progressSnapshotId), ["snapshot-new", "snapshot-old"], "newest reporting date first");
  assert.ok(snapshots.every((snapshot) => !("assignmentCount" in snapshot)), "the list response carries no assignment count");
});

test("lets backend own the computed progress baseline", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); if (path.endsWith("/estimate-lines")) return [{ id: "line-1", assignmentExternalId: "asg-1" }]; if (path.includes("/feed")) return { snapshot: {}, assignments: [{ assignmentExternalId: "asg-1", actualQuantity: "12.5", manualOverride: null }] }; if (path.includes("/progress-override")) return { computedValue: "12.5", overrideValue: "14" }; throw new Error(path); } };
  await createApiProgressAdapter(context, client).createOverride({ progressSnapshotId: "snapshot-1", assignmentExternalId: "asg-1", overrideValue: "14", reason: "صورت‌جلسه" });
  const request = calls.find((call) => call.path.includes("/progress-override"));
  assert.deepEqual(JSON.parse(request.options.body), { progressSnapshotId: "snapshot-1", overrideValue: "14", reason: "صورت‌جلسه" });
});

test("carries the Backend's canEdit verdict instead of dropping it", async () => {
  // FinanceSettingsResponse ships canEdit so the UI does not reimplement the
  // role policy and then offer a form the PATCH refuses.
  const settings = { id: "settings-1", projectId: "project-1", grossBuiltArea: "4250.0000", currency: "IRR", revision: 1, effectiveFrom: "2026-06-01", reason: "ثبت اولیه", createdBy: "user-1", createdAt: "2026-06-01T09:00:00Z", canEdit: false };
  const client = { async request(path) { return path.endsWith("/settings/revisions") ? [] : settings; } };
  const result = await createApiSettingsAdapter(context, client).getSettings();
  assert.equal(result.canEdit, false, "a closed verdict must survive the mapping");
});

test("a Backend that says nothing about canEdit leaves the decision open", async () => {
  const settings = { id: "settings-1", projectId: "project-1", grossBuiltArea: "4250.0000", currency: "IRR", revision: 1, effectiveFrom: "2026-06-01", reason: "ثبت اولیه", createdBy: "user-1", createdAt: "2026-06-01T09:00:00Z" };
  const client = { async request(path) { return path.endsWith("/settings/revisions") ? [] : settings; } };
  const result = await createApiSettingsAdapter(context, client).getSettings();
  assert.equal(result.canEdit, null, "null is not false: it means nobody answered, so the host permission decides");
});

test("an invoice target carries the stage its activity belongs to", async () => {
  /* The picker groups by stage, and the stage is never stored -- it is read from the
     estimate line's own activity every time. So the adapter has to carry it through, and
     the stage is the FIRST segment of the activity's code: «۳.۲.۱» belongs to stage «۳»,
     which is the level the report draws. */
  const client = { async request(path) {
    if (path.endsWith("/resources")) return [{ id: "resource-1", type: "material", code: "R1", title: "میلگرد", baseUnit: "kg" }];
    if (path.endsWith("/estimate-lines")) return [{ id: "line-1", resourceId: "resource-1", activityExternalId: "3.2.1", activityTitle: "آرماتوربندی", wbsCode: "3.2.1" }];
    if (path.includes("/activities?")) return { items: [{ wbsCode: "3", title: "سفت‌کاری" }, { wbsCode: "3.2", title: "نباید برداشته شود" }], page: 1, pageSize: 200, totalItems: 2, totalPages: 1 };
    throw new Error(path);
  } };
  const [target] = await createApiInvoicesAdapter(context, client).getInvoiceTargets();
  assert.equal(target.wbsCode, "3.2.1");
  assert.equal(target.stageCode, "3");
  assert.equal(target.stageTitle, "سفت‌کاری", "the stage name comes from the catalogue row whose code has no dot");
  assert.equal(target.label, "آرماتوربندی · میلگرد", "the activity's name, not its numbering");
});

test("a stage catalogue that will not load costs a label, never the invoice", async () => {
  /* Somebody is standing there with a delivery note. Refusing to open the form because a
     NAME could not be fetched would stop them recording real money; the picker still
     groups correctly and simply shows the stage by number. */
  const client = { async request(path) {
    if (path.endsWith("/resources")) return [];
    if (path.endsWith("/estimate-lines")) return [{ id: "line-1", resourceId: "resource-1", activityExternalId: "5.1", wbsCode: "5.1" }];
    if (path.includes("/activities?")) throw new Error("catalogue unavailable");
    throw new Error(path);
  } };
  const [target] = await createApiInvoicesAdapter(context, client).getInvoiceTargets();
  assert.equal(target.stageCode, "5");
  assert.equal(target.stageTitle, null);
});
