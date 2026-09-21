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

function recordingAdapter({ approveFails = false, existing = [] } = {}) {
  const calls = [];
  return {
    calls,
    /* Asked for each direction separately, because the endpoint filters the unit pair
       exactly and a rule answering this crossing may be stored the other way round. */
    async conversionRules({ fromUnit, toUnit }) {
      calls.push(["list", fromUnit, toUnit]);
      return { items: existing.filter((rule) => rule.fromUnit === fromUnit
                                             && rule.toUnit === toUnit) };
    },
    async createConversionRule(payload) {
      calls.push(["create", payload]);
      return { id: "rule-1", status: "draft" };
    },
    async supersedeConversionRule(ruleId, payload) {
      calls.push(["supersede", ruleId, payload]);
      return { id: ruleId, status: "superseded" };
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
  const ui = { dialog };
  const directions = [...root.querySelectorAll('input[type="radio"]')];
  return Object.assign(ui, {
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
    existing: root.querySelector(".conversion-rule-dialog__existing"),
    replacing: root.querySelector(".conversion-rule-dialog__replacing"),
    effect: root.querySelector(".conversion-rule-dialog__effect"),
    feedback: root.querySelector(".form-feedback"),
  });
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

/* WHAT ALREADY ANSWERS THIS CROSSING, AND WHAT PRESSING SAVE WILL DO TO IT.
 *
 * A person who cannot see the rule that already exists writes a second one. Either the
 * database refuses it — the partial unique index permits one approved, open rule per scope
 * and unit pair — or, in the opposite direction, the service refuses it, because 22 and
 * 0.05 are not each other's inverse and two live answers to one question is worse than
 * none. Both refusals arrive at the end of a form somebody has already filled in.
 *
 * So the rules are read when the dialog opens, and the one occupying the chosen scope
 * turns the save button into a replacement.
 */

const ORG_RULE = Object.freeze({
  id: "rule-org", scopeType: "organization", fromUnit: "kg", toUnit: "each",
  factorValue: "22", status: "approved", version: 3, effectiveTo: null,
});

test("the rules already written for this crossing are read and shown", async () => {
  const adapter = recordingAdapter({ existing: [ORG_RULE] });
  const ui = open(PRODUCT_DEPENDENT, adapter);
  await ui.dialog.loadExisting();

  assert.deepEqual(adapter.calls.map((c) => c.slice(0, 3)),
                   [["list", "each", "kg"], ["list", "kg", "each"]],
                   "both spellings, because a rule may be stored the other way round");
  const shown = ui.existing.textContent;
  assert.match(shown, /۱ کیلوگرم = ۲۲ عدد/);
  assert.match(shown, /کل سازمان/);
  assert.match(shown, /در حال اعمال/);
});

test("with nothing written, it says so rather than showing an empty box", async () => {
  const ui = open(PRODUCT_DEPENDENT, recordingAdapter({ existing: [] }));
  await ui.dialog.loadExisting();
  assert.match(ui.existing.textContent, /هیچ قانونی برای این عبور ثبت نشده/);
});

test("a host without the settings endpoint says that, not «nothing exists»", async () => {
  /* The two are different facts and lead to opposite actions. */
  const ui = open(PRODUCT_DEPENDENT, { async createConversionRule() {},
                                       async approveConversionRule() {} });
  await ui.dialog.loadExisting();
  assert.match(ui.existing.textContent, /در دسترس نیست/);
});

test("the scope that already has a rule turns save into a replacement", async () => {
  const ui = open(PRODUCT_DEPENDENT, recordingAdapter({ existing: [ORG_RULE] }));
  await ui.dialog.loadExisting();

  assert.equal(ui.replacing.hidden, true, "no scope is occupied until one is chosen");
  assert.match(ui.save.textContent, /ثبت و اعمال/);

  ui.scope.value = "organization";
  ui.scope.dispatch("change");
  assert.equal(ui.replacing.hidden, false);
  assert.match(ui.replacing.textContent, /۱ کیلوگرم = ۲۲ عدد/);
  assert.match(ui.replacing.textContent, /نسخهٔ ۳/);
  assert.match(ui.save.textContent, /جایگزینی قانون/,
               "the button must say what pressing it will do to the rule in force");

  ui.scope.value = "project";
  ui.scope.dispatch("change");
  assert.equal(ui.replacing.hidden, true, "another scope is another slot, and it is empty");
  assert.match(ui.save.textContent, /ثبت و اعمال/);
});

test("replacing writes, closes the old one, and only then puts the new one in force", async () => {
  /* THE ORDER IS THE SAFETY. The database permits one approved, open rule per scope and
     unit pair, so approving before closing is refused outright; and closing before the
     replacement exists would leave the crossing unanswered if the write then failed. */
  const adapter = recordingAdapter({ existing: [ORG_RULE] });
  const ui = open(PRODUCT_DEPENDENT, adapter);
  await ui.dialog.loadExisting();
  fill(ui, { scope: "organization", direction: "reverse", factor: "24" });
  ui.acknowledge.checked = true;
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const order = adapter.calls.map((c) => c[0]).filter((name) => name !== "list");
  assert.deepEqual(order, ["create", "supersede", "approve"]);
  const payload = adapter.calls.find((c) => c[0] === "create")[1];
  assert.equal(payload.supersedesRuleId, "rule-org",
               "the new rule has to name the one it replaces, or the chain is unreadable");
  assert.equal(payload.fromUnit, "kg");
  assert.equal(payload.toUnit, "each");
  assert.equal(adapter.calls.find((c) => c[0] === "supersede")[1], "rule-org");
});

test("writing into an empty scope closes nothing", async () => {
  const adapter = recordingAdapter({ existing: [ORG_RULE] });
  const ui = open(PRODUCT_DEPENDENT, adapter);
  await ui.dialog.loadExisting();
  fill(ui, { scope: "project", direction: "forward", factor: "22" });
  ui.acknowledge.checked = true;
  ui.save.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const order = adapter.calls.map((c) => c[0]).filter((name) => name !== "list");
  assert.deepEqual(order, ["create", "approve"]);
  assert.equal(adapter.calls.find((c) => c[0] === "create")[1].supersedesRuleId, undefined);
});

/* WHAT THE RULE DOES TO THE PRICE, BEFORE IT IS SAVED.
 *
 * The units can be right and the factor can be right and the rule still be backwards. The
 * resulting price is the only place that shows, and it is the number the person came here
 * to produce.
 */

const PRICED = Object.freeze({
  ...CONTEXT, fromUnit: "kg", toUnit: "branch",
  sourcePriceIRR: "932000", quantity: "10",
});

test("the converted price is shown, worked the way the server works it", () => {
  const ui = open(PRICED, recordingAdapter());
  choose(ui, "reverse");                       // «۱ شاخه چند کیلوگرم است؟»
  ui.factor.value = "22";
  ui.factor.dispatch("input");
  const shown = ui.effect.textContent;
  assert.match(shown, /۲٬۰۵۰٬۴۰۰/, `932000 × 22 rials is 2,050,400 toman; got: ${shown}`);
  assert.match(shown, /۲۰٬۵۰۴٬۰۰۰/, "and the row's cost at a quantity of ten");
});

test("the other direction gives the other number, in the same place", () => {
  const ui = open(PRICED, recordingAdapter());
  choose(ui, "forward");                       // «۱ کیلوگرم چند شاخه است؟»
  ui.factor.value = "22";
  ui.factor.dispatch("input");
  assert.match(ui.effect.textContent, /۴٬۲۳۶/,
               "932000 ÷ 22 rials is about 4,236 toman — the same inputs, a price 484 "
               + "times apart, which is exactly why this is on screen");
});

test("with no sheet price it says why there is no number, and shows none", () => {
  const ui = open({ ...PRICED, sourcePriceIRR: null }, recordingAdapter());
  choose(ui, "reverse");
  ui.factor.value = "22";
  ui.factor.dispatch("input");
  assert.equal(ui.effect.textContent, "");
  const notes = [...ui.root.querySelectorAll("p")].map((p) => p.textContent).join(" | ");
  assert.match(notes, /قیمت روزی برای این محصول ثبت نشده/);
});

test("a quantity nobody knows produces no row cost, and no zero", () => {
  const ui = open({ ...PRICED, quantity: null }, recordingAdapter());
  choose(ui, "reverse");
  ui.factor.value = "22";
  ui.factor.dispatch("input");
  assert.match(ui.effect.textContent, /۲٬۰۵۰٬۴۰۰/);
  assert.doesNotMatch(ui.effect.textContent, /هزینهٔ این ردیف/);
});

test("a scope holding two live rules closes both, and says so before it does", async () => {
  /* The state the live project is actually in. Closing one and approving beside the other
     is refused by the partial unique index — at the end of a form somebody already filled
     in, with a constraint name for a message. */
  const both = [
    { id: "a1", scopeType: "organization", fromUnit: "kg", toUnit: "each",
      factorValue: "0.045", status: "approved", version: 1, effectiveTo: null },
    { id: "a2", scopeType: "organization", fromUnit: "each", toUnit: "kg",
      factorValue: "22", status: "approved", version: 2, effectiveTo: null },
  ];
  const adapter = recordingAdapter({ existing: both });
  const ui = open(PRODUCT_DEPENDENT, adapter);
  await ui.dialog.loadExisting();
  ui.scope.value = "organization";
  ui.scope.dispatch("change");

  assert.match(ui.replacing.textContent, /۲ قانون فعال دارد/);
  assert.match(ui.replacing.textContent, /۱ کیلوگرم = ۰٫۰۴۵ عدد/);
  assert.match(ui.replacing.textContent, /۱ عدد = ۲۲ کیلوگرم/);

  fill(ui, { scope: "organization", direction: "reverse", factor: "24" });
  ui.acknowledge.checked = true;
  ui.save.click();
  for (let tick = 0; tick < 6; tick += 1) await new Promise((r) => setTimeout(r, 0));

  const order = adapter.calls.map((c) => c[0]).filter((name) => name !== "list");
  assert.deepEqual(order, ["create", "supersede", "supersede", "approve"],
                   "both have to be closed before the replacement is put in force");
  /* Sorted: which of two equally-live rules is closed first is not a fact worth pinning,
     and the list arrives in whatever order the two direction queries answered. */
  assert.deepEqual(adapter.calls.filter((c) => c[0] === "supersede").map((c) => c[1]).sort(),
                   ["a1", "a2"]);
});
