import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { createManualMarketPriceDialog } =
  await import("../../src/features/prices/manual-market-price-dialog.js");

/* A price for something the worksheet will never carry.
 *
 * It becomes a listing in the same table the sheet's rows live in, under the same chips.
 * Two things about that are worth pinning: the category is not optional — a price filed
 * under no chip is reachable only by scrolling the whole sheet — and a chip that has to be
 * made is made BEFORE the price, because the service refuses a price whose category does
 * not exist.
 */

const CATEGORIES = Object.freeze([
  { category: "rebar", label: "میلگرد", itemCount: 622, declared: false, scopeLevel: null },
  { category: "pipe", label: "لوله", itemCount: 992, declared: false, scopeLevel: null },
  { category: "scaffold", label: "داربست", itemCount: 0, declared: true, scopeLevel: "organization" },
]);

function recordingAdapter({ categoryFails = false, priceFails = false } = {}) {
  const calls = [];
  return {
    calls,
    async createCategory(payload) {
      calls.push(["category", payload]);
      if (categoryFails) throw new Error("این دسته از قبل وجود دارد.");
      return { ...payload, declared: true, itemCount: 0 };
    },
    async createManualPrice(payload) {
      calls.push(["price", payload]);
      if (priceFails) throw new Error("ثبت قیمت رد شد.");
      return { providerItemId: "item-9", ...payload, alreadyRecorded: false };
    },
  };
}

function open(adapter, onSaved = () => {}) {
  const dialog = createManualMarketPriceDialog({ categories: CATEGORIES, adapter, onSaved });
  const root = dialog.element;
  const selects = [...root.querySelectorAll("select")];
  return {
    root,
    product: root.querySelector('input[name="productName"]'),
    category: selects.find((s) => s.name === "category"),
    scope: selects.find((s) => s.name === "scopeLevel"),
    unit: selects.find((s) => s.name === "sourceUnit"),
    newCategory: root.querySelector('input[name="newCategory"]'),
    price: root.querySelector('input[name="price"]'),
    reason: root.querySelector("textarea"),
    save: [...root.querySelectorAll("button")].find((b) => b.textContent === "ثبت قیمت"),
    feedback: root.querySelector(".form-feedback"),
  };
}

function fill(ui, { product = "داربست فلزی", category = "rebar", unit = "kg",
                    price = "500000", reason = "استعلام تلفنی" } = {}) {
  ui.product.value = product;
  ui.category.value = category;
  ui.category.dispatch("change");
  ui.unit.value = unit;
  ui.price.value = price;
  ui.reason.value = reason;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("every chip the project can see is offered, plus a way to make one", () => {
  const ui = open(recordingAdapter());
  const values = [...ui.category.querySelectorAll("option")].map((o) => o.value);
  assert.deepEqual(values.slice(0, 4), ["", "rebar", "pipe", "scaffold"]);
  assert.equal(values[values.length - 1], "__new__", "the way out comes last");
  /* A chip somebody declared and a chip the sheet produced are one list. A person filtering
     by «داربست» should not have to know which kind it is. */
  assert.match([...ui.category.querySelectorAll("option")].find((o) => o.value === "scaffold").textContent, /داربست/);
});

test("the form for making a chip stays out of the way until it is asked for", () => {
  const ui = open(recordingAdapter());
  assert.equal(ui.newCategory.parentNode.parentNode.hidden, true);
  ui.category.value = "__new__";
  ui.category.dispatch("change");
  assert.equal(ui.newCategory.parentNode.parentNode.hidden, false);
});

test("a price under an existing chip is one call", async () => {
  const adapter = recordingAdapter();
  let saved = null;
  const ui = open(adapter, (result) => { saved = result; });
  fill(ui, { category: "rebar" });
  ui.save.click();
  await settle();
  await settle();

  assert.deepEqual(adapter.calls.map((c) => c[0]), ["price"], "no chip needed, no chip made");
  const [, payload] = adapter.calls[0];
  assert.equal(payload.category, "rebar");
  assert.equal(payload.sourceUnit, "kg");
  assert.equal(payload.priceIrr, "5000000", "تومان in the box, rials on the wire");
  assert.equal(saved?.providerItemId, "item-9");
});

test("a chip is made before the price it is for, and at the level chosen", async () => {
  /* Order matters and is not cosmetic: the service refuses a price whose category does not
     exist, so sending them the other way round would fail every time. */
  const adapter = recordingAdapter();
  const ui = open(adapter);
  fill(ui, { category: "__new__" });
  ui.newCategory.value = "داربست";
  ui.scope.value = "organization";
  ui.save.click();
  await settle();
  await settle();

  assert.deepEqual(adapter.calls.map((c) => c[0]), ["category", "price"]);
  assert.deepEqual(adapter.calls[0][1], { category: "داربست", label: "داربست", scopeLevel: "organization" });
  assert.equal(adapter.calls[1][1].category, "داربست", "the price lands under the chip just made");
});

test("a chip is never made twice when the price after it fails", async () => {
  /* The chip survives the failure, which is the right way round: an empty category is a
     word somebody can use or ignore, while a second attempt that re-declares it would hit
     the service's duplicate refusal and hide the real error. */
  const adapter = recordingAdapter({ priceFails: true });
  const ui = open(adapter);
  fill(ui, { category: "__new__" });
  ui.newCategory.value = "داربست";
  ui.save.click();
  await settle();
  await settle();

  assert.deepEqual(adapter.calls.map((c) => c[0]), ["category", "price"]);
  assert.match(ui.feedback.textContent, /ثبت قیمت رد شد/);

  ui.save.click();
  await settle();
  await settle();
  assert.deepEqual(adapter.calls.map((c) => c[0]), ["category", "price", "price"],
                   "the retry sends the price alone");
});

test("the category is required, and so is everything a price needs to mean anything", async () => {
  const adapter = recordingAdapter();
  const ui = open(adapter);

  fill(ui, { category: "" });
  ui.category.value = "";
  ui.save.click();
  await settle();
  assert.match(ui.feedback.textContent, /دسته/);
  assert.equal(adapter.calls.length, 0, "nothing is sent while the form is incomplete");

  fill(ui, { unit: "" });
  ui.unit.value = "";
  ui.save.click();
  await settle();
  assert.match(ui.feedback.textContent, /واحد/);

  fill(ui, { price: "0" });
  ui.save.click();
  await settle();
  assert.match(ui.feedback.textContent, /قیمت/);

  fill(ui, { reason: "" });
  ui.reason.value = "";
  ui.save.click();
  await settle();
  assert.match(ui.feedback.textContent, /دلیل/);
  assert.equal(adapter.calls.length, 0);
});

test("the service's own refusal is shown, not a guess about which call failed", async () => {
  const adapter = recordingAdapter({ categoryFails: true });
  const ui = open(adapter);
  fill(ui, { category: "__new__" });
  ui.newCategory.value = "میلگرد";
  ui.save.click();
  await settle();
  await settle();
  assert.match(ui.feedback.textContent, /از قبل وجود دارد/);
  assert.deepEqual(adapter.calls.map((c) => c[0]), ["category"], "the price is not sent after a refused chip");
});

test("opening with no chips in hand fetches them, rather than showing an empty menu", async () => {
  /* The page loads categories inside `loadMarketPrices`, which does not run until somebody
     presses «نمایش قیمت روز بازار». A person who opens this dialog first was shown an empty
     menu, and the only way forward was to invent a category that already existed. */
  const adapter = recordingAdapter();
  let asked = 0;
  adapter.listCategories = async () => { asked += 1; return CATEGORIES; };
  const dialog = createManualMarketPriceDialog({ categories: [], adapter, onSaved: () => {} });
  await settle();
  await settle();
  assert.equal(asked, 1);
  const values = [...dialog.element.querySelector("select").querySelectorAll("option")]
    .map((o) => o.value);
  assert.ok(values.includes("rebar") && values.includes("scaffold"));
});

test("chips already in hand are used as they are, with no second request", async () => {
  const adapter = recordingAdapter();
  let asked = 0;
  adapter.listCategories = async () => { asked += 1; return []; };
  createManualMarketPriceDialog({ categories: CATEGORIES, adapter, onSaved: () => {} });
  await settle();
  assert.equal(asked, 0, "the page already paid for this list");
});

test("a category list that will not load costs the list, never the dialog", async () => {
  /* «+ دستهٔ جدید» is still there, which is the one path that needs no list at all. */
  const adapter = recordingAdapter();
  adapter.listCategories = async () => { throw new Error("دسته‌ها دریافت نشد."); };
  const dialog = createManualMarketPriceDialog({ categories: [], adapter, onSaved: () => {} });
  await settle();
  await settle();
  assert.match(dialog.element.querySelector(".form-feedback").textContent, /دریافت نشد/);
  const values = [...dialog.element.querySelector("select").querySelectorAll("option")]
    .map((o) => o.value);
  assert.ok(values.includes("__new__"));
});

test("a level this account cannot grant is shown, disabled, with the reason", () => {
  /* Refused in the SERVICE and never at the route, so the request gives no warning: an
     account without the right would fill the whole form and be turned down on the last
     step. Disabled rather than removed — somebody who needs an organization-wide chip
     should see that the level exists and is somebody else's to grant, which is a different
     message from it not being a thing at all. */
  const dialog = createManualMarketPriceDialog({
    categories: CATEGORIES, adapter: recordingAdapter(), canManageSettings: false, onSaved: () => {} });
  const scope = [...dialog.element.querySelectorAll("select")].find((s) => s.name === "scopeLevel");
  const state = [...scope.querySelectorAll("option")]
    .map((o) => [o.value, Boolean(o.disabled)]);
  assert.deepEqual(state, [["project", false], ["organization", true], ["global", true]]);
  assert.match(scope.textContent, /مدیریت تنظیمات مالی/, "the reason travels with the refusal");
});

test("an account that may state things for the tenant is offered every level", () => {
  const dialog = createManualMarketPriceDialog({
    categories: CATEGORIES, adapter: recordingAdapter(), canManageSettings: true, onSaved: () => {} });
  const scope = [...dialog.element.querySelectorAll("select")].find((s) => s.name === "scopeLevel");
  assert.deepEqual([...scope.querySelectorAll("option")].map((o) => Boolean(o.disabled)),
                   [false, false, false]);
});
