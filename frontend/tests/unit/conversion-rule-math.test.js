import test from "node:test";
import assert from "node:assert/strict";

import { convertedUnitPriceIRR, lineCostIRR, occupantsOf, occupiedBy, rational,
         roundToInteger, rulesForCrossing } from "../../src/features/financial-items/conversion-rule-math.js";

/* The arithmetic this module exists to get right, checked against the SERVER's own.
 *
 * `daily_estimate.convert_daily_unit_price` states the convention once:
 *
 *     a rule says      1 from_unit = factor × to_unit
 *     a price converts price per from_unit ÷ factor
 *
 * Every case below is a number that path produces, or would produce. If these tests and
 * that function ever disagree, the dialog is showing somebody a price they will not get,
 * which is worse than showing them nothing.
 */

const SHEET_PRICE = "932000";   // rials per kilogram, from the live listing this was built for

test("the direction the resolver asks in divides", () => {
  /* «۱ کیلوگرم = ۱٫۲ شاخه» against a price per kilogram. The live server answered this
     exact row with conversionMultiplier 1.2 and 932000/1.2 rials per branch. */
  assert.equal(convertedUnitPriceIRR({
    priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "branch",
    statedFrom: "kg", statedTo: "branch", factor: "1.2",
  }), "776667");
});

test("the direction a person actually knows multiplies", () => {
  /* «۱ شاخه = ۲۲ کیلوگرم» against a price per kilogram: a branch costs twenty-two
     kilograms' worth. Stated the other way the same claim is 1/22, and the server divides
     by it — the same number, reached without ever writing 0.0454545 down. */
  assert.equal(convertedUnitPriceIRR({
    priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "branch",
    statedFrom: "branch", statedTo: "kg", factor: "22",
  }), "20504000");
});

test("the two directions of one claim give the same price", () => {
  /* The property that matters: which way somebody writes a rule must not change what it
     produces. Stated backwards and rounded to twelve places — the column's own precision —
     the two answers differ by less than a rial on a twenty-million-rial price. */
  const said = convertedUnitPriceIRR({
    priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "branch",
    statedFrom: "branch", statedTo: "kg", factor: "22" });
  const typed = convertedUnitPriceIRR({
    priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "branch",
    statedFrom: "kg", statedTo: "branch", factor: "0.045454545455" });
  assert.equal(said, "20504000");
  assert.ok(Math.abs(Number(said) - Number(typed)) < 1,
            `stating it backwards gave ${typed} and forwards gave ${said}`);
});

test("a rule about two other units prices nothing", () => {
  /* Not zero, and not the price unchanged. A rule that does not bridge THESE units has
     nothing to say about this row, and a number here would be invented. */
  assert.equal(convertedUnitPriceIRR({
    priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "branch",
    statedFrom: "ton", statedTo: "kg", factor: "1000",
  }), null);
});

test("a zero or unreadable factor is no factor, never a division by zero", () => {
  for (const factor of ["0", "0.0", "", "-4", "abc", null, undefined, "1e3"]) {
    assert.equal(convertedUnitPriceIRR({
      priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "branch",
      statedFrom: "branch", statedTo: "kg", factor,
    }), null, `factor ${JSON.stringify(factor)} must produce no price`);
  }
});

test("two units that are the same need no rule and get no price", () => {
  assert.equal(convertedUnitPriceIRR({
    priceIRR: SHEET_PRICE, sourceUnit: "kg", selectedUnit: "kg",
    statedFrom: "kg", statedTo: "kg", factor: "1",
  }), null);
});

test("the money is exact, not floating point", () => {
  /* 0.1 + 0.2 is the reason this module is built on BigInt. A price of 1 rial through a
     factor of 0.1 is exactly 10, not 9.999999999999998. */
  assert.equal(convertedUnitPriceIRR({
    priceIRR: "1", sourceUnit: "kg", selectedUnit: "bag",
    statedFrom: "kg", statedTo: "bag", factor: "0.1",
  }), "10");
  /* And a price big enough to leave the range a double can count in whole numbers. */
  assert.equal(convertedUnitPriceIRR({
    priceIRR: "9007199254740993", sourceUnit: "kg", selectedUnit: "bag",
    statedFrom: "bag", statedTo: "kg", factor: "3",
  }), "27021597764222979");
});

test("rounding is half-up, where a person would put it", () => {
  assert.equal(roundToInteger(rational("2.5")), "3");
  assert.equal(roundToInteger(rational("2.4")), "2");
  assert.equal(roundToInteger(rational("2.49999")), "2");
});

test("the row's cost is its quantity at the converted price", () => {
  assert.equal(lineCostIRR({ unitPriceIRR: "20504000", quantity: "3538.11" }),
               "72545407440");
  assert.equal(lineCostIRR({ unitPriceIRR: "20504000", quantity: null }), null,
               "a quantity nobody knows must not become one");
});

/* WHICH RULE IS IN THE WAY.
 *
 * Deliberately NOT the server's precedence. That decides which of several rules wins, and
 * a second implementation of it would eventually disagree with the first. This answers the
 * narrower question the person can act on: is the slot I am writing into already taken?
 */

const RULES = Object.freeze([
  { id: "r-org", scopeType: "organization", fromUnit: "branch", toUnit: "kg",
    factorValue: "22", status: "approved", version: 1, effectiveTo: null },
  { id: "r-item", scopeType: "provider_item", fromUnit: "kg", toUnit: "branch",
    factorValue: "1.2", status: "approved", version: 1, effectiveTo: null,
    providerItemId: "item-1" },
  { id: "r-other-item", scopeType: "provider_item", fromUnit: "kg", toUnit: "branch",
    factorValue: "9", status: "approved", version: 1, effectiveTo: null,
    providerItemId: "item-2" },
  { id: "r-closed", scopeType: "project", fromUnit: "kg", toUnit: "branch",
    factorValue: "3", status: "approved", version: 1, effectiveTo: "2026-01-01" },
]);

const CROSSING = { fromUnit: "kg", toUnit: "branch" };

test("a rule written the other way round still occupies the scope", () => {
  /* The whole reason the server refuses it: branch→kg and kg→branch at one scope are two
     live answers to one question, and 22 and 0.05 are not each other's inverse. Finding it
     here means the person is offered a replacement instead of a refusal. */
  const found = occupiedBy(RULES, { ...CROSSING, scopeType: "organization" });
  assert.equal(found?.id, "r-org");
});

test("a narrow rule occupies the scope only for the thing it is about", () => {
  assert.equal(occupiedBy(RULES, { ...CROSSING, scopeType: "provider_item",
                                   providerItemId: "item-1" })?.id, "r-item");
  assert.equal(occupiedBy(RULES, { ...CROSSING, scopeType: "provider_item",
                                   providerItemId: "item-3" }), null,
               "another listing's weighing is not in this listing's way");
});

test("a closed rule is not in anybody's way", () => {
  assert.equal(occupiedBy(RULES, { ...CROSSING, scopeType: "project" }), null);
});

test("an empty scope is empty", () => {
  assert.equal(occupiedBy(RULES, { ...CROSSING, scopeType: "global" }), null);
  assert.equal(occupiedBy([], { ...CROSSING, scopeType: "organization" }), null);
  assert.equal(occupiedBy(undefined, { ...CROSSING, scopeType: "organization" }), null);
});

test("a draft occupies the scope too", () => {
  /* Two drafts in opposite directions are a conflict waiting for somebody to approve both.
     The server counts them, and a dialog that did not would offer to write the second. */
  const drafts = [{ id: "d", scopeType: "project", fromUnit: "branch", toUnit: "kg",
                    factorValue: "22", status: "draft", effectiveTo: null }];
  assert.equal(occupiedBy(drafts, { ...CROSSING, scopeType: "project" })?.id, "d");
});

test("the crossing's rules are listed narrowest first, both directions, live only", () => {
  const listed = rulesForCrossing(RULES, CROSSING).map((rule) => rule.id);
  assert.deepEqual(listed, ["r-item", "r-other-item", "r-org"]);
});

test("rules about other units are not listed", () => {
  const listed = rulesForCrossing(
    [...RULES, { id: "r-ton", scopeType: "global", fromUnit: "ton", toUnit: "kg",
                 factorValue: "1000", status: "approved", effectiveTo: null }],
    CROSSING).map((rule) => rule.id);
  assert.ok(!listed.includes("r-ton"));
});

test("a scope holding two live rules reports both, approved first", () => {
  /* Measured on the live project: one listing held an approved kg→branch AND an approved
     branch→kg, written before the server started refusing the pair. Replacing one of them
     leaves the other in force, and the new rule is then refused by the unique index. */
  const both = [
    { id: "d", scopeType: "provider_item", fromUnit: "kg", toUnit: "branch",
      factorValue: "5", status: "draft", effectiveTo: null, providerItemId: "item-1" },
    { id: "a1", scopeType: "provider_item", fromUnit: "kg", toUnit: "branch",
      factorValue: "1.2", status: "approved", effectiveTo: null, providerItemId: "item-1" },
    { id: "a2", scopeType: "provider_item", fromUnit: "branch", toUnit: "kg",
      factorValue: "20", status: "approved", effectiveTo: null, providerItemId: "item-1" },
  ];
  const held = occupantsOf(both, { ...CROSSING, scopeType: "provider_item",
                                   providerItemId: "item-1" });
  assert.deepEqual(held.map((rule) => rule.status),
                   ["approved", "approved", "draft"],
                   "what is in force has to be closed first and named first");
  assert.deepEqual(held.map((rule) => rule.id).slice(0, 2).sort(), ["a1", "a2"]);
  assert.equal(occupiedBy(both, { ...CROSSING, scopeType: "provider_item",
                                  providerItemId: "item-1" }).status, "approved",
               "a draft must never be the one named as the rule in force");
});
