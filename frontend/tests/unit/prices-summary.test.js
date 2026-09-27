import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { createPricesSummary } = await import("../../src/features/finance-home/prices-summary.js");
const { loadMarketSamples, MARKET_SAMPLE_CATEGORIES } =
  await import("../../src/features/finance-home/finance-home-page.js");

/* THE «قیمت‌های روز» CARD SHOWS THE MARKET.
 *
 * Asked 2026-09-27: the card showed three prices of 100,000 toman -- the first three
 * priced RESOURCES, which on this project are seed rates -- and the reader wanted a brick,
 * an I-beam and a rebar from the daily-price table instead.
 */

const listing = (category, name, price, id = `${category}-1`) => ({
  providerItemId: id, name, category, currentPriceIRR: price, active: true,
});

function sheet(byCategory, { categories = null, historyFails = false } = {}) {
  const calls = { current: [], history: [] };
  return {
    calls,
    async listCategories() {
      return { items: (categories ?? Object.keys(byCategory)).map((category) => ({ category })) };
    },
    async listCurrentPrices({ category }) {
      calls.current.push(category);
      return { items: byCategory[category] ?? [] };
    },
    async listPriceHistory(id) {
      calls.history.push(id);
      if (historyFails) throw new Error("no history today");
      /* Newest first, as the service answers. */
      return { items: [{ priceIRR: "1000000", workflowDate: "2026-09-27", validationStatus: "valid" },
                       { priceIRR: "900000", workflowDate: "2026-09-20", validationStatus: "valid" }] };
    },
  };
}

test("the three named categories are asked first, one priced listing each", async () => {
  const adapter = sheet({
    brick: [listing("brick", "آجر سفال", null, "b0"), listing("brick", "آجر نما", "12000")],
    ibeam: [listing("ibeam", "تیرآهن ۱۸", "164000000")],
    rebar: [listing("rebar", "میلگرد ۱۴", "913600")],
    pipe: [listing("pipe", "لوله", "1")],
  });
  const samples = await loadMarketSamples(adapter);
  assert.deepEqual(samples.map((s) => s.name), ["آجر نما", "تیرآهن ۱۸", "میلگرد ۱۴"],
                   "an unpriced listing is skipped, and the fourth category is never reached");
  assert.deepEqual(adapter.calls.current, ["brick", "ibeam", "rebar"]);
  assert.deepEqual([...MARKET_SAMPLE_CATEGORIES], ["brick", "ibeam", "rebar"]);
  assert.equal(samples[0].trendItem.trend.trendDirection, "up", "the listing's own history draws its trend");
});

test("a category with nothing priced is filled from the sheet's other categories, never from the hourly chip", async () => {
  const adapter = sheet({
    brick: [listing("brick", "آجر", null)],
    ibeam: [listing("ibeam", "تیرآهن", "164000000")],
    rebar: [listing("rebar", "میلگرد", "913600")],
    work: [listing("work", "جرثقیل", "5650000")],
    pipe: [listing("pipe", "لوله", "1500000")],
  });
  const samples = await loadMarketSamples(adapter);
  assert.deepEqual(samples.map((s) => s.name), ["تیرآهن", "میلگرد", "لوله"]);
  assert.ok(!adapter.calls.current.includes("work"));
});

test("no adapter, or a sheet that fails, yields no samples rather than an error", async () => {
  assert.deepEqual(await loadMarketSamples(null), []);
  const broken = { listCategories: async () => { throw new Error("x"); },
                   listCurrentPrices: async () => { throw new Error("x"); },
                   listPriceHistory: async () => { throw new Error("x"); } };
  assert.deepEqual(await loadMarketSamples(broken), []);
  const noHistory = sheet({ rebar: [listing("rebar", "میلگرد", "913600")] }, { historyFails: true });
  const samples = await loadMarketSamples(noHistory, ["rebar"]);
  assert.equal(samples.length, 1, "a trend that cannot be read does not lose the price");
});

test("the card draws the market rows first and fills the rest from resource rates", () => {
  const samples = [{ providerItemId: "r1", name: "میلگرد ۱۴", currentPriceIRR: "913600",
                     trendItem: { resource: { resourceId: "r1" }, trend: { trendDirection: "none", trendPoints: [] } } }];
  const workspace = { currentPrices: [
    { resource: { resourceId: "x", title: "قلم آزمایشی" }, currentPrice: { unitPriceIRR: "1000000" }, trend: null },
    { resource: { resourceId: "y", title: "قلم دوم" }, currentPrice: { unitPriceIRR: "2000000" }, trend: null },
    { resource: { resourceId: "z", title: "قلم سوم" }, currentPrice: { unitPriceIRR: "3000000" }, trend: null },
  ], history: [] };
  const section = createPricesSummary({ workspace, samples });
  const names = [...section.querySelectorAll("tbody tr .prices-summary__name")].map((td) => td.textContent);
  assert.deepEqual(names, ["میلگرد ۱۴", "قلم آزمایشی", "قلم دوم"], "three rows, the market first");
  const prices = [...section.querySelectorAll("tbody tr .prices-summary__price")].map((td) => td.textContent);
  assert.equal(prices[0], "۹۱٬۳۶۰");
  /* And with three market rows, no resource rate is shown at all. */
  const full = createPricesSummary({ workspace, samples: [samples[0], { ...samples[0], providerItemId: "r2", name: "آجر" },
                                                           { ...samples[0], providerItemId: "r3", name: "تیرآهن" }] });
  assert.equal(full.querySelectorAll("tbody tr").length, 3);
  assert.doesNotMatch(full.textContent, /قلم آزمایشی/);
});

test("without any sample the card behaves exactly as before", () => {
  const workspace = { currentPrices: [
    { resource: { resourceId: "x", title: "قلم" }, currentPrice: { unitPriceIRR: "1000000" }, trend: null },
  ], history: [] };
  assert.match(createPricesSummary({ workspace }).textContent, /قلم/);
  assert.match(createPricesSummary({ workspace: { currentPrices: [] } }).textContent, /هنوز قیمت روزی/);
});
