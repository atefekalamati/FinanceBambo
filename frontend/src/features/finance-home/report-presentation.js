const TYPE_LABELS = Object.freeze({
  material: "مصالح",
  labor: "نیروی انسانی",
  equipment: "تجهیزات",
  general_cost: "هزینه عمومی",
});

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : 0n;
}

function absolute(value) {
  return value < 0n ? -value : value;
}

export function buildBreakdownPresentation(rows = []) {
  const normalized = rows.map((row) => ({
    resourceType: row.resourceType,
    label: TYPE_LABELS[row.resourceType] ?? "نوع تعریف‌نشده",
    initialEstimateIrr: String(row.initialEstimateIrr ?? "0"),
    actualCostIrr: String(row.actualCostIrr ?? "0"),
    forecastFinalIrr: String(row.forecastFinalIrr ?? "0"),
  }));
  const values = normalized.flatMap((row) => [row.initialEstimateIrr, row.actualCostIrr, row.forecastFinalIrr]).map((value) => absolute(exactInteger(value)));
  const maximum = values.reduce((result, value) => value > result ? value : result, 0n);
  return normalized.map((row) => ({
    ...row,
    bars: {
      initial: maximum === 0n ? 0 : Number((absolute(exactInteger(row.initialEstimateIrr)) * 10000n) / maximum) / 100,
      actual: maximum === 0n ? 0 : Number((absolute(exactInteger(row.actualCostIrr)) * 10000n) / maximum) / 100,
      forecast: maximum === 0n ? 0 : Number((absolute(exactInteger(row.forecastFinalIrr)) * 10000n) / maximum) / 100,
    },
  }));
}
