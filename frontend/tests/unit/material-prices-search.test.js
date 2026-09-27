import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { renderMaterialPrices, foldSearchText } =
  await import("../../src/features/prices/material-prices-section.js");

/* TWO SEARCHES ON THE DAILY-PRICES PAGE, asked for 2026-09-27: one over the category
 * chips, on the page; one over product names, at the service. */

const CATEGORIES = [
  { category: "brick", label: "آجر", activeCount: 210, itemCount: 210, inactiveCount: 0 },
  { category: "rebar", label: "میلگرد", activeCount: 312, itemCount: 312, inactiveCount: 0 },
  { category: "ibeam", label: "تیرآهن", activeCount: 89, itemCount: 89, inactiveCount: 0 },
  { category: "profile", label: "پروفیل / قوطی", activeCount: 36, itemCount: 36, inactiveCount: 0 },
  { category: "واتر استاپ", label: "واتر استاپ", activeCount: 1, itemCount: 1, inactiveCount: 0 },
];

function row(over = {}) {
  return { providerItemId: "i1", externalId: "R1", name: "میلگرد ۱۴", category: "rebar",
           currentPriceIRR: "913600", status: "ready", statusLabel: "آماده", active: true, specs: {}, ...over };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 5));
const type = (input, value) => { input.value = value; input.dispatch("input"); };

test("the chip search hides chips whose label does not match, overflow included, and says how many", () => {
  const section = renderMaterialPrices([row()], { categories: CATEGORIES, onSelectCategory: () => {} });
  const box = section.querySelector("[name=categorySearch]");
  assert.ok(box, "a category search box");
  type(box, "واتر");
  const chips = [...section.querySelectorAll(".material-prices__chip")];
  const visible = chips.filter((chip) => !chip.hidden).map((chip) => chip.dataset.category);
  assert.deepEqual(visible, ["واتر استاپ"], "only the matching chip, even though it lives in the overflow menu");
  assert.equal(section.querySelector(".material-prices__more").open, true, "the overflow opens to show it");
  assert.match(section.querySelector(".material-prices__search-note").textContent, /دسته پنهان شد/);
  type(box, "");
  assert.ok(chips.every((chip) => !chip.hidden), "clearing the box brings every chip back");
  assert.equal(section.querySelector(".material-prices__search-note").textContent, "");
});

test("the chip search folds case, spaces and keyboard", () => {
  assert.equal(foldSearchText("پروفیل / قوطی"), "پروفیل/قوطی");
  assert.equal(foldSearchText("ميلگرد"), "میلگرد", "Arabic ya is Persian ye");
  const section = renderMaterialPrices([row()], { categories: CATEGORIES, onSelectCategory: () => {} });
  type(section.querySelector("[name=categorySearch]"), "ميل گرد");
  const visible = [...section.querySelectorAll(".material-prices__chip")].filter((c) => !c.hidden);
  assert.deepEqual(visible.map((c) => c.dataset.category), ["rebar"]);
});

test("the product search asks the page after a pause, once per distinct text, and on Enter at once", async () => {
  const asked = [];
  const section = renderMaterialPrices([row()], {
    categories: CATEGORIES, onSelectCategory: () => {},
    onSearchProduct: (value) => asked.push(value), searchDebounceMs: 1,
  });
  const box = section.querySelector("[name=productSearch]");
  type(box, "میل");
  type(box, "میلگرد ۱۴");
  assert.deepEqual(asked, [], "nothing is sent while typing");
  await settle();
  assert.deepEqual(asked, ["میلگرد ۱۴"], "one request, for the final text");
  type(box, "میلگرد ۱۴ ");
  await settle();
  assert.deepEqual(asked, ["میلگرد ۱۴"], "trailing space is not a new search");
  box.value = "آجر";
  /* The shim fires listeners with `{target}` only, so Enter is sent by hand. */
  box.listeners.get("keydown").forEach((handler) => handler({ key: "Enter", preventDefault() {} }));
  assert.deepEqual(asked, ["میلگرد ۱۴", "آجر"], "Enter does not wait");
});

test("the product box shows the query the page handed back, so it survives a re-render", () => {
  const section = renderMaterialPrices([row()], {
    categories: CATEGORIES, onSelectCategory: () => {}, onSearchProduct: () => {}, productQuery: "تیرآهن ۱۸",
  });
  assert.equal(section.querySelector("[name=productSearch]").value, "تیرآهن ۱۸");
});

test("without a product handler there is no product box, and the chip bar is untouched", () => {
  const section = renderMaterialPrices([row()], { categories: CATEGORIES, onSelectCategory: () => {} });
  assert.equal(section.querySelector("[name=productSearch]"), null);
  const labels = [...section.querySelector(".material-prices__filters").children].map((n) => n.textContent);
  assert.equal(labels[0], "همه");
});
