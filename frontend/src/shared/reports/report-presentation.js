import { buildValueTicks, chooseAxisCeiling } from "../charts/value-ticks.js";

const TYPE_LABELS = Object.freeze({
  material: "مصالح",
  labor: "نیروی انسانی",
  equipment: "تجهیزات",
  general_cost: "هزینه‌های عمومی پروژه",
});

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : 0n;
}

/**
 * The same parse, but `null` where the value was never stated.
 *
 * `exactInteger` answers `0n` so the axis arithmetic above always has a number to work
 * with, which is right for a scale and wrong for a figure: a category the Backend could
 * not compute is not a category that came to nothing, and only one of the two may be
 * drawn as a bar of no height.
 */
function statedInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

function absolute(value) {
  return value < 0n ? -value : value;
}

function buildExactScale(entries) {
  const maximum = entries.reduce((result, entry) => {
    const value = absolute(exactInteger(entry.value));
    return value > result ? value : result;
  }, 0n);

  return entries.map((entry) => ({
    ...entry,
    magnitude: maximum === 0n
      ? 0
      : Number((absolute(exactInteger(entry.value)) * 10000n) / maximum) / 100,
  }));
}

/**
 * LiveMetrics declares four of its money fields as nullable, and null there
 * means the Backend could not compute the number — a missing current price, an
 * unset gross area — not that the number is zero. Coercing it to "0" would draw
 * a real bar labelled ۰ تومان and tell the reader the project has no remaining
 * cost. Keep the null: `createTomanDisplay` renders it as «قابل محاسبه نیست»,
 * and an uncomputable value gets no bar, because there is no height to draw.
 */
function exactOrNull(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? String(value) : null;
}

//: The four bars, and the metric each one draws. Exported because the caller has to
//: decide, per metric, whether the figure may be drawn at all -- see `withheld` below.
export const MANAGEMENT_BARS = Object.freeze([
  { key: "initial", metric: "initialEstimateIrr", label: "برآورد اولیه" },
  { key: "actual", metric: "actualCostIrr", label: "هزینه واقعی ثبت‌شده" },
  { key: "remaining", metric: "remainingPhysicalCostIrr", label: "هزینه بروز باقیمانده" },
  { key: "forecast", metric: "forecastFinalCostIrr", label: "پیش‌بینی هزینه نهایی" },
]);

export const MANAGEMENT_METRIC_KEYS = Object.freeze(MANAGEMENT_BARS.map((bar) => bar.metric));

/**
 * @param withheld  metric keys whose value must be treated as absent however the service
 *   stated it.
 *
 * The note above keeps a null null, which covers the figure the service could not work
 * out. It does not cover the other one: a sum the service DID publish, as `0`, over none
 * of the project's lines. That is a stated value and arrives here as "0", so the guard
 * above lets it through and the chart draws «۰ تومان» beside «هزینه بروز باقیمانده» --
 * measured on terrace, where the card next to it read «قابل محاسبه نیست». One panel, two
 * answers, and the wrong one is the one that looks like a number.
 *
 * Whether a sum rests on nothing is a question about the report's line counts, not about
 * `metrics`, and this module is given only `metrics`. So the caller -- which already
 * makes exactly this judgement for the cards -- makes it once and names the keys here,
 * and both surfaces withhold the same figures for the same reason.
 */
export function buildOverviewComparisons(metrics = {}, { withheld = [] } = {}) {
  const held = new Set(withheld);
  return Object.freeze({
    management: buildExactScale(MANAGEMENT_BARS.map((bar) => ({
      key: bar.key,
      metric: bar.metric,
      label: bar.label,
      value: held.has(bar.metric) ? null : exactOrNull(metrics[bar.metric]),
    }))),
  });
}


/**
 * The bullet form of the same comparison.
 *
 * A bar chart answers "which category is biggest". This answers the question the
 * bar chart never did: **did this category go past what was estimated for it**.
 * The estimate stops being a second bar and becomes a target marker on the one
 * track the actual cost is drawn along, so passing it is a thing you see rather
 * than a thing you work out by comparing two lengths.
 *
 * The scale is shared across every row and runs to a round number, so the rows
 * stay comparable as amounts and any bar can be read against the axis. The
 * over/under reading, which a shared scale cannot give on its own, is carried by
 * `consumedPercent` beside each row.
 */
function toPercent(actual, estimate) {
  if (estimate <= 0n) return null;
  // Exact: rial are integers and a percentage of them must not go through a
  // float on its way to the screen.
  return Number((actual * 1000n) / estimate) / 10;
}

export function buildBulletPresentation(rows = []) {
  const normalized = rows.map((row) => {
    const estimate = statedInteger(row.initialEstimateIrr);
    const actual = statedInteger(row.actualCostIrr);
    return {
      resourceType: row.resourceType,
      label: TYPE_LABELS[row.resourceType] ?? "نوع تعریف‌نشده",
      // Null is carried, not defaulted. A type whose estimate could not be worked out
      // — this project's equipment lines state no quantity and no rate — is not a type
      // budgeted at nothing, and the table beside this chart already prints "قابل محاسبه
      // نیست" for it.
      initialEstimateIrr: row.initialEstimateIrr == null ? null : String(row.initialEstimateIrr),
      revisedEstimateIrr: row.revisedEstimateIrr == null ? null : String(row.revisedEstimateIrr),
      actualCostIrr: row.actualCostIrr == null ? null : String(row.actualCostIrr),
      forecastFinalIrr: row.forecastFinalIrr == null ? null : String(row.forecastFinalIrr),
      estimate,
      actual,
    };
  });

  const ceilingSource = normalized.reduce((result, row) => {
    const estimate = row.estimate ?? 0n;
    const actual = row.actual ?? 0n;
    const candidate = estimate > actual ? estimate : actual;
    return candidate > result ? candidate : result;
  }, 0n);
  const axis = chooseAxisCeiling(ceilingSource);
  const ceiling = axis?.ceiling ?? 0n;
  const magnitude = (value) => (ceiling <= 0n || value <= 0n ? 0 : Number((value * 10000n) / ceiling) / 100);

  return Object.freeze({
    ceilingIrr: String(ceiling),
    ticks: ceiling > 0n ? buildValueTicks(ceilingSource, { roundUp: true }) : [],
    rows: normalized.map(({ estimate, actual, ...row }) => {
      // A category with no estimate is not a category budgeted at nothing. It is
      // one whose estimate could not be worked out — most often because its
      // lines carry no estimate price — and saying "۰٪ مصرف شده" about it would
      // be an answer to a question nobody could answer.
      const hasEstimate = estimate !== null && estimate > 0n;
      return Object.freeze({
        ...row,
        hasEstimate,
        // A category whose reversals outweigh its documents has a negative
        // actual. It gets no bar rather than a bar drawn from its size.
        actualBelowZero: actual !== null && actual < 0n,
        estimateMagnitude: hasEstimate ? magnitude(estimate) : null,
        // Null actual means the figure is unavailable, so there is no bar to draw --
        // as opposed to a real zero, which draws a bar of no height and means it.
        actualMagnitude: actual === null ? null : magnitude(actual),
        consumedPercent: hasEstimate && actual !== null ? toPercent(actual, estimate) : null,
        overBudget: hasEstimate && actual !== null && actual > estimate,
        overspendIrr: hasEstimate && actual !== null && actual > estimate
          ? String(actual - estimate) : null,
      });
    }),
  });
}
