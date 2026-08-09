import test from "node:test";
import assert from "node:assert/strict";
import { compareDecimalStrings } from "../../src/shared/validation/decimal-validation.js";

test("compares exact decimal strings without floating point conversion", () => {
  assert.equal(compareDecimalStrings("9000.0000", "8500"), 1);
  assert.equal(compareDecimalStrings("0.1000", "0.1"), 0);
  assert.equal(compareDecimalStrings("999999999999999999.99", "999999999999999999.98"), 1);
  assert.equal(compareDecimalStrings("12.0001", "12.0010"), -1);
});
