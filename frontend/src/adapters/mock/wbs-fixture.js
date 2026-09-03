/**
 * The project's level-1 breakdown, as the reference dataset states it.
 *
 * Codes, titles, activity counts and weights are the real ones from the host's
 * own level-1 control report, so the finance page and the progress page name the
 * same phases in the same order. Progress percentages are that report's too.
 *
 * The money is derived, not invented twice: each phase's estimate is the
 * project's total estimate split by the phase's weight, and its actual cost is
 * that estimate carried to the phase's reported progress, adjusted by a cost
 * factor where the phase has run above or below its rate. The consequence is a
 * dataset that reconciles — the phases sum to the project's own برآورد اولیه —
 * and that still shows the case the report exists to reveal: a phase over its
 * budget while the project as a whole is under.
 *
 * None of this survives the real endpoint. `GET /reports/live/by-wbs` replaces
 * it wholesale; see docs/BACKEND_NEEDS_LEVEL1_REPORT_FA.md.
 */

/** code, title, activity count, weight (sums to 100), progress %, cost factor */
const PHASES = Object.freeze([
  ["1.2", "تخریب ساختمان قدیمی", 1, 50, 100, 100],
  ["1.3", "تجهیزکارگاه", 1, 35, 100, 112],
  ["1.4", "خاکبرداری", 2, 50, 100, 96],
  ["1.5", "سازه نگهبان", 5, 100, 100, 104],
  ["1.6", "فونداسيون", 10, 100, 100, 100],
  ["1.7", "دیوارهای حائل", 4, 150, 100, 98],
  ["1.8", "اجرای سازه بتنی", 158, 2200, 100, 108],
  ["1.9", "سفتكاري", 73, 700, 97, 101],
  ["1.10", "کفسازی", 50, 150, 4, 100],
  ["1.11", "تاسيسات مكانيكي فاز 1", 166, 1000, 27, 118],
  ["1.12", "تاسيسات الكتريكي فاز 1", 30, 400, 15, 100],
  ["1.13", "نازك كاري واحدهای مسکونی", 126, 1200, 0, 100],
  ["1.14", "دكوراسيون", 129, 950, 0, 100],
  ["1.15", "نصبیات تاسیسات مکانیکی و الکتریکی", 159, 500, 0, 100],
  ["1.16", "آسانسور", 12, 150, 0, 100],
  ["1.17", "نماي ساختمان و پنجره ها", 34, 900, 29, 94],
  ["1.18", "فضاهاي عمومي", 121, 1150, 8, 100],
  ["1.19", "تجهيزات عمومي و زیربنایی تاسيسات", 37, 200, 0, 100],
  ["1.20", "نطافت و برچیدن کارگاه", 1, 15, 0, 100],
]);

/** How each phase's cost splits across resource types, in per-mille. */
const TYPE_MIX = Object.freeze({
  material: 560, labor: 280, equipment: 110, general_cost: 50,
});

/**
 * Level 2 for the phases the report is most likely to be opened on. A phase with
 * no entry here reports `childCount: 0` and its detail page says the breakdown
 * has not been imported, rather than showing an empty table as if it were a
 * finished answer.
 */
const CHILDREN = Object.freeze({
  "1.8": [
    ["1.8.1", "آرماتوربندی", 62, 420],
    ["1.8.2", "قالب‌بندی", 48, 330],
    ["1.8.3", "بتن‌ریزی", 30, 180],
    ["1.8.4", "عمل‌آوری و کیورینگ", 12, 45],
    ["1.8.5", "قالب‌برداری", 6, 25],
  ],
  "1.11": [
    ["1.11.1", "لوله‌کشی آب سرد و گرم", 58, 340],
    ["1.11.2", "لوله‌کشی فاضلاب", 44, 260],
    ["1.11.3", "کانال‌کشی هوا", 38, 250],
    ["1.11.4", "نصب تجهیزات موتورخانه", 26, 150],
  ],
  "1.9": [
    ["1.9.1", "دیوارچینی", 40, 550],
    ["1.9.2", "نعل درگاه و وادار", 18, 250],
    ["1.9.3", "شیب‌بندی بام", 15, 200],
  ],
});

const PROJECT_ESTIMATE_IRR = 18650000000n;

function splitByWeight(total, weights) {
  const sum = weights.reduce((result, weight) => result + BigInt(weight), 0n);
  if (sum === 0n) return weights.map(() => 0n);
  let allocated = 0n;
  return weights.map((weight, index) => {
    if (index === weights.length - 1) return total - allocated;
    const share = (total * BigInt(weight)) / sum;
    allocated += share;
    return share;
  });
}

function breakdownOf(total) {
  const keys = Object.keys(TYPE_MIX);
  const shares = splitByWeight(total, keys.map((key) => TYPE_MIX[key]));
  return Object.fromEntries(keys.map((key, index) => [key, String(shares[index])]));
}

/** The level-1 rows, plus level 2 for the phases that have it. */
export function buildWbsNodes() {
  const estimates = splitByWeight(PROJECT_ESTIMATE_IRR, PHASES.map(([, , , weight]) => weight));

  const level1 = PHASES.map(([wbsCode, title, activityCount, weight, progress, factor], index) => {
    const estimate = estimates[index];
    // estimate x progress x cost factor, all in integer arithmetic so the row
    // totals stay exact rather than drifting a rial per phase.
    const actual = (estimate * BigInt(progress) * BigInt(factor)) / 10000n;
    const remaining = estimate > actual ? estimate - actual : 0n;
    const forecast = progress === 0 ? estimate : (actual * 100n) / BigInt(Math.max(progress, 1)) * BigInt(factor) / 100n;
    const children = CHILDREN[wbsCode] ?? [];
    return {
      wbsCode,
      title,
      parentWbsCode: null,
      activityCount,
      childCount: children.length,
      weight: String(weight / 100),
      progressPercent: String(progress),
      initialEstimateIrr: String(estimate),
      revisedEstimateIrr: String(estimate),
      actualCostIrr: String(actual),
      remainingPhysicalCostIrr: String(remaining),
      moneyRequiredIrr: String(remaining),
      forecastFinalIrr: String(forecast > estimate ? forecast : estimate),
      breakdown: breakdownOf(actual),
    };
  });

  const level2 = level1.flatMap((parent) => {
    const children = CHILDREN[parent.wbsCode] ?? [];
    if (!children.length) return [];
    const estimateShares = splitByWeight(BigInt(parent.initialEstimateIrr), children.map(([, , , weight]) => weight));
    const actualShares = splitByWeight(BigInt(parent.actualCostIrr), children.map(([, , , weight]) => weight));
    return children.map(([wbsCode, title, activityCount], index) => ({
      wbsCode,
      title,
      parentWbsCode: parent.wbsCode,
      activityCount,
      childCount: 0,
      weight: null,
      progressPercent: parent.progressPercent,
      initialEstimateIrr: String(estimateShares[index]),
      revisedEstimateIrr: String(estimateShares[index]),
      actualCostIrr: String(actualShares[index]),
      remainingPhysicalCostIrr: String(
        estimateShares[index] > actualShares[index] ? estimateShares[index] - actualShares[index] : 0n),
      moneyRequiredIrr: null,
      forecastFinalIrr: String(estimateShares[index]),
      breakdown: breakdownOf(actualShares[index]),
    }));
  });

  return [...level1, ...level2];
}

/**
 * Cost that reaches no phase, because its invoice line carries no estimate line.
 * Roughly a third of the seeded documents are in that state, which is what the
 * live database looks like today — the report has to be able to say so.
 */
export function unattributedActualIrr(nodes) {
  const attributed = nodes
    .filter((node) => node.parentWbsCode === null)
    .reduce((result, node) => result + BigInt(node.actualCostIrr), 0n);
  return String((attributed * 9n) / 100n);
}
