import test from "node:test";
import assert from "node:assert/strict";
import { renderDetail } from "../../src/features/invoices/invoices-page.js";
import { reviewCard } from "../../src/features/ai-review/ai-review-page.js";

/**
 * A control an account may not use stays on the screen, switched off, with a
 * line saying why.
 *
 * The alternative this replaces was to draw nothing. An invoice sitting at «در
 * انتظار تأیید» with no button at all reads as a page that failed, not as a
 * document waiting on somebody else — and the reader's next move is to ask a
 * colleague who sees a different screen. Reading the register and recording
 * into it are separate grants, so the register opens for anyone who may read
 * the figures and the refusal is drawn where the action would have been.
 */
class RenderNode {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attributes = {}; this.disabled = false;
    this.style = { setProperty() {} };
    this.dataset = {};
    const names = new Set();
    this.classList = { add: (...values) => values.forEach((value) => names.add(value)),
                       remove: (...values) => values.forEach((value) => names.delete(value)),
                       contains: (value) => names.has(value), toggle() {} };
  }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return (this.value ?? "") + this.children.map((child) => child.textContent).join(" "); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener() { this.listened = true; }
  append(...children) { this.children.push(...children); }
  // Enough of a tree to satisfy the shared table, which walks its own head.
  querySelectorAll(selector) {
    const tag = selector.replace(/[^a-z]/gi, "");
    return [this, ...this.children.flatMap((child) => [...child.querySelectorAll(selector)])]
      .filter((node) => node !== this && node.tag === tag);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  get className() { return this.attributes.class ?? ""; }
  set className(value) { this.attributes.class = value; }
}

function withDocument(run) {
  const previous = globalThis.document;
  globalThis.document = {
    createElement: (tag) => new RenderNode(tag),
    createElementNS: (ns, tag) => new RenderNode(tag),
    createTextNode: (text) => Object.assign(new RenderNode("text"), { textContent: text }),
    createDocumentFragment: () => new RenderNode("fragment"),
  };
  try { return run(); } finally {
    if (previous === undefined) delete globalThis.document; else globalThis.document = previous;
  }
}

const flatten = (node) => [node, ...node.children.flatMap(flatten)];
/* Only the controls that act on the document. The dialog also carries the
   shared table, which brings buttons of its own for columns and search — those
   read the invoice and are nobody's decision to make. */
const buttons = (node) => flatten(node)
  .filter((child) => child.className.includes("invoice-detail-actions"))
  .flatMap((actions) => flatten(actions).filter((child) => child.tag === "button"));
const text = (node) => node.textContent;

const INVOICE = Object.freeze({
  invoiceNumber: "F-1", vendorName: "فروشنده", invoiceDate: "2026-06-01",
  submittedBy: "u-1", source: "manual", lines: [],
  rawLinesTotalIRR: "0", discountIRR: "0", taxIRR: "0", shippingIRR: "0",
  otherCostsIRR: "0", finalAmountIRR: "1000",
});
const options = (canEdit) => ({
  canEdit, project: { name: "پ", code: "c" },
  onSubmit() {}, onConfirm() {}, onVoid() {}, onCorrective() {},
});

test("every decision an invoice is waiting on is shown, whoever is reading", () => withDocument(() => {
  for (const invoiceStatus of ["draft", "awaitingConfirmation", "confirmed"]) {
    const granted = renderDetail({ ...INVOICE, invoiceStatus }, options(true));
    const refused = renderDetail({ ...INVOICE, invoiceStatus }, options(false));
    assert.ok(buttons(granted).length > 0, `${invoiceStatus} offers nothing to an account that may act`);
    assert.deepEqual(
      buttons(refused).map((button) => button.textContent),
      buttons(granted).map((button) => button.textContent),
      `${invoiceStatus} hides its actions instead of switching them off`,
    );
    assert.ok(buttons(refused).every((button) => button.disabled),
      `${invoiceStatus} left a control live for an account that may not use it`);
    assert.ok(buttons(granted).every((button) => !button.disabled),
      `${invoiceStatus} switched a control off for an account that may use it`);
    assert.match(text(refused), /نیازمند مجوز «مدیریت فاکتورها» است/,
      `${invoiceStatus} refuses without saying why`);
    assert.doesNotMatch(text(granted), /نیازمند مجوز/,
      `${invoiceStatus} tells an account that may act that it may not`);
  }
}));

/**
 * Decided by the product owner on 2026-09-12, after the service had already
 * decided it: who may confirm is «مدیریت فاکتورها» and nothing else.
 *
 * The page used to require that the confirmer be the submitter. It was the last
 * place that rule survived -- the service dropped it from its guard and from the
 * confirming UPDATE's WHERE clause -- so the button was refusing a request the
 * API would have accepted. It also inverted what the queue is for: raising and
 * approving are meant to be two people, and this made them one. The case it
 * broke is the ordinary one -- a رییس سازمان approving what a کارشناس sent up.
 */
test("confirming is a permission, not a question of who filed the invoice", () => withDocument(() => {
  const status = "awaitingConfirmation";
  const submitted = { ...INVOICE, invoiceStatus: status, submittedBy: "u-1" };

  // Someone else's invoice, and the grant is held: the button works.
  const reviewer = renderDetail(submitted, options(true));
  assert.match(text(reviewer), /تأیید نهایی فاکتور/);
  assert.doesNotMatch(text(reviewer), /فقط ثبت‌کننده مجاز است/,
    "the submitter rule came back");
  assert.ok(buttons(reviewer).every((button) => !button.disabled),
    "an account holding the grant was refused an invoice it did not file");

  // Without the grant it is off, and the notice says which grant -- the one
  // refusal that is about this account rather than about this invoice.
  const noGrant = renderDetail(submitted, options(false));
  assert.match(text(noGrant), /تأیید نهایی فاکتور/);
  assert.ok(buttons(noGrant).every((button) => button.disabled));
  assert.match(text(noGrant), /نیازمند مجوز «مدیریت فاکتورها» است/);
}));

test("the page reads nothing about who is signed in", () => withDocument(() => {
  // The identity of the reader decided the confirm button until this change, and
  // the option carrying it is gone. A render that still depended on it would now
  // be comparing against undefined and silently disabling the button for
  // everyone, so this asserts the dependency is actually gone rather than
  // defaulted: no reader identity is passed here at all.
  const node = renderDetail({ ...INVOICE, invoiceStatus: "awaitingConfirmation", submittedBy: "u-9" },
    options(true));
  assert.ok(buttons(node).every((button) => !button.disabled));
}));


/**
 * The original invoice image or voice file is the one thing on the review card
 * that is not extracted data, and the service refuses it to an account without
 * the invoice grant. Asking anyway would draw a broken image where the document
 * should be, which reads as a failed upload rather than as a refusal.
 */
const DRAFT = Object.freeze({
  draftId: "d-1", reviewStatus: "awaitingReview", version: 1, fields: [],
  file: { fileId: "f-1", originalNameSafe: "invoice.png", logicalType: "invoice_image" },
});

test("the original document is never requested without the grant", () => withDocument(() => {
  const asked = [];
  const adapter = { getFileContentUrl: (fileId) => { asked.push(fileId); return `/api/files/${fileId}/content`; } };
  const options = (canEdit) => ({ draft: DRAFT, targets: [], adapter, canEdit, onChanged() {}, root: new RenderNode("div") });

  const refused = reviewCard(options(false));
  assert.deepEqual(asked, [], "the card asked the service for a file this account may not have");
  assert.match(refused.textContent, /نمایش فایل اصلی نیازمند مجوز «مدیریت فاکتورها» است/);
  assert.equal(flatten(refused).filter((node) => node.tag === "img").length, 0,
    "a broken image was drawn where the refusal belongs");

  const granted = reviewCard(options(true));
  assert.deepEqual(asked, ["f-1"], "the card did not fetch the document for an account that may see it");
  assert.equal(flatten(granted).filter((node) => node.tag === "img").length, 1);
  assert.doesNotMatch(granted.textContent, /نیازمند مجوز/);
}));
