import test from "node:test";
import assert from "node:assert/strict";

import { createApiInvoicesAdapter } from "../../src/adapters/api/invoices-api-adapter.js";
import { createApiAttachmentsAdapter } from "../../src/adapters/api/attachments-api-adapter.js";
import { createMockInvoicesAdapter } from "../../src/adapters/mock/invoices-adapter.js";
import { validateInvoiceHeader } from "../../src/features/invoices/invoices-validation.js";

/**
 * The number belongs to the project, and the service allocates it inside the
 * transaction that writes the invoice.
 *
 * These lock the client's half of that: it sends no number at all. The request
 * models forbid unknown fields, so a payload that still carries `invoiceNumber`
 * is not quietly ignored -- it is a 422, and it would take out invoice creation
 * on every path at once. That failure appears only against the real service, so
 * it is asserted here on the payload rather than left to a live call to find.
 */

const context = { projectId: "p-1", organizationId: "o-1", userId: "u-1", permissionCodes: ["finance.edit", "finance.manage_invoice"] };

const RESPONSE = {
  id: "i-1", invoiceSeq: 7, invoiceNumber: "007", invoiceDate: "2026-08-10",
  vendorName: "فروشنده", description: null, source: "manual", status: "draft",
  discountIrr: "0", taxIrr: "0", shippingIrr: "0", otherCostsIrr: "0",
  finalAmountIrr: "1000", financialEffectSign: 1, originalInvoiceId: null,
  idempotencyKey: "key", version: 1, submittedBy: "u-1", confirmedBy: null,
  confirmedAt: null, createdAt: "2026-08-10T08:00:00Z",
  lines: [{ estimateLineId: null, resourceId: "resource-general", quantity: null, unit: null, unitPriceIrr: null, rawAmountIrr: "1000", finalLineAmountIrr: "1000", description: null }],
};

function recordingClient(calls) {
  return {
    async request(path, options) {
      calls.push({ path, options });
      if (path.endsWith("/resources")) return [{ id: "resource-general", type: "general_cost", code: "GEN", title: "مجوز", baseUnit: null }];
      if (path.endsWith("/estimate-lines")) return [];
      if (path.includes("/extractions/")) return { draftId: "draft-1" };
      return RESPONSE;
    },
  };
}

const bodyOf = (calls, ending) => JSON.parse(calls.find((call) => call.path.endsWith(ending) && call.options?.method === "POST").options.body);
const header = { invoiceDate: "2026-08-10", vendorName: "فروشنده", description: "" };
const lines = (targetId) => [{ targetId, targetType: "general_cost", lineAmountIRR: "1000", description: "" }];
const adjustments = { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" };

test("the manual draft asks for no number", async () => {
  const calls = [];
  const adapter = createApiInvoicesAdapter(context, recordingClient(calls));
  const targets = await adapter.getInvoiceTargets();
  await adapter.createDraft({ header, lines: lines(targets[0].targetId), adjustments, duplicateOverrideReason: null, idempotencyKey: "k-1" });
  assert.ok(!("invoiceNumber" in bodyOf(calls, "/invoices")), "the create payload still carries invoiceNumber");
});

test("the corrective document asks for no number either", async () => {
  const calls = [];
  const adapter = createApiInvoicesAdapter(context, recordingClient(calls));
  const targets = await adapter.getInvoiceTargets();
  await adapter.createCorrective({ originalInvoiceId: "i-0", header, lines: lines(targets[0].targetId), adjustments, financialEffectSign: -1, reason: "اصلاح مبلغ", idempotencyKey: "k-2" });
  assert.ok(!("invoiceNumber" in bodyOf(calls, "/corrective")), "the corrective payload still carries invoiceNumber");
});

test("a confirmed extraction sends the supplier's fields, not a number for this project", async () => {
  const calls = [];
  const adapter = createApiAttachmentsAdapter(context, recordingClient(calls), { getInvoiceTargets: async () => [{ targetId: "target-1", targetType: "general_cost", label: "مجوز", unit: null }] });
  await adapter.confirmExtraction({
    draftId: "draft-1", expectedVersion: 2, idempotencyKey: "k-3", fieldConfirmations: [],
    // What the extractor read off the paper travels in, and must not travel out.
    invoice: { invoiceNumber: "INV-77/A", invoiceDate: "2026-08-10", vendorName: "فروشنده", resourceId: "target-1", totalIRR: "5000" },
  });
  const body = bodyOf(calls, "/confirm");
  // Named rather than searched for: if the request stops nesting the invoice, this
  // must fail loudly instead of passing because it looked somewhere empty.
  assert.ok(body.invoice && typeof body.invoice === "object", "the confirm request no longer nests an invoice");
  assert.ok(!("invoiceNumber" in body.invoice), "the reviewed payload still carries invoiceNumber");
  assert.equal(body.invoice.vendorName, "فروشنده", "the supplier's own fields still travel");
});

test("both forms of the number come back from the service, neither is invented here", async () => {
  const calls = [];
  const adapter = createApiInvoicesAdapter(context, recordingClient(calls));
  const invoice = await adapter.getInvoice("i-1");
  assert.equal(invoice.invoiceSeq, 7);
  assert.equal(invoice.invoiceNumber, "007");
});

test("the header no longer has a number to require", () => {
  const result = validateInvoiceHeader({ invoiceDate: "2026-08-10", vendorName: "فروشنده", description: "" });
  assert.equal(result.valid, true);
  assert.ok(!("invoiceNumber" in result.errors));
  assert.ok(!("invoiceNumber" in result.values), "a number in `values` goes straight back into the payload");
});

test("the preview allocates one number per invoice, on every path, in order", async () => {
  const adapter = createMockInvoicesAdapter({ ...context });
  const seeded = await adapter.getInvoices({ pageSize: 200 });
  const highest = Math.max(...seeded.items.map((item) => item.invoiceSeq));

  const targets = await adapter.getInvoiceTargets();
  const draft = await adapter.createDraft({ header, lines: lines(targets[0].targetId), adjustments, duplicateOverrideReason: null, idempotencyKey: "seq-1" });
  assert.equal(draft.invoiceSeq, highest + 1);
  assert.equal(draft.invoiceNumber, String(highest + 1).padStart(3, "0"));

  // The reversal used to be handed the number of the invoice it cancels, so one
  // number named two documents of opposite sign. It takes its own now.
  const confirmed = seeded.items.find((item) => item.invoiceStatus === "confirmed");
  const reversal = await adapter.voidInvoice({ invoiceId: confirmed.invoiceId, expectedVersion: confirmed.version, idempotencyKey: "seq-2", reason: "ابطال برای آزمون" });
  assert.equal(reversal.invoiceSeq, highest + 2);
  assert.notEqual(reversal.invoiceSeq, confirmed.invoiceSeq);
});

test("the number is written for a reader, and padding is a floor rather than a ceiling", async () => {
  const adapter = createMockInvoicesAdapter({ ...context }, { initialState: "empty" });
  const targets = await adapter.getInvoiceTargets();
  const first = await adapter.createDraft({ header, lines: lines(targets[0].targetId), adjustments, duplicateOverrideReason: null, idempotencyKey: "pad-1" });
  assert.equal(first.invoiceSeq, 1);
  assert.equal(first.invoiceNumber, "001", "a project's first invoice is 001");
});
