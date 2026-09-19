import test from "node:test";
import assert from "node:assert/strict";

import {
  AMOUNT_MODES,
  ESTIMATE_LINE_TOTAL_SUPPORTED,
  amountModesFor,
  availableAmountModes,
  statesTotal,
  validateInvoiceLine,
} from "../../src/features/invoices/invoices-validation.js";
import { createMockInvoicesAdapter } from "../../src/adapters/mock/invoices-adapter.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/* An estimate line may be billed either way.
 *
 * A delivery note states a quantity and a rate — twelve tonnes at eight hundred thousand —
 * and the site multiplies them. A contractor's bill for the same activity states one number
 * and no breakdown, and the person holding it should not have to invent a rate so the form
 * will accept it.
 *
 * The service has always taken either: `InvoiceLineCreate` refuses only the COMBINATION,
 * and `services/invoices.py` reads a stated amount as the raw amount. So this was a
 * question the interface was not asking, not a capability it lacked.
 */

const chr10 = String.fromCharCode(10);

const ESTIMATE = Object.freeze({
  targetId: "t-rebar", targetType: "estimate_line", label: "آرماتوربندی · میلگرد",
  unit: "kg", estimateLineId: "line-1", resourceId: "resource-rebar",
});

const GENERAL = Object.freeze({
  targetId: "t-permit", targetType: "general_cost", label: "هزینه مجوز",
  unit: null, estimateLineId: null, resourceId: "resource-permit",
});

test("an estimate line has both shapes; a general cost has one", () => {
  /* A general cost has no quantity to state, so «مقدار × قیمت واحد» is not a shape it has.
     A menu with one option in it is a question with one answer. */
  assert.deepEqual(amountModesFor(ESTIMATE).map((m) => m.value),
                   [AMOUNT_MODES.COMPUTED, AMOUNT_MODES.TOTAL]);
  assert.deepEqual(amountModesFor(GENERAL).map((m) => m.value), [AMOUNT_MODES.TOTAL]);
});

test("a shape the service refuses is offered, marked, and never sent", () => {
  /* `services/invoices.py:67` refuses a stated amount unless the resource is a general
     cost. The shape is still SHOWN, carrying that reason -- somebody billing a lump sum
     needs to see it exists and what stands in its way -- and `availableAmountModes` is what
     anything sending a request must ask. */
  const total = amountModesFor(ESTIMATE).find((m) => m.value === AMOUNT_MODES.TOTAL);
  assert.equal(total.available, ESTIMATE_LINE_TOTAL_SUPPORTED);
  if (!ESTIMATE_LINE_TOTAL_SUPPORTED) {
    assert.match(total.reason, /سرویس/);
    assert.deepEqual(availableAmountModes(ESTIMATE), [AMOUNT_MODES.COMPUTED]);
    /* And a stale selection falls back rather than producing a refused request. */
    const { values } = validateInvoiceLine(
      { quantity: "12", unitPriceIRR: "800000" }, ESTIMATE, AMOUNT_MODES.TOTAL);
    assert.equal(values.quantity, "12");
    assert.equal(values.lineAmountIRR, "");
  }
  /* A general cost is unaffected: its one shape is the one the service takes. */
  assert.deepEqual(availableAmountModes(GENERAL), [AMOUNT_MODES.TOTAL]);
});

test("billed as one figure, a line carries no quantity and no rate", () => {
  /* Written against the general cost, which is the target the service takes a total on
     today. The moment `ESTIMATE_LINE_TOTAL_SUPPORTED` is true this holds for an estimate
     line too, by the same code path -- the shape never depended on the target's type. */
  const { valid, values } = validateInvoiceLine(
    { amountIRR: "5000000", description: "صورت‌وضعیت پیمانکار" }, GENERAL, AMOUNT_MODES.TOTAL);
  assert.equal(valid, true);
  assert.equal(values.lineAmountIRR, "5000000");
  /* Explicitly null, not absent. The service refuses an amount sent beside a quantity, and
     «I left it out» and «I sent nothing» must not be two different requests. */
  assert.equal(values.quantity, null);
  assert.equal(values.unit, null);
  assert.equal(values.unitPriceIRR, null);
  assert.equal(values.targetType, "general_cost");
});

test("billed as a quantity, the same line keeps working exactly as before", () => {
  const { valid, values } = validateInvoiceLine(
    { quantity: "12", unitPriceIRR: "800000", description: "" }, ESTIMATE, AMOUNT_MODES.COMPUTED);
  assert.equal(valid, true);
  assert.equal(values.quantity, "12", "normalised, not padded — unchanged from before");
  assert.equal(values.unitPriceIRR, "800000");
  assert.equal(values.unit, "kg");
  assert.equal(values.lineAmountIRR, "", "the site multiplies; the line states no total");
});

test("a general cost is billed as a total whatever mode it is handed", () => {
  /* The shape is not a preference there. Handing it the other mode must not produce a line
     asking for a quantity that does not exist. */
  for (const mode of [AMOUNT_MODES.COMPUTED, AMOUNT_MODES.TOTAL, null, "nonsense"]) {
    const { valid, values } = validateInvoiceLine({ amountIRR: "250000" }, GENERAL, mode);
    assert.equal(valid, true, `mode ${mode}`);
    assert.equal(values.lineAmountIRR, "250000");
    assert.equal(values.quantity, null);
  }
});

test("each mode is judged on what it actually asked for", () => {
  const missingAmount = validateInvoiceLine({ amountIRR: "0" }, GENERAL, AMOUNT_MODES.TOTAL);
  assert.equal(missingAmount.valid, false);
  assert.ok(missingAmount.errors.amountIRR, "a total of nothing is not a total");

  const missingRate = validateInvoiceLine({ quantity: "12", unitPriceIRR: "" }, ESTIMATE, AMOUNT_MODES.COMPUTED);
  assert.equal(missingRate.valid, false);
  assert.ok(missingRate.errors.unitPriceIRR);
  /* And the quantity is NOT complained about in total mode, which is the whole point. */
  assert.equal(validateInvoiceLine({ amountIRR: "1" }, GENERAL, AMOUNT_MODES.TOTAL).errors.quantity,
               undefined);
});

test("what a line states is read from the line, never from its target's type", () => {
  assert.equal(statesTotal({ lineAmountIRR: "500" }), true);
  assert.equal(statesTotal({ lineAmountIRR: "" }), false);
  assert.equal(statesTotal({ lineAmountIRR: "0" }), false, "zero is not an amount");
  assert.equal(statesTotal({ quantity: "12", unitPriceIRR: "800000" }), false);
  assert.equal(statesTotal({}), false);
});

test("an invoice mixing both shapes comes to the sum of them", async () => {
  /* The end of the chain: what the service is asked for, and what it answers. */
  const context = { organizationId: "org-1", projectId: "p-1", userId: "user-1",
                    permissionCodes: ["finance.view", "finance.edit"] };
  const adapter = createMockInvoicesAdapter(context, { initialState: "success" });
  const targets = await adapter.getInvoiceTargets();
  const estimate = targets.find((t) => t.targetType === "estimate_line");
  const other = targets.filter((t) => t.targetType === "estimate_line")[1];

  const created = await adapter.createDraft({
    header: { invoiceDate: "2026-09-19", vendorName: "پیمانکار", description: "" },
    lines: [
      // quantity × rate: 10 × 100,000 = 1,000,000
      { targetId: estimate.targetId, targetType: "estimate_line", targetLabel: estimate.label,
        quantity: "10.0000", unit: estimate.unit, unitPriceIRR: "100000", lineAmountIRR: "", description: "" },
      // and one figure off the document, against an estimate line all the same
      { targetId: other.targetId, targetType: "estimate_line", targetLabel: other.label,
        quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: "750000", description: "صورت‌وضعیت" },
    ],
    adjustments: { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" },
    duplicateOverrideReason: "",
    idempotencyKey: "mixed-shapes-1",
  });

  assert.equal(created.finalAmountIRR, "1750000");
  const [byQuantity, byTotal] = created.lines;
  assert.equal(byQuantity.lineAmountIRR, "1000000");
  assert.equal(byTotal.lineAmountIRR, "750000",
               "an estimate line billed as one figure is not multiplied by anything");
});

test("the control exists before anything paints with it", () => {
  /* `paintTargets()` runs on the way into the line step and calls `paintAmountFields`,
     which reads the mode control. Declared BELOW that call, opening the step threw on a
     `const` still in its temporal dead zone and the editor never rendered at all -- a
     crash no unit test here could see, because they all call the validator directly.
     Caught by driving the real form; pinned by reading the order. */
  const source = readFileSync(
    fileURLToPath(new URL("../../src/features/invoices/invoices-page.js", import.meta.url)), "utf8");
  const body = source.split("function renderLinesStep()")[1] ?? "";
  const step = body.split(chr10 + "  function ")[0];
  const declared = step.indexOf("const modeSelect");
  const firstPaint = step.indexOf("paintTargets();");
  assert.ok(declared > 0 && firstPaint > 0, "the step no longer looks like this");
  assert.ok(declared < firstPaint,
            "the amount-mode control must be declared before the first paint reads it");
});
