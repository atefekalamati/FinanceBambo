import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { trendRows, overallDirection, createPriceTrendDetailDialog } =
  await import("../../src/shared/components/price-trend-detail.js");
const { createPriceTrend } =
  await import("../../src/shared/components/price-trend.js");
const { materialPriceTrend, renderMaterialPrices } =
  await import("../../src/features/prices/material-prices-section.js");

/* The points behind a sparkline, read one at a time.
 *
 * A sparkline says «up» in a thumbnail and that is its value — but it is also the only
 * place these figures appear, and the shape of a line answers neither «when did it move»
 * nor «by how much». Pressing it opens exactly the points it was drawn from: the same
 * array, the same order, no request of its own — drawn again at a size where each point
 * can be chosen, and answered for one point at a time.
 */

const POINTS = [
  { effectiveFrom: "2026-06-01", unitPriceIrr: "900000" },
  { effectiveFrom: "2026-07-01", unitPriceIrr: "950000" },
  { effectiveFrom: "2026-08-01", unitPriceIrr: "950000" },
  { effectiveFrom: "2026-09-01", unitPriceIrr: "932000" },
];

/* ─────────────────────────── the conversion, on its own ─────────────────────────── */

test("rows keep the line's own order — oldest first, never re-sorted", () => {
  /* The caller built that array to draw with. A panel that disagreed with the picture
     above it would be worse than no panel. */
  assert.deepEqual(trendRows(POINTS).map((r) => r.effectiveFrom),
                   ["2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]);
});

test("each row carries its step from the one before it, exactly", () => {
  const rows = trendRows(POINTS);
  assert.deepEqual(rows.map((r) => r.direction), [null, "up", "flat", "down"]);
  assert.deepEqual(rows.map((r) => r.changeIrr), [null, "50000", "0", "18000"]);
});

test("the first row has no step, because nothing precedes it", () => {
  /* «no change» and «nothing to compare with» are different facts and only one of them
     is about the price. */
  assert.equal(trendRows(POINTS)[0].changeIrr, null);
  assert.equal(trendRows(POINTS)[0].direction, null);
});

test("the step is exact at magnitudes a float would round", () => {
  const rows = trendRows([{ effectiveFrom: "a", unitPriceIrr: "123456789012345678" },
                          { effectiveFrom: "b", unitPriceIrr: "123456789012345679" }]);
  assert.equal(rows[1].changeIrr, "1", "one rial must survive");
});

test("points stating no usable amount are dropped, never shown as zero", () => {
  /* The line drops them too, for the same reason. */
  const rows = trendRows([...POINTS, { effectiveFrom: "2026-10-01", unitPriceIrr: null },
                          { effectiveFrom: "2026-11-01", unitPriceIrr: "12.5" }]);
  assert.equal(rows.length, 4);
});

test("fewer than five points produces fewer than five rows, and nothing invented", () => {
  assert.equal(trendRows(POINTS.slice(0, 2)).length, 2);
  assert.deepEqual(trendRows([]), []);
  assert.deepEqual(trendRows(undefined), []);
});

test("the overall direction is first against last, not the final step", () => {
  /* The run above ends on a fall and still finished higher than it began. Reporting the
     last step as «the trend» would call that a decline. */
  assert.equal(overallDirection(trendRows(POINTS)), "up");
  assert.equal(overallDirection(trendRows([POINTS[0], POINTS[3]].reverse())), "down");
  assert.equal(overallDirection(trendRows([POINTS[1], POINTS[2]])), "flat");
  assert.equal(overallDirection(trendRows([POINTS[0]])), "none");
  assert.equal(overallDirection([]), "none");
});

/* ─────────────────────────────── the panel ─────────────────────────────── */

function openDialog(points, title = "میلگرد ۱۶") {
  const modal = createPriceTrendDetailDialog({ title, points });
  document.body.append(modal.element);
  return modal;
}

const dateOf = (modal) => modal.element.querySelector(".trend-detail__date").textContent;
const amountOf = (modal) => modal.element.querySelector(".trend-detail__amount").textContent;
const stepOf = (modal) => modal.element.querySelector(".trend-detail__step").textContent;
const dotsOf = (modal) => modal.element.querySelectorAll(".trend-detail__dot");
const hitsOf = (modal) => modal.element.querySelectorAll(".trend-detail__hit");

test("three bands and a chart — the panel has no fourth thing in it", () => {
  /* The size of this panel is the point: one small screen that never scrolls. Every band
     is present whatever the data says, so choosing a point moves no box. */
  const panel = openDialog(POINTS).element.querySelector(".trend-detail__panel");
  assert.deepEqual(panel.children.map((child) => child.className.split(" ")[0]),
                   ["trend-detail__head", "trend-detail__date",
                    "trend-detail__chart", "trend-detail__price"]);
});

test("the chart draws one point per price, and no more", () => {
  const modal = openDialog(POINTS);
  assert.equal(dotsOf(modal).length, 4);
  assert.equal(hitsOf(modal).length, 4, "each dot has a target big enough to hit");
  assert.equal(modal.element.querySelectorAll(".trend-detail__line").length, 1);
});

test("it opens on the newest point, because that is the figure the table showed", () => {
  const modal = openDialog(POINTS);
  assert.match(dateOf(modal), /شهریور ۱۴۰۵/);
  assert.match(amountOf(modal), /۹۳٬۲۰۰/);
  assert.match(stepOf(modal), /▼/, "it fell to get there, and the panel says so");
  assert.ok(dotsOf(modal)[3].className.includes("trend-detail__dot--on"),
            "and the last dot is the one marked");
});

test("choosing a point re-answers both bands and nothing else", () => {
  const modal = openDialog(POINTS);
  hitsOf(modal)[0].dispatch("mouseenter");
  assert.match(dateOf(modal), /خرداد ۱۴۰۵/);
  assert.match(amountOf(modal), /۹۰٬۰۰۰/);
  assert.equal(stepOf(modal), "اولین قیمت ثبت‌شده",
               "nothing precedes the first point, which is not the same as no change");
  assert.equal(dotsOf(modal).filter((d) => d.className.includes("--on")).length, 1,
               "exactly one point is ever the chosen one");
});

test("a point reached by pointer and by keyboard is the same point", () => {
  /* Hover, click and focus are one question asked three ways. */
  for (const how of ["click", "focus", "mouseenter"]) {
    const modal = openDialog(POINTS);
    hitsOf(modal)[1].dispatch(how);
    assert.match(amountOf(modal), /۹۵٬۰۰۰/, `«${how}» must choose the point too`);
    assert.match(stepOf(modal), /▲/);
  }
});

test("only the chosen point is in the tab order", () => {
  /* Four data points should not cost four presses of Tab to walk past; the arrow keys
     move between them once the chart is reached. */
  const modal = openDialog(POINTS);
  const tabbable = hitsOf(modal).filter((hit) => hit.getAttribute("tabindex") === "0");
  assert.equal(tabbable.length, 1);
  assert.equal(tabbable[0], hitsOf(modal)[3], "and it is the one being read");
});

test("every point states its own date and amount for a screen reader", () => {
  const labels = hitsOf(openDialog(POINTS)).map((hit) => hit.getAttribute("aria-label"));
  assert.equal(labels.length, 4);
  assert.match(labels[0], /خرداد ۱۴۰۵/);
  assert.match(labels[0], /۹۰٬۰۰۰/);
});

test("the date is a business date, not a grouped quantity", () => {
  /* «۱۱ خرداد ۱۴۰۵». A year is not an amount, so it carries no thousands separator. */
  const modal = openDialog(POINTS);
  hitsOf(modal)[0].dispatch("click");
  assert.doesNotMatch(dateOf(modal), /۱٬۴۰۵/);
});

test("the panel names the product and where the whole run ended up", () => {
  const modal = openDialog(POINTS);
  assert.equal(modal.element.querySelector(".trend-detail__title").textContent, "میلگرد ۱۶");
  assert.equal(modal.element.querySelector(".trend-detail__overall").textContent, "افزایشی",
               "first point against last — not the final step, which fell");
});

test("a run of identical prices is drawn flat instead of dividing by zero", () => {
  const flat = [{ effectiveFrom: "2026-06-01", unitPriceIrr: "500000" },
                { effectiveFrom: "2026-07-01", unitPriceIrr: "500000" }];
  const modal = openDialog(flat);
  assert.deepEqual(dotsOf(modal).map((dot) => dot.getAttribute("cy")), ["42", "42"],
                   "both at mid height");
  assert.equal(stepOf(modal), "بدون تغییر");
});

test("a panel opened on nothing says so instead of drawing an empty chart", () => {
  const modal = openDialog([]);
  assert.equal(dotsOf(modal).length, 0);
  assert.match(modal.element.textContent, /هنوز قیمتی ثبت نشده/);
  assert.ok(modal.element.querySelector(".trend-detail__date"),
            "the bands stay, so the panel is the size it always is");
});

test("the close button closes it, and it leaves the document", () => {
  const modal = openDialog(POINTS);
  const close = modal.element.querySelector(".trend-detail__close");
  assert.equal(close.getAttribute("aria-label"), "بستن");
  close.click();
  modal.element.dispatch("close");   // the stub does not fire native dialog events
  assert.equal(modal.element.parentNode, null);
});

test("a click on the backdrop closes it; a click inside does not", () => {
  /* The panel is one element precisely so this can be told apart: a click landing on the
     dialog ITSELF only happens outside it. */
  const inside = openDialog(POINTS);
  inside.element.querySelector(".trend-detail__panel").dispatch("click");
  assert.notEqual(inside.element.parentNode, null, "a click on the content must not close it");

  const outside = openDialog(POINTS);
  outside.element.dispatch("click");
  outside.element.dispatch("close");
  assert.equal(outside.element.parentNode, null);
});

/* ───────────────────── the sparkline as a control ───────────────────── */

const ITEM = { resource: { resourceId: "item-1" },
               trend: { trendDirection: "up", trendPoints: POINTS } };

test("without a handler the cell is the div it always was", () => {
  /* The two other places drawing this sparkline pass nothing and must not change. */
  const cell = createPriceTrend(ITEM, []);
  assert.equal(cell.tagName, "DIV");
  assert.equal(cell.getAttribute("aria-haspopup"), null);
});

test("with a handler it becomes a real button, not a listener on the drawing", () => {
  /* A listener on the SVG is reachable by mouse and by nothing else: no tab stop, no
     Enter, no Space, nothing for a screen reader to announce. */
  const cell = createPriceTrend(ITEM, [], { onOpen: () => {} });
  assert.equal(cell.tagName, "BUTTON");
  assert.equal(cell.type, "button");
  assert.equal(cell.getAttribute("aria-haspopup"), "dialog");
  assert.match(cell.getAttribute("aria-label"), /جزئیات روند قیمت/);
  assert.match(cell.getAttribute("aria-label"), /افزایشی/);
  assert.ok(cell.className.includes("price-trend"),
            "it keeps the class, so the cell is laid out exactly as before");
});

test("pressing it hands over the very points the line was drawn from", () => {
  /* Not a fetch, not a copy built from something else: the same array. */
  let given = null;
  createPriceTrend(ITEM, [], { onOpen: (points) => { given = points; } }).click();
  assert.deepEqual(given.map((p) => p.unitPriceIrr),
                   POINTS.map((p) => p.unitPriceIrr));
});

test("a line with no points is not offered as a control", () => {
  const empty = { resource: { resourceId: "x" }, trend: { trendDirection: "none", trendPoints: [] } };
  const cell = createPriceTrend(empty, [], { onOpen: () => {} });
  assert.equal(cell.tagName, "DIV");
  assert.match(cell.textContent, /بدون سابقه/);
});

test("a line the chart refuses to draw is not a control either", () => {
  /* The regression this pins: interactivity was decided on «are there points», the
     drawing on «is there a direction». The two disagreed on 49 of 50 rows of this
     project, each of them a focusable button that drew «بدون سابقه» and did nothing. */
  const undrawable = { resource: { resourceId: "x" },
                       trend: { trendDirection: "none", trendPoints: POINTS } };
  const cell = createPriceTrend(undrawable, [], { onOpen: () => {} });
  assert.equal(cell.tagName, "DIV", "no tab stop where there is no line");
  assert.equal(cell.getAttribute("aria-haspopup"), null);
  assert.match(cell.textContent, /بدون سابقه/);
});

test("a single point draws no line, so it opens nothing", () => {
  /* One price is not a trend: the chart has nothing to slope. */
  const once = { resource: { resourceId: "x" }, trend: { trendPoints: [POINTS[0]] } };
  assert.equal(createPriceTrend(once, [], { onOpen: () => {} }).tagName, "DIV");
});

/* ───────────────── the same behaviour whatever priced the row ───────────────── */

const observation = (date, price) => ({ workflowDate: date, priceIRR: price,
                                        validationStatus: "valid" });

test("a hand-entered price and a sheet price produce the same rows", () => {
  /* The component receives points, not a source. Whatever writes them — a manual entry,
     the market sheet, or whatever comes next — arrives here identically. */
  const history = [observation("2026-09-01", "932000"), observation("2026-08-01", "950000")];
  const sheet = materialPriceTrend({ providerItemId: "p-1" }, history);
  const manual = materialPriceTrend({ providerItemId: "p-2" }, history.map(
    (o) => ({ ...o, origin: "manual" })));
  assert.deepEqual(trendRows(sheet.trend.trendPoints), trendRows(manual.trend.trendPoints));
  assert.deepEqual(trendRows(sheet.trend.trendPoints).map((r) => r.unitPriceIrr),
                   ["950000", "932000"], "newest-first observations arrive oldest-first");
});

test("the prices table offers the control, and only for this row's own listing", () => {
  /* A panel must never be able to show another product's history: the points it is given
     are the ones keyed on this row's providerItemId. */
  document.body.replaceChildren();   // panels the tests above opened and left behind
  const row = { providerItemId: "p-1", name: "میلگرد ۱۶", category: "rebar",
                priceIRR: "932000", specs: {} };
  const section = renderMaterialPrices([row], {
    categories: [{ category: "rebar", label: "میلگرد", activeCount: 1, itemCount: 1 }],
    selectedCategory: "rebar",
    onSelectCategory: () => {},
    priceHistories: new Map([["p-1", [observation("2026-09-01", "932000"),
                                      observation("2026-08-01", "950000")]],
                             ["p-OTHER", [observation("2026-09-01", "1")]]]),
  });
  const control = section.querySelector(".price-trend--interactive");
  assert.ok(control, "the trend cell is a control");
  control.click();
  const dialog = document.body.querySelector(".trend-detail");
  assert.ok(dialog, "pressing it opens the panel");
  assert.match(dialog.querySelector(".trend-detail__title").textContent, /میلگرد ۱۶/);
  assert.equal(dialog.querySelectorAll(".trend-detail__dot").length, 2,
               "this row's two observations, and not the other row's one");
  assert.match(dialog.querySelector(".trend-detail__amount").textContent, /۹۳٬۲۰۰/);
  dialog.remove();
});
