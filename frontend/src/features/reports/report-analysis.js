const TYPE_LABELS = Object.freeze({
  material: "مصالح",
  labor: "نیروی انسانی",
  equipment: "تجهیزات و ماشین‌آلات",
  general_cost: "هزینه‌های عمومی پروژه",
});

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : 0n;
}

function absolute(value) {
  return value < 0n ? -value : value;
}

export function buildPriceVariancePresentation(rows = []) {
  const maximum = rows.reduce((result, row) => {
    const value = absolute(exactInteger(row.varianceIrr));
    return value > result ? value : result;
  }, 0n);

  return rows.map((row) => {
    const value = exactInteger(row.varianceIrr);
    return Object.freeze({
      ...row,
      resourceTypeLabel: TYPE_LABELS[row.resourceType] ?? "نوع تعریف‌نشده",
      varianceIrr: String(row.varianceIrr ?? "0"),
      direction: value > 0n ? "increase" : value < 0n ? "decrease" : "stable",
      directionLabel: value > 0n ? "افزایش هزینه" : value < 0n ? "کاهش هزینه" : "بدون تغییر",
      magnitude: maximum === 0n ? 0 : Number((absolute(value) * 10000n) / maximum) / 100,
    });
  });
}

export function buildQuantityVariancePresentation(rows = []) {
  return rows.map((row) => Object.freeze({
    ...row,
    resourceTypeLabel: TYPE_LABELS[row.resourceType] ?? "نوع تعریف‌نشده",
    varianceQuantity: String(row.varianceQuantity ?? "0"),
  }));
}
