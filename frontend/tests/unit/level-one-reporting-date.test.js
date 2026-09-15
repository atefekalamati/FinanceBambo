/**
 * Which day the phase report is read at.
 *
 * A snapshot and a reporting date are two different facts. The snapshot says which
 * PROGRESS facts to use -- how far the work had got when that schedule was saved. The
 * reporting date is the FINANCIAL cutoff: which estimates and which confirmed documents
 * are effective. The finance home page has always said so in its own comment, and read at
 * today while pinning progress to the chosen snapshot.
 *
 * The phase report read at the SNAPSHOT'S date instead, and that is a different question:
 * "what was the estimate on 2025-10-02" -- before any of these lines existed. The honest
 * answer to that question is nothing, so the service answered nothing, and every phase
 * showed «—» on a page reached by clicking a figure of 3,607,438,967,777 rial.
 *
 * Measured on bambo_canonical_test, same project and same source version:
 *
 *     reportingDate=2025-10-02  ->  totals null, 0 of 13 phases state an estimate
 *     reportingDate=2026-09-15  ->  totals 3,607,438,967,777, 8 of 13 state one
 *
 * This is a source-level test on purpose. The page is a large render that needs adapters,
 * a chart and a router; what must never come back is the one LINE that chose the date, and
 * that is what this reads.
 */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const SOURCE = readFileSync(
  fileURLToPath(new URL("../../src/features/level-one/level-one-page.js", import.meta.url)),
  "utf8");
const HOME = readFileSync(
  fileURLToPath(new URL("../../src/features/finance-home/finance-home-page.js", import.meta.url)),
  "utf8");

test("the phase report is read at today, not at the snapshot's own date", () => {
  const request = SOURCE.split("const request = {")[1].split("};")[0];
  assert.match(request, /reportingDate:\s*getTehranTodayIso\(\)/,
               "the financial cutoff is today");
  assert.doesNotMatch(request, /reportingDate:\s*snapshot\.reportingDate/,
                      "the snapshot's date is not the financial cutoff");
});

test("the snapshot still decides which progress facts are used", () => {
  // Today is the money question; the snapshot is still the progress question. Dropping it
  // would make the drilldown read a different schedule from the page above it.
  const request = SOURCE.split("const request = {")[1].split("};")[0];
  assert.match(request, /progressSnapshotId:\s*snapshot\.progressSnapshotId/);
});

test("the page above and the page below ask for the same day", () => {
  // The two pages disagreeing is the whole defect: one showed 3.6 trillion and the other,
  // one click away, showed an em dash in every row.
  for (const source of [SOURCE, HOME]) {
    assert.ok(source.includes("getTehranTodayIso()"),
              "both pages read the estimate at today");
  }
});

test("the provenance line names the date the figures were read at", () => {
  // It used to print the snapshot's date beside amounts read at another one, which names
  // a day the numbers are not from.
  const block = SOURCE.split("function renderProvenance(")[1].split("\n  }")[0];
  assert.match(block, /تاریخ گزارش: \$\{formatBusinessDate\(data\.reportingDate\)\}/,
               "the report date shown is the one the request used");
  assert.ok(block.includes("وضعیت برنامه زمانی"),
            "and the schedule's own date is named separately, not instead");
});
