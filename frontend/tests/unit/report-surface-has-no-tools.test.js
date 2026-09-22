import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { createFinancialItemsPage } =
  await import("../../src/features/financial-items/financial-items-page.js");
const { SURFACES } = await import("../../src/core/config/routes.js");

/* گزارش مالی reads; امور مالی calculates.
 *
 * Connecting an item to a market listing, converting between units, stating a rate by
 * hand -- these MAKE the numbers. A button that starts one of them on the report surface
 * invites a reader to change the report they came to read.
 *
 * This renders the real page on both surfaces and counts the buttons, rather than reading
 * the source: the leak it is guarding against was not a missing rule but a cell that drew
 * a button without asking about the surface, and only a render can see that.
 */

const RESOURCE = {
  resourceId: "20000000-0000-4000-8000-000000000001",
  type: "material", code: "MAT-REBAR", title: "میلگرد آجدار A3",
  baseUnit: "kg", dimension: "mass", source: "progress_feed",
};

const LINE = {
  lineId: "30000000-0000-4000-8000-000000000001",
  activityExternalId: "ACT-102", activityTitle: "اجرای فونداسیون", wbsCode: "1.2",
  assignmentExternalId: "asg-foundation-rebar",
  resourceId: RESOURCE.resourceId,
  originalQuantity: "380000.0000", revisedQuantity: "410000.0000",
  originalUnitPriceIRR: "290000", originalAmount: null, revisedAmount: null,
  source: "progress_feed",
};

/* A row whose units do not agree, which is exactly the state that offers «تبدیل واحد» --
   so the report surface is measured on the row most likely to show a tool, not on a quiet
   one that would have shown nothing either way. */
const STATUS = {
  estimateLineId: LINE.lineId, status: "needs_factor", statusLabel: "نیازمند ضریب تبدیل",
  reason: null, dailyItemCostIRR: null,
  componentCount: 1, readyComponentCount: 0, unresolvedComponentCount: 1,
  providerName: "فولاد مبارکه", productName: "میلگرد ۱۶", sourceSummary: null,
  sourcePriceUnit: "ton", selectedUnit: "kg",
};

function stubs() {
  return {
    context: { organizationId: "org-1", projectId: "p-1", projectCode: "P1",
               permissionCodes: ["finance.view", "finance.edit"] },
    adapter: {
      async getWorkspace() { return { resources: [RESOURCE], estimateLines: [LINE] }; },
    },
    priceMappingAdapter: { async statuses() { return [STATUS]; } },
    pricesAdapter: { async createPriceVersion() { return {}; } },
  };
}

async function render(surface) {
  const root = createFinancialItemsPage({ ...stubs(), surface });
  // The page loads on mount and paints when the promises settle.
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  return root;
}

function actions(root) {
  return [...root.querySelectorAll("button")]
    .map((button) => button.dataset?.action)
    .filter(Boolean);
}

test("the report surface offers no pricing tool on any row", async () => {
  const root = await render(SURFACES.REPORT);
  const found = actions(root);
  assert.deepEqual(found, [], `گزارش مالی must offer no tool, found: ${found.join(", ")}`);
});

test("the report surface still reads: the table and its rows are there", async () => {
  /* The tools are gone and the report is not. A test that only counted buttons would pass
     just as well on a page that failed to render at all. */
  const root = await render(SURFACES.REPORT);
  const text = root.textContent ?? "";
  assert.ok(/میلگرد آجدار A3/.test(text), "the row must still be reported");
  assert.ok(/خروجی اکسل/.test(text), "the export must still be offered");
});

test("امور مالی keeps every tool the report gave up", async () => {
  /* The other half of the same rule. Moving the tools off the report is only correct if
     they are still somewhere, and this is where. */
  const root = await render(SURFACES.OPERATIONS);
  const found = new Set(actions(root));
  assert.ok(found.has("map-price"), "اتصال به قیمت روز belongs on امور مالی");
  assert.ok(found.has("fix-unit"), "تبدیل واحد belongs on امور مالی");
  assert.ok(found.has("manual-price"), "ثبت دستی قیمت روز belongs on امور مالی");
});

/* AND IT SHOWS NO METHOD EITHER.
 *
 * A tool invites the reader to change the report. A note saying HOW a number was recorded
 * invites them to weigh it — «قیمت دستی» reads as a caveat about a figure that has none,
 * and «قانون تبدیل» answers a question only somebody who can act on it is asking. Both
 * belong to امور مالی, where the person reading them can do something about it.
 *
 * Rendered on both surfaces rather than read from the source, for the same reason the
 * tool tests are: the leak this guards against is a cell that drew a note without asking
 * which surface it was on.
 */

/* A row priced by hand: a resource price with no component cost, which is what produces
   the «قیمت دستی» note. The unit row above carries the factor-source note instead. */
const MANUAL_LINE = { ...LINE, lineId: "30000000-0000-4000-8000-000000000002",
                      assignmentExternalId: "asg-manual" };
const MANUAL_STATUS = { ...STATUS, estimateLineId: MANUAL_LINE.lineId,
                        status: "needs_components", statusLabel: "نیازمند افزودن مصالح",
                        componentCount: 0, readyComponentCount: 0,
                        unresolvedComponentCount: 0, factorSource: "conversion_rule",
                        sourcePriceUnit: null, selectedUnit: null };

async function renderManual(surface) {
  const base = stubs();
  const root = createFinancialItemsPage({
    ...base, surface,
    adapter: { async getWorkspace() {
      return { resources: [RESOURCE],
               estimateLines: [{ ...MANUAL_LINE, currentUnitPriceIRR: "32000000" }] };
    } },
    priceMappingAdapter: { async statuses() { return [MANUAL_STATUS]; } },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  return root;
}

test("گزارش مالی shows the figure and not how it was recorded", async () => {
  const root = await renderManual(SURFACES.REPORT);
  const text = root.textContent ?? "";
  assert.doesNotMatch(text, /قیمت دستی/,
                      "how the price was entered is not the reader's question");
  assert.match(text, /۳٬۲۰۰٬۰۰۰/, "and the figure itself is still there");
});

test("امور مالی keeps the note, because somebody there can act on it", async () => {
  const root = await renderManual(SURFACES.OPERATIONS);
  assert.match(root.textContent ?? "", /قیمت دستی/);
});

test("گزارش مالی does not name what crossed the two units", async () => {
  /* «قانون تبدیل» versus «وزن‌کشی همین محصول» is a judgement about how far to trust a
     conversion — a working question, on a page that does no work. */
  const root = await render(SURFACES.REPORT);
  assert.doesNotMatch(root.textContent ?? "", /قانون تبدیل|وزن‌کشی همین محصول/);
});

test("امور مالی still names it", async () => {
  const withFactor = { ...STATUS, factorSource: "conversion_rule" };
  const base = stubs();
  const root = createFinancialItemsPage({
    ...base, surface: SURFACES.OPERATIONS,
    priceMappingAdapter: { async statuses() { return [withFactor]; } },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(root.textContent ?? "", /قانون تبدیل/);
});
