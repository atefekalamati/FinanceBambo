import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PRIMARY, SECONDARY, IDENTITY, defaultVisibleColumns } from "../../src/shared/components/data-table.js";

const source = readFileSync(
  fileURLToPath(new URL("../../src/shared/components/data-table.js", import.meta.url)),
  "utf8",
);

const COLUMNS = Object.freeze([
  { key: "name", label: "نام", tier: IDENTITY },
  { key: "amount", label: "مبلغ", tier: PRIMARY },
  { key: "unit", label: "واحد", tier: SECONDARY, keepOnTablet: true },
  { key: "note", label: "یادداشت", tier: SECONDARY },
]);

const at = (width) => (query) => ({
  matches: query === "(max-width: 36rem)" ? width <= 576 : width <= 1024,
});

test("a tier decides which columns a width starts with", () => {
  assert.deepEqual([...defaultVisibleColumns(COLUMNS, at(1440))], ["name", "amount", "unit", "note"]);
  // Tablet keeps the secondary column that asked to stay.
  assert.deepEqual([...defaultVisibleColumns(COLUMNS, at(900))], ["name", "amount", "unit"]);
  assert.deepEqual([...defaultVisibleColumns(COLUMNS, at(390))], ["name", "amount"]);
});

test("the width is asked again on every render, not once per page", () => {
  // The bug this replaced: defaultVisibleColumns was called once, so a table
  // opened on a desktop and turned to a phone kept nine columns -- 1584px of
  // them inside a 335px screen. The render reads the width now.
  assert.match(source, /const shown = effectiveColumns\(columns, visible\)/);
  assert.match(source, /function effectiveColumns\(columns, visible\)/);
  assert.match(source, /CHOSEN_BY_READER\.has\(visible\) \? visible : defaultVisibleColumns\(columns\)/);
});

test("the breakpoint watcher is registered once and closes over nothing", () => {
  // Two earlier attempts registered a listener per table and per visible-Set.
  // Both leaked: with forced collection, 23 listeners and 634 nodes became 540
  // and 8644 over three navigation cycles, because the callback held the
  // columns and the columns held the detached tree. A matchMedia listener lives
  // as long as the page and there is no unmount hook here to remove one, so the
  // only safe number of them is a constant.
  assert.match(source, /let watchingTiers = false/);
  assert.match(source, /if \(watchingTiers \|\| typeof globalThis\.matchMedia !== "function"\) return/);
  assert.match(source, /watchingTiers = true/);
  // It finds its work in the document rather than in a closure.
  assert.match(source, /document\.querySelectorAll\("table\[data-tiered\]"\)/);
  // And takes no arguments, so it cannot be given something to hold.
  assert.match(source, /function reapplyTierDefaults\(\) \{/);
});

test("the tier travels on the element, because that is all the watcher can see", () => {
  assert.match(source, /cell\.dataset\.tier = columns\[index\]\.tier/);
  assert.match(source, /cell\.dataset\.keepTablet = "true"/);
  assert.match(source, /table\.dataset\.tiered = "true"/);
});

test("a reader's choice outranks the width, and is recorded where both can read it", () => {
  // Twice on purpose: in the Set for the next render, and on the element for
  // the watcher, which reads the document and cannot see a Set.
  assert.match(source, /CHOSEN_BY_READER\.add\(visible\)/);
  assert.match(source, /node\.dataset\.columnsChosen = "true"/);
  assert.match(source, /if \(table\.dataset\.columnsChosen === "true"\) return/);
  // Weak, so a Set belonging to a page that has gone away is not held here.
  assert.match(source, /const CHOSEN_BY_READER = new WeakSet\(\)/);
});

test("the chooser reads its ticks back from the table it is about", () => {
  // The watcher changes a table on a rotation and holds no reference to the
  // inputs -- that is what keeps it from leaking -- so the chooser must ask the
  // element, or it shows eight ticks over a three-column table.
  assert.match(source, /function syncBoxes\(\)/);
  assert.match(source, /function open\(\) \{\s*syncBoxes\(\);/);
  assert.match(source, /box\.checked = !cell\.hidden/);
});
