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
