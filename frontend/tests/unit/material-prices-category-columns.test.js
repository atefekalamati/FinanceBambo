/**
 * Each material category shows its own worksheet's columns, and nobody else's.
 *
 * The daily-price page used to render one table shape for every category: نام محصول، دسته،
 * منبع، قیمت روز، واحد، واحد قلم هزینه، تاریخ برگه، وضعیت. That is wrong in both
 * directions. It HID what each sheet states -- an angle's thickness, weight, length and
 * branch count; a brick's code, dimensions and square-metre price -- and it SHOWED columns
 * no worksheet has, so «واحد قلم هزینه» sat over rows whose sheet says nothing of the kind.
 *
 * What replaces it is not a bigger hardcoded list. The columns come from the Backend, per
 * category, derived from the keys the importer actually found in that worksheet. This file
 * pins that: the page must hold no per-category list of its own, a column must never appear
 * for a category whose sheet lacks it, and an empty cell must stay empty.
 */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { installDom } from "../helpers/dom.js";

installDom();

const { columnsFor, cellValue, renderMaterialPrices } =
  await import("../../src/features/prices/material-prices-section.js");

const SECTION_SOURCE = readFileSync(
  fileURLToPath(new URL("../../src/features/prices/material-prices-section.js", import.meta.url)),
  "utf8");

/* The schemas as the Backend publishes them, copied here as the contract this page is
   written against. They are NOT a second source of truth: the test asserts the page uses
   whatever it is given, and the backend's own tests pin that these match the worksheets. */
const CATEGORIES = [
  { category: "angle", label: "نبشی", columns: [
    { key: "source", label: "منبع", kind: "base" },
    { key: "product", label: "محصول", kind: "base" },
    { key: "ضخامت", label: "ضخامت", kind: "spec", numeric: true },
    { key: "وزن", label: "وزن", kind: "spec", numeric: true },
    { key: "طول", label: "طول", kind: "spec", numeric: false },
    { key: "تعداد شاخه", label: "تعداد شاخه", kind: "spec", numeric: true },
    { key: "price", label: "قیمت", kind: "base", numeric: true },
    { key: "workflowDate", label: "تاریخ آپدیت ورک فلو", kind: "base" },
    { key: "productId", label: "productId", kind: "base" },
  ] },
  { category: "ibeam", label: "تیرآهن", columns: [
    { key: "source", label: "منبع", kind: "base" },
    { key: "product", label: "محصول", kind: "base" },
    { key: "وزن - کیلوگرم", label: "وزن (کیلوگرم)", kind: "spec", numeric: true },
    { key: "price", label: "قیمت", kind: "base", numeric: true },
    { key: "workflowDate", label: "تاریخ آپدیت ورک فلو", kind: "base" },
    { key: "productId", label: "productId", kind: "base" },
  ] },
  { category: "brick", label: "آجر", columns: [
    { key: "source", label: "منبع", kind: "base" },
    { key: "product", label: "محصول", kind: "base" },
    { key: "کد", label: "کد", kind: "spec", numeric: false },
    { key: "ابعاد", label: "ابعاد", kind: "spec", numeric: false },
    { key: "وزن", label: "وزن", kind: "spec", numeric: true },
    { key: "price", label: "قیمت", kind: "base", numeric: true },
    { key: "قیمت در هر مترمربع", label: "قیمت در هر مترمربع", kind: "spec", numeric: true },
    { key: "workflowDate", label: "تاریخ آپدیت ورک فلو", kind: "base" },
    { key: "productId", label: "productId", kind: "base" },
  ] },
  { category: "pipe", label: "لوله", columns: [
    { key: "source", label: "منبع", kind: "base" },
    { key: "product", label: "محصول", kind: "base" },
    { key: "price", label: "قیمت", kind: "base", numeric: true },
    { key: "workflowDate", label: "تاریخ آپدیت ورک فلو", kind: "base" },
    { key: "productId", label: "productId", kind: "base" },
  ] },
];

function labels(category) {
  return columnsFor(category, CATEGORIES).map((column) => column.label);
}

function row(over = {}) {
  return {
    providerName: "Mashhad Foolad",
    name: "نبشی10*100*100 شکفته",
    externalId: "ANGLE-1YCN7SX0GRHC1A",
    category: "angle",
    currentPriceIRR: "925600",
    workflowDateJalali: "1405/06/23",
    resolutionStatus: "resolved",
    specs: { "ضخامت": "10.0", "وزن": "90.0", "طول": "6 متر", "تعداد شاخه": "22.0" },
    ...over,
  };
}

/* --------------------------------------------------------------- the column schemas */

test("angle shows exactly its worksheet's columns", () => {
  assert.deepEqual(labels("angle"), [
    "منبع", "محصول", "ضخامت", "وزن", "طول", "تعداد شاخه",
    "قیمت", "تاریخ آپدیت ورک فلو", "productId",
  ]);
});

test("brick shows its own, including the square-metre price beside the price", () => {
  assert.deepEqual(labels("brick"), [
    "منبع", "محصول", "کد", "ابعاد", "وزن",
    "قیمت", "قیمت در هر مترمربع", "تاریخ آپدیت ورک فلو", "productId",
  ]);
});

test("ibeam does not borrow angle's columns", () => {
  // The I-beam worksheet states a weight and nothing else. «تعداد شاخه» and «طول» over its
  // rows would be empty cells reading as missing data about a product that has neither.
  const shown = labels("ibeam");
  for (const foreign of ["تعداد شاخه", "ضخامت", "ابعاد", "کد"]) {
    assert.ok(!shown.includes(foreign), `${foreign} is not an I-beam column`);
  }
  assert.ok(shown.includes("وزن (کیلوگرم)"));
});

test("a worksheet that states no measurements gets a short honest table", () => {
  // Pipe. Five columns, none invented.
  assert.deepEqual(labels("pipe"),
    ["منبع", "محصول", "قیمت", "تاریخ آپدیت ورک فلو", "productId"]);
});

test("no category renders the old generic column set", () => {
  const retired = ["واحد قلم هزینه", "وضعیت", "قیمت روز", "تاریخ برگه", "نام محصول"];
  for (const { category } of CATEGORIES) {
    for (const column of retired) {
      assert.ok(!labels(category).includes(column),
                `${category} still shows the generic column ${column}`);
    }
  }
});

test("the page holds no per-category column list of its own", () => {
  /* The schema comes from the Backend. A copy here would drift, and the first symptom
     would be one worksheet's column rendered over another worksheet's rows.
     Comments are stripped first: this file's own prose names those columns to explain
     itself, and a header appearing in a sentence is not a schema. */
  const code = SECTION_SOURCE
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
  for (const key of ["ضخامت", "تعداد شاخه", "قیمت در هر مترمربع", "وزن - کیلوگرم", "ابعاد"]) {
    assert.ok(!code.includes(key),
              `${key} is hardcoded in the page's code; it must come from the API`);
  }
});

test("with no category chosen, only what every worksheet supplies is shown", () => {
  // A mixed table cannot show per-category measurements without inventing empty cells.
  assert.deepEqual(labels(null),
    ["منبع", "محصول", "دسته", "قیمت", "تاریخ آپدیت ورک فلو", "productId"]);
});

/* ------------------------------------------------------------------------ the values */

test("a numeric spec reads as a number, not as the sheet's float", () => {
  // The sheet's own cell carries «10.0» and «22.0» in Latin digits. Beside a price
  // written «۹۲٬۲۸۰» in the same row that reads as two different systems, and the
  // trailing «.0» is an artefact of the spreadsheet, not a measurement to a tenth.
  // `numeric` is the backend saying this cell may be treated as a number, and it is the
  // only thing that licenses reformatting it.
  const columns = columnsFor("angle", CATEGORIES);
  assert.equal(cellValue(columns.find((c) => c.key === "ضخامت"), row()), "۱۰");
  assert.equal(cellValue(columns.find((c) => c.key === "تعداد شاخه"), row()), "۲۲");
});

test("a spec the backend does not call numeric travels verbatim", () => {
  // «۶ متر» is a sentence and «۲۰*۱۰*۷» is a size. Formatting either would be reading it
  // as a quantity it is not, so only the flagged columns are touched.
  const columns = columnsFor("angle", CATEGORIES);
  assert.equal(cellValue(columns.find((c) => c.key === "طول"),
                         row({ specs: { "طول": "6 متر" } })), "6 متر");
  assert.equal(cellValue(columnsFor("brick", CATEGORIES).find((c) => c.key === "ابعاد"),
                         row({ specs: { "ابعاد": "20*10*7" } })), "20*10*7");
});

test("a square-metre price is grouped like the price beside it", () => {
  const columns = columnsFor("brick", CATEGORIES);
  const perSquare = columns.find((c) => c.key === "قیمت در هر مترمربع");
  assert.equal(cellValue(perSquare, row({ specs: { "قیمت در هر مترمربع": "364500.0" } })),
               "۳۶۴٬۵۰۰");
});

test("a blank worksheet cell stays blank and never becomes zero", () => {
  const columns = columnsFor("brick", CATEGORIES);
  const perSquare = columns.find((c) => c.key === "قیمت در هر مترمربع");
  // 8 of 210 bricks state no square-metre price. A zero there would say it is free.
  assert.equal(cellValue(perSquare, row({ specs: {} })), "—");
  assert.equal(cellValue(perSquare, row({ specs: { "قیمت در هر مترمربع": null } })), "—");
  assert.equal(cellValue(perSquare, row({ specs: { "قیمت در هر مترمربع": "" } })), "—");
});

test("a real zero in the sheet is kept as a zero", () => {
  const columns = columnsFor("angle", CATEGORIES);
  const weight = columns.find((c) => c.key === "وزن");
  // Still a zero after formatting: the sheet said zero, and «۰» says the same thing.
  assert.equal(cellValue(weight, row({ specs: { "وزن": "0" } })), "۰");
});

test("the base cells read the row's own fields", () => {
  const columns = columnsFor("angle", CATEGORIES);
  const by = (key) => columns.find((c) => c.key === key);
  assert.equal(cellValue(by("source"), row()), "Mashhad Foolad");
  assert.equal(cellValue(by("product"), row()), "نبشی10*100*100 شکفته");
  assert.equal(cellValue(by("productId"), row()), "ANGLE-1YCN7SX0GRHC1A");
  assert.equal(cellValue(by("workflowDate"), row()), "1405/06/23");
});

test("a price the backend could not resolve shows no number", () => {
  const columns = columnsFor("angle", CATEGORIES);
  const price = columns.find((c) => c.key === "price");
  assert.equal(cellValue(price, row({ currentPriceIRR: null })), "—");
});

/* ------------------------------------------------------------------------ rendering */

test("the rendered header row is the chosen category's", () => {
  const section = renderMaterialPrices([row()], {
    categories: CATEGORIES, selectedCategory: "angle", onSelectCategory: () => {},
  });
  const headers = [...section.querySelectorAll("th")].map((th) => th.textContent);
  assert.deepEqual(headers, [
    "منبع", "محصول", "ضخامت", "وزن", "طول", "تعداد شاخه",
    "قیمت", "تاریخ آپدیت ورک فلو", "productId",
  ]);
});

test("switching the category rebuilds the headers", () => {
  const angle = renderMaterialPrices([row()], { categories: CATEGORIES, selectedCategory: "angle" });
  const ibeam = renderMaterialPrices([row({ category: "ibeam", specs: { "وزن - کیلوگرم": "155.0" } })],
                                     { categories: CATEGORIES, selectedCategory: "ibeam" });
  const of = (node) => [...node.querySelectorAll("th")].map((th) => th.textContent);
  assert.notDeepEqual(of(angle), of(ibeam));
  assert.ok(of(angle).includes("تعداد شاخه"));
  assert.ok(!of(ibeam).includes("تعداد شاخه"));
});

test("a spec header says which worksheet key it came from", () => {
  const section = renderMaterialPrices([row()], { categories: CATEGORIES, selectedCategory: "angle" });
  const specs = [...section.querySelectorAll("th")].filter((th) => th.dataset.columnKind === "spec");
  assert.deepEqual(specs.map((th) => th.dataset.columnKey),
                   ["ضخامت", "وزن", "طول", "تعداد شاخه"]);
});

test("the rendered row has one cell per header", () => {
  const section = renderMaterialPrices([row()], { categories: CATEGORIES, selectedCategory: "angle" });
  const headers = section.querySelectorAll("th").length;
  const cells = section.querySelectorAll("tbody td").length;
  assert.equal(cells, headers, "a row with more or fewer cells than headers is misaligned");
});

test("status and unit are not columns", () => {
  // They belong to how this system read the price, not to what the worksheet states. They
  // travel as a badge under the name instead.
  const section = renderMaterialPrices([row({ resolutionStatus: "missing_factor" })],
                                       { categories: CATEGORIES, selectedCategory: "angle" });
  const headers = [...section.querySelectorAll("th")].map((th) => th.textContent);
  assert.ok(!headers.includes("وضعیت"));
  assert.ok(!headers.includes("واحد"));
  assert.ok(section.querySelectorAll(".material-price__badge").length >= 1,
            "the status still reaches the reader, as a badge");
});
