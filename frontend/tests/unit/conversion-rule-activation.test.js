import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { createConversionRuleDialog } =
  await import("../../src/features/financial-items/conversion-rule-dialog.js");
const { factorSourceLabel } =
  await import("../../src/features/financial-items/financial-items-presentation.js");

/* Writing a conversion rule has to end in a NUMBER CHANGING.
 *
 * A rule arrives as a draft, and both resolution queries filter `status='approved'` in
 * SQL — so a dialog that only created one would let somebody write «۱ شاخه = ۲۲ کیلوگرم»,
 * watch it save, and find the row still blocked. These tests are about that gap: the rule
 * is created AND put in force, the admission travels with it, and a half-finished attempt
 * is finished rather than duplicated.
 */

const CONTEXT = Object.freeze({
  fromUnit: "ton", toUnit: "kg",
  providerItemId: "item-1", providerId: "provider-1", category: "rebar",
  productName: "میلگرد ۱۶", providerName: "فولاد مبارکه", categoryLabel: "میلگرد",
});

/** A crossing the registry cannot make: a count against a mass. */
const PRODUCT_DEPENDENT = Object.freeze({ ...CONTEXT, fromUnit: "each", toUnit: "kg" });

function recordingAdapter({ approveFails = false } = {}) {
  const calls = [];
  return {
    calls,
    async createConversionRule(payload) {
      calls.push(["create", payload]);
      return { id: "rule-1", status: "draft" };
    },
    async approveConversionRule(ruleId, payload) {
      calls.push(["approve", ruleId, payload]);
      if (approveFails) throw new Error("تأیید انجام نشد");
      return { id: ruleId, status: "approved" };
    },
  };
}

function open(context, adapter, onSaved = () => {}) {
  const dialog = createConversionRuleDialog({ context, adapter, onSaved });
  const root = dialog.element;
  return {
    root,
    scope: root.querySelector("select"),
    factor: root.querySelector('input[name="factorValue"]'),
    reason: root.querySelector("textarea"),
    acknowledge: root.querySelector('input[name="productDependentAcknowledged"]'),
    save: [...root.querySelectorAll("button")].find((b) => /ثبت و اعمال|تأیید و اعمال/.test(b.textContent)),
    note: [...root.querySelectorAll("p")].find((p) => p.className === "table-note" && p.textContent.includes("پیش‌نویس")),
    feedback: root.querySelector(".form-feedback"),
  };
}

function fill(ui, { scope = "project", factor = "22", reason = "وزن یک شاخه از برگهٔ فروشنده" } = {}) {
  ui.scope.value = scope;
  ui.scope.dispatch("change");   // the stub fires one listener type directly; see tests/helpers/dom.js
  ui.factor.value = factor;
  ui.reason.value = reason;
}

test("the admission is offered only where there is something to admit", () => {
  /* tonne to kilogram is arithmetic — nobody's word is involved, and the server stores the
     flag as false however it arrives. A checkbox about responsibility, shown where none is
     being taken, teaches people to tick it without reading. */
  const arithmetic = open(CONTEXT, recordingAdapter());
  fill(arithmetic, { scope: "project" });
  assert.equal(arithmetic.acknowledge.parentNode.hidden, true);

  const weighing = open(PRODUCT_DEPENDENT, recordingAdapter());
  fill(weighing, { scope: "project" });
  assert.equal(weighing.acknowledge.parentNode.hidden, false,
               "«each» against «kg» is a weighing of one product and must say so");
});

test("at the narrowest scope even a weighing needs no admission", () => {
  /* A `provider_item` rule IS a statement about exactly the thing that was weighed. The
     server has always allowed it, and asking for an admission there would be asking
     somebody to take responsibility for saying what they measured. */
  const ui = open(PRODUCT_DEPENDENT, recordingAdapter());
  fill(ui, { scope: "provider_item" });
  assert.equal(ui.acknowledge.parentNode.hidden, true);
});

test("switching to a broader scope reveals it, and back again unticks it", () => {
  /* Unticked, not merely hidden. A hidden box that stays checked would send an admission
     nobody made on the next attempt. */
  const ui = open(PRODUCT_DEPENDENT, recordingAdapter());
  fill(ui, { scope: "project" });
  ui.acknowledge.checked = true;
  fill(ui, { scope: "provider_item" });
  assert.equal(ui.acknowledge.parentNode.hidden, true);
  assert.equal(ui.acknowledge.checked, false);
});

test("saving writes the rule AND puts it in force", async () => {
  const adapter = recordingAdapter();
  let saved = 0;
  const ui = open(PRODUCT_DEPENDENT, adapter, () => { saved += 1; });
  fill(ui, { scope: "project" });
  ui.acknowledge.checked = true;
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(adapter.calls.map((c) => c[0]), ["create", "approve"],
                   "a draft changes no number anywhere, so creating alone is not saving");
  assert.equal(adapter.calls[0][1].productDependentAcknowledged, true);
  assert.equal(adapter.calls[0][1].factorValue, "22");
  assert.equal(adapter.calls[1][1], "rule-1", "it approves the rule it just wrote");
  assert.equal(saved, 1, "the caller is told once, after the rule is actually in force");
});

test("an unticked box sends a false admission, not a missing one", async () => {
  /* The field is always sent. Omitting it would make «I did not admit this» and «this
     client is too old to know about admissions» the same message. */
  const adapter = recordingAdapter();
  const ui = open(PRODUCT_DEPENDENT, adapter);
  fill(ui, { scope: "project" });
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(adapter.calls[0][1].productDependentAcknowledged, false);
});

test("a rule that saved but did not take effect is finished, never written twice", async () => {
  /* Two identical rules differing only in which one is approved is a worse state than the
     draft being recovered from. The second press approves the rule that already exists. */
  const adapter = recordingAdapter({ approveFails: true });
  const ui = open(PRODUCT_DEPENDENT, adapter);
  fill(ui, { scope: "project" });
  ui.acknowledge.checked = true;
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(adapter.calls.map((c) => c[0]), ["create", "approve"]);
  assert.match(ui.feedback.textContent, /تأیید انجام نشد/);
  const note = [...ui.root.querySelectorAll("p")].find((p) => /پیش‌نویس/.test(p.textContent));
  assert.ok(note && !note.hidden, "the reader must be told a rule exists and is doing nothing");
  assert.match(ui.save.textContent, /تأیید و اعمال/,
               "the button must say what pressing it will do now");

  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(adapter.calls.map((c) => c[0]), ["create", "approve", "approve"],
                   "the second attempt must finish the first rule, not write another");
});

test("the factor's origin is named, and an origin nobody planned for is reported", () => {
  assert.equal(factorSourceLabel("provider_item"), "وزن‌کشی همین محصول");
  assert.equal(factorSourceLabel("conversion_rule"), "قانون تبدیل");
  assert.equal(factorSourceLabel("registry"), "تبدیل استاندارد واحد");
  assert.equal(factorSourceLabel(null), null, "nothing converted, nothing to say");
  /* Not swallowed. A row that quietly says nothing is how a reader concludes no conversion
     happened, which is a different fact from one this page has no word for yet. */
  assert.match(factorSourceLabel("density_table") ?? "", /density_table/);
});
