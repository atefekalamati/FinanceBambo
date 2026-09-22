import test from "node:test";
import assert from "node:assert/strict";

import { coverageNote, coverageOf, unavailableReason }
  from "../../src/features/finance-home/metric-coverage.js";

/* What a figure says about itself when it is missing, and when it is only partly there.
 *
 * The board used to answer both with «داده مبنا موجود نیست» — a sentence true of every
 * absent figure, which tells nobody which of four gaps they are looking at nor whether it
 * is two lines or eight hundred. Neither half of that is something a reader can act on.
 */

const REPORT = (metrics, extra = {}) => ({
  metrics,
  missingPriceCount: 0,
  missingEstimateLineCount: 0,
  progressQuality: { missingCount: 0, unmappedLineCount: 0 },
  ...extra,
});

test("a figure that is stated explains nothing — it is the number that speaks", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "2000000000" },
                        { missingPriceCount: 4 });
  assert.equal(unavailableReason(report, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده با قیمت روز"),
               "کار باقیمانده با قیمت روز",
               "a complete project reads exactly as it always did");
});

test("an absent figure names the gap and counts it", () => {
  const report = REPORT({ remainingPhysicalCostIrr: null },
                        { progressQuality: { missingCount: 5, unmappedLineCount: 0 } });
  const note = coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده با قیمت روز");
  assert.match(note, /۵ ردیف مقدار اجراشده‌ای ندارد/,
               "«نمی‌دانم چقدر انجام شده» is the gap, and five is how much of it");
  assert.doesNotMatch(note, /قیمت روز وصل نشده/, "a gap with no lines behind it is not named");
});

test("two gaps are both named, because fixing one would not bring the figure back", () => {
  const report = REPORT({ remainingPhysicalCostIrr: null },
                        { missingPriceCount: 3,
                          progressQuality: { missingCount: 5, unmappedLineCount: 2 } });
  const note = coverageNote(report, "remainingPhysicalCostIrr", "…");
  assert.match(note, /۳ ردیف هنوز به قیمت روز وصل نشده/);
  assert.match(note, /۷ ردیف مقدار اجراشده‌ای ندارد/,
               "unmapped lines are a progress gap too, and are counted with it");
});

test("the forecast names the conversion gap its own gate has", () => {
  /* The service counts conversions inside its gate and publishes no total, so this is
     known only as «some» — but naming it is what tells a reader which screen to open. */
  const report = REPORT({ forecastFinalCostIrr: null });
  assert.match(coverageNote(report, "forecastFinalCostIrr", "…"),
               /ضریب تبدیل واحد ثبت نشده/);
});

test("the per-square-meter figures name the area, not the prices", () => {
  const report = REPORT({ actualCostPerSquareMeterIrr: null }, { missingPriceCount: 9 });
  const note = coverageNote(report, "actualCostPerSquareMeterIrr", "…");
  assert.match(note, /زیربنای کل پروژه ثبت نشده/);
  assert.doesNotMatch(note, /قیمت روز/, "the price count has nothing to do with this one");
});

test("a gap nobody can name falls back rather than printing an empty sentence", () => {
  const report = REPORT({ remainingPhysicalCostIrr: null });
  assert.equal(unavailableReason(report, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageNote(report, "remainingPhysicalCostIrr", "…"), "داده مبنا موجود نیست");
});

/* COVERAGE — what a published but partial figure owes its reader. */

test("a figure built from every line says nothing extra", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "5" },
                        { computedLineCount: 835, totalLineCount: 835 });
  assert.equal(coverageOf(report, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده"), "کار باقیمانده",
               "a badge on every card is a badge nobody reads");
});

test("a figure that left lines out says how many", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "5" },
                        { computedLineCount: 830, totalLineCount: 835 });
  assert.deepEqual(coverageOf(report, "remainingPhysicalCostIrr"),
                   { computed: 830, total: 835, excluded: 5 });
  assert.equal(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده"),
               "کار باقیمانده · ۵ ردیف در این عدد نیامده");
});

test("a service that does not count yet is not guessed at", () => {
  /* Deriving a share here from the gap counts would be a second implementation of the
     service's own arithmetic, and would drift from it the first time either changed. */
  const report = REPORT({ remainingPhysicalCostIrr: "5" }, { missingPriceCount: 4 });
  assert.equal(coverageOf(report, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده"), "کار باقیمانده");
});

test("nonsense counts are ignored rather than drawn", () => {
  for (const extra of [{ computedLineCount: 5, totalLineCount: 0 },
                       { computedLineCount: "x", totalLineCount: 10 },
                       { computedLineCount: 900, totalLineCount: 835 }]) {
    const report = REPORT({ remainingPhysicalCostIrr: "5" }, extra);
    assert.equal(coverageOf(report, "remainingPhysicalCostIrr"), null,
                 `counts ${JSON.stringify(extra)} must not produce a coverage note`);
  }
});

test("an absent report is answered, not thrown at", () => {
  assert.equal(unavailableReason(undefined, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageOf(null, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageNote({}, "remainingPhysicalCostIrr", "…"), "داده مبنا موجود نیست");
});
