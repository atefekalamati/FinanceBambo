import test from "node:test";
import assert from "node:assert/strict";
import { normalizeDecimalInput, validateEffectiveDate, validateGrossBuiltArea, validateSettingsRevision } from "../../src/features/settings/settings-validation.js";

test("normalizes Persian digits without floating point conversion", () => {
  assert.equal(normalizeDecimalInput("۴٬۲۵۰٫۱۲۵۰"), "4250.1250");
});

test("accepts positive exact areas and rejects zero or excessive precision", () => {
  assert.deepEqual(validateGrossBuiltArea("004250.1200"), { valid: true, value: "4250.1200", message: "" });
  assert.equal(validateGrossBuiltArea("0.0001").valid, true);
  assert.equal(validateGrossBuiltArea("0.0000").valid, false);
  assert.equal(validateGrossBuiltArea("12.12345").valid, false);
});

test("rejects impossible effective dates", () => {
  assert.equal(validateEffectiveDate("2026-02-28").valid, true);
  assert.equal(validateEffectiveDate("2026-02-31").valid, false);
});

test("requires a non-empty audited reason", () => {
  const result = validateSettingsRevision({ grossBuiltArea: "4250", effectiveDate: "2026-08-08", reason: "  " });
  assert.equal(result.valid, false);
  assert.match(result.errors.reason, /دلیل/);
});
