import test from "node:test";
import assert from "node:assert/strict";

import { EQUIPMENT_TYPE, equipmentRows, foldPersian, groupByUnit, isPriced,
         pricingProgress, selectRows }
  from "../../src/features/settings/equipment-pricing-model.js";

/* What the equipment pricing section shows.
 *
 * The section reads the same workspace the prices page reads, so these tests are written
 * against that shape rather than a convenient one: `currentPrices` entries carrying a
 * `resource` and up to three resolved prices.
 */

const entry = (title, type, baseUnit, current = null, extra = {}) => ({
  resource: { resourceId: `r-${title}`, type, title, code: `EQ-${title}`, baseUnit },
  currentPrice: current,
  projectPrice: extra.projectPrice ?? null,
  organizationPrice: extra.organizationPrice ?? null,
  trend: {},
});

const WORKSPACE = {
  currentPrices: [
    entry("کامیون", EQUIPMENT_TYPE, "hour",
          { scope: "project", unitPriceIRR: "32000000", effectiveFrom: "2026-09-01" }),
    entry("بیل مکانیکی", EQUIPMENT_TYPE, "hour"),
    entry("جرثقیل", EQUIPMENT_TYPE, "day",
          { scope: "organization", unitPriceIRR: "520000000", effectiveFrom: "2026-08-01" }),
    entry("گریدر", EQUIPMENT_TYPE, null),
    entry("میلگرد", "material", "kg",
          { scope: "project", unitPriceIRR: "900000", effectiveFrom: "2026-09-01" }),
  ],
};

test("only the machines are listed, with the unit the schedule gave them", () => {
  /* A material has a market price arriving from a sheet and is priced on the prices page.
     Mixing the two here would put a rebar row in a section about machines. */
  const rows = equipmentRows(WORKSPACE);
  assert.deepEqual(rows.map((r) => r.title), ["کامیون", "بیل مکانیکی", "جرثقیل", "گریدر"]);
  assert.deepEqual(rows.map((r) => r.unit), ["hour", "hour", "day", null]);
});

test("a machine with no price says so rather than reading as zero", () => {
  const rows = equipmentRows(WORKSPACE);
  const dig = rows.find((r) => r.title === "بیل مکانیکی");
  assert.equal(dig.unitPriceIRR, null, "no price is not a price of nothing");
  assert.equal(isPriced(dig), false);
  assert.equal(isPriced(rows.find((r) => r.title === "کامیون")), true);
});

test("an empty or absent workspace produces an empty list, not a crash", () => {
  assert.deepEqual(equipmentRows(null), []);
  assert.deepEqual(equipmentRows({}), []);
  assert.deepEqual(equipmentRows({ currentPrices: [] }), []);
});

test("the counter says how much of the job is left", () => {
  assert.deepEqual(pricingProgress(equipmentRows(WORKSPACE)), { total: 4, priced: 2 });
});

/* SEARCH AND FILTER */

test("the filter separates priced from unpriced", () => {
  const rows = equipmentRows(WORKSPACE);
  assert.deepEqual(selectRows(rows, { filter: "priced" }).map((r) => r.title),
                   ["کامیون", "جرثقیل"]);
  assert.deepEqual(selectRows(rows, { filter: "unpriced" }).map((r) => r.title),
                   ["بیل مکانیکی", "گریدر"]);
  assert.equal(selectRows(rows, { filter: "all" }).length, 4);
});

test("search matches the name and the code", () => {
  const rows = equipmentRows(WORKSPACE);
  assert.deepEqual(selectRows(rows, { search: "کامیون" }).map((r) => r.title), ["کامیون"]);
  assert.deepEqual(selectRows(rows, { search: "EQ-جرثقیل" }).map((r) => r.title), ["جرثقیل"]);
  assert.deepEqual(selectRows(rows, { search: "   " }).length, 4, "blank search hides nothing");
});

test("search survives the spellings a Persian keyboard actually produces", () => {
  /* «ی» and «ي» are different characters and look the same. A list searched literally
     loses rows to a difference the reader cannot see. */
  const rows = equipmentRows(WORKSPACE);
  assert.deepEqual(selectRows(rows, { search: "كاميون" }).map((r) => r.title), ["کامیون"],
                   "Arabic kaf and yeh must find the Persian spelling");
  assert.equal(foldPersian("۱۲۳"), "123", "Persian digits compare as digits");
  assert.equal(foldPersian("١٢٣"), "123", "and Arabic ones too");
});

test("search and filter apply together", () => {
  const rows = equipmentRows(WORKSPACE);
  assert.deepEqual(selectRows(rows, { search: "ی", filter: "unpriced" }).map((r) => r.title),
                   ["بیل مکانیکی", "گریدر"]);
});

/* GROUPING */

test("machines are grouped by the unit they are measured in", () => {
  /* A column where some figures are per hour and some per day, interleaved, is a column
     somebody will misread. */
  const groups = groupByUnit(equipmentRows(WORKSPACE));
  assert.deepEqual(groups.map((g) => g.unit), ["day", "hour", null]);
  assert.deepEqual(groups.find((g) => g.unit === "hour").rows.map((r) => r.title),
                   ["بیل مکانیکی", "کامیون"]);
});

test("the group the file left unmeasured comes last", () => {
  /* It cannot be priced at all until somebody says per what, and burying it among the
     rest hides that. */
  const groups = groupByUnit(equipmentRows(WORKSPACE));
  assert.equal(groups[groups.length - 1].unit, null);
  assert.deepEqual(groups[groups.length - 1].rows.map((r) => r.title), ["گریدر"]);
});

test("each group counts its own progress", () => {
  const groups = groupByUnit(equipmentRows(WORKSPACE));
  assert.equal(groups.find((g) => g.unit === "hour").pricedCount, 1);
  assert.equal(groups.find((g) => g.unit === "day").pricedCount, 1);
  assert.equal(groups.find((g) => g.unit === null).pricedCount, 0);
});

test("grouping an empty list produces no groups", () => {
  assert.deepEqual(groupByUnit([]), []);
  assert.deepEqual(groupByUnit(undefined), []);
});

/* WHICH PRICE IS IN FORCE */

test("a project price standing over an organization one carries both", () => {
  /* The single thing somebody revising a row needs to know: revising the level that is
     not in force changes nothing they can see. */
  const workspace = { currentPrices: [
    entry("لودر", EQUIPMENT_TYPE, "hour",
          { scope: "project", unitPriceIRR: "40000000", effectiveFrom: "2026-09-01" },
          { projectPrice: { scope: "project", unitPriceIRR: "40000000" },
            organizationPrice: { scope: "organization", unitPriceIRR: "52100000" } }),
  ] };
  const [row] = equipmentRows(workspace);
  assert.equal(row.unitPriceIRR, "40000000");
  assert.equal(row.priceScope, "project");
  assert.equal(row.organizationPrice.unitPriceIRR, "52100000");
});
