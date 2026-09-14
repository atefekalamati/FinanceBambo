/**
 * The daily-price link, as the financial-items page presents it.
 *
 * Two things are being defended here and they pull against each other. The feature has to
 * be reachable from the row a person is reading -- so the row gains an action, a status and
 * a converted price. And ریز برآورد has to keep the shape people navigate it by -- so the
 * COLUMN LIST must not move. A column added "just for this" is how a table stops being
 * legible, and it would be invisible to every other test in this directory.
 *
 * The rest is about the answers that are not numbers. An item whose units cannot be crossed
 * shows «ناسازگار» and no figure; one nobody has mapped shows «نیازمند انتخاب نوع قلم». A
 * zero in either place would be a claim that the material is free.
 */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { installDom } from "../helpers/dom.js";

installDom();

const { statusChip, createPriceMappingPanel } =
  await import("../../src/features/financial-items/price-mapping-panel.js");

const PAGE_SOURCE = readFileSync(
  fileURLToPath(new URL("../../src/features/financial-items/financial-items-page.js", import.meta.url)),
  "utf8");
const ADAPTER_SOURCE = readFileSync(
  fileURLToPath(new URL("../../src/adapters/api/item-price-mappings-api-adapter.js", import.meta.url)),
  "utf8");

/* ------------------------------------------------------------------ table stability */

test("the ریز برآورد column list is unchanged by this feature", () => {
  // Read off the page's own definition. The feature is specified to work through the
  // existing unit, daily price, source and operations columns -- not by adding one.
  const block = PAGE_SOURCE.split("function estimateLineColumns()")[1].split("}\n")[0];
  const keys = [...block.matchAll(/\{\s*key:\s*"([a-zA-Z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(keys, [
    "identity", "unit", "originalQuantity", "revisedQuantity", "scheduleCost",
    "originalPrice", "currentPrice", "source", "actions",
  ], "the mapping workflow must reuse these columns, never add one");
});

test("the four columns the workflow feeds are the ones it is specified to feed", () => {
  for (const key of ["unit", "currentPrice", "source", "actions"]) {
    assert.ok(PAGE_SOURCE.includes(`key: "${key}"`), `${key} column is gone`);
  }
});

/* ---------------------------------------------------------------------- status chips */

test("every status renders its own Persian label", () => {
  const cases = [
    ["ready", "آماده"],
    ["needs_product", "نیازمند انتخاب نوع قلم"],
    ["needs_unit", "نیازمند انتخاب واحد"],
    ["needs_factor", "نیازمند ضریب تبدیل"],
    ["incompatible", "ناسازگار"],
    ["no_price", "بدون قیمت روز"],
  ];
  for (const [status, label] of cases) {
    const chip = statusChip(status, label);
    assert.equal(chip.textContent, label);
    assert.equal(chip.dataset.status, status);
  }
});

test("a ready chip is styled apart from one that is blocked", () => {
  // They mean different things to the reader: one is a figure to use, one is waiting on a
  // fact nobody has. Same class would make them the same thing on screen.
  assert.notEqual(statusChip("ready", "آماده").className,
                  statusChip("incompatible", "ناسازگار").className);
});

/* ----------------------------------------------------------------------- the panel */

function adapterStub(overrides = {}) {
  const calls = { candidates: [], preview: [], saved: [] };
  return {
    calls,
    async filters() {
      return {
        providers: [{ id: "p1", name: "AhanOnline" }],
        productTypes: [],
        categories: [{ category: "rebar", label: "میلگرد", itemCount: 311 }],
        units: [{ code: "kg", label: "کیلوگرم", dimension: "mass", dimensionLabel: "جرم" },
                { code: "ton", label: "تن", dimension: "mass", dimensionLabel: "جرم" }],
      };
    },
    async candidates(filters) {
      calls.candidates.push(filters);
      return {
        items: [{
          providerItemId: "item-1", externalId: "REBAR-1", name: "میلگرد آجدار ۱۰",
          categoryLabel: "میلگرد", providerName: "AhanOnline",
          sourceUnitCode: "kg", currentPriceIRR: "913600", active: true,
          specs: { "واحد - وزن": "کیلو" },
          specColumns: [{ key: "واحد - وزن", label: "واحد وزن", numeric: false }],
        }],
        page: 1, pageSize: 25, totalItems: 1,
      };
    },
    async preview(lineId, body) {
      calls.preview.push(body);
      return overrides.preview ?? {
        status: "ready", statusLabel: "آماده", reason: null,
        convertedDailyUnitPriceIRR: "913600", dailyItemCostIRR: "9136000",
        quantity: "10", selectedUnit: body.selectedUnit,
      };
    },
    async saveMapping(lineId, payload) {
      calls.saved.push(payload);
      return { id: "m1", version: 1, ...payload };
    },
    ...("filtersOverride" in overrides ? {} : {}),
  };
}

const LINE = { estimateLineId: "line-1", activityExternalId: "1.5.1" };
const RESOURCE = { title: "آرماتوربندی فونداسیون" };

/* The panel loads its filters and then its candidates, each behind its own await. A
   single macrotask turn lands in the middle of that chain, so this drains several --
   enough for the render to finish and few enough that a genuine hang still fails. */
async function settle(turns = 8) {
  for (let i = 0; i < turns; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

/** The panel's buttons, by their visible label. */
function button(panel, label) {
  return [...panel.querySelectorAll("button")].find((node) => node.textContent === label);
}

test("the panel lists candidates with the worksheet's own category columns", async () => {
  const adapter = adapterStub();
  const panel = createPriceMappingPanel({ line: LINE, resource: RESOURCE, adapter, canEdit: true });
  await settle();
  const text = panel.textContent;
  assert.ok(text.includes("میلگرد آجدار ۱۰"), "the product is listed");
  assert.ok(text.includes("AhanOnline"), "the provider is shown");
  assert.ok(text.includes("واحد وزن"), "the category's own spec column is shown");
});

test("the panel never fetches a spreadsheet", () => {
  // The sheet is read by a server-side import. A page that fetched it would leak its
  // address to every viewer and let whoever can edit it decide what Finance displays.
  const source = readFileSync(
    fileURLToPath(new URL("../../src/features/financial-items/price-mapping-panel.js", import.meta.url)),
    "utf8");
  for (const forbidden of ["docs.google.com", "sheets.googleapis", "spreadsheets"]) {
    assert.ok(!source.includes(forbidden), `${forbidden} must not appear`);
    assert.ok(!ADAPTER_SOURCE.includes(forbidden), `${forbidden} must not appear in the adapter`);
  }
});

test("the adapter talks only to the Finance API", () => {
  const paths = [...ADAPTER_SOURCE.matchAll(/client\.request\(\s*`([^`]+)`/g)].map((m) => m[1]);
  assert.ok(paths.length >= 6, "every endpoint should go through client.request");
  for (const path of paths) {
    assert.ok(path.startsWith("${base}"), `${path} must be under the finance base`);
  }
});

test("a viewer without finance.edit can look and cannot save", () => {
  const adapter = adapterStub();
  const panel = createPriceMappingPanel({ line: LINE, resource: RESOURCE, adapter, canEdit: false });
  const save = button(panel, "ثبت اتصال");
  assert.equal(save.disabled, true);
  assert.ok(panel.textContent.includes("finance.edit"), "it says which access is missing");
});

test("saving requires a product, a unit and a reason", async () => {
  const adapter = adapterStub();
  const panel = createPriceMappingPanel({ line: LINE, resource: RESOURCE, adapter, canEdit: true });
  await settle();
  const save = button(panel, "ثبت اتصال");
  save.click();
  await settle();
  assert.equal(adapter.calls.saved.length, 0, "nothing is saved without a choice");
});

test("choosing a product asks the server what it converts to, and saves what was shown", async () => {
  const adapter = adapterStub();
  const saved = [];
  const panel = createPriceMappingPanel({
    line: LINE, resource: RESOURCE, adapter, canEdit: true,
    onSaved: (row) => saved.push(row),
  });
  await settle();
  const pick = button(panel, "انتخاب");
  assert.ok(pick, "a candidate offers a choose button");
  pick.click();
  await settle();

  // The conversion is Decimal arithmetic on the server. Doing it here would be a second
  // implementation in floating point that disagrees in the last digits.
  assert.equal(adapter.calls.preview.length, 1);
  assert.equal(adapter.calls.preview[0].providerItemId, "item-1");
  assert.ok(panel.textContent.includes("آماده"), "the preview status is shown before saving");

  panel.querySelector("textarea").value = "میلگرد این ردیف از همین محصول است";
  const save = button(panel, "ثبت اتصال");
  save.click();
  await settle();
  assert.equal(adapter.calls.saved.length, 1);
  assert.deepEqual(adapter.calls.saved[0], {
    providerItemId: "item-1",
    selectedUnit: "kg",
    reason: "میلگرد این ردیف از همین محصول است",
  });
  assert.equal(saved.length, 1, "the page is told so it can refresh the table");
});

test("an unresolved preview shows the reason and no figure", async () => {
  const adapter = adapterStub({
    preview: {
      status: "needs_factor", statusLabel: "نیازمند ضریب تبدیل",
      reason: "ضریب تبدیل لازم است",
      convertedDailyUnitPriceIRR: null, dailyItemCostIRR: null, quantity: "10",
    },
  });
  const panel = createPriceMappingPanel({ line: LINE, resource: RESOURCE, adapter, canEdit: true });
  await settle();
  button(panel, "انتخاب").click();
  await settle();
  assert.ok(panel.textContent.includes("ضریب تبدیل لازم است"), "the reason is stated");
  assert.ok(panel.textContent.includes("نیازمند ضریب تبدیل"), "the status chip is shown");

  /* The unknown figures render as an em dash. Asserted on the figure cells themselves
     rather than by scanning the whole panel for a zero: the quantity «۱۰» contains the
     Persian zero, so a text search would fail on a correct render. */
  const figures = panel.querySelector(".price-mapping-panel__figures");
  const values = figures.children.filter((node) => node.tagName === "DD")
    .map((node) => node.textContent);
  assert.equal(values[1], "—", "the converted price is unknown, not zero");
  assert.equal(values[3], "—", "this line's daily cost is unknown, not zero");
});
