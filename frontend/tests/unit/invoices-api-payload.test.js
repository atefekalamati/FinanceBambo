import test from "node:test";
import assert from "node:assert/strict";
import { createApiInvoicesAdapter } from "../../src/adapters/api/invoices-api-adapter.js";

/**
 * What the browser actually puts on the wire.
 *
 * The endpoint answers 422 with `{"field": "invoiceNumber", "message": "Extra inputs are
 * not permitted"}` -- it refuses the field rather than accepting and ignoring it, because
 * the number is allocated per project when the invoice is written. So a payload carrying
 * one makes manual invoice creation impossible from the browser, which is what was
 * shipped. These assert the payload, not the page, because the payload is the thing the
 * service refused.
 */

const context = { organizationId: "org-1", projectId: "project-1" };

function recordingClient(answer) {
  return {
    sent: [],
    async request(path, options) {
      this.sent.push({ path, body: options?.body ? JSON.parse(options.body) : null,
                       method: options?.method ?? "GET" });
      if (path.endsWith("/resources")) return [];
      if (path.endsWith("/estimate-lines")) return [];
      return answer;
    },
  };
}

const answer = {
  id: "invoice-1", invoiceSeq: 42, invoiceNumber: "042", invoiceDate: "2026-08-09",
  vendorName: "فروشنده", description: null, source: "manual", status: "draft",
  discountIrr: "0", taxIrr: "0", shippingIrr: "0", otherCostsIrr: "0",
  finalAmountIrr: "1000", idempotencyKey: "k", version: 1,
  submittedBy: "00000000-0000-4000-8000-000000000001", createdAt: "2026-08-09T00:00:00Z",
  lines: [],
};

const header = { invoiceDate: "2026-08-09", vendorName: "فروشنده", description: "" };
const adjustments = { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" };

test("the create payload carries no invoice number", async () => {
  const client = recordingClient(answer);
  await createApiInvoicesAdapter(context, client).createDraft({
    header, lines: [], adjustments, idempotencyKey: "k-1" });
  const post = client.sent.find((call) => call.method === "POST");
  assert.ok(post, "no create was sent");
  assert.ok(!("invoiceNumber" in post.body),
    "sending invoiceNumber is the 422 this test exists to prevent");
  assert.equal(post.body.vendorName, "فروشنده", "the rest of the header is still sent");
});

test("the corrective payload carries no invoice number either", async () => {
  const client = recordingClient(answer);
  await createApiInvoicesAdapter(context, client).createCorrective({
    originalInvoiceId: "invoice-0", header, lines: [], adjustments,
    financialEffectSign: -1, reason: "اصلاح", idempotencyKey: "k-2" });
  const post = client.sent.find((call) => call.method === "POST");
  assert.ok(!("invoiceNumber" in post.body));
  assert.equal(post.body.source, "corrective");
  assert.equal(post.body.financialEffectSign, -1);
});

test("both forms of the assigned number reach the page", async () => {
  // The padded string is what a reader sees; the integer is what a client sorts on. The
  // service sends both and the adapter must not drop either.
  const client = recordingClient(answer);
  const created = await createApiInvoicesAdapter(context, client).createDraft({
    header, lines: [], adjustments, idempotencyKey: "k-3" });
  assert.equal(created.invoiceNumber, "042");
  assert.equal(created.invoiceSeq, 42);
});

test("an older answer without invoiceSeq still maps, with the sequence absent", async () => {
  const client = recordingClient({ ...answer, invoiceSeq: undefined });
  const created = await createApiInvoicesAdapter(context, client).createDraft({
    header, lines: [], adjustments, idempotencyKey: "k-4" });
  assert.equal(created.invoiceNumber, "042");
  assert.equal(created.invoiceSeq, null, "absent is null, never zero");
});
