import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildMonthlyTrendPreview, isMonthlyTrendPreviewEnabled, PREVIEW_FLAG } from "../../src/adapters/api/monthly-trend-preview.js";
import { createApiReportsAdapter } from "../../src/adapters/api/reports-api-adapter.js";
import { buildMonthlyTrend, TREND_MODES } from "../../src/features/finance-home/monthly-trend.js";

/**
 * TEMPORARY, alongside src/adapters/api/monthly-trend-preview.js. Delete this
 * file when the Backend ships a monthly report.
 *
 * The point of these tests is not the fabricated numbers — it is that they
 * cannot reach a screen unless a developer explicitly asks, and that they are
 * labelled when they do.
 */

const context = { organizationId: "org-1", projectId: "project-1" };
const client = { async request() { throw new Error("the preview must not call the API"); } };

test("the preview is off unless it is explicitly asked for", () => {
  assert.equal(isMonthlyTrendPreviewEnabled({ search: "", hash: "#/finance" }, {}), false);
  assert.equal(isMonthlyTrendPreviewEnabled({ search: "?other=1", hash: "#/finance?x=2" }, {}), false);
  assert.equal(isMonthlyTrendPreviewEnabled({ search: `?${PREVIEW_FLAG}=0`, hash: "" }, {}), false);
  assert.equal(isMonthlyTrendPreviewEnabled({}, {}), false, "no location at all must not enable it");
});

test("the preview turns on from the query string, the hash query, or an explicit global", () => {
  assert.equal(isMonthlyTrendPreviewEnabled({ search: `?${PREVIEW_FLAG}=1`, hash: "#/finance" }, {}), true);
  assert.equal(isMonthlyTrendPreviewEnabled({ search: "", hash: `#/finance?${PREVIEW_FLAG}=1` }, {}), true);
  assert.equal(isMonthlyTrendPreviewEnabled({ search: "", hash: "" }, { __BAMBO_MONTHLY_TREND_PREVIEW__: true }), true);
  assert.equal(isMonthlyTrendPreviewEnabled({ search: "", hash: "" }, { __BAMBO_MONTHLY_TREND_PREVIEW__: "yes" }), false, "only an explicit true counts");
});

test("with the flag off the adapter still reports the series as unavailable", async () => {
  const before = globalThis.__BAMBO_MONTHLY_TREND_PREVIEW__;
  delete globalThis.__BAMBO_MONTHLY_TREND_PREVIEW__;
  try {
    const result = await createApiReportsAdapter(context, client).getMonthlyTrend({ reportingDate: "2026-08-22" });
    assert.deepEqual(result.months, []);
    assert.equal(result.estimateSource, "unavailable");
  } finally {
    if (before !== undefined) globalThis.__BAMBO_MONTHLY_TREND_PREVIEW__ = before;
  }
});

test("with the flag on the adapter returns a labelled preview and never calls the API", async () => {
  globalThis.__BAMBO_MONTHLY_TREND_PREVIEW__ = true;
  try {
    const result = await createApiReportsAdapter(context, client).getMonthlyTrend({ reportingDate: "2026-08-22" });
    assert.equal(result.estimateSource, "preview", "the UI keys its warning off this");
    assert.ok(result.previewNotice, "a preview must carry the text that admits what it is");
    assert.equal(result.months.length, 12);
  } finally {
    delete globalThis.__BAMBO_MONTHLY_TREND_PREVIEW__;
  }
});

test("preview months are exact IRR strings ending on the reporting month", () => {
  const { months } = buildMonthlyTrendPreview({ reportingDate: "2026-08-22" });
  assert.equal(months.length, 12);
  assert.ok(months.every((month) => /^\d+$/.test(month.actualCostIrr)), "money stays exact integer IRR");
  assert.ok(months.every((month) => month.estimateIrr === null || /^\d+$/.test(month.estimateIrr)));

  const keys = months.map((month) => `${month.persianYear}-${String(month.persianMonth).padStart(2, "0")}`);
  assert.deepEqual(keys, [...keys].sort(), "oldest first, with no gaps to fill later");
  assert.equal(new Set(keys).size, 12, "no month repeats");
  assert.equal(months.at(-1).persianMonth, 5, "مرداد ۱۴۰۵ is the reporting month for 2026-08-22");
});

test("the preview exercises every state the chart can draw", () => {
  const view = buildMonthlyTrend({ months: buildMonthlyTrendPreview({ reportingDate: "2026-08-22" }).months, mode: TREND_MODES.PERIODIC });
  const directions = new Set(view.points.map((point) => point.direction));
  assert.ok(directions.has("over"), "at least one month above the baseline");
  assert.ok(directions.has("under"), "at least one month below it");
  assert.ok(directions.has(null), "and one with no estimate, so the line gap is visible");
  assert.equal(view.estimatePartial, true);
  assert.equal(view.hasEstimate, true);
});

test("every place the preview touches names itself as temporary", () => {
  const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
  const adapter = read("../../src/adapters/api/reports-api-adapter.js");
  const page = read("../../src/features/finance-home/finance-home-page.js");
  const css = read("../../src/features/finance-home/finance-home.css");
  assert.match(adapter, /TEMPORARY/, "the call site must say so");
  assert.match(page, /TEMPORARY/, "so must the notice that renders it");
  assert.match(css, /TEMPORARY/, "and the style that dresses it");
});
