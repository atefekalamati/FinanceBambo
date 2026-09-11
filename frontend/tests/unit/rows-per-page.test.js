import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  ALL_ROWS_CEILING,
  DEFAULT_ROWS_PER_PAGE,
  ROW_COUNT_OPTIONS,
  clampPage,
  pageCount,
  resolveSize,
} from "../../src/shared/preferences/rows-per-page.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

test("a page size is a number to slice by, never the word the reader picked", () => {
  // "all" is what the menu says; a slice needs a count, and one that grows with
  // the list rather than a constant that would cut a longer one short.
  assert.equal(resolveSize(25, 900), 25);
  assert.equal(resolveSize("all", 80), 80);
  assert.equal(resolveSize("all", 5000), ALL_ROWS_CEILING);
  // An empty list still has a page, so the size is never zero: slicing by zero
  // returns nothing for every page and the table would read as empty forever.
  assert.equal(resolveSize("all", 0), 1);
  assert.equal(resolveSize(0, 40), DEFAULT_ROWS_PER_PAGE);
});

test("there is always a page one, even with nothing on it", () => {
  assert.equal(pageCount(0, 25), 1);
  assert.equal(pageCount(25, 25), 1);
  assert.equal(pageCount(26, 25), 2);
});

test("raising the row count lands the reader on a page that exists", () => {
  // 70 rows at ten is seven pages; at a hundred it is one. A reader on page 7
  // who switches must not be left on a page number that no longer exists.
  assert.equal(clampPage(7, 70, 10), 7);
  assert.equal(clampPage(7, 70, 100), 1);
  // And the last page rather than the first, which is nearer what they read.
  assert.equal(clampPage(7, 70, 25), 3);
  assert.equal(clampPage(0, 70, 10), 1);
});

test("the offered sizes are the ones the footer draws", () => {
  const source = read("../../src/shared/components/data-table.js");
  assert.match(source, /ROW_COUNT_OPTIONS\.forEach/);
  assert.deepEqual([...ROW_COUNT_OPTIONS], [10, 25, 50, 100, "all"]);
});

test("every table that pages keeps its page number in the page, not the component", () => {
  // paint() rebuilds the tree on every change, so a component holding its own
  // page would lose it on each repaint -- and two things remembering it would
  // disagree. The component takes the number and hands back the next one.
  const component = read("../../src/shared/components/data-table.js");
  assert.doesNotMatch(component, /let\s+currentPage/, "the component keeps page state of its own");
  assert.match(component, /export function createPagedDataTable/);
  assert.match(component, /export function createTablePagination/);

  [
    "../../src/features/prices/prices-page.js",
    "../../src/features/financial-items/financial-items-page.js",
    "../../src/features/progress/progress-page.js",
    "../../src/features/settings/settings-page.js",
  ].forEach((path) => {
    const source = read(path);
    assert.match(source, /getRowsPerPage\(/, `${path} does not read the reader's choice`);
    assert.match(source, /onChange: \(next\) =>|onChange: \(next\)=>/, `${path} never accepts a new page`);
  });
});

test("the register asks the server for its page; the others slice what they hold", () => {
  const invoices = read("../../src/features/invoices/invoices-page.js");
  // Invoices have no ceiling, so that endpoint pages server-side: both controls
  // must reload rather than re-slice, and «همه» is the endpoint's maximum.
  assert.match(invoices, /onPageChange: \(next\) => \{ filters\.page = next; load\(\); \}/);
  assert.match(invoices, /filters\.pageSize = next === "all" \? SUMMARY_PAGE_SIZE : next/);
  // The PRD opens the register at fifty, not at this module's twenty-five.
  assert.match(invoices, /getRowsPerPage\("invoices", 50\)/);
  // A stored "all" must never reach the adapter as a word: getInvoices would
  // read NaN and fall back to fifty, which is not what the reader chose.
  assert.match(invoices, /storedSize === "all" \? SUMMARY_PAGE_SIZE : storedSize/);

  // The client-side helper slices after the caller has filtered, never before.
  const component = read("../../src/shared/components/data-table.js");
  assert.match(component, /rows\.slice\(start, start \+ size\)/);
});
