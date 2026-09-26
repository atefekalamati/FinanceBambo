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
                        { requiredLineCount: 835, totalLineCount: 835 });
  assert.equal(coverageOf(report, "remainingPhysicalCostIrr"), null);
  assert.equal(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده"), "کار باقیمانده",
               "a badge on every card is a badge nobody reads");
});

test("a figure that left lines out says how many", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "5" },
                        { requiredLineCount: 830, totalLineCount: 835 });
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

/* A SUM OVER NO LINES IS NOT A SMALL NUMBER.
 *
 * The service publishes it as `0` on purpose: it excludes the lines it cannot use, states
 * the total, and leaves the counts to say how much of the project that is. For 2 of 715
 * that is right — a partial sum is a number a reader can use. For 0 of 715 it is not:
 * «۰ تومان» beside «هزینه کار باقی‌مانده» reads as «the work is finished».
 */

const { restsOnNothing } = await import("../../src/features/finance-home/metric-coverage.js");

test("a figure built from no lines at all is withheld, not drawn as zero", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "0" },
                        { requiredLineCount: 0, totalLineCount: 715 });
  assert.equal(restsOnNothing(report, "remainingPhysicalCostIrr"), true);
  assert.match(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده"),
               /هیچ‌کدام از ۷۱۵ ردیف/);
});

test("a figure built from some lines is still drawn, and qualified", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "5" },
                        { requiredLineCount: 2, totalLineCount: 715 });
  assert.equal(restsOnNothing(report, "remainingPhysicalCostIrr"), false);
  assert.match(coverageNote(report, "remainingPhysicalCostIrr", "کار باقیمانده"),
               /۷۱۳ ردیف در این عدد نیامده/);
});

/* THE FORECAST ANSWERS TO ITS OWN COUNT.
 *
 * Measured on the live service: computedLineCount 0 while requiredLineCount is 52,
 * because what is still to BUY is known from the purchase ledger whether or not anyone
 * measured site progress. One count cannot describe both figures.
 */

test("the forecast is not judged by the count that belongs to the executed value", () => {
  const report = REPORT({ currentExecutedValueIrr: "0", forecastFinalCostIrr: "8347173100000" },
                        { computedLineCount: 0, requiredLineCount: 52, totalLineCount: 715 });
  assert.equal(restsOnNothing(report, "forecastFinalCostIrr"), false,
               "52 lines built it; it is not a sum over nothing");
  assert.match(coverageNote(report, "forecastFinalCostIrr", "پیش‌بینی"),
               /۶۶۳ ردیف در این عدد نیامده/);
  assert.equal(restsOnNothing(report, "currentExecutedValueIrr"), true,
               "and the other figure, on the same payload, rests on nothing");
});

/* «هزینه بروز باقیمانده» ANSWERS TO THE FORECAST'S COUNT, since 2026-09-26.
 *
 * The service made it the same ledger-settled sum as «بودجه موردنیاز تا تکمیل»: what a
 * material or equipment line still has to pay for is read from its invoices, whether or
 * not anyone measured its progress. So on the payload above -- nothing measured, 52 lines
 * with a price -- the remaining cost rests on those 52, not on nothing. Reading it against
 * `computedLineCount` would withhold a figure the service built from 52 lines.
 */
test("the remaining cost is judged by the forecast's count, not the executed value's", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "6654488100000" },
                        { computedLineCount: 0, requiredLineCount: 52, totalLineCount: 715 });
  assert.equal(restsOnNothing(report, "remainingPhysicalCostIrr"), false);
  assert.match(coverageNote(report, "remainingPhysicalCostIrr", "باقیمانده"),
               /۶۶۳ ردیف در این عدد نیامده/);
});

test("a service that publishes no count for a figure leaves it unqualified", () => {
  /* Before `requiredLineCount` shipped, reading `computedLineCount` beside the forecast
     printed «هیچ ردیفی در این عدد نیامده» next to 8,347 billion. Silence is better. */
  const report = REPORT({ forecastFinalCostIrr: "8347173100000" },
                        { computedLineCount: 0, totalLineCount: 715 });
  assert.equal(restsOnNothing(report, "forecastFinalCostIrr"), false);
  assert.equal(coverageNote(report, "forecastFinalCostIrr", "پیش‌بینی"), "پیش‌بینی");
});

/* THE MARK ON THE CHART, AND THE LINE IN THE WARNINGS.
 *
 * A card has a sub-line to qualify its figure in. A bar has a label and nothing else, and
 * the list of everything wrong with a calculation is somewhere else again. Same facts,
 * three places, one source.
 */

const { coverageTooltip, coverageWarnings } =
  await import("../../src/features/finance-home/metric-coverage.js");

test("a figure built from every line gets no mark at all", () => {
  /* A mark on every bar is a mark nobody reads. */
  const report = REPORT({ remainingPhysicalCostIrr: "5" },
                        { requiredLineCount: 715, totalLineCount: 715 });
  assert.equal(coverageTooltip(report, "remainingPhysicalCostIrr"), null);
  assert.deepEqual(coverageWarnings(report), []);
});

test("a partial figure states both halves, because they answer different questions", () => {
  const report = REPORT({ forecastFinalCostIrr: "8347173100000" },
                        { requiredLineCount: 52, totalLineCount: 715 });
  const tip = coverageTooltip(report, "forecastFinalCostIrr");
  assert.match(tip, /۵۲ ردیف از ۷۱۵ ردیف/, "what it rests on");
  assert.match(tip, /۶۶۳ ردیف در آن نیامده/, "and what it does not");
});

test("a figure resting on nothing says so rather than counting to zero", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "0" },
                        { requiredLineCount: 0, totalLineCount: 715 });
  assert.match(coverageTooltip(report, "remainingPhysicalCostIrr"),
               /هیچ‌کدام از ۷۱۵ ردیف/);
});

test("a figure the service never published gets no mark — the card says why instead", () => {
  const report = REPORT({ forecastFinalCostIrr: null },
                        { requiredLineCount: 52, totalLineCount: 715 });
  assert.equal(coverageTooltip(report, "forecastFinalCostIrr"), null);
});

test("the warnings name the figures a count governs, once, not one line each", () => {
  /* Five metrics, two counts. Five lines saying «built on 52 of 715» would be one fact
     printed five times, and a list nobody finishes is a list that warns nobody. */
  const report = REPORT({ remainingPhysicalCostIrr: "0", currentExecutedValueIrr: "0",
                          forecastFinalCostIrr: "8347173100000",
                          moneyRequiredToContinueIrr: "6654488100000" },
                        { computedLineCount: 0, requiredLineCount: 52, totalLineCount: 715 });
  const messages = coverageWarnings(report).map((w) => w.message);
  assert.equal(messages.length, 2);
  assert.match(messages[0], /ارزش اجراشده/);
  assert.match(messages[0], /هیچ‌کدام از ۷۱۵ ردیف/);
  assert.match(messages[1], /هزینه بروز باقیمانده، پیش‌بینی هزینه نهایی/);
  assert.match(messages[1], /۵۲ ردیف از ۷۱۵/);
  assert.match(messages[1], /۶۶۳ ردیف در آن‌ها نیامده/);
});

test("a group whose figures are all absent is not reported as a coverage problem", () => {
  /* The card already names WHICH gap made each one absent. Repeating it here under a
     different description would report one gap twice. */
  const report = REPORT({ forecastFinalCostIrr: null, moneyRequiredToContinueIrr: null,
                          forecastPerSquareMeterIrr: null },
                        { requiredLineCount: 0, totalLineCount: 715 });
  assert.deepEqual(coverageWarnings(report).filter((w) => /پیش‌بینی/.test(w.message)), []);
});

test("a service that publishes no counts produces no marks and no warnings", () => {
  const report = REPORT({ remainingPhysicalCostIrr: "5", forecastFinalCostIrr: "9" });
  assert.equal(coverageTooltip(report, "remainingPhysicalCostIrr"), null);
  assert.deepEqual(coverageWarnings(report), []);
});
