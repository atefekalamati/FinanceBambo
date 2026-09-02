import { chooseAxisCeiling } from "./value-ticks.js";

/**
 * The cumulative cost curve: plan against actual, both climbing period by period.
 *
 * This is the money twin of the progress S-curve the host platform already
 * issues. The shape carries the same claim — where the project said it would be
 * by now, and where it actually is — measured in rial instead of percent.
 *
 * Both series are staircases of their own periods: the value at period N is the
 * sum of every period up to and including N, so the curve can only climb. That
 * property is not decoration. A cumulative series that dips would be telling the
 * reader money was un-spent, and the smoothing below is chosen specifically to
 * keep it from happening.
 *
 * Money stays BigInt on exact integer IRR. Floats appear only as drawing
 * magnitudes — a percentage of the plot — never as an amount or a deviation.
 */

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

/**
 * The axis ceiling, with room above the data for the case the project is
 * heading for.
 *
 * A cost curve is not a progress curve: progress cannot pass 100, but spending
 * can pass the estimate, and the moment it does is exactly what the reader
 * opened the chart to see. An axis that ends at the plan's final value would
 * clip that overrun against the top edge, or worse, rescale so the two curves
 * look like they still meet. The headroom is added before the 1-2-5 ladder
 * rounds up, so the ceiling stays a number a person would have chosen.
 */
export function chooseCurveCeiling(maximum, { headroomPercent = 15, intervals = 4, maximumLines = 6 } = {}) {
  const top = typeof maximum === "bigint" ? maximum : exactInteger(maximum);
  if (top === null || top <= 0n) return null;
  const lifted = (top * BigInt(100 + Math.max(0, headroomPercent))) / 100n;
  return chooseAxisCeiling(lifted, { intervals, maximumLines });
}

/** Lines from zero to the ceiling, one per step. */
function ticksTo(ceiling, step) {
  const ticks = [];
  for (let value = 0n; value <= ceiling; value += step) {
    ticks.push({
      valueIrr: String(value),
      magnitude: ceiling === 0n ? 0 : Number((value * 10000n) / ceiling) / 100,
    });
    if (ticks.length > 32) break; // a guard, not a limit a real axis reaches
  }
  return ticks;
}

function magnitude(value, ceiling) {
  if (ceiling <= 0n) return 0;
  if (value <= 0n) return 0;
  return Number((value * 10000n) / ceiling) / 100;
}

/**
 * Fritsch–Carlson monotone cubic tangents.
 *
 * An ordinary Catmull–Rom or cardinal spline overshoots around a sharp change in
 * slope, which on a cumulative series draws a visible dip before a steep climb —
 * a curve that says spending went backwards in a month it did not. This
 * constrains each tangent so the interpolant is monotone wherever the data is,
 * which for a running total is everywhere.
 */
function monotoneTangents(xs, ys) {
  const count = xs.length;
  if (count < 2) return new Array(count).fill(0);

  const secants = [];
  for (let index = 0; index < count - 1; index += 1) {
    const run = xs[index + 1] - xs[index];
    secants.push(run === 0 ? 0 : (ys[index + 1] - ys[index]) / run);
  }

  const tangents = new Array(count);
  tangents[0] = secants[0];
  tangents[count - 1] = secants[count - 2];
  for (let index = 1; index < count - 1; index += 1) {
    const before = secants[index - 1];
    const after = secants[index];
    tangents[index] = before * after <= 0 ? 0 : (before + after) / 2;
  }

  for (let index = 0; index < count - 1; index += 1) {
    const secant = secants[index];
    if (secant === 0) {
      tangents[index] = 0;
      tangents[index + 1] = 0;
      continue;
    }
    const left = tangents[index] / secant;
    const right = tangents[index + 1] / secant;
    const squared = left * left + right * right;
    if (squared > 9) {
      const scale = 3 / Math.sqrt(squared);
      tangents[index] = scale * left * secant;
      tangents[index + 1] = scale * right * secant;
    }
  }
  return tangents;
}

/**
 * A smooth path through the given magnitudes, in the chart's own 0–100 space.
 * `y` is measured from the bottom, so the caller flips it once when it draws
 * rather than every helper here having to know which way up the plot is.
 */
export function curvePath(series) {
  if (!series.length) return "";
  if (series.length === 1) return `M ${series[0].x} ${series[0].y}`;

  const xs = series.map((point) => point.x);
  const ys = series.map((point) => point.y);
  const tangents = monotoneTangents(xs, ys);

  let path = `M ${xs[0]} ${ys[0]}`;
  for (let index = 0; index < series.length - 1; index += 1) {
    const run = (xs[index + 1] - xs[index]) / 3;
    const c1x = xs[index] + run;
    const c1y = ys[index] + tangents[index] * run;
    const c2x = xs[index + 1] - run;
    const c2y = ys[index + 1] - tangents[index + 1] * run;
    path += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${xs[index + 1]} ${ys[index + 1]}`;
  }
  return path;
}

/**
 * Builds both curves from already-cumulative rows.
 *
 * Feed it the output of `buildMonthlyTrend({ mode: CUMULATIVE })`, whose
 * `actualIrr` and `estimateIrr` are running totals rather than each period's own
 * spend. A row whose `actualIrr` is null is a period the project has not reached
 * yet: the actual curve stops there and the plan carries on alone, which is the
 * shape the reader recognises from the progress report.
 */
export function buildCostCurve({ points = [], headroomPercent = 15 } = {}) {
  const rows = [...points];
  if (!rows.length) {
    return Object.freeze({
      isEmpty: true, ceilingIrr: "0", ticks: [], actual: [], plan: [],
      actualPath: "", areaPath: "", planPath: "", marker: null,
      hasPlan: false, planPartial: false, hasActual: false,
    });
  }

  const amounts = [];
  rows.forEach((row) => {
    const actual = exactInteger(row.actualIrr);
    const plan = exactInteger(row.estimateIrr);
    if (actual !== null) amounts.push(actual);
    if (plan !== null) amounts.push(plan);
  });
  const top = amounts.reduce((result, value) => (value > result ? value : result), 0n);
  const axis = chooseCurveCeiling(top, { headroomPercent });
  const ceiling = axis?.ceiling ?? 0n;

  // Evenly spaced: the periods are a sequence of reports, not a measured
  // timeline, and spacing them by their day counts would make a short period
  // look like a pause in spending.
  const span = rows.length === 1 ? 1 : rows.length - 1;
  const xAt = (index) => (rows.length === 1 ? 50 : (index * 100) / span);

  const actual = [];
  const plan = [];
  rows.forEach((row, index) => {
    const x = xAt(index);
    const actualIrr = exactInteger(row.actualIrr);
    const planIrr = exactInteger(row.estimateIrr);
    if (actualIrr !== null) {
      actual.push({ x, y: magnitude(actualIrr, ceiling), valueIrr: String(actualIrr), index, row });
    }
    if (planIrr !== null) {
      plan.push({ x, y: magnitude(planIrr, ceiling), valueIrr: String(planIrr), index, row });
    }
  });

  const actualPath = curvePath(actual);
  const last = actual[actual.length - 1] ?? null;

  return Object.freeze({
    isEmpty: false,
    ceilingIrr: String(ceiling),
    ticks: axis ? ticksTo(ceiling, axis.step) : [],
    actual,
    plan,
    actualPath,
    // The filled area is the same curve closed down to the baseline. Built from
    // the identical path string so the fill can never drift from its own edge.
    areaPath: actual.length > 1 && actualPath
      ? `${actualPath} L ${last.x} 0 L ${actual[0].x} 0 Z`
      : "",
    planPath: curvePath(plan),
    // Where the actual series stops — the reader's "you are here".
    marker: last ? { x: last.x, y: last.y, valueIrr: last.valueIrr, row: last.row } : null,
    hasActual: actual.length > 0,
    hasPlan: plan.length > 0,
    planPartial: plan.length > 0 && plan.length < rows.length,
    periods: rows.map((row, index) => ({
      x: xAt(index),
      key: row.key,
      label: row.periodLabel ?? row.label ?? "",
      shortLabel: row.shortLabel ?? row.periodLabel ?? row.label ?? "",
      fullLabel: row.fullLabel ?? row.label ?? "",
    })),
  });
}
