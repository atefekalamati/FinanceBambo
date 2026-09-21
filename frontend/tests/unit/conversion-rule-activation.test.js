import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { installDom } from "../helpers/dom.js";

installDom();

const { createConversionRuleDialog } =
  await import("../../src/features/financial-items/conversion-rule-dialog.js");
const { factorSourceLabel } =
  await import("../../src/features/financial-items/financial-items-presentation.js");

test("conversion dialog is displayed only while open and removed after closing", () => {
  const css = readFileSync(new URL("../../src/features/financial-items/financial-items.css", import.meta.url), "utf8");
  assert.match(css, /\.conversion-rule-dialog\[open\]\s*\{[^}]*display:\s*grid/s);
  assert.doesNotMatch(css, /\.conversion-rule-dialog\s*\{[^}]*display:/s);

  const modal = createConversionRuleDialog({ context: { fromUnit: "kg", toUnit: "branch" }, adapter: recordingAdapter() });
  document.body.append(modal.element);
  const cancel = [...modal.element.querySelectorAll("button")].find((button) => button.textContent === "انصراف");
  assert.ok(cancel);
  cancel.click();
  modal.element.dispatch("close"); // The DOM stub does not dispatch native dialog events.
  assert.equal(modal.element.parentNode, null);
});

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
  const directions = [...root.querySelectorAll('input[type="radio"]')];
  return {
    root,
    scope: root.querySelector("select"),
    directions,
    forward: directions.find((input) => input.value === "forward"),
    reverse: directions.find((input) => input.value === "reverse"),
    factor: root.querySelector('input[name="factorValue"]'),
    reason: root.querySelector("textarea"),
    acknowledge: root.querySelector('input[name="productDependentAcknowledged"]'),
    save: [...root.querySelectorAll("button")].find((b) => /ثبت و اعمال|تأیید و اعمال/.test(b.textContent)),
    note: [...root.querySelectorAll("p")].find((p) => p.className === "table-note" && p.textContent.includes("پیش‌نویس")),
    sentence: root.querySelector(".conversion-rule-dialog__sentence"),
    feedback: root.querySelector(".form-feedback"),
  };
}

/** Picks a direction the way a person does: the browser checks it, then fires `change`. */
function choose(ui, which) {
  ui[which].checked = true;
  ui[which].dispatch("change");
}

function fill(ui, { scope = "project", factor = "22", reason = "وزن یک شاخه از برگهٔ فروشنده",
                    direction = "forward" } = {}) {
  ui.scope.value = scope;
  ui.scope.dispatch("change");   // the stub fires one listener type directly; see tests/helpers/dom.js
  if (direction) choose(ui, direction);
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

test("a scope that outlives this project is offered only to an account that may state one", () => {
  /* `finance.manage_settings` is checked in the service and never at a route, so the
     dialog cannot learn about it from a failed request. It has to be told before it offers
     the choice, or it offers one whose only possible answer is 403. */
  const denied = createConversionRuleDialog({
    context: PRODUCT_DEPENDENT, adapter: recordingAdapter(), canManageSettings: false, onSaved: () => {} });
  const scope = denied.element.querySelector("select");
  const state = Object.fromEntries([...scope.querySelectorAll("option")]
    .map((o) => [o.value, Boolean(o.disabled)]));
  assert.equal(state.provider_item, false);
  assert.equal(state.category, false);
  assert.equal(state.project, false);
  assert.equal(state.organization, true);
  assert.equal(state.global, true);
  assert.match(scope.textContent, /مدیریت تنظیمات مالی/);

  const allowed = createConversionRuleDialog({
    context: PRODUCT_DEPENDENT, adapter: recordingAdapter(), canManageSettings: true, onSaved: () => {} });
  assert.deepEqual([...allowed.element.querySelector("select").querySelectorAll("option")]
    .map((o) => Boolean(o.disabled)), [false, false, false, false, false, false]);
});

/* WHICH SIDE IS THE ONE.
 *
 * The pricing path asks kilogram->branch, because the price is per kilogram and the line
 * is measured in branches. Nobody knows that number. What a person knows is that a branch
 * weighs twenty-two kilograms, and forcing them to state the crossing in the direction the
 * resolver happens to ask in means typing 0.0454545… -- a number they cannot check against
 * the seller's sheet, rounded once and then rounded into every price the rule produces.
 *
 * So both questions are offered, the answer is stored exactly as it was said, and the
 * server reads the rule from either side.
 */

test("neither direction is preselected, and nothing can be typed until one is", () => {
  const ui = open(CONTEXT, recordingAdapter());
  assert.deepEqual(ui.directions.map((input) => Boolean(input.checked)), [false, false],
                   "a default would be silently wrong half the time");
  assert.equal(ui.factor.disabled, true,
               "a number typed before the question is picked is an answer to nothing");
  assert.match(ui.sentence.textContent, /کدام طرف را می‌دانید/);
});

test("the two questions name the two real units, one each way round", () => {
  const ui = open(PRODUCT_DEPENDENT, recordingAdapter());   // each -> kg
  const asked = ui.directions.map((input) => input.parentNode.textContent);
  assert.equal(asked.length, 2);
  assert.ok(asked.some((text) => /۱ عدد چند کیلوگرم است/.test(text)), asked.join(" | "));
  assert.ok(asked.some((text) => /۱ کیلوگرم چند عدد است/.test(text)), asked.join(" | "));
});

test("choosing a direction rewrites the sentence and opens the number", () => {
  const ui = open(PRODUCT_DEPENDENT, recordingAdapter());
  choose(ui, "reverse");
  assert.equal(ui.factor.disabled, false);
  ui.factor.value = "22";
  ui.factor.dispatch("input");
  /* The typed characters, echoed verbatim rather than prettified into Persian
     digits: the sentence exists to show what is about to be SENT. */
  assert.equal(ui.sentence.textContent, "۱ کیلوگرم = 22 عدد");

  choose(ui, "forward");
  ui.factor.dispatch("input");
  assert.equal(ui.sentence.textContent, "۱ عدد = 22 کیلوگرم",
               "the same number against the other question is a different claim, and the "
               + "sentence is the only place that difference is visible");
});

test("the reverse direction is sent as stated, with the units swapped and the number intact", async () => {
  /* Not inverted here. 1/22 is 0.045454545454… and any inversion this dialog performed
     would round it, put a number nobody can verify into the audit record, and then apply
     that rounding to every price. The server inverts at full precision when it resolves. */
  const adapter = recordingAdapter();
  const ui = open(PRODUCT_DEPENDENT, adapter);              // fromUnit each, toUnit kg
  fill(ui, { scope: "provider_item", direction: "reverse", factor: "22" });
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const payload = adapter.calls[0][1];
  assert.equal(payload.fromUnit, "kg");
  assert.equal(payload.toUnit, "each");
  assert.equal(payload.factorValue, "22");
});

test("the forward direction sends the row's own crossing, untouched", async () => {
  const adapter = recordingAdapter();
  const ui = open(PRODUCT_DEPENDENT, adapter);
  fill(ui, { scope: "provider_item", direction: "forward", factor: "22" });
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const payload = adapter.calls[0][1];
  assert.equal(payload.fromUnit, "each");
  assert.equal(payload.toUnit, "kg");
});

test("saving with no direction picked writes nothing and says what is missing", async () => {
  const adapter = recordingAdapter();
  const ui = open(PRODUCT_DEPENDENT, adapter);
  fill(ui, { scope: "provider_item", direction: null });
  ui.factor.disabled = false;   // a person cannot reach this; a stale DOM could
  ui.factor.value = "22";
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(adapter.calls, [], "a factor with no direction must not reach the server");
  assert.match(ui.feedback.textContent, /کدام طرف/);
});
