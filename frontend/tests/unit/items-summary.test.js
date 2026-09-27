import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { createItemsSummary, estimateAmountIrr, selectSummaryRows, stageCode } =
  await import("../../src/features/finance-home/items-summary.js");

/* THE CARD ON THE REPORT PAGE: three lines, the biggest, with what they were estimated at.
 *
 * Revised 2026-09-27. It used to show the three oldest lines and a unit beside each
 * quantity -- on this project three seed rows of «۱ واحد», on a real one three of 426
 * equipment lines with no quantity, so «—» beside «ساعت».
 */

const material = { resourceId: "r-steel", type: "material", title: "آهن آلات", baseUnit: "کیلوگرم" };
const machine = { resourceId: "r-crane", type: "work", title: "جرثقیل", baseUnit: "hour" };
const general = { resourceId: "r-permit", type: "general_cost", title: "مجوز", baseUnit: null };

function line(resourceId, changes = {}) {
  return { lineId: `l-${resourceId}-${Math.random()}`, resourceId, activityExternalId: "1.9.4.2",
           wbsCode: null, originalQuantity: null, revisedQuantity: null,
           originalUnitPriceIRR: null, originalAmount: null, revisedAmount: null, ...changes };
}

test("a line's estimate is quantity × its fixed rate, exact and rounded once", () => {
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "860416.2200", originalUnitPriceIRR: "1400000" }), material),
               "1204582708000");
  /* Rounded half away from zero, once, at the last step: 0.0005 rial is 0, 0.5 rial is 1. */
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "0.0005", originalUnitPriceIRR: "1" }), material), "0");
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "0.5", originalUnitPriceIRR: "1" }), material), "1");
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "-2.5", originalUnitPriceIRR: "3" }), material), "-8", "half away from zero on the negative side too");
  /* The revised quantity wins over the original, as everywhere else. */
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "10", revisedQuantity: "12", originalUnitPriceIRR: "100" }), material), "1200");
});

test("a line missing either factor has no estimate, not a zero one", () => {
  assert.equal(estimateAmountIrr(line("r-crane", { originalUnitPriceIRR: "500" }), machine), null, "no quantity");
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "10" }), material), null, "no rate");
  assert.equal(estimateAmountIrr(line("r-steel", { originalQuantity: "abc", originalUnitPriceIRR: "1" }), material), null);
});

test("a general cost's estimate is its stated amount, revised first", () => {
  assert.equal(estimateAmountIrr(line("r-permit", { originalAmount: "5000" }), general), "5000");
  assert.equal(estimateAmountIrr(line("r-permit", { originalAmount: "5000", revisedAmount: "6000" }), general), "6000");
  assert.equal(estimateAmountIrr(line("r-permit"), general), null);
});

test("the stage code is the first three segments of the line's WBS", () => {
  assert.equal(stageCode({ wbsCode: "1.9.4.2.7" }), "1.9.4");
  assert.equal(stageCode({ wbsCode: null, activityExternalId: "1.9.4.2" }), "1.9.4", "the activity code when the line carries no WBS");
  assert.equal(stageCode({ wbsCode: "1.4" }), "1.4", "a shorter code is not padded");
  assert.equal(stageCode({ wbsCode: "", activityExternalId: null }), null);
});

test("the three largest estimates are chosen, and lines without one come last", () => {
  const workspace = {
    resources: [material, machine, general],
    estimateLines: [
      line("r-crane", { activityExternalId: "1.5.1.1" }),                                   // no quantity → no estimate
      line("r-steel", { originalQuantity: "10", originalUnitPriceIRR: "100", activityExternalId: "1.1.1.1" }),        // 1,000
      line("r-permit", { originalAmount: "9000000", activityExternalId: "1.2.1.1" }),          // 9,000,000
      line("r-steel", { originalQuantity: "500", originalUnitPriceIRR: "1000", activityExternalId: "1.3.1.1" }),      // 500,000
      line("r-steel", { originalQuantity: "1", originalUnitPriceIRR: "20000", activityExternalId: "1.4.1.1" }),       // 20,000
      line("r-ghost", { originalQuantity: "1", originalUnitPriceIRR: "99999999" }),           // no resource → never shown
    ],
  };
  const rows = selectSummaryRows(workspace);
  assert.deepEqual(rows.map((row) => row.amountIrr), ["9000000", "500000", "20000"]);
  /* Age plays no part: the 1,000 line was created before the 9,000,000 one. */
  assert.deepEqual(selectSummaryRows(workspace, 10).map((row) => row.amountIrr),
                   ["9000000", "500000", "20000", "1000", null]);
});

test("the card keeps its three columns and shows stage, quantity with unit, and estimate", () => {
  const section = createItemsSummary({ workspace: {
    resources: [material, machine],
    estimateLines: [
      line("r-steel", { originalQuantity: "860416.2200", originalUnitPriceIRR: "1400000", activityExternalId: "1.9.4.2" }),
      line("r-crane", { activityExternalId: "1.5.1.1" }),
    ],
  } });
  assert.equal(section.className, "overview-card prices-summary items-summary", "the card's classes are unchanged");
  const headers = [...section.querySelectorAll("th")].map((th) => th.textContent);
  assert.equal(headers.length, 3);
  assert.deepEqual(headers, ["قلم هزینه", "مقدار", "مبلغ برآورد (تومان)"]);
  const rows = [...section.querySelectorAll("tbody tr")];
  assert.equal(rows.length, 2);
  const [steel, crane] = rows;
  assert.equal(steel.querySelector(".items-summary__stage").textContent, "1.9.4");
  assert.equal(steel.querySelector(".prices-summary__name").title, "1.9.4 · آهن آلات");
  assert.equal(steel.querySelector(".prices-summary__price").textContent, "۸۶۰٬۴۱۶٫۲۲ کیلوگرم");
  assert.equal(steel.querySelector(".prices-summary__trend").textContent, "۱۲۰٬۴۵۸٬۲۷۰٬۸۰۰");
  /* No quantity: a dash, and no unit beside it. */
  assert.equal(crane.querySelector(".prices-summary__price").textContent, "—");
  assert.equal(crane.querySelector(".prices-summary__trend").textContent, "—");
  /* Every cell still carries the classes the shared card layout sizes by. */
  for (const row of rows) {
    assert.ok(row.querySelector("td.prices-summary__name"));
    assert.ok(row.querySelector("td.prices-summary__price"));
    assert.ok(row.querySelector("td.prices-summary__trend"));
  }
});

test("an empty workspace and an error keep their notices", () => {
  assert.match(createItemsSummary({ workspace: { resources: [], estimateLines: [] } }).textContent,
               /هنوز قلم برآوردی/);
  /* The notice carries the presenter's message for a 503, not its title. */
  assert.match(createItemsSummary({ error: { status: 503, code: "X", message: "" } }).textContent,
               /دوباره تلاش کنید/);
});
