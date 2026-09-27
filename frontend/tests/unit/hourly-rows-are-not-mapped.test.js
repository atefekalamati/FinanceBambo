import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { installDom } from "../helpers/dom.js";

installDom();

const { HOURLY_RATE_WORDING, isHourlyRate } =
  await import("../../src/features/financial-items/financial-items-presentation.js");
const { createManualPriceDialog } =
  await import("../../src/features/financial-items/manual-price-dialog.js");

const PAGE_SOURCE = readFileSync(
  fileURLToPath(new URL("../../src/features/financial-items/financial-items-page.js", import.meta.url)),
  "utf8");

/* A CREW OR A MACHINE IS NOT LINKED TO THE SHEET; IT IS PRICED BY THE HOUR.
 *
 * Reported 2026-09-27: «نیرو و تجهیزات جزو دسته‌بندی‌ها نیستند و نمی‌شود ... به قلم‌ها
 * متصل کرد». They never could be. The link panel searches supplier listings, and a
 * machine's rate is a price version somebody set, not a listing. What was wrong is that
 * every hourly row still offered the link, opened the panel, and wore «وصل نشده».
 */

test("the kind `work` is hourly, and so are the two names it used to have", () => {
  assert.equal(isHourlyRate({ type: "work" }), true);
  assert.equal(isHourlyRate({ type: "labor" }), true, "a row stored before 0038");
  assert.equal(isHourlyRate({ type: "equipment" }), true, "a row stored before 0038");
  assert.equal(isHourlyRate({ type: "material" }), false);
  assert.equal(isHourlyRate({ type: "general_cost" }), false);
  assert.equal(isHourlyRate(null), false);
});

test("the link button is guarded by the hourly test in the one place it is made", () => {
  const branch = PAGE_SOURCE.split('dataset.action = "map-price"')[0].split("\n").slice(-12).join("\n");
  assert.match(branch, /!isHourlyRate\(resource\)/,
               "«اتصال به قیمت روز» must not be offered to an hourly row");
});

test("the three cells an hourly row differs in all read the shared wording", () => {
  for (const key of ["sheetUnit", "unpriced", "set", "edit", "method"]) {
    assert.match(PAGE_SOURCE, new RegExp(`HOURLY_RATE_WORDING\\.${key}\\b`), key);
  }
  /* And the chip: `needs_components` on an hourly row is not a state a person can fix. */
  assert.match(PAGE_SOURCE, /priced\.status !== "ready" && !manualOnly && !hourly/);
});

test("the manual-price dialog greets an hourly row with the hourly heading", () => {
  const machine = { resourceId: "r", type: "work", title: "جرثقیل", baseUnit: "hour" };
  const adapter = { setManualPrice: async () => ({}) };
  const heading = (options) => createManualPriceDialog({ line: { lineId: "l" }, adapter, ...options })
    .element.querySelector("h2").textContent;
  assert.equal(heading({ resource: machine }), HOURLY_RATE_WORDING.set);
  assert.equal(heading({ resource: machine, current: "100" }), HOURLY_RATE_WORDING.edit);
  assert.equal(heading({ resource: { ...machine, type: "material" } }), "ثبت دستی قیمت روز",
               "a material keeps its wording");
});
