import { formatDisplayNumber } from "../../shared/formatters/display.js";

/* Why a live figure is missing, and how much of the project one covers when it is not.
 *
 * THE TWO SENTENCES A FIGURE OWES ITS READER
 * «داده مبنا موجود نیست» is not one of them. It is true of every absent figure on the
 * board and tells nobody which of four different gaps they are looking at, nor whether it
 * is two lines or eight hundred. A reader who cannot tell those apart cannot fix either.
 *
 * So: when a figure is absent, name the gap and count it. When a figure is present but
 * built from some of the project's lines, say how many it left out. When it is present and
 * complete, say nothing at all — a badge on every card is a badge nobody reads.
 *
 * NO THRESHOLD HERE, DELIBERATELY
 * A rule that hides a figure below some share of coverage would, on a healthy project,
 * never fire — and a branch that never runs is a branch nobody has ever seen work. The
 * first time it fired would be the first time it was tested, on the worst day. The figure
 * is shown whenever the service states one; the coverage note is what qualifies it.
 */

/** Which gap stops which figure. Mirrors the service's own gates, and nothing more. */
const BLOCKERS = Object.freeze({
  currentExecutedValueIrr: ["price", "progress"],
  remainingPhysicalCostIrr: ["price", "progress"],
  moneyRequiredToContinueIrr: ["price", "progress", "conversion"],
  forecastFinalCostIrr: ["price", "progress", "conversion"],
  forecastPerSquareMeterIrr: ["price", "progress", "conversion", "area"],
  initialEstimateIrr: ["estimate"],
  revisedEstimateIrr: ["estimate"],
  actualCostPerSquareMeterIrr: ["area"],
});

/** The figure itself. It lives under `metrics`; the gap counts live beside it. */
function valueOf(report, key) {
  return report?.metrics?.[key];
}

function stated(report, key) {
  const value = valueOf(report, key);
  return value !== null && value !== undefined;
}

/** How many lines each gap is holding, read from what the service already publishes. */
function gapCounts(report) {
  const progress = report?.progressQuality ?? {};
  return {
    price: Number(report?.missingPriceCount ?? 0) || 0,
    progress: (Number(progress.missingCount ?? 0) || 0)
            + (Number(progress.unmappedLineCount ?? 0) || 0),
    estimate: Number(report?.missingEstimateLineCount ?? 0) || 0,
    /* The service counts conversions inside its own gate and publishes no total for them,
       so this is known only as «some». Named anyway: a reader told «ضریب تبدیل» knows
       which screen to open, which is the whole job of the sentence. */
    conversion: null,
    area: null,
  };
}

/* Counts are written the way every other number in this module is written. A card that
   says «۲ ردیف» beside one that says «2 ردیف» is two cards a reader stops trusting. */
const count = (value) => formatDisplayNumber(String(value));

const GAP_TEXT = Object.freeze({
  price: (n) => `${count(n)} ردیف هنوز به قیمت روز وصل نشده`,
  progress: (n) => `${count(n)} ردیف مقدار اجراشده‌ای ندارد`,
  estimate: (n) => `${count(n)} ردیف برآورد اولیه ندارد`,
  conversion: () => "برای بعضی ردیف‌ها ضریب تبدیل واحد ثبت نشده",
  area: () => "زیربنای کل پروژه ثبت نشده",
});

/**
 * Why this figure is absent, in the reader's own terms, or null when it is present.
 *
 * Only gaps that actually have lines behind them are named. A figure blocked by two
 * different gaps names both, because fixing one of them will not bring it back and a
 * person who is told only the first will think it should have.
 */
export function unavailableReason(report, key) {
  if (stated(report, key)) return null;
  const counts = gapCounts(report);
  const named = (BLOCKERS[key] ?? [])
    .filter((gap) => counts[gap] === null || counts[gap] > 0)
    .map((gap) => GAP_TEXT[gap](counts[gap]));
  if (!named.length) return null;
  return `${named.join(" و ")}.`;
}

/**
 * Which published count measures each figure's coverage.
 *
 * TWO COUNTS, BECAUSE THE SERVICE APPLIES TWO RULES. A figure about work DONE needs a
 * price and a measurement. A figure about money still to SPEND needs a price and, for
 * material and equipment, no measurement at all — what is left to pay for comes from the
 * invoices, not from site progress. Measured on this project the two differ completely:
 * 0 lines against 52.
 *
 * So a single count cannot describe both, and reading `computedLineCount` beside the
 * forecast produced «هیچ ردیفی در این عدد نیامده» next to a figure of 8,347 billion. A
 * figure whose count the service does not publish is left unqualified rather than
 * qualified wrongly.
 *
 * «هزینه بروز باقیمانده» moved from the first count to the second on 2026-09-26, when the
 * service made it the same ledger-settled figure as «بودجه موردنیاز تا تکمیل»: one sum
 * under two names, so one coverage count.
 */
const COVERAGE_COUNT = Object.freeze({
  currentExecutedValueIrr: "computedLineCount",
  remainingPhysicalCostIrr: "requiredLineCount",
  moneyRequiredToContinueIrr: "requiredLineCount",
  forecastFinalCostIrr: "requiredLineCount",
  forecastPerSquareMeterIrr: "requiredLineCount",
});

/**
 * Whether this figure is a sum over NO lines at all.
 *
 * The service publishes such a sum as `0`, deliberately: it excludes the lines it cannot
 * use and states the total, leaving the counts to say how much of the project that is.
 * For every partial sum that is right — 2 of 715 is a number a reader can use. For a sum
 * over zero lines it is not: «۰ تومان» beside «هزینه کار باقی‌مانده» reads as «the work
 * is finished», which is the one reading no gap should ever produce.
 *
 * So this is where the figure is withheld — a presentation decision, made once, where the
 * figure is drawn. The service keeps publishing the number for anyone who wants it.
 */
export function restsOnNothing(report, key) {
  const field = COVERAGE_COUNT[key];
  if (!field) return false;
  const computed = Number(report?.[field]);
  return Number.isFinite(computed) && computed === 0;
}

/**
 * How much of the project a published figure was built from.
 *
 * `null` when the service says nothing — which is every version before it learned to
 * count, and is why this reads two optional fields rather than deriving a share from the
 * gap counts. A share computed here from `missingPriceCount` would be a guess at the
 * service's own arithmetic, and would drift from it the first time either changed.
 */
export function coverageOf(report, key) {
  if (!stated(report, key)) return null;
  const field = COVERAGE_COUNT[key];
  if (!field) return null;
  const computed = Number(report?.[field]);
  const total = Number(report?.totalLineCount);
  if (!Number.isFinite(computed) || !Number.isFinite(total) || total <= 0) return null;
  if (computed >= total) return null;      // complete: nothing to qualify
  return { computed, total, excluded: total - computed };
}

/* The figures each coverage count governs, and what to call them together.
 *
 * Grouped rather than listed one by one because the counts are what differ, not the
 * figures: five separate lines saying «built on 52 of 715» would be one fact printed
 * five times, and a warnings list nobody finishes reading is a warnings list that warns
 * nobody. */
const COVERAGE_GROUPS = Object.freeze([
  { field: "computedLineCount",
    keys: ["currentExecutedValueIrr"],
    label: "ارزش اجراشده" },
  { field: "requiredLineCount",
    keys: ["remainingPhysicalCostIrr", "moneyRequiredToContinueIrr", "forecastFinalCostIrr", "forecastPerSquareMeterIrr"],
    label: "هزینه بروز باقیمانده، پیش‌بینی هزینه نهایی و پیش‌بینی هر مترمربع" },
]);

/** `{computed, total}` for one governing count, or null when it cannot be read. */
function span(report, field) {
  const computed = Number(report?.[field]);
  const total = Number(report?.totalLineCount);
  if (!Number.isFinite(computed) || !Number.isFinite(total) || total <= 0) return null;
  if (computed >= total) return null;      // whole: there is nothing to qualify
  return { computed, total };
}

/**
 * The whole sentence, for a mark the reader hovers.
 *
 * The card's sub-line has one line to work in and says «۶۶۳ ردیف در این عدد نیامده»;
 * that is the fact, with the reader left to infer what it was built from. A figure on a
 * chart has no sub-line at all, so the mark beside it carries the full statement instead
 * — both halves, because «۵۲ of ۷۱۵» and «۶۶۳ missing» answer different questions and a
 * reader deciding whether to trust the number wants both.
 *
 * Null when there is nothing to say: no figure, no count, or a figure built from every
 * line there is. A mark that appears on a complete figure is a mark that means nothing.
 */
export function coverageTooltip(report, key) {
  if (!stated(report, key)) return null;
  const field = COVERAGE_COUNT[key];
  if (!field) return null;
  const reach = span(report, field);
  if (!reach) return null;
  if (reach.computed === 0) {
    return `هیچ‌کدام از ${count(reach.total)} ردیف این پروژه در این عدد نیامده است.`;
  }
  return `این عدد بر ${count(reach.computed)} ردیف از ${count(reach.total)} ردیف پروژه بنا شده است؛ `
    + `${count(reach.total - reach.computed)} ردیف در آن نیامده.`;
}

/**
 * The same facts as warnings, for the list that collects everything wrong with a
 * calculation.
 *
 * A mark on a chart is seen by whoever is looking at that chart. Somebody auditing the
 * figures opens «هشدارهای کیفیت محاسبه» and expects to find every reason a number might
 * be wrong in one place — and «this total is missing 663 of the project's lines» is
 * exactly such a reason, even though the service raised no warning about it: the service
 * published the counts and considers the matter stated.
 */
export function coverageWarnings(report) {
  return COVERAGE_GROUPS.flatMap(({ field, keys, label }) => {
    /* A group whose figures the service did not publish is not a coverage problem. The
       card already says WHY each one is absent, and naming it here as well would report
       one gap twice under two different descriptions. */
    if (!keys.some((key) => stated(report, key))) return [];
    const reach = span(report, field);
    if (!reach) return [];
    const code = `COVERAGE_${field}`;
    if (reach.computed === 0) {
      return [{ code,
        message: `${label}: هیچ‌کدام از ${count(reach.total)} ردیف این پروژه هنوز قابل محاسبه نیست.` }];
    }
    return [{ code,
      message: `${label} بر ${count(reach.computed)} ردیف از ${count(reach.total)} ردیف پروژه بنا شده‌اند؛ `
        + `${count(reach.total - reach.computed)} ردیف در آن‌ها نیامده است.` }];
  });
}

/** The card's sub-line: the description when all is well, the qualification when not. */
export function coverageNote(report, key, description) {
  const reason = unavailableReason(report, key);
  if (reason) return reason;
  if (!stated(report, key)) return "داده مبنا موجود نیست";
  if (restsOnNothing(report, key)) {
    const total = formatDisplayNumber(String(Number(report?.totalLineCount) || 0));
    return `هیچ‌کدام از ${total} ردیف این پروژه هنوز قابل محاسبه نیست.`;
  }
  const coverage = coverageOf(report, key);
  if (!coverage) return description;
  return `${description} · ${count(coverage.excluded)} ردیف در این عدد نیامده`;
}
