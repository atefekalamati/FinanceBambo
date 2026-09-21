import assert from "node:assert/strict";
import test from "node:test";

import { installDom } from "../helpers/dom.js";

installDom();

const { alignmentCell, priceCell, renderMaterialPrices, sheetDateLabel, statusText,
        unitCell } =
  await import("../../src/features/prices/material-prices-section.js");

function row(changes = {}) {
  return {
    providerItemId: "11111111-1111-4111-8111-111111111111",
    externalId: "REBAR-1",
    name: "میلگرد آجدار ۸ A3 سمنان",
    category: "rebar",
    providerName: "Mashhad Foolad",
    active: true,
    inactiveReason: null,
    worksheet: "steel -Rebar",
    currentPriceIRR: "955000",
    rawPrice: "95500",
    sourceCurrency: "TOMAN",
    secondaryPriceIRR: null,
    secondaryPriceBasis: null,
    sourceUnit: "کیلو",
    sourceUnitCode: "kg",
    displayUnit: null,
    targetUnit: null,
    conversionFactor: null,
    conversionNote: null,
    factorOrigin: null,
    label: null,
    labelDisplayName: null,
    labelSourceBasis: null,
    financeResourceUnit: null,
    unitAlignment: "not_mapped",
    workflowDateRaw: "1405-06-22",
    workflowDateJalali: "1405/06/22",
    workflowDate: "2026-09-13",
    observedAt: "2026-09-13T00:00:00Z",
    observedAtSource: "workflow_date",
    fetchedAt: "2026-09-14T09:00:00Z",
    validationStatus: "valid",
    validationReasons: [],
    resolutionStatus: "resolved",
    resolutionReason: null,
    sourceRowNumber: 2,
    sourceUrl: "https://docs.google.com/spreadsheets/d/X/export?format=xlsx",
    ...changes,
  };
}

test("a missing price is an em dash, and never a zero", () => {
  for (const missing of [null, undefined]) {
    assert.equal(priceCell(row({ currentPriceIRR: missing })), "—");
  }
  // The thing this is really guarding: nothing anywhere turns absence into 0.
  const cell = priceCell(row({ currentPriceIRR: null }));
  assert.doesNotMatch(cell, /0/, "a missing price must not render any digit");
  assert.doesNotMatch(cell, /۰/, "including a Persian zero");
});

test("a real price is rendered through the shared money formatter", () => {
  const cell = priceCell(row());
  assert.notEqual(cell, "—");
  assert.match(cell, /[۰-۹0-9]/, "a price that exists shows digits");
});

test("each way a price can be unusable gets its own sentence", () => {
  const seen = new Set();
  // All nine, because collapsing any two would tell two different people the same
  // useless thing: one has to weigh a product, another has to approve a mapping.
  for (const status of ["stale", "unresolved_price", "unresolved_unit", "incompatible_unit",
                        "missing_factor", "unresolved_mapping", "invalid_source", "inactive"]) {
    const text = statusText(row({ resolutionStatus: status }));
    assert.ok(text, `${status} must say something`);
    assert.ok(!seen.has(text), `${status} must not reuse another status's wording`);
    seen.add(text);
  }
});

test("a resolved price needs no explanation", () => {
  assert.equal(statusText(row()), "");
});

test("the backend's reason is shown beside the label, not instead of it", () => {
  const text = statusText(row({
    resolutionStatus: "missing_factor",
    resolutionReason: "برای تبدیل کیلوگرم به عدد ضریبی لازم است که مخصوص همین کالاست",
  }));
  assert.match(text, /ضریب تبدیل این کالا ثبت نشده/);
  assert.match(text, /کیلوگرم/);
  assert.match(text, /عدد/);
});

test("the sheet's own Jalali date is what the reader sees", () => {
  assert.equal(sheetDateLabel(row()), "1405/06/22");
});

test("a date that could not be read says so rather than showing today", () => {
  const label = sheetDateLabel(row({
    workflowDateJalali: null, workflowDate: null, workflowDateRaw: "به زودی",
  }));
  assert.match(label, /خوانا نشد/);
  assert.match(label, /به زودی/, "the unreadable cell is quoted so it can be fixed");
});

test("a row with no date at all says there is none", () => {
  const label = sheetDateLabel(row({
    workflowDateJalali: null, workflowDate: null, workflowDateRaw: null,
  }));
  assert.equal(label, "بدون تاریخ");
});

test("a price with no stated unit says so instead of assuming one", () => {
  // All three cleared: the code the backend read, the raw spelling, and the unit the price
  // ended up in. Leaving any one set would make this pass for the wrong reason.
  assert.equal(unitCell(row({
    sourceUnit: null, sourceUnitCode: null, targetUnit: null, displayUnit: null,
  })), "واحد اعلام نشده");
});

test("a converted price is marked as converted, and says which kind", () => {
  const byUnits = unitCell(row({
    targetUnit: "g", conversionFactor: "1000", factorOrigin: "dimension" }));
  assert.match(byUnits, /تبدیل‌شده/);

  const byProduct = unitCell(row({
    targetUnit: "kg", conversionFactor: "2.8", factorOrigin: "manual" }));
  assert.match(byProduct, /ضریب کالا/,
    "a factor somebody measured is not the same claim as a ratio between units");
});

test("the unit column shows the unit the PRICE is in, never the one merely asked for", () => {
  // The one lie this column could tell: «متر» beside a price still per branch.
  const cell = unitCell(row({
    displayUnit: "m", targetUnit: null, sourceUnitCode: "branch", conversionFactor: null }));
  assert.doesNotMatch(cell, /متر$/, "the chosen unit was not reached and is not claimed");
});

test("the Finance unit and the verdict travel together", () => {
  assert.match(alignmentCell(row({ financeResourceUnit: "kg", unitAlignment: "aligned" })),
    /هم‌واحد/);
  const convertible = alignmentCell(row({
    financeResourceUnit: "ton", unitAlignment: "convertible" }));
  assert.match(convertible, /قابل تبدیل/);
  assert.match(convertible, /تن/, "both units are shown, not a verdict on its own");
  assert.match(alignmentCell(row()), /وصل نشده/);
});

test("an empty answer is an empty state, never an example row", () => {
  const section = renderMaterialPrices([]);
  assert.equal(section.querySelectorAll("tbody tr").length, 0);
  assert.match(section.textContent, /هنوز هیچ قیمتی از برگه مصالح وارد نشده/);
  // The guard that matters: no digits, so nothing can be mistaken for a figure.
  assert.doesNotMatch(section.querySelector(".inline-notice").textContent, /[0-9۰-۹]/);
});

test("the section says these are observations and not the project's Finance price", () => {
  const section = renderMaterialPrices([row()]);
  assert.match(section.textContent, /مشاهده/);
  assert.match(section.textContent, /قیمت رسمی/,
    "the reader must be told this is not the price invoices are measured against");
});

test("a row whose price is unusable still appears, with its reason", () => {
  const section = renderMaterialPrices([row({
    currentPriceIRR: null,
    resolutionStatus: "unresolved_price",
    resolutionReason: "price is blank",
  })]);
  /* Seven on امور مالی. «واحد» and «وضعیت» were never worksheet columns -- they describe
     how this system READ the price, not what the sheet states -- so they moved under the
     product name as a badge. «منشأ» joined them later and is the one column here that is
     not from a worksheet at all: it says whether an import read the price or a person
     typed it, and it is withheld from the report surface. See
     material-prices-category-columns.test.js. */
  const cells = [...section.querySelectorAll("tbody tr td")].map((td) => td.textContent);
  assert.equal(cells.length, 7);
  assert.ok(cells.some((text) => text.includes("—")), "the price cell is an em dash");
  assert.match(section.textContent, /قیمت خوانا نیست/);
  assert.match(section.textContent, /price is blank/);
});

test("the count of unusable rows is stated rather than left for the reader to add up", () => {
  const section = renderMaterialPrices([
    row(),
    row({ externalId: "REBAR-2", currentPriceIRR: null, resolutionStatus: "unresolved_price" }),
  ]);
  assert.match(section.textContent, /۱ قلم از ۲ قلم|1 قلم از 2 قلم/);
});

test("a converted row carries the explanation of what was applied", () => {
  const section = renderMaterialPrices([row({
    displayUnit: "g",
    conversionFactor: "1000",
    conversionNote: "converted from kg to g by dividing the unit price by 1000",
  })]);
  const tr = section.querySelector("tbody tr");
  assert.match(tr.title, /dividing/);
});

test("five primary categories stay visible and every other category lives in the more menu", () => {
  const chosen = [];
  const section = renderMaterialPrices([row()], {
    categories: [
      { category: "rebar", activeCount: 590, itemCount: 590, inactiveCount: 0 },
      { category: "angle", label: "نبشی", activeCount: 12, itemCount: 12, inactiveCount: 0 },
    ],
    selectedCategory: "rebar",
    onSelectCategory: (value) => chosen.push(value),
  });
  const filter = section.querySelector(".material-prices__filters");
  assert.deepEqual(filter.children.slice(0, 6).map((chip) => chip.textContent),
    ["همه", "آجر", "میلگرد (590)", "تیرآهن", "ناودانی", "لوله"]);

  const more = filter.children[6];
  assert.equal(more.tagName, "DETAILS");
  assert.equal(more.children[0].textContent, "…");
  more.open = true;
  /* The test DOM deliberately supports only selectors the product generally uses; use the
     menu's own button here rather than teaching it a one-off data selector. */
  more.querySelector("button").click();
  assert.equal(more.open, false);
  assert.deepEqual(chosen, ["angle"]);
});

test("the prices page loads market prices on entry instead of waiting for a display button", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(
    new URL("../../src/features/prices/prices-page.js", import.meta.url), "utf8");
  assert.match(source, /state = createRequestState\(REQUEST_STATUS\.SUCCESS, workspace\);\s*await loadMarketPrices\(\);/);
  assert.doesNotMatch(source, /نمایش قیمت روز بازار/);
});

test("the module reaches no external address", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(
    new URL("../../src/features/prices/material-prices-section.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /docs\.google\.com/,
    "the UI must read the database through the backend, never a spreadsheet");
  assert.doesNotMatch(source, /\bfetch\s*\(/,
    "this module renders; fetching belongs to the adapter");
});
