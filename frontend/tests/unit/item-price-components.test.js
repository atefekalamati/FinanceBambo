/**
 * The materials an item consumes, as the financial-items page presents them.
 *
 * Two things are being defended here and they pull against each other. The feature has to
 * be reachable from the row a person is reading -- so the row gains an action, a status and
 * a total. And ریز برآورد has to keep the shape people navigate it by -- so the COLUMN LIST
 * must not move. A column added "just for this" is how a table stops being legible, and it
 * would be invisible to every other test in this directory.
 *
 * The rest is about the answers that are not numbers. A row nobody has started shows
 * «نیازمند افزودن مصالح»; a row where one of three materials has no price shows the total of
 * the other two AND says it is two of three. A zero in either place would be a claim that
 * the work is free, and a total shown without the count would be a partial sum wearing the
 * face of a finished one.
 *
 * THE WORKED EXAMPLE, throughout: «کانال‌کنی», 500 m³ of trenching, consuming
 *     rebar  80 kg per m³ at 1,014,600 rial/kg  -> 40,000 kg -> 40,584,000,000
 *     pipe   1,200 m in total at 50,000 rial/m  ->  1,200 m  ->     60,000,000
 *                                                               ----------------
 *                                                                40,644,000,000
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
const PANEL_SOURCE = readFileSync(
  fileURLToPath(new URL("../../src/features/financial-items/price-mapping-panel.js", import.meta.url)),
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
  ], "the materials workflow must reuse these columns, never add one");
});

test("the row's «قیمت روز» cell shows the TOTAL, not one material's price", () => {
  // A line priced from three materials has no single converted unit price, and showing
  // the first one would understate the row by however much the others come to.
  const cell = PAGE_SOURCE.split("function dailyPriceCell(")[1].split("\nfunction ")[0];
  assert.ok(cell.includes("priced.dailyItemCostIRR"), "the total is what the cell prints");
  assert.ok(!cell.includes("convertedDailyUnitPriceIRR"),
            "a per-unit price of one material must not stand in for the row");
});

test("an open panel survives the refresh that follows saving a material", () => {
  /* `loadPriceStatuses()` calls `paint()`, and `paint()` replaces the page's children --
     the open panel among them. Under the one-product workflow that was harmless because
     saving closed the panel; a line priced from a LIST is entered without closing, so the
     repaint took the panel out of the document after the first material and the next click
     landed on a row action. Caught in a real browser, pinned here. */
  const paint = PAGE_SOURCE.split("function paint()")[1].split("\n  }")[0];
  assert.ok(paint.includes("openPricePanel"), "paint() must put the open panel back");
  assert.ok(paint.includes("showAccessibleDialog"),
            "and re-show it: a dialog removed from the document leaves the top layer");
  assert.ok(PAGE_SOURCE.includes("openPricePanel = null"),
            "closing the panel must clear the reference, or a stale node is re-appended");
});

test("«منبع» names one material and counts several", () => {
  assert.ok(PAGE_SOURCE.includes("priced?.sourceSummary"),
            "several materials collapse to a summary rather than to the first name");
});

/* ---------------------------------------------------------------------- status chips */

test("every status renders its own Persian label", () => {
  const cases = [
    ["ready", "آماده"],
    ["needs_components", "نیازمند افزودن مصالح"],
    ["needs_usage_quantity", "نیازمند مقدار مصرف مصالح"],
    ["partially_unresolved", "بخشی از اجزای قیمت‌گذاری ناقص است"],
    ["needs_factor", "نیازمند ضریب تبدیل"],
    ["incompatible", "تبدیل واحد ناسازگار است"],
    ["no_price", "قیمت روز معتبر وجود ندارد"],
  ];
  for (const [status, label] of cases) {
    const chip = statusChip(status, label);
    assert.equal(chip.textContent, label);
    assert.equal(chip.dataset.status, status);
  }
});

test("ready, partial and blocked are three different things on screen", () => {
  // A partly-priced row is not an unstarted one and not a broken one. Same class for any
  // two of them would make them the same thing to a reader.
  const classes = ["ready", "partially_unresolved", "incompatible"]
    .map((status) => statusChip(status, "x").className);
  assert.equal(new Set(classes).size, 3);
});

/* ----------------------------------------------------------------------- the adapter */

test("neither the panel nor the adapter fetches a spreadsheet", () => {
  // The sheet is read by a server-side import. A page that fetched it would leak its
  // address to every viewer and let whoever can edit it decide what Finance displays.
  for (const forbidden of ["docs.google.com", "sheets.googleapis", "spreadsheets"]) {
    assert.ok(!PANEL_SOURCE.includes(forbidden), `${forbidden} must not appear in the panel`);
    assert.ok(!ADAPTER_SOURCE.includes(forbidden), `${forbidden} must not appear in the adapter`);
  }
});

test("the adapter talks only to the Finance API", () => {
  const paths = [...ADAPTER_SOURCE.matchAll(/client\.request\(\s*`([^`]+)`/g)].map((m) => m[1]);
  assert.ok(paths.length >= 8, "every endpoint should go through client.request");
  for (const path of paths) {
    assert.ok(path.startsWith("${base}") || path.startsWith("${line("),
              `${path} must be under the finance base`);
  }
});

test("no mock or sample data is compiled into either module", () => {
  for (const source of [PANEL_SOURCE, ADAPTER_SOURCE]) {
    for (const forbidden of ["mockData", "sampleData", "FAKE_", "fixtures"]) {
      assert.ok(!source.includes(forbidden), `${forbidden} must not appear`);
    }
  }
});

/* ------------------------------------------------------------------------- the panel */

const CANDIDATES = {
  rebar: {
    providerItemId: "item-rebar", externalId: "REBAR-1", name: "میلگرد آجدار ۱۰",
    category: "rebar", categoryLabel: "میلگرد", providerName: "AhanOnline",
    providerId: "p1", sourceUnitCode: "kg", currentPriceIRR: "1014600", active: true,
    specs: { "واحد - وزن": "کیلو" },
    specColumns: [{ key: "واحد - وزن", label: "واحد وزن", numeric: false }],
  },
  pipe: {
    providerItemId: "item-pipe", externalId: "PIPE-1", name: "لوله پلی اتیلن ۱۱۰",
    category: "pipe", categoryLabel: "لوله", providerName: "PipeCo", providerId: "p2",
    sourceUnitCode: "m", currentPriceIRR: "50000", active: true,
    specs: {}, specColumns: [],
  },
};

function component(over = {}) {
  return {
    componentId: "c-rebar", id: "v1", estimateLineId: "line-1",
    providerItemId: "item-rebar", status: "ready", statusLabel: "آماده", reason: null,
    reasonText: "بر اساس نقشهٔ اجرایی",
    convertedDailyUnitPriceIRR: "1014600", componentQuantity: "40000",
    componentDailyCostIRR: "40584000000", sourcePriceIRR: "1014600",
    selectedUnit: "kg", sourceUnit: "kg", usageMode: "per_msp_unit",
    usageQuantity: "80", usageUnit: "kg", productName: "میلگرد آجدار ۱۰",
    providerName: "AhanOnline", categoryLabel: "میلگرد", active: true, version: 1,
    specs: {}, specColumns: [], ...over,
  };
}

function adapterStub(overrides = {}) {
  const calls = { candidates: [], filters: [], previewComponent: [], previewTotal: [],
                  added: [], updated: [], deactivated: [] };
  let components = overrides.components ?? [];
  return {
    calls,
    get components() { return components; },
    async filters(params = {}) {
      calls.filters.push(params);
      return {
        categories: [{ category: "rebar", label: "میلگرد", itemCount: 311 },
                     { category: "pipe", label: "لوله", itemCount: 992 }],
        providers: params.category === "pipe"
          ? [{ id: "p2", name: "PipeCo" }]
          : [{ id: "p1", name: "AhanOnline" }, { id: "p2", name: "PipeCo" }],
        productTypes: params.providerId === "p1" ? ["A3"] : [],
        units: [{ code: "kg", label: "کیلوگرم", dimension: "mass", dimensionLabel: "جرم" },
                { code: "ton", label: "تن", dimension: "mass", dimensionLabel: "جرم" },
                { code: "m", label: "متر", dimension: "length", dimensionLabel: "طول" }],
        usageModes: [
          { value: "per_msp_unit", label: "به ازای هر واحد فعالیت",
            hint: "مقدار مصالح برای یک واحد از این قلم" },
          { value: "total_quantity", label: "مقدار کل برای این قلم",
            hint: "مقدار کل مصالح برای تمام این قلم" },
        ],
      };
    },
    async candidates(filters) {
      calls.candidates.push(filters);
      const items = filters.category === "pipe" ? [CANDIDATES.pipe] : [CANDIDATES.rebar];
      return { items, page: 1, pageSize: 25, totalItems: items.length };
    },
    async componentsFor() {
      return {
        line: { estimateLineId: "line-1", activityExternalId: "1.5.1", title: "کانال‌کنی",
                mspUnit: "m3", mspQuantity: "500", mspCostIRR: "120000000",
                originalUnitPriceIRR: "240000" },
        components,
        total: overrides.total ?? {
          estimateLineId: "line-1", status: "ready", statusLabel: "آماده", reason: null,
          dailyItemCostIRR: components.length ? "40584000000" : null,
          componentCount: components.length, readyComponentCount: components.length,
          unresolvedComponentCount: 0,
        },
      };
    },
    async previewComponent(lineId, draft) {
      calls.previewComponent.push(draft);
      return overrides.preview ?? component({
        componentId: null, id: null, reasonText: null,
        selectedUnit: draft.selectedUnit, usageMode: draft.usageMode,
        usageQuantity: draft.usageQuantity,
      });
    },
    async previewTotal(lineId, draft) {
      calls.previewTotal.push(draft);
      return {
        estimateLineId: lineId, status: "ready", statusLabel: "آماده", reason: null,
        dailyItemCostIRR: "40644000000", componentCount: 2, readyComponentCount: 2,
        unresolvedComponentCount: 0,
      };
    },
    async addComponent(lineId, payload) {
      calls.added.push(payload);
      components = [...components, component({ componentId: `c-${components.length}` })];
      return { id: "v1", componentId: "c-new", version: 1, ...payload };
    },
    async updateComponent(lineId, componentId, payload) {
      calls.updated.push({ componentId, ...payload });
      return { id: "v2", componentId, version: 2, ...payload };
    },
    async deactivateComponent(lineId, componentId, reason) {
      calls.deactivated.push({ componentId, reason });
      components = components.map((existing) =>
        existing.componentId === componentId ? { ...existing, active: false } : existing);
      return { id: "v2", componentId, version: 2, active: false, reason };
    },
  };
}

const LINE = { lineId: "line-1", activityExternalId: "1.5.1" };
const RESOURCE = { title: "کانال‌کنی" };

/* The panel loads its filters and then its components, each behind its own await, and the
   preview is two calls in parallel. A single macrotask turn lands in the middle of that
   chain, so this drains several -- enough for the render to finish and few enough that a
   genuine hang still fails. */
async function settle(turns = 10) {
  for (let i = 0; i < turns; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

function button(panel, label) {
  return [...panel.querySelectorAll("button")].find((node) => node.textContent === label);
}

function field(panel, name) {
  return panel.querySelector(`[name=${name}]`);
}

function open(adapter, { canEdit = true, onSaved } = {}) {
  return createPriceMappingPanel({ line: LINE, resource: RESOURCE, adapter, canEdit, onSaved });
}

test("the header states what the schedule says about the activity being priced", async () => {
  // «۸۰ کیلوگرم به ازای هر مترمکعب» means nothing until a reader can see the 500 m³.
  const panel = open(adapterStub());
  await settle();
  const text = panel.querySelector(".price-mapping-panel__head").textContent;
  assert.ok(text.includes("۵۰۰"), "the activity quantity is shown");
  assert.ok(text.includes("مترمکعب"), "in the activity's own unit");
});

test("a line with no materials says so instead of showing a zero", async () => {
  const panel = open(adapterStub());
  await settle();
  const list = panel.querySelector(".price-components__list");
  assert.ok(list.textContent.includes("هنوز مصالحی ثبت نشده"), "it says nobody has started");
  const total = panel.querySelector(".price-components__total");
  assert.ok(total.textContent.includes("—"), "the cost is unknown, not zero");
});

test("each material shows its own usage, quantity and cost", async () => {
  const panel = open(adapterStub({ components: [component()] }));
  await settle();
  const card = panel.querySelector(".price-component");
  const text = card.textContent;
  assert.ok(text.includes("میلگرد آجدار ۱۰"), "the product is named");
  assert.ok(text.includes("۸۰"), "the usage figure is shown");
  assert.ok(text.includes("به ازای هر واحد فعالیت"), "and what that figure means");
  assert.ok(text.includes("۴۰٬۰۰۰"), "the quantity it works out to is shown");
});

test("the author's own reason is kept beside the pricing reason", async () => {
  // Two different sentences: why this material is on the line, and why there is no number.
  const panel = open(adapterStub({
    components: [component({ status: "no_price", statusLabel: "قیمت روز معتبر وجود ندارد",
                             reason: "قیمت روز معتبر وجود ندارد",
                             componentDailyCostIRR: null })],
  }));
  await settle();
  const text = panel.querySelector(".price-component").textContent;
  assert.ok(text.includes("بر اساس نقشهٔ اجرایی"), "the author's justification survives");
  assert.ok(text.includes("قیمت روز معتبر وجود ندارد"), "and so does the pricing reason");
});

test("a partly priced row shows the total AND how much of the list it came from", async () => {
  const panel = open(adapterStub({
    components: [component()],
    total: {
      estimateLineId: "line-1", status: "partially_unresolved",
      statusLabel: "بخشی از اجزای قیمت‌گذاری ناقص است",
      reason: "بخشی از اجزای قیمت‌گذاری ناقص است: قیمت روز معتبر وجود ندارد",
      dailyItemCostIRR: "40584000000", componentCount: 3, readyComponentCount: 2,
      unresolvedComponentCount: 1,
    },
  }));
  await settle();
  const total = panel.querySelector(".price-components__total").textContent;
  assert.ok(total.includes("۴٬۰۵۸٬۴۰۰٬۰۰۰"), "the resolved total is shown in toman");
  assert.ok(total.includes("۲ از ۳"), "and so is how much of the list produced it");
});

/* --------------------------------------------------------------------- the cascade */

test("choosing a category narrows the providers and clears what it invalidates", async () => {
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();

  const category = field(panel, "category");
  const provider = field(panel, "providerId");
  provider.value = "p1";
  category.value = "pipe";
  category.dispatch("change");
  await settle();

  assert.deepEqual(adapter.calls.filters.at(-1), { category: "pipe", providerId: undefined },
                   "the narrowed category is sent and the stale provider is not");
  assert.equal(provider.value, "", "a provider chosen under another category does not survive");
  assert.equal(adapter.calls.candidates.at(-1).category, "pipe");
});

test("product types are asked for by category AND provider together", async () => {
  // A supplier who sells no brick must not offer a type that exists only on somebody
  // else's brick: the cascade would then yield an empty product list, which reads as a
  // broken page rather than as an empty category.
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();

  field(panel, "category").value = "rebar";
  field(panel, "providerId").value = "p1";
  field(panel, "providerId").dispatch("change");
  await settle();
  assert.deepEqual(adapter.calls.filters.at(-1), { category: "rebar", providerId: "p1" });
});

test("nothing is previewed until product, unit, mode and quantity are all answered", async () => {
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();

  button(panel, "انتخاب").click();
  await settle();
  assert.equal(adapter.calls.previewComponent.length, 0,
               "a product alone is not enough to price anything");

  field(panel, "usageMode").value = "per_msp_unit";
  field(panel, "usageMode").dispatch("change");
  await settle();
  assert.equal(adapter.calls.previewComponent.length, 0, "nor is a mode with no quantity");

  field(panel, "usageQuantity").value = "80";
  field(panel, "usageQuantity").dispatch("input");
  await settle();
  assert.equal(adapter.calls.previewComponent.length, 1, "now every answer is there");
  assert.deepEqual(adapter.calls.previewComponent[0], {
    providerItemId: "item-rebar", selectedUnit: "kg",
    usageMode: "per_msp_unit", usageQuantity: "80",
  });
});

test("the usage mode has no default, and choosing one explains what it means", async () => {
  // «۵۰۰» is either 500 per cubic metre or 500 altogether, and on a 500 m³ trench those
  // differ by a factor of 500. Picking one for the person is picking their answer.
  const panel = open(adapterStub());
  await settle();
  assert.equal(field(panel, "usageMode").value, "",
               "the option list itself preselects nothing");
  button(panel, "افزودن مصالح").click();
  await settle();
  assert.equal(field(panel, "usageMode").value, "", "and opening the form preselects nothing");

  field(panel, "usageMode").value = "total_quantity";
  field(panel, "usageMode").dispatch("change");
  await settle();
  assert.ok(panel.textContent.includes("مقدار کل مصالح برای تمام این قلم"),
            "the hint says which of the two readings was chosen");
});

test("the preview shows the material's cost and what the ROW will come to", async () => {
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();
  button(panel, "انتخاب").click();
  field(panel, "usageMode").value = "per_msp_unit";
  field(panel, "usageQuantity").value = "80";
  field(panel, "usageQuantity").dispatch("input");
  await settle();

  const preview = panel.querySelector(".price-component-form__preview").textContent;
  assert.ok(preview.includes("۴٬۰۵۸٬۴۰۰٬۰۰۰"), "this material's daily cost");
  assert.ok(preview.includes("۴٬۰۶۴٬۴۰۰٬۰۰۰"), "and the row's total once it is saved");
  assert.equal(adapter.calls.previewTotal.length, adapter.calls.previewComponent.length);
});

test("an unresolved preview states the reason and shows no figure", async () => {
  const adapter = adapterStub({
    preview: {
      status: "needs_factor", statusLabel: "نیازمند ضریب تبدیل",
      reason: "نیازمند ضریب تبدیل", sourcePriceIRR: "22000000", sourceUnit: "branch",
      convertedDailyUnitPriceIRR: null, componentQuantity: null,
      componentDailyCostIRR: null, selectedUnit: "kg",
    },
  });
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();
  button(panel, "انتخاب").click();
  field(panel, "usageMode").value = "per_msp_unit";
  field(panel, "usageQuantity").value = "80";
  field(panel, "usageQuantity").dispatch("input");
  await settle();

  /* Asserted on the figure cells themselves rather than by scanning for a zero: «۸۰»
     contains no zero but «۴۰٬۰۰۰» does, so a text search would fail on a correct render. */
  const values = panel.querySelector(".price-component-form__figures").children
    .filter((node) => node.tagName === "DD").map((node) => node.textContent);
  assert.equal(values[1], "—", "the converted price is unknown, not zero");
  assert.equal(values[3], "—", "this material's daily cost is unknown, not zero");
  assert.ok(panel.textContent.includes("نیازمند ضریب تبدیل"), "the reason is stated");
});

/* ---------------------------------------------------------------------- saving */

test("saving requires a product, a unit, a mode, a quantity and a reason", async () => {
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();
  button(panel, "ثبت مصالح").click();
  await settle();
  assert.equal(adapter.calls.added.length, 0, "nothing is saved without a choice");

  button(panel, "انتخاب").click();
  field(panel, "usageMode").value = "per_msp_unit";
  field(panel, "usageQuantity").value = "80";
  field(panel, "usageQuantity").dispatch("input");
  await settle();
  button(panel, "ثبت مصالح").click();
  await settle();
  assert.equal(adapter.calls.added.length, 0, "nor without a reason");
  assert.ok(panel.textContent.includes("دلیل ثبت این مصالح الزامی است"));
});

test("a saved material carries exactly what was shown, and the list reloads", async () => {
  const adapter = adapterStub();
  const saved = [];
  const panel = open(adapter, { onSaved: () => saved.push(true) });
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();
  button(panel, "انتخاب").click();
  field(panel, "usageMode").value = "per_msp_unit";
  field(panel, "usageQuantity").value = "80";
  field(panel, "usageQuantity").dispatch("input");
  await settle();
  panel.querySelector("textarea").value = "بر اساس نقشهٔ اجرایی";
  button(panel, "ثبت مصالح").click();
  await settle();

  assert.deepEqual(adapter.calls.added, [{
    providerItemId: "item-rebar", selectedUnit: "kg", usageMode: "per_msp_unit",
    usageQuantity: "80", reason: "بر اساس نقشهٔ اجرایی",
  }]);
  assert.equal(saved.length, 1, "the page is told so the row's total refreshes");
  assert.equal(panel.querySelectorAll(".price-component").length, 1,
               "the new material appears in the list without leaving the panel");
});

test("the panel stays open after a save so a second material can be added", async () => {
  // A line is priced from a LIST. Closing after the first entry would make adding the
  // second a fresh trip through the table.
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "افزودن مصالح").click();
  await settle();
  button(panel, "انتخاب").click();
  field(panel, "usageMode").value = "total_quantity";
  field(panel, "usageQuantity").value = "1200";
  field(panel, "usageQuantity").dispatch("input");
  await settle();
  panel.querySelector("textarea").value = "طول کل ترانشه";
  button(panel, "ثبت مصالح").click();
  await settle();
  assert.ok(button(panel, "افزودن مصالح"), "the add button is back for the next material");
});

test("editing one material sends a correction under its own identity", async () => {
  const adapter = adapterStub({ components: [component()] });
  const panel = open(adapter);
  await settle();
  button(panel, "ویرایش").click();
  await settle();
  field(panel, "usageQuantity").value = "90";
  field(panel, "usageQuantity").dispatch("input");
  await settle();
  button(panel, "ثبت ویرایش").click();
  await settle();

  assert.deepEqual(adapter.calls.updated, [{
    componentId: "c-rebar", providerItemId: "item-rebar", selectedUnit: "kg",
    usageMode: "per_msp_unit", usageQuantity: "90", reason: "بر اساس نقشهٔ اجرایی",
  }]);
  assert.equal(adapter.calls.added.length, 0, "an edit is not a second material");
});

test("retiring a material asks why, and refuses without an answer", async () => {
  // The reason IS the record of why a material left the line. A confirm dialog that only
  // asks "are you sure" collects nothing.
  const adapter = adapterStub({ components: [component()] });
  const panel = open(adapter);
  await settle();
  button(panel, "حذف از این قلم").click();
  await settle();
  button(panel, "تأیید حذف").click();
  await settle();
  assert.equal(adapter.calls.deactivated.length, 0, "no reason, no deactivation");

  field(panel, "deactivateReason").value = "از نقشه حذف شد";
  button(panel, "تأیید حذف").click();
  await settle();
  assert.deepEqual(adapter.calls.deactivated,
                   [{ componentId: "c-rebar", reason: "از نقشه حذف شد" }]);
});

test("a retired material stays visible and is marked as retired", async () => {
  const adapter = adapterStub({ components: [component({ active: false })] });
  const panel = open(adapter);
  await settle();
  const card = panel.querySelector(".price-component");
  assert.ok(card.classList.contains("price-component--retired"));
  assert.ok(card.textContent.includes("کنار گذاشته شده"));
  assert.equal(button(panel, "ویرایش"), undefined, "a retired material offers no edit");
});

test("a viewer without finance.edit can look and cannot change anything", async () => {
  const panel = open(adapterStub({ components: [component()] }), { canEdit: false });
  await settle();
  assert.equal(button(panel, "افزودن مصالح").disabled, true);
  assert.equal(button(panel, "ویرایش"), undefined, "no per-material actions are offered");
  assert.ok(panel.textContent.includes("finance.edit"), "it says which access is missing");
});
