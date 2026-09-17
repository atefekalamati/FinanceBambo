import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { renderDetail, editableLines } = await import("../../src/features/invoices/invoices-page.js");

/* An invoice nobody has confirmed is a draft of a claim about money, and a draft nobody
 * may correct is not a draft.
 *
 * Both statuses before `confirmed` are open. «در انتظار تأیید» is precisely where somebody
 * reads an invoice closely enough to find the mistake, and a review that cannot lead to a
 * change is a queue rather than a review. Once confirmed the document is immutable and the
 * corrective workflow is the only honest route, so the button is withheld — not disabled,
 * which would promise a door that is not there.
 */

function invoice(overrides = {}) {
  return {
    invoiceId: "invoice-1", invoiceNumber: "001", invoiceSeq: 1,
    invoiceDate: "2026-09-10", vendorName: "فروشندهٔ نمونه", description: "تحویل اول",
    source: "manual", invoiceStatus: "draft", version: 3,
    discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0",
    rawLinesTotalIRR: "1000", finalAmountIRR: "1000",
    financialEffectSign: 1, originalInvoiceId: null, idempotencyKey: "key-1",
    submittedBy: "user-1", confirmedBy: null, confirmedAt: null, createdAt: "2026-09-10T08:00:00Z",
    lines: [{
      invoiceLineId: "invoice-1-1", targetType: "estimate_line", targetLabel: "آرماتوربندی · میلگرد",
      estimateLineId: "line-1", resourceId: "resource-1",
      quantity: "12.0000", unit: "kg", unitPriceIRR: "80000",
      lineAmountIRR: "960000", rawAmountIRR: "960000", description: "",
    }],
    ...overrides,
  };
}

function detail(inv, { canEdit = true, onEdit = () => {} } = {}) {
  return renderDetail(inv, {
    canEdit, project: { name: "پروژه", code: "P1" },
    onSubmit: () => {}, onConfirm: () => {}, onVoid: () => {}, onCorrective: () => {}, onEdit,
  });
}

function editButton(dialog) {
  return [...dialog.querySelectorAll("button")].find((b) => b.dataset?.action === "edit-invoice") ?? null;
}

test("the way back in sits beside the way to paper", () => {
  /* Asked for by position, not only by existence: a reader who has just printed an invoice
     and spotted the error looks where their hand already is. */
  const dialog = detail(invoice());
  const edit = editButton(dialog);
  assert.ok(edit, "a draft must offer an edit");
  const row = edit.parentNode;
  const labels = [...row.children].map((child) => child.textContent.trim());
  assert.ok(labels.includes("چاپ فاکتور") && labels.includes("ویرایش فاکتور"),
            `the edit belongs in the row that holds the print, found: ${labels.join(" | ")}`);
});

test("an invoice waiting for confirmation is still editable", () => {
  /* The status this is most for. Somebody is reading it to decide whether to confirm; when
     they find the mistake, the answer must not be "raise a corrective document". */
  assert.ok(editButton(detail(invoice({ invoiceStatus: "awaitingConfirmation" }))));
});

test("a confirmed invoice offers no edit at all", () => {
  for (const status of ["confirmed", "voided", "corrected"]) {
    assert.equal(editButton(detail(invoice({ invoiceStatus: status }))), null,
                 `«${status}» is locked, and a button there would promise a door that is not there`);
  }
});

test("a reader who may not write is offered nothing to press", () => {
  assert.equal(editButton(detail(invoice(), { canEdit: false })), null);
});

test("pressing it hands over the invoice being read, not its number", () => {
  /* The wizard opens ON this document — it needs the version to write against and the
     lines to fill the form, so the whole invoice travels. */
  let handed = null;
  const dialog = detail(invoice(), { onEdit: (inv) => { handed = inv; } });
  editButton(dialog).click();
  assert.equal(handed?.invoiceId, "invoice-1");
  assert.equal(handed?.version, 3, "the version the person was looking at is what a save must pin to");
  assert.equal(handed?.lines.length, 1);
});

test("a host that passes no edit handler renders exactly as before", () => {
  /* The parameter is optional on purpose: `renderDetail` is exported and the ai-review
     surface renders it too. A missing handler must not produce a button that does nothing. */
  const dialog = renderDetail(invoice(), {
    canEdit: true, project: { name: "پروژه", code: "P1" },
    onSubmit: () => {}, onConfirm: () => {}, onVoid: () => {}, onCorrective: () => {},
  });
  assert.equal(editButton(dialog), null);
});

const TARGETS = Object.freeze([
  { targetId: "t-rebar", targetType: "estimate_line", label: "آرماتوربندی · میلگرد",
    unit: "kg", estimateLineId: "line-1", resourceId: "resource-rebar" },
  { targetId: "t-permit", targetType: "general_cost", label: "هزینه مجوز",
    unit: null, estimateLineId: null, resourceId: "resource-permit" },
]);

test("a saved line finds its way back by identifier, never by label", () => {
  /* The label is built from whatever the cost item is called TODAY. Matching on the words
     would re-point a line at a different item the first time somebody renames one, and the
     invoice would move money without anybody touching it. */
  const [line] = editableLines(invoice(), TARGETS);
  assert.equal(line.targetId, "t-rebar");
  assert.equal(line.quantity, "12.0000");
  assert.equal(line.unitPriceIRR, "80000");
});

test("the raw amount goes back in the box, not the line's final amount", () => {
  /* `lineAmountIRR` is the line AFTER the header's discount and tax were spread across it.
     Prefilling with it would fold this invoice's tax into the typed figure — and fold it in
     again on the next save. */
  const general = invoice({ lines: [{
    invoiceLineId: "invoice-1-1", targetType: "general_cost", targetLabel: "هزینه مجوز",
    estimateLineId: null, resourceId: "resource-permit",
    quantity: null, unit: null, unitPriceIRR: null,
    lineAmountIRR: "1100000", rawAmountIRR: "1000000", description: "",
  }] });
  const [line] = editableLines(general, TARGETS);
  assert.equal(line.lineAmountIRR, "1000000");
});

test("a line that names nothing is dropped, not matched to whatever came first", () => {
  /* Comparing two absent identifiers is true, so a line with no `resourceId` would bind to
     the first general-cost item in the list — an edit re-pointing money at something nobody
     chose. Dropping it leaves a count somebody can notice. */
  const nameless = invoice({ lines: [{
    invoiceLineId: "invoice-1-1", targetType: "general_cost", targetLabel: "؟",
    estimateLineId: null, resourceId: null,
    quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: "5", rawAmountIRR: "5", description: "",
  }] });
  assert.deepEqual(editableLines(nameless, TARGETS), []);
});

test("a line whose cost item no longer exists is dropped rather than guessed at", () => {
  const orphan = invoice({ lines: [{
    invoiceLineId: "invoice-1-1", targetType: "estimate_line", targetLabel: "حذف‌شده",
    estimateLineId: "line-deleted", resourceId: "resource-gone",
    quantity: "1", unit: "kg", unitPriceIRR: "1", lineAmountIRR: "1", rawAmountIRR: "1", description: "",
  }] });
  assert.deepEqual(editableLines(orphan, TARGETS), []);
});
