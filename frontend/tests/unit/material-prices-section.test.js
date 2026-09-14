import assert from "node:assert/strict";
import test from "node:test";

import { installDom } from "../helpers/dom.js";

installDom();

const { priceCell, renderMaterialPrices, sheetDateLabel, statusText, unitCell } =
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
    displayUnit: null,
    conversionFactor: null,
    conversionNote: null,
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
  for (const status of ["unresolved_price", "unresolved_unit", "unmapped", "stale"]) {
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
    resolutionStatus: "unresolved_unit",
    resolutionReason: "no conversion factor from 'kg' to 'piece' for this product",
  }));
  assert.match(text, /واحد تبدیل نشده/);
  assert.match(text, /kg/);
  assert.match(text, /piece/);
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
  assert.equal(unitCell(row({ sourceUnit: null, displayUnit: null })), "واحد اعلام نشده");
});

test("a converted price is marked as converted", () => {
  const cell = unitCell(row({ displayUnit: "g", conversionFactor: "1000" }));
  assert.match(cell, /تبدیل‌شده/);
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
  const cells = [...section.querySelectorAll("tbody tr td")].map((td) => td.textContent);
  assert.equal(cells.length, 7);
  assert.ok(cells.includes("—"), "the price cell is an em dash");
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

test("category filters come from the data and never from a hardcoded list", () => {
  const chosen = [];
  const section = renderMaterialPrices([row()], {
    categories: [{ category: "rebar", activeCount: 590, itemCount: 590, inactiveCount: 0 }],
    selectedCategory: "rebar",
    onSelectCategory: (value) => chosen.push(value),
  });
  const chips = [...section.querySelectorAll(".app-chip")].map((chip) => chip.textContent);
  assert.deepEqual(chips, ["همه", "rebar (590)"]);
  section.querySelectorAll(".app-chip")[0].click();
  assert.deepEqual(chosen, [null]);
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
