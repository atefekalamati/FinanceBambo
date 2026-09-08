import test from "node:test";
import assert from "node:assert/strict";
import {
  amountChange, estimateAmount, scheduleCostOf,
} from "../../src/features/financial-items/financial-items-presentation.js";
import { createApiFinancialItemsAdapter } from "../../src/adapters/api/financial-items-api-adapter.js";

/**
 * An amount is a product, and actual cost is a payment.
 *
 * Neither is a figure anyone may supply from elsewhere: an amount exists only
 * where both a quantity and a unit price do, and an actual cost only where a
 * confirmed invoice names the line. The schedule's cost for the activity is
 * near both of them on the page and is neither of them.
 */

const context = { organizationId: "org-1", projectId: "terrace" };

const resource = {
  id: "r-1", type: "material", code: "MPP-R98", title: "بتن 400", baseUnit: "m3",
  dimension: "volume", externalResourceId: null, sourceResourceUid: 98,
  createdBy: "u", createdAt: "2026-01-01",
};
const activities = [{ activityExternalId: "1.6", taskExternalId: "500", title: "اصلاح هندسی بلوار شاهنامه",
  wbsCode: "1.6", mppTaskCostIrr: "1352000000", status: "active" }];

function stub(line, prices = []) {
  return {
    request(path) {
      if (path.endsWith("/resources")) return Promise.resolve([resource]);
      if (path.endsWith("/estimate-lines")) return Promise.resolve([line]);
      if (path.includes("/activities?")) {
        return Promise.resolve({ items: activities, page: 1, pageSize: 200, totalItems: 1, totalPages: 1 });
      }
      if (path.includes("/prices/current?")) return Promise.resolve(prices);
      if (path.endsWith("/unit-registry")) return Promise.resolve({ items: [] });
      throw new Error(`unexpected request ${path}`);
    },
  };
}

const line = (extra = {}) => ({
  id: "l-1", resourceId: "r-1", activityExternalId: "1.6", assignmentExternalId: "3001",
  sourceAssignmentUid: 3001, sourceTaskUid: 500, originalQuantity: null, revisedQuantity: null,
  originalUnitPriceIrr: null, actualCostIrr: null, source: "progress_feed", revision: 0,
  revisions: [], ...extra,
});

test("an amount exists only where both a quantity and a unit price do", () => {
  assert.equal(estimateAmount("120", "85000"), "10200000");
  assert.equal(estimateAmount(null, "85000"), null, "no quantity, no amount");
  assert.equal(estimateAmount("120", null), null, "no price, no amount");
  assert.equal(estimateAmount(null, null), null);
});

test("a real zero quantity produces a real zero amount", () => {
  assert.equal(estimateAmount("0", "500"), "0");
  assert.equal(estimateAmount("120", "0"), "0");
});

test("the arithmetic stays exact at rial magnitudes a float would round", () => {
  assert.equal(estimateAmount("9600", "75000"), "720000000");
  assert.equal(estimateAmount("10.5", "3.25"), "34.125");
  assert.equal(estimateAmount("1234567.8901", "98765.4321"), "121932631122.51181221");
});

test("a change is reported only when both amounts are known", () => {
  assert.equal(amountChange("10200000", "13340000"), "3140000");
  assert.equal(amountChange("13340000", "10200000"), "-3140000");
  assert.equal(amountChange(null, "13340000"), null);
  assert.equal(amountChange("10200000", null), null);
});

test("the schedule's cost for the activity never becomes the line's amount", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub(line())).getWorkspace();
  const [only] = workspace.estimateLines;
  assert.equal(scheduleCostOf(only), "1352000000", "the activity's figure is present");
  assert.equal(estimateAmount(only.originalQuantity, only.originalUnitPriceIRR), null,
    "and the line's amount stays unknown beside it");
  assert.equal(estimateAmount(only.revisedQuantity, only.currentUnitPriceIRR), null);
});

test("actual cost comes from confirmed invoices and is null when none name the line", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub(line())).getWorkspace();
  assert.equal(workspace.estimateLines[0].actualCostIRR, null);
  assert.notEqual(workspace.estimateLines[0].actualCostIRR, 0);
  assert.notEqual(workspace.estimateLines[0].actualCostIRR, "0");
});

test("an actual cost the invoices really state is carried through unchanged", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub(line({ actualCostIrr: "15568010000" })))
    .getWorkspace();
  assert.equal(workspace.estimateLines[0].actualCostIRR, "15568010000");
});

test("an actual cost of exactly zero is a real zero and stays visible", async () => {
  // Invoice lines that cancel out sum to zero. That is a recorded fact, unlike
  // the absence above, and the page must not turn it back into an em-dash.
  const workspace = await createApiFinancialItemsAdapter(context, stub(line({ actualCostIrr: "0" })))
    .getWorkspace();
  assert.equal(workspace.estimateLines[0].actualCostIRR, "0");
});

test("the schedule's cost is never read as an actual cost", async () => {
  const workspace = await createApiFinancialItemsAdapter(context, stub(line())).getWorkspace();
  const [only] = workspace.estimateLines;
  assert.equal(scheduleCostOf(only), "1352000000");
  assert.equal(only.actualCostIRR, null, "a plan is not a payment");
});

test("a priced line amounts to quantity times the price in force today", async () => {
  const workspace = await createApiFinancialItemsAdapter(
    context,
    stub(line({ originalQuantity: "120.0000", revisedQuantity: "145.0000", originalUnitPriceIrr: "85000" }),
         [{ resourceId: "r-1", currentPriceIrr: "92000", scopeKind: "project" }]),
  ).getWorkspace();
  const [only] = workspace.estimateLines;
  // Trailing zeros from the quantity's scale are dropped: the value is the same
  // number, and a rial figure printed with four decimal places reads as a defect.
  assert.equal(estimateAmount(only.originalQuantity, only.originalUnitPriceIRR), "10200000");
  assert.equal(estimateAmount(only.revisedQuantity, only.currentUnitPriceIRR), "13340000");
  assert.equal(amountChange("10200000.0000", "13340000.0000"), "3140000");
});
