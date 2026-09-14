/**
 * Cost rolled up the project's own breakdown structure.
 *
 * The host platform issues a level-1 progress report: one row per phase, planned
 * against actual, weighted. This is the same report in rial — what each phase was
 * estimated to cost and what it has cost so far — so a reader holding both is
 * looking at one project from two sides rather than at two unrelated documents.
 *
 * Everything here consumes the shape `GET /reports/live/by-wbs` is specified to
 * return (see docs/BACKEND_NEEDS_LEVEL1_REPORT_FA.md). That endpoint does not
 * exist yet. Nothing in this file reaches for it: it takes node rows and returns
 * a drawable view, so when the endpoint ships only the adapter changes.
 *
 * Money is BigInt on exact integer IRR. Floats appear only as drawing
 * magnitudes — a percentage of the widest bar — never as an amount.
 */

const RESOURCE_TYPES = Object.freeze(["material", "labor", "equipment", "general_cost"]);

export const RESOURCE_TYPE_LABELS = Object.freeze({
  material: "مصالح",
  labor: "نیروی انسانی",
  equipment: "تجهیزات",
  general_cost: "هزینه عمومی",
});

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

function amount(value) {
  return exactInteger(value) ?? 0n;
}

/**
 * Orders WBS codes the way the structure reads, not the way strings sort.
 *
 * "1.10" sorts before "1.2" lexicographically, which would put the tenth phase
 * second and scatter the rest. Each dot-separated segment is compared as a
 * number where it is one, and as text where it is not — a project numbering its
 * phases "A.1" still gets a stable order instead of an exception.
 */
export function compareWbsCodes(left, right) {
  const leftParts = String(left ?? "").split(".");
  const rightParts = String(right ?? "").split(".");
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const a = leftParts[index];
    const b = rightParts[index];
    if (a === undefined) return -1;
    if (b === undefined) return 1;
    const numericA = /^\d+$/.test(a) ? Number(a) : null;
    const numericB = /^\d+$/.test(b) ? Number(b) : null;
    if (numericA !== null && numericB !== null) {
      if (numericA !== numericB) return numericA - numericB;
    } else if (a !== b) {
      return a < b ? -1 : 1;
    }
  }
  return 0;
}

/** The direct children of `parentWbsCode`, or the roots when it is null. */
export function childrenOf(nodes = [], parentWbsCode = null) {
  return nodes
    .filter((node) => (node.parentWbsCode ?? null) === (parentWbsCode ?? null))
    .sort((left, right) => compareWbsCodes(left.wbsCode, right.wbsCode));
}

export function findNode(nodes = [], wbsCode) {
  return nodes.find((node) => node.wbsCode === wbsCode) ?? null;
}

function magnitude(value, ceiling) {
  if (ceiling <= 0n || value <= 0n) return 0;
  return Number((value * 10000n) / ceiling) / 100;
}

/** Exact percentage as a string, e.g. "112.4" — never a float on money. */
function percentText(part, whole) {
  if (whole <= 0n) return null;
  const scaled = (part * 1000n) / whole;
  const units = scaled / 10n;
  const tenths = scaled % 10n;
  return tenths === 0n ? String(units) : `${units}.${tenths}`;
}

/**
 * The drawable view of one level of the structure.
 *
 * `nodes` are the rows for that level. Both series share one ceiling so the rows
 * stay comparable to each other — a phase estimated at a tenth of another should
 * look like a tenth. The ceiling clears the actuals too, or a phase that has
 * overrun would be cut off at the end of its track and stop looking like one.
 */
export function buildWbsView({ nodes = [], unattributedActualIrr = null,
                               unmappedEstimateIrr = null,
                               unmappedEstimateLineCount = 0 } = {}) {
  const ordered = [...nodes].sort((left, right) => compareWbsCodes(left.wbsCode, right.wbsCode));
  if (!ordered.length) {
    return Object.freeze({
      isEmpty: true, rows: [], ceilingIrr: "0", totals: null,
      hasEstimate: false, unattributed: null, overBudgetCount: 0,
    });
  }

  const ceiling = ordered.reduce((result, node) => {
    const estimate = amount(node.initialEstimateIrr);
    const actual = amount(node.actualCostIrr);
    const forecast = amount(node.forecastFinalIrr);
    return [estimate, actual, forecast].reduce((top, value) => (value > top ? value : top), result);
  }, 0n);

  const rows = ordered.map((node) => {
    // Stated separately from the arithmetic value: a phase whose estimate the Backend
    // could not work out reports null, and null must survive to the chart. Reading it as
    // zero drew it as a bar of height nothing labelled ۰, which is what a phase budgeted
    // at nothing looks like — two different facts wearing one picture.
    const statedEstimate = exactInteger(node.initialEstimateIrr);
    const estimate = statedEstimate ?? 0n;
    // Lines of this phase that state no baseline. The estimate beside it is the sum
    // of the rest, so the two numbers only mean anything together.
    const missingEstimateLines = Number(node.missingEstimateLineCount ?? 0) || 0;
    const revised = node.revisedEstimateIrr == null ? estimate : amount(node.revisedEstimateIrr);
    const actual = amount(node.actualCostIrr);
    // Stated separately for the same reason the estimate is: the service answers null
    // wherever it could not finish the calculation, and a forecast of "nothing" is a
    // different claim from "not worked out". Twelve of the thirteen phases on the
    // candidate arrive null, and all twelve used to print as ۰.
    const statedForecast = exactInteger(node.forecastFinalIrr);
    const forecast = statedForecast ?? 0n;
    const hasEstimate = statedEstimate !== null && estimate > 0n;
    const deviation = hasEstimate ? actual - estimate : null;
    return {
      wbsCode: node.wbsCode,
      title: node.title ?? node.wbsCode,
      parentWbsCode: node.parentWbsCode ?? null,
      activityCount: node.activityCount ?? 0,
      childCount: node.childCount ?? 0,
      hasChildren: (node.childCount ?? 0) > 0,
      missingEstimateLineCount: missingEstimateLines,
      estimateIsPartial: statedEstimate !== null && missingEstimateLines > 0,
      // Zero lines is not a costing of zero. A phase with no estimate lines has nothing to
      // sum, so its blank says "not costed" where another phase's blank says "not worked
      // out" -- and the reader has to be able to tell those apart.
      estimateLineCount: Number(node.estimateLineCount ?? 0) || 0,
      hasEstimateBasis: (Number(node.estimateLineCount ?? 0) || 0) > 0,
      initialEstimateIrr: statedEstimate === null ? null : String(estimate),
      revisedEstimateIrr: statedEstimate === null && node.revisedEstimateIrr == null
        ? null : String(revised),
      actualCostIrr: String(actual),
      remainingPhysicalCostIrr: node.remainingPhysicalCostIrr ?? null,
      moneyRequiredIrr: node.moneyRequiredIrr ?? null,
      forecastFinalIrr: statedForecast === null ? null : String(forecast),
      breakdown: normalizeBreakdown(node.breakdown),
      hasEstimate,
      // Only meaningful against an estimate; a phase with none reports null
      // rather than 0, which would read as "spent nothing of a real budget".
      consumedPercent: hasEstimate ? percentText(actual, estimate) : null,
      deviationIrr: deviation === null ? null : String(deviation),
      overBudget: deviation !== null && deviation > 0n,
      started: actual > 0n,
      estimateMagnitude: statedEstimate === null ? null : magnitude(estimate, ceiling),
      actualMagnitude: magnitude(actual, ceiling),
      forecastMagnitude: statedForecast === null ? null : magnitude(forecast, ceiling),
    };
  });

  const sum = (key) => rows.reduce((result, row) => result + amount(row[key]), 0n);
  const missingEstimateLines = rows.reduce(
    (result, row) => result + row.missingEstimateLineCount, 0);
  // A total is only a total when every phase is in it. With one phase unavailable the
  // sum is a subtotal, and publishing it under "برآورد اولیه مراحل" would understate the
  // project by however much the missing phases hold.
  const estimateKnownEverywhere = rows.every((row) => row.initialEstimateIrr !== null);
  const totalEstimate = estimateKnownEverywhere ? sum("initialEstimateIrr") : null;
  const totalActual = sum("actualCostIrr");
  const unattributed = exactInteger(unattributedActualIrr);

  return Object.freeze({
    isEmpty: false,
    rows,
    ceilingIrr: String(ceiling),
    hasEstimate: rows.some((row) => row.hasEstimate),
    overBudgetCount: rows.filter((row) => row.overBudget).length,
    totals: Object.freeze({
      initialEstimateIrr: totalEstimate === null ? null : String(totalEstimate),
      actualCostIrr: String(totalActual),
      // A total over phases whose forecast is unknown would be a subtotal under the name
      // of a total, which is the same mistake the estimate total above refuses.
      forecastFinalIrr: rows.every((row) => row.forecastFinalIrr !== null)
        ? String(sum("forecastFinalIrr")) : null,
      consumedPercent: totalEstimate === null ? null : percentText(totalActual, totalEstimate),
      activityCount: rows.reduce((result, row) => result + (row.activityCount ?? 0), 0),
      // The project-wide version of the same qualification. A total that adds up
      // across every phase can still be missing lines inside them.
      missingEstimateLineCount: missingEstimateLines,
      estimateIsPartial: totalEstimate !== null && missingEstimateLines > 0,
      // How many phases have no estimate basis at all. Separate from the count of lines
      // missing a baseline: those are lines inside a phase that does have some.
      stagesWithoutEstimateBasis: rows.filter((row) => !row.hasEstimateBasis).length,
      // And a second, different absence: lines whose activity reaches no phase at all are
      // not inside any row above, so this total cannot contain them however complete each
      // phase is. The service reports both the count and the amount; without them the
      // stages quietly sum to less than the project's own estimate.
      unmappedEstimateIrr: exactInteger(unmappedEstimateIrr) === null
        ? null : String(exactInteger(unmappedEstimateIrr)),
      unmappedEstimateLineCount: Number(unmappedEstimateLineCount ?? 0) || 0,
    }),
    /**
     * Cost that reaches no phase at all.
     *
     * An invoice line may carry no estimate line, and a cost with no estimate
     * line has no activity and therefore no phase. Left out silently, the phases
     * would sum to less than the project total and nothing on the page would say
     * why — so it is carried here and shown as its own row.
     */
    unattributed: unattributed === null || unattributed === 0n ? null : Object.freeze({
      actualCostIrr: String(unattributed),
      magnitude: magnitude(unattributed, ceiling),
      sharePercent: percentText(unattributed, totalActual + unattributed),
    }),
  });
}

function normalizeBreakdown(breakdown) {
  if (!breakdown || typeof breakdown !== "object") return null;
  const entries = RESOURCE_TYPES
    .map((type) => [type, exactInteger(breakdown[type])])
    .filter(([, value]) => value !== null);
  if (!entries.length) return null;
  const total = entries.reduce((result, [, value]) => result + value, 0n);
  return entries.map(([type, value]) => ({
    resourceType: type,
    label: RESOURCE_TYPE_LABELS[type] ?? type,
    amountIrr: String(value),
    sharePercent: percentText(value, total),
    magnitude: magnitude(value, entries.reduce((top, [, v]) => (v > top ? v : top), 0n)),
  }));
}
