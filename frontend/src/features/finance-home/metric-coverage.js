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
 * How much of the project a published figure was built from.
 *
 * `null` when the service says nothing — which is every version before it learned to
 * count, and is why this reads two optional fields rather than deriving a share from the
 * gap counts. A share computed here from `missingPriceCount` would be a guess at the
 * service's own arithmetic, and would drift from it the first time either changed.
 */
export function coverageOf(report, key) {
  if (!stated(report, key)) return null;
  const computed = Number(report?.computedLineCount);
  const total = Number(report?.totalLineCount);
  if (!Number.isFinite(computed) || !Number.isFinite(total) || total <= 0) return null;
  if (computed >= total) return null;      // complete: nothing to qualify
  return { computed, total, excluded: total - computed };
}

/** The card's sub-line: the description when all is well, the qualification when not. */
export function coverageNote(report, key, description) {
  const reason = unavailableReason(report, key);
  if (reason) return reason;
  if (!stated(report, key)) return "داده مبنا موجود نیست";
  const coverage = coverageOf(report, key);
  if (!coverage) return description;
  return `${description} · ${count(coverage.excluded)} ردیف در این عدد نیامده`;
}
