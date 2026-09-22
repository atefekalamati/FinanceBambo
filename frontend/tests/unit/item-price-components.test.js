/**
 * What prices one item of ریز برآورد, as the financial-items page presents it.
 *
 * ONE LINE IS ONE MATERIAL
 * An estimate line here is one resource on one activity -- it arrives that way from the MPP
 * assignment rows, already naming «آرماتور» and its own quantity in kilograms. So it is
 * linked to ONE market listing. There is no list of materials underneath it and nothing to
 * add to: a material inside a material is a level this data does not have.
 *
 * Two things are defended here and they pull against each other. The feature has to be
 * reachable from the row a person is reading -- so the row gains an action, a status and a
 * figure. And ریز برآورد has to keep the shape people navigate it by -- so the COLUMN LIST
 * must not move. A column added "just for this" is how a table stops being legible.
 *
 * The rest is about the answers that are not numbers. A line nobody has linked says so; a
 * line whose price is quoted per branch while the item is measured in kilograms says
 * «نیازمند ضریب تبدیل» and offers the way to answer it. A zero in either place would be a
 * claim that the work is free.
 *
 * THE WORKED EXAMPLE, throughout: «آرماتور» on «کانال‌کنی», 40,000 kg,
 *     priced from «میلگرد آجدار ۱۰» at 1,014,600 rial/kg -> 40,584,000,000
 */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { installDom } from "../helpers/dom.js";
import { formatTomanFromIrr } from "../../src/shared/formatters/money.js";

installDom();

const { statusChip, createPriceMappingPanel } =
  await import("../../src/features/financial-items/price-mapping-panel.js");
const { groupDailyPriceCell } =
  await import("../../src/features/financial-items/financial-items-page.js");

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

test("the ریز برآورد columns are the ones the table was specified with", () => {
  /* Read off the page's own definition. Locked deliberately: a column added "just for
     this" is how a table stops being legible, and it would be invisible to every other
     test here. The list was redefined once, on purpose -- two unit columns beside each
     other because the gap between them is what blocks a daily price, and one quantity
     column instead of two because the original and the revised said the same thing on
     every row that has never been revised. Changing it again is a decision, not a
     detail, and this is where that decision has to be made explicitly. */
  const block = PAGE_SOURCE.split("function estimateLineColumns()")[1].split("}\n")[0];
  const keys = [...block.matchAll(/\{\s*key:\s*"([a-zA-Z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(keys, [
    "identity", "mspUnit", "sheetUnit", "revisedQuantity", "scheduleCost",
    "originalPrice", "currentPrice", "source", "actions",
  ], "adding or renaming a column of ریز برآورد is a decision to make here first");
});

test("the row's «قیمت روز» cell shows the TOTAL, not one material's price", () => {
  // A line priced from three materials has no single converted unit price, and showing
  // the first one would understate the row by however much the others come to.
  const cell = PAGE_SOURCE.split("function dailyPriceCell(")[1].split("\nfunction ")[0];
  assert.ok(cell.includes("priced.dailyItemCostIRR"), "the total is what the cell prints");
  assert.ok(!cell.includes("convertedDailyUnitPriceIRR"),
            "a per-unit price of one material must not stand in for the row");
});

test("the activity row sums exact current costs from its child rows", () => {
  const rows = [{ lineId: "line-1" }, { lineId: "line-2" }];
  const statuses = new Map([
    ["line-1", { dailyItemCostIRR: "9007199254740993" }],
    ["line-2", { dailyItemCostIRR: "7" }],
  ]);
  const cell = groupDailyPriceCell(rows, statuses);
  assert.ok(cell.textContent.includes(formatTomanFromIrr("9007199254741000", { withCurrency: false })),
    "the total remains exact above Number precision when formatted for display");
  assert.doesNotMatch(cell.textContent, /از/, "a complete total needs no partial warning");
});

test("an incomplete activity current-cost total states its coverage", () => {
  const cell = groupDailyPriceCell(
    [{ lineId: "line-1" }, { lineId: "line-2" }],
    new Map([["line-1", { dailyItemCostIRR: "1000" }]]),
  );
  assert.match(cell.textContent, /1.*از.*2|۱.*از.*۲/);
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
  rebarKg: {
    providerItemId: "item-rebar", externalId: "REBAR-1", name: "میلگرد آجدار ۱۰",
    category: "rebar", categoryLabel: "میلگرد", providerName: "AhanOnline",
    providerId: "p1", sourceUnitCode: "kg", currentPriceIRR: "1014600", active: true,
    specs: { "واحد - وزن": "کیلو" },
    specColumns: [{ key: "واحد - وزن", label: "واحد وزن", numeric: false }],
  },
  /* The case the whole conversion story exists for: quoted per branch, used per kilogram. */
  rebarBranch: {
    providerItemId: "item-rebar-branch", externalId: "REBAR-2", name: "میلگرد آجدار ۱۶ شاخه‌ای",
    category: "rebar", categoryLabel: "میلگرد", providerName: "AhanOnline",
    providerId: "p1", sourceUnitCode: "branch", currentPriceIRR: "22000000", active: true,
    specs: {}, specColumns: [],
  },
};

function connection(over = {}) {
  return {
    componentId: "c-rebar", id: "v1", estimateLineId: "line-1",
    providerItemId: "item-rebar", status: "ready", statusLabel: "آماده", reason: null,
    reasonText: "قیمت این قلم از همین محصول گرفته می‌شود",
    convertedDailyUnitPriceIRR: "1014600", componentQuantity: "40000",
    componentDailyCostIRR: "40584000000", sourcePriceIRR: "1014600",
    selectedUnit: "kg", sourceUnit: "kg", productName: "میلگرد آجدار ۱۰",
    providerName: "AhanOnline", category: "rebar", categoryLabel: "میلگرد",
    active: true, version: 1, specs: {}, specColumns: [], ...over,
  };
}

function adapterStub(overrides = {}) {
  const calls = { candidates: [], filters: [], preview: [], connected: [],
                  reconnected: [], disconnected: [], rules: [] };
  let current = overrides.connection ?? null;
  return {
    calls,
    get connection() { return current; },
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
                { code: "branch", label: "شاخه", dimension: "count", dimensionLabel: "تعداد" },
                { code: "m", label: "متر", dimension: "length", dimensionLabel: "طول" }],
      };
    },
    async candidates(filters) {
      calls.candidates.push(filters);
      const items = filters.category === "pipe" ? [] : [CANDIDATES.rebarKg, CANDIDATES.rebarBranch];
      return { items, page: 1, pageSize: 25, totalItems: items.length };
    },
    async connectionFor() {
      return {
        line: { estimateLineId: "line-1", activityExternalId: "1.5.1", title: "کانال‌کنی",
                mspUnit: "kg", mspQuantity: "40000", mspCostIRR: "120000000",
                originalUnitPriceIRR: "240000" },
        connection: current,
        total: overrides.total ?? {
          estimateLineId: "line-1", status: current ? "ready" : "needs_components",
          statusLabel: current ? "آماده" : "نیازمند افزودن مصالح", reason: null,
          dailyItemCostIRR: current ? "40584000000" : null,
        },
      };
    },
    async preview(lineId, draft) {
      calls.preview.push(draft);
      return overrides.preview ?? connection({
        componentId: null, id: null, reasonText: null, selectedUnit: draft.selectedUnit,
      });
    },
    async connect(lineId, payload) {
      calls.connected.push(payload);
      current = connection({ componentId: "c-new" });
      return { id: "v1", componentId: "c-new", version: 1, ...payload };
    },
    async reconnect(lineId, componentId, payload) {
      calls.reconnected.push({ componentId, ...payload });
      return { id: "v2", componentId, version: 2, ...payload };
    },
    async disconnect(lineId, componentId, reason) {
      calls.disconnected.push({ componentId, reason });
      current = null;
      return { id: "v2", componentId, version: 2, active: false, reason };
    },
    async createConversionRule(payload) {
      calls.rules.push(payload);
      return { id: "rule-1", ...payload };
    },
  };
}

const LINE = { lineId: "line-1", activityExternalId: "1.5.1" };
const RESOURCE = { title: "آرماتور" };

/* The panel loads its filters and then its connection, each behind its own await, and the
   preview is another. A single macrotask turn lands in the middle of that chain, so this
   drains several -- enough for the render to finish and few enough that a genuine hang
   still fails. */
async function settle(turns = 10) {
  for (let i = 0; i < turns; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

function button(root, label) {
  return [...root.querySelectorAll("button")].find((node) => node.textContent === label);
}

function field(root, name) {
  return root.querySelector(`[name=${name}]`);
}

/* Choosing a product is a button inside the card, not the card. Clicking the card did
   nothing and the assertions that followed passed for the wrong reason. */
function pick(root, index = 0) {
  const buttons = [...root.querySelectorAll(".price-candidate button")]
    .filter((node) => node.textContent === "انتخاب");
  assert.ok(buttons[index], "a candidate to choose");
  buttons[index].click();
}

function open(adapter, { canEdit = true, onSaved } = {}) {
  return createPriceMappingPanel({ line: LINE, resource: RESOURCE, adapter, canEdit, onSaved });
}

test("an unlinked line says so rather than showing a zero", async () => {
  const panel = open(adapterStub());
  await settle();

  assert.match(panel.textContent, /هنوز به قیمت روز وصل نشده/);
  assert.ok(!/۰ تومان/.test(panel.querySelector(".price-components__total").textContent),
            "no figure at all is right; zero would say the work is free");
});

test("the panel offers one connection, and stops offering once there is one", async () => {
  const empty = open(adapterStub());
  await settle();
  assert.equal(button(empty, "اتصال به قیمت روز").hidden, false);

  const linked = open(adapterStub({ connection: connection() }));
  await settle();
  assert.equal(button(linked, "اتصال به قیمت روز").hidden, true,
               "a second listing for one line is a state this page cannot produce");
});

test("the linked card shows the line's own quantity and what it costs today", async () => {
  const panel = open(adapterStub({ connection: connection() }));
  await settle();
  const card = panel.querySelector(".price-component");

  assert.match(card.textContent, /میلگرد آجدار ۱۰/);
  assert.match(card.textContent, /مقدار این قلم/);
  assert.match(card.textContent, /هزینه روز این قلم/);
  assert.ok(!/مصرف/.test(card.textContent),
            "usage was a question about a material inside a material; there is none");
});

test("the form asks for a product and a unit, and never for a usage", async () => {
  const panel = open(adapterStub());
  await settle();
  button(panel, "اتصال به قیمت روز").click();
  await settle();

  assert.ok(field(panel, "selectedUnit"), "the official unit is still a choice");
  assert.equal(field(panel, "usageMode"), null, "the line already states its quantity");
  assert.equal(field(panel, "usageQuantity"), null);
});

test("nothing is previewed until both a product and a unit are answered", async () => {
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "اتصال به قیمت روز").click();
  await settle();

  assert.equal(adapter.calls.preview.length, 0);
  pick(panel);
  await settle();
  assert.ok(adapter.calls.preview.length >= 1, "a chosen product preselects its own unit");
  assert.equal(adapter.calls.preview.at(-1).selectedUnit, "kg");
});

test("saving requires a product, a unit and a reason", async () => {
  const adapter = adapterStub();
  const panel = open(adapter);
  await settle();
  button(panel, "اتصال به قیمت روز").click();
  await settle();
  pick(panel);
  await settle();

  button(panel, "ثبت اتصال").click();
  await settle();
  assert.match(panel.querySelector(".form-feedback").textContent, /دلیل/);
  assert.equal(adapter.calls.connected.length, 0);

  field(panel, "reason").value = "قیمت این قلم از همین محصول گرفته می‌شود";
  button(panel, "ثبت اتصال").click();
  await settle();
  assert.equal(adapter.calls.connected.length, 1);
  assert.deepEqual(adapter.calls.connected[0], {
    providerItemId: "item-rebar",
    selectedUnit: "kg",
    reason: "قیمت این قلم از همین محصول گرفته می‌شود",
  });
});

test("a mismatched unit is an answer with a way out, not a dead end", async () => {
  const adapter = adapterStub({
    preview: connection({
      status: "needs_factor", statusLabel: "نیازمند ضریب تبدیل",
      reason: "نیازمند ضریب تبدیل", sourceUnit: "branch", selectedUnit: "kg",
      convertedDailyUnitPriceIRR: null, componentDailyCostIRR: null,
      providerItemId: "item-rebar-branch", productName: "میلگرد آجدار ۱۶ شاخه‌ای",
    }),
  });
  const panel = open(adapter);
  await settle();
  button(panel, "اتصال به قیمت روز").click();
  await settle();
  pick(panel);
  await settle();

  assert.match(panel.textContent, /نیازمند ضریب تبدیل/);
  assert.ok(button(panel, "تعریف قانون تبدیل واحد"),
            "the person who hit this is the person who can answer it");
  assert.equal(button(panel, "ثبت اتصال").disabled, false,
               "which listing prices this line is worth recording before the crossing is measured");
});

test("the conversion button appears for no other unresolved status", async () => {
  for (const status of ["no_price", "needs_unit", "ready"]) {
    const panel = open(adapterStub({ preview: connection({ status, statusLabel: status }) }));
    await settle();
    button(panel, "اتصال به قیمت روز").click();
    await settle();
    pick(panel);
    await settle();
    assert.match(panel.querySelector(".price-component-form__preview").textContent,
                 /\S/, "the preview must have rendered, or this proves nothing");
    assert.equal(button(panel, "تعریف قانون تبدیل واحد"), undefined,
                 `${status} is a different problem and a conversion rule would not fix it`);
  }
});

test("changing the product sends a correction under the stored identity", async () => {
  const adapter = adapterStub({ connection: connection() });
  const panel = open(adapter);
  await settle();
  button(panel, "تغییر محصول").click();
  await settle();
  field(panel, "reason").value = "تأمین‌کننده عوض شد";
  button(panel, "ثبت تغییر").click();
  await settle();

  assert.equal(adapter.calls.reconnected.length, 1);
  assert.equal(adapter.calls.reconnected[0].componentId, "c-rebar");
  assert.equal(adapter.calls.connected.length, 0, "a change is not a second connection");
});

test("removing a link asks why, and refuses without an answer", async () => {
  const adapter = adapterStub({ connection: connection() });
  const panel = open(adapter);
  await settle();
  button(panel, "برداشتن اتصال").click();
  await settle();

  const confirm = [...panel.querySelectorAll("button")]
    .find((node) => /تأیید/.test(node.textContent));
  assert.ok(confirm, "removing asks for a reason in place");
  confirm.click();
  await settle();
  assert.equal(adapter.calls.disconnected.length, 0, "no reason, no record of why");
});

test("a viewer without finance.edit can look and cannot change anything", async () => {
  const panel = open(adapterStub({ connection: connection() }), { canEdit: false });
  await settle();

  assert.equal(button(panel, "اتصال به قیمت روز").disabled, true);
  assert.equal(button(panel, "تغییر محصول"), undefined);
  assert.match(panel.textContent, /finance\.edit/);
});

/* ------------------------------------------------------- the report surface reads only */

test("گزارش مالی is handed no pricing tool at all", () => {
  /* Connecting an item to a listing, converting units, stating a rate by hand: these are
     how the numbers are MADE, and they live on امور مالی. The report is where they are
     read. Both handlers are gated on the surface in ONE place, and the cells render from
     the handlers -- so this single assertion covers every button any cell draws from them,
     including ones not written yet.

     It is asserted because it was once false: «اتصال به قیمت روز» asked only whether the
     handler existed and appeared on the report from the day it was written. */
  const mapGate = /onMapPrice:\s*!readOnly && priceMappingAdapter \?/.test(PAGE_SOURCE);
  const manualGate = /onManualPrice:\s*!readOnly && pricesAdapter \?/.test(PAGE_SOURCE);
  assert.ok(mapGate, "the daily-price link must be withheld from the report surface");
  assert.ok(manualGate, "the manual price must be withheld from the report surface");
});

test("a cell may not reach around the surface gate to open a pricing tool", () => {
  /* The cells receive `onMapPrice`/`onManualPrice` and nothing else -- they never see the
     adapters, so a cell cannot build its own opener. If one ever names an adapter directly,
     the gate above stops being the only way in and this test says so. */
  const after = PAGE_SOURCE.split("function renderEstimateLineTable")[1] ?? "";
  const table = after.split("export function createFinancialItemsPage")[0];
  assert.ok(!/priceMappingAdapter|pricesAdapter/.test(table),
            "renderEstimateLineTable must depend on the handlers, never on an adapter");
});
