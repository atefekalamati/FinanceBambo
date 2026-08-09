import test from "node:test";
import assert from "node:assert/strict";
import { createMockInvoicesAdapter } from "../../src/adapters/mock/invoices-adapter.js";

const context = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "11111111-1111-4111-8111-111111111111",
  projectId: "sample_site_01",
};

test("lists invoices with default fifty-item pagination and project scope", async () => {
  const adapter = createMockInvoicesAdapter(context);
  const first = await adapter.getInvoices();
  const second = await adapter.getInvoices({ page: 2 });
  assert.equal(first.items.length, 50);
  assert.equal(first.pageSize, 50);
  assert.equal(first.totalItems, 53);
  assert.equal(first.totalPages, 2);
  assert.equal(second.items.length, 3);
  assert.ok(first.items.every((invoice) => invoice.organizationId === context.organizationId && invoice.projectId === context.projectId));
});

test("filters invoices by status, source, and Persian search text", async () => {
  const adapter = createMockInvoicesAdapter(context);
  const result = await adapter.getInvoices({ query: "مصالح پایدار", status: "awaitingConfirmation", source: "image" });
  assert.ok(result.totalItems > 0);
  assert.ok(result.items.every((invoice) => invoice.vendorName.includes("مصالح پایدار")));
  assert.ok(result.items.every((invoice) => invoice.invoiceStatus === "awaitingConfirmation" && invoice.source === "image"));
});

test("keeps invoice, file, and extraction lifecycle fields separate", async () => {
  const adapter = createMockInvoicesAdapter(context);
  const list = await adapter.getInvoices();
  const invoice = await adapter.getInvoice(list.items[0].invoiceId);
  assert.ok(["draft", "awaitingConfirmation", "confirmed", "voided", "corrected"].includes(invoice.invoiceStatus));
  assert.equal("processingStatus" in invoice, false);
  assert.equal("reviewStatus" in invoice, false);
  assert.ok(/^\d+$/.test(invoice.finalAmountIRR));
  assert.ok(invoice.lines.every((line) => /^\d+$/.test(line.lineAmountIRR)));
});

test("caps page size at two hundred and returns detached invoice details", async () => {
  const adapter = createMockInvoicesAdapter(context);
  const list = await adapter.getInvoices({ pageSize: 500 });
  assert.equal(list.pageSize, 200);
  const detail = await adapter.getInvoice(list.items[0].invoiceId);
  detail.vendorName = "تغییر آزمایشی";
  assert.notEqual((await adapter.getInvoice(detail.invoiceId)).vendorName, "تغییر آزمایشی");
});

test("supports empty, recoverable error, and not-found states", async () => {
  assert.equal((await createMockInvoicesAdapter(context, { initialState: "empty" }).getInvoices()).totalItems, 0);
  await assert.rejects(createMockInvoicesAdapter(context, { initialState: "error" }).getInvoices(), (error) => error.status === 503 && Boolean(error.requestId));
  await assert.rejects(createMockInvoicesAdapter(context).getInvoice("missing"), (error) => error.status === 404);
});

test("previews and creates a zero-effect manual invoice draft with exact IRR totals", async () => {
  const adapter = createMockInvoicesAdapter({ ...context, permissionCodes: ["finance.view", "finance.edit"] });
  const targets = await adapter.getInvoiceTargets();
  const lines = [
    { targetId: targets[0].targetId, targetType: "estimate_line", targetLabel: targets[0].label, quantity: "1.2500", unit: "kg", unitPriceIRR: "80001", lineAmountIRR: "", description: "" },
    { targetId: targets[2].targetId, targetType: "general_cost", targetLabel: targets[2].label, quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: "500000", description: "" },
  ];
  const adjustments = { discountIRR: "100", taxIRR: "200", shippingIRR: "300", otherCostsIRR: "400" };
  const header = { invoiceNumber: "ف-جدید", invoiceDate: "2026-08-09", vendorName: "فروشنده نمونه", description: "" };
  const preview = await adapter.previewDraft({ header, lines, adjustments });
  assert.equal(preview.lines[0].lineAmountIRR, "100001");
  assert.equal(preview.rawLinesTotalIRR, "600001");
  assert.equal(preview.finalAmountIRR, "600801");
  const draft = await adapter.createDraft({ header, lines, adjustments });
  assert.equal(draft.invoiceStatus, "draft");
  assert.equal(draft.source, "manual");
  assert.equal(draft.confirmedAt, null);
});

test("rejects draft creation without the coarse approved edit permission", async () => {
  const adapter = createMockInvoicesAdapter({ ...context, permissionCodes: ["finance.view"] });
  await assert.rejects(adapter.createDraft({ header: { invoiceNumber: "x", invoiceDate: "2026-08-09", vendorName: "v" }, lines: [{}], adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" } }), (error) => error.status === 403);
});

test("detects a similar invoice and requires an audited continuation reason", async () => {
  const adapter = createMockInvoicesAdapter({ ...context, permissionCodes: ["finance.view", "finance.edit"] });
  const header = { invoiceNumber: "ف-001", invoiceDate: "2026-07-01", vendorName: "فروشگاه ساختمانی بامبو نمونه", description: "" };
  const lines = [{ targetId: "general-permit", targetType: "general_cost", targetLabel: "هزینه مجوز نمونه", quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: "121750000", description: "" }];
  const adjustments = { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" };
  const preview = await adapter.previewDraft({ header, lines, adjustments });
  assert.equal(preview.duplicateMatches.length, 1);
  assert.equal(preview.duplicateMatches[0].invoiceId, "invoice-demo-001");
  await assert.rejects(adapter.createDraft({ header, lines, adjustments }), (error) => error.code === "INVOICE_DUPLICATE_REASON_REQUIRED");
  const draft = await adapter.createDraft({ header, lines, adjustments, duplicateOverrideReason: "خرید مستقل براساس حواله دوم" });
  assert.equal(draft.duplicateWarning, true);
  assert.equal(draft.duplicateOverrideReason, "خرید مستقل براساس حواله دوم");
  assert.deepEqual(draft.duplicateOfInvoiceIds, ["invoice-demo-001"]);
});
