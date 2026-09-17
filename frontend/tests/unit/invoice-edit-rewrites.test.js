import test from "node:test";
import assert from "node:assert/strict";

import { createMockInvoicesAdapter } from "../../src/adapters/mock/invoices-adapter.js";

const context = Object.freeze({
  organizationId: "org-1", projectId: "p-1", userId: "user-1",
  permissionCodes: ["finance.view", "finance.edit"],
});

/* An edit corrects the document it opened. It does not raise a second one.
 *
 * The register is read as a history of what was bought; a typo answered with a corrective
 * document puts two rows there where one purchase happened, and every total downstream has
 * to know to net them. Before the confirmation locks it, there is nothing to net — the
 * invoice is simply rewritten.
 */

async function draftWithLines(adapter) {
  const targets = await adapter.getInvoiceTargets();
  const estimate = targets.find((t) => t.targetType === "estimate_line");
  const general = targets.find((t) => t.targetType === "general_cost");
  const lines = [
    { targetId: estimate.targetId, targetType: "estimate_line", targetLabel: estimate.label,
      quantity: "10.0000", unit: estimate.unit, unitPriceIRR: "100000", lineAmountIRR: "", description: "" },
    { targetId: general.targetId, targetType: "general_cost", targetLabel: general.label,
      quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: "500000", description: "" },
  ];
  const created = await adapter.createDraft({
    header: { invoiceDate: "2026-09-10", vendorName: "فروشندهٔ نمونه", description: "" },
    lines,
    adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
    duplicateOverrideReason: "",
    idempotencyKey: `key-${lines.length}-${estimate.targetId}`,
  });
  return { created, lines, estimate, general };
}

test("an edit rewrites the invoice, keeping its identity and its number", async () => {
  const adapter = createMockInvoicesAdapter(context, { initialState: "success" });
  const before = (await adapter.getInvoices({ pageSize: 200 })).totalItems;
  const { created, lines } = await draftWithLines(adapter);

  const edited = await adapter.updateInvoice({
    invoiceId: created.invoiceId,
    expectedVersion: created.version,
    header: { invoiceDate: "2026-09-12", vendorName: "فروشندهٔ اصلاح‌شده", description: "پس از بازبینی" },
    lines: [{ ...lines[0], quantity: "14.0000" }, lines[1]],
    adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
  });

  assert.equal(edited.invoiceId, created.invoiceId, "the same document");
  assert.equal(edited.invoiceNumber, created.invoiceNumber, "an edit does not take a new number");
  assert.equal(edited.vendorName, "فروشندهٔ اصلاح‌شده");
  assert.equal(edited.invoiceDate, "2026-09-12");
  assert.equal(edited.version, created.version + 1, "the version moves, so a stale save is refused");

  const after = (await adapter.getInvoices({ pageSize: 200 })).totalItems;
  assert.equal(after, before + 1, "one invoice was created and none was added by editing it");
});

test("changing a quantity changes what the invoice comes to", async () => {
  const adapter = createMockInvoicesAdapter(context, { initialState: "success" });
  const { created, lines } = await draftWithLines(adapter);
  // 10 × 100,000 + 500,000 = 1,500,000
  assert.equal(created.finalAmountIRR, "1500000");

  const edited = await adapter.updateInvoice({
    invoiceId: created.invoiceId, expectedVersion: created.version,
    header: { invoiceDate: "2026-09-10", vendorName: "فروشندهٔ نمونه", description: "" },
    lines: [{ ...lines[0], quantity: "14.0000" }, lines[1]],
    adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
  });
  // 14 × 100,000 + 500,000 = 1,900,000
  assert.equal(edited.finalAmountIRR, "1900000",
               "the whole document is recomputed, not one line patched in place");
});

test("an invoice waiting for confirmation can still be corrected", async () => {
  const adapter = createMockInvoicesAdapter(context, { initialState: "success" });
  const { created, lines } = await draftWithLines(adapter);
  const submitted = await adapter.submitDraft({
    invoiceId: created.invoiceId, expectedVersion: created.version });
  assert.equal(submitted.invoiceStatus, "awaitingConfirmation");

  const edited = await adapter.updateInvoice({
    invoiceId: created.invoiceId, expectedVersion: submitted.version,
    header: { invoiceDate: "2026-09-10", vendorName: "اصلاح در صف تأیید", description: "" },
    lines, adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
  });
  assert.equal(edited.vendorName, "اصلاح در صف تأیید");
  assert.equal(edited.invoiceStatus, "awaitingConfirmation", "correcting it does not send it back to the start");
});

test("a confirmed invoice refuses the edit and names the way that is open", async () => {
  const adapter = createMockInvoicesAdapter(context, { initialState: "success" });
  const { created, lines } = await draftWithLines(adapter);
  const submitted = await adapter.submitDraft({ invoiceId: created.invoiceId, expectedVersion: created.version });
  const confirmed = await adapter.confirmInvoice({
    invoiceId: created.invoiceId, expectedVersion: submitted.version, idempotencyKey: "confirm-1" });
  assert.equal(confirmed.invoiceStatus, "confirmed");

  await assert.rejects(() => adapter.updateInvoice({
    invoiceId: created.invoiceId, expectedVersion: confirmed.version,
    header: { invoiceDate: "2026-09-10", vendorName: "دیر شد", description: "" },
    lines, adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
  }), (error) => {
    assert.equal(error.status, 409);
    assert.match(error.message, /سند اصلاحی/, "the refusal must name the route that IS open");
    return true;
  });
});

test("a save against a version somebody has moved on is refused, not applied", async () => {
  /* Two people with the invoice open. One submits it; the other presses save on the copy
     they were reading. Overwriting would silently discard the first person's act. */
  const adapter = createMockInvoicesAdapter(context, { initialState: "success" });
  const { created, lines } = await draftWithLines(adapter);
  await adapter.submitDraft({ invoiceId: created.invoiceId, expectedVersion: created.version });

  await assert.rejects(() => adapter.updateInvoice({
    invoiceId: created.invoiceId,
    expectedVersion: created.version,        // the version the second reader still holds
    header: { invoiceDate: "2026-09-10", vendorName: "بازنویسی کور", description: "" },
    lines, adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
  }), (error) => {
    assert.equal(error.code, "STALE_VERSION");
    return true;
  });
});
