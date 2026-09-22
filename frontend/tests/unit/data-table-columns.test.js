import test from "node:test";
import assert from "node:assert/strict";

import { IDENTITY, PRIMARY, SECONDARY, defaultVisibleColumns, pagedRows, repeatedGroupColumnLabel }
  from "../../src/shared/components/data-table.js";

/** A matchMedia that answers for one viewport width, in rem at a 16px root. */
const atWidth = (pixels) => (query) => {
  const max = /max-width:\s*([\d.]+)rem/.exec(query);
  return { matches: max ? pixels <= Number(max[1]) * 16 : false };
};

const columns = [
  { key: "identity", label: "شماره", tier: IDENTITY },
  { key: "vendor", label: "فروشنده", tier: PRIMARY },
  { key: "date", label: "تاریخ", tier: SECONDARY, keepOnTablet: true },
  { key: "source", label: "منبع", tier: SECONDARY },
];

test("a desktop starts with every column", () => {
  const visible = defaultVisibleColumns(columns, atWidth(1440));
  assert.deepEqual([...visible].sort(), ["date", "identity", "source", "vendor"]);
});

test("a tablet keeps only the secondary columns that asked to stay", () => {
  const visible = defaultVisibleColumns(columns, atWidth(900));
  assert.ok(visible.has("date"), "keepOnTablet column survives the tablet width");
  assert.ok(!visible.has("source"), "a plain secondary column does not");
  assert.ok(visible.has("identity") && visible.has("vendor"));
});

test("a phone drops every secondary column, keepOnTablet included", () => {
  const visible = defaultVisibleColumns(columns, atWidth(390));
  assert.deepEqual([...visible].sort(), ["identity", "vendor"]);
});

test("the identity column is in every default, at every width", () => {
  // Reset reads this, and a reset that could drop the pinned column would
  // leave rows with nothing naming them.
  for (const width of [320, 390, 480, 768, 1024, 1440, 1920]) {
    assert.ok(defaultVisibleColumns(columns, atWidth(width)).has("identity"), `identity at ${width}`);
  }
});

test("without matchMedia the answer is the widest one, not an empty table", () => {
  assert.equal(defaultVisibleColumns(columns, undefined).size, columns.length);
});

test("an open group may repeat labels only in its otherwise-empty cells", () => {
  const amount = { key: "amount", label: "مبلغ", tier: PRIMARY };
  const actions = { key: "actions", label: ["", "عملیات"], tier: SECONDARY };

  assert.equal(repeatedGroupColumnLabel(amount, undefined, true), "مبلغ");
  assert.equal(repeatedGroupColumnLabel(actions, null, true), "عملیات");
  assert.equal(repeatedGroupColumnLabel(amount, "100", true), "");
  assert.equal(repeatedGroupColumnLabel(columns[0], undefined, true), "");
  assert.equal(repeatedGroupColumnLabel(amount, undefined, false), "");
});

test("a grouped page counts parents and keeps every child of its selected parents", () => {
  const rows = [
    { parent: "A", child: 1 },
    { parent: "A", child: 2 },
    { parent: "B", child: 3 },
    { parent: "C", child: 4 },
    { parent: "C", child: 5 },
    { parent: "C", child: 6 },
  ];
  const first = pagedRows(rows, { key: (row) => row.parent }, 0, 2);
  assert.equal(first.total, 3, "the total is three parent rows, not six children");
  assert.deepEqual(first.rows.map((row) => row.child), [1, 2, 3]);

  const second = pagedRows(rows, { key: (row) => row.parent }, 2, 2);
  assert.deepEqual(second.rows.map((row) => row.child), [4, 5, 6],
    "all children of the parent on page two stay with it");
});
