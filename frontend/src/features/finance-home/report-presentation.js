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
