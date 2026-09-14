/**
 * Every unit the Backend defines has a Persian label on the page.
 *
 * `UNIT_REGISTRY` is described in its own source as "one place, and the only place":
 * `finance_resources` validates `base_unit` against it, `/unit-registry` publishes it, and
 * the frontend builds its unit dropdowns from that endpoint. But `formatUnitLabel` carries
 * a SECOND list, and a second list drifts. It did: the registry grew to fifteen units when
 * material-price units were coordinated and this table still had eight, so a resource
 * measured in grams, litres or millimetres rendered as «واحد تعریف‌نشده».
 *
 * That string is the page saying "I do not know this unit". Using it for a unit the system
 * does know destroys the only signal that tells a real unknown apart from a known one --
 * which is the whole reason the label exists.
 *
 * So this reads the backend registry, exactly as `api-routes-exist.test.js` reads
 * `backend/contracts/openapi.json`, and compares. The precedent matters: the alternative is
 * a frontend test asserting what the frontend already believes.
 *
 * Labels are NOT compared for wording. `day` is «روز دستگاه» here and «روز» in the
 * registry, deliberately, because this page shows equipment days. Coverage is the contract;
 * phrasing belongs to whoever renders it.
 */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { formatUnitLabel } from "../../src/shared/formatters/display.js";

const REGISTRY_SOURCE = readFileSync(
  fileURLToPath(new URL("../../../backend/app/finance/domain/unit_registry.py", import.meta.url)),
  "utf8",
);

/** The codes the backend registry declares, read from its own source. */
function registryCodes() {
  const body = REGISTRY_SOURCE.split("UNIT_REGISTRY: dict[str, UnitDefinition] = {")[1];
  assert.ok(body, "UNIT_REGISTRY is not declared the way this test reads it");
  const table = body.split("\n}")[0];
  return [...table.matchAll(/^\s*"([a-z0-9_]+)":\s*UnitDefinition\(/gm)].map((m) => m[1]);
}

test("the test can actually see the backend registry", () => {
  const codes = registryCodes();
  // Without this, a parser that silently matched nothing would make every assertion below
  // pass by having nothing to check -- the failure mode this whole file exists to catch.
  assert.ok(codes.length >= 15, `read only ${codes.length} codes from the registry`);
  for (const expected of ["kg", "m3", "each", "hour"]) {
    assert.ok(codes.includes(expected), `${expected} missing from the parsed registry`);
  }
});

test("every registry unit renders as a label rather than as «واحد تعریف‌نشده»", () => {
  const missing = registryCodes().filter((code) => formatUnitLabel(code) === "واحد تعریف‌نشده");
  assert.deepEqual(
    missing,
    [],
    "these units are defined by the Backend and have no label here, so the page calls them undefined",
  );
});

test("every registry unit renders in Persian, not as its own code", () => {
  // A label that is just the code back again is the other way this can look fine and say
  // nothing: `formatUnitLabel` returns non-Latin input unchanged, so only a Latin code
  // reaching the screen proves the lookup missed.
  const unlabelled = registryCodes().filter((code) => formatUnitLabel(code) === code);
  assert.deepEqual(unlabelled, [], "these render as their raw code");
});

test("an unknown unit still says it is unknown", () => {
  // The guard above must not be satisfied by labelling everything.
  assert.equal(formatUnitLabel("furlong"), "واحد تعریف‌نشده");
  assert.equal(formatUnitLabel("unit"), "واحد تعریف‌نشده");
});

test("no unit at all is stated as such, not as a unit", () => {
  assert.equal(formatUnitLabel(null), "بدون واحد");
  assert.equal(formatUnitLabel(""), "بدون واحد");
  assert.equal(formatUnitLabel(undefined), "بدون واحد");
});
