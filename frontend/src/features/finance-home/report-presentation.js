import { buildValueTicks, chooseAxisCeiling } from "../../shared/charts/value-ticks.js";

const TYPE_LABELS = Object.freeze({
  material: "مصالح",
  labor: "نیروی انسانی",
  equipment: "تجهیزات",
  general_cost: "هزینه‌های عمومی پروژه",
});

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : 0n;
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

export function buildOverviewComparisons(metrics = {}) {
  return Object.freeze({
    management: buildExactScale([
      { key: "initial", label: "برآورد اولیه", value: exactOrNull(metrics.initialEstimateIrr) },
      { key: "actual", label: "هزینه واقعی ثبت‌شده", value: exactOrNull(metrics.actualCostIrr) },
      { key: "remaining", label: "هزینه کار باقی‌مانده با قیمت روز", value: exactOrNull(metrics.remainingPhysicalCostIrr) },
      { key: "forecast", label: "پیش‌بینی هزینه نهایی", value: exactOrNull(metrics.forecastFinalCostIrr) },
    ]),
  });
}

export function buildBreakdownPresentation(rows = []) {
  const normalized = rows.map((row) => ({
    resourceType: row.resourceType,
    label: TYPE_LABELS[row.resourceType] ?? "نوع تعریف‌نشده",
    initialEstimateIrr: String(row.initialEstimateIrr ?? "0"),
    revisedEstimateIrr: row.revisedEstimateIrr == null ? null : String(row.revisedEstimateIrr),
    actualCostIrr: String(row.actualCostIrr ?? "0"),
    remainingPhysicalCostIrr: row.remainingPhysicalCostIrr == null ? null : String(row.remainingPhysicalCostIrr),
    forecastFinalIrr: String(row.forecastFinalIrr ?? "0"),
  }));
  const values = normalized.flatMap((row) => [row.initialEstimateIrr, row.actualCostIrr]).map((value) => absolute(exactInteger(value)));
  const maximum = values.reduce((result, value) => value > result ? value : result, 0n);
  return normalized.map((row) => ({
    ...row,
    bars: {
      initial: maximum === 0n ? 0 : Number((absolute(exactInteger(row.initialEstimateIrr)) * 10000n) / maximum) / 100,
      actual: maximum === 0n ? 0 : Number((absolute(exactInteger(row.actualCostIrr)) * 10000n) / maximum) / 100,
    },
  }));
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
    const estimate = exactInteger(row.initialEstimateIrr);
    const actual = exactInteger(row.actualCostIrr);
    return {
      resourceType: row.resourceType,
      label: TYPE_LABELS[row.resourceType] ?? "نوع تعریف‌نشده",
      initialEstimateIrr: String(row.initialEstimateIrr ?? "0"),
      revisedEstimateIrr: row.revisedEstimateIrr == null ? null : String(row.revisedEstimateIrr),
      actualCostIrr: String(row.actualCostIrr ?? "0"),
      forecastFinalIrr: String(row.forecastFinalIrr ?? "0"),
      estimate,
      actual,
    };
  });

  const ceilingSource = normalized.reduce((result, row) => {
    const candidate = row.estimate > row.actual ? row.estimate : row.actual;
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
      const hasEstimate = estimate > 0n;
      return Object.freeze({
        ...row,
        hasEstimate,
        // A category whose reversals outweigh its documents has a negative
        // actual. It gets no bar rather than a bar drawn from its size.
        actualBelowZero: actual < 0n,
        estimateMagnitude: hasEstimate ? magnitude(estimate) : null,
        actualMagnitude: magnitude(actual),
        consumedPercent: hasEstimate ? toPercent(actual, estimate) : null,
        overBudget: hasEstimate && actual > estimate,
        overspendIrr: hasEstimate && actual > estimate ? String(actual - estimate) : null,
      });
    }),
  });
}
