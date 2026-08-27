/**
 * One row per item, not one per estimate line.
 *
 * The service answers with an estimate line each: میلگرد used on ACT-102 and
 * میلگرد used on ACT-201 arrive as two rows, correctly, because a line is what a
 * quantity is revised on and what a price is applied to. A card headed
 * «بیشترین انحراف قیمت» is a different question — it asks which *items* moved
 * the project — and answering it with two rows both labelled میلگرد reads as a
 * duplicate, because on that card it is one.
 *
 * So the rows are folded back onto the item. What is summed is only what the
 * service already computed from the current state: the live price version and
 * the latest revised quantity. No superseded price and no pre-revision quantity
 * is added in — the arithmetic here never reaches for history, because the rows
 * it is given never contain any.
 *
 * A total of exactly zero is dropped. A line whose quantity was never revised
 * has a deviation of zero and belongs on the estimate table, not on a card that
 * claims to list the largest deviations.
 *
 * Everything is exact. Money is an integer rial string and quantities carry four
 * documented decimal places; both are added as integers, never as floats.
 */

const DECIMAL = /^-?\d+(\.\d+)?$/;

function parseDecimal(value) {
  const text = String(value ?? "").trim();
  if (!DECIMAL.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  const negative = whole.startsWith("-");
  const digits = `${whole.replace("-", "")}${fraction}`;
  return { scaled: BigInt(negative ? `-${digits}` : digits), scale: fraction.length };
}

/** Adds two decimal strings without ever converting them to a number. */
export function addExactDecimal(left, right) {
  const first = parseDecimal(left);
  const second = parseDecimal(right);
  if (!first) return second ? formatDecimal(second) : null;
  if (!second) return formatDecimal(first);
  const scale = Math.max(first.scale, second.scale);
  const lift = (value) => value.scaled * 10n ** BigInt(scale - value.scale);
  return formatDecimal({ scaled: lift(first) + lift(second), scale });
}

function formatDecimal({ scaled, scale }) {
  if (scale === 0) return String(scaled);
  const negative = scaled < 0n;
  const digits = (negative ? -scaled : scaled).toString().padStart(scale + 1, "0");
  const whole = digits.slice(0, digits.length - scale);
  const fraction = digits.slice(digits.length - scale);
  return `${negative ? "-" : ""}${whole}.${fraction}`;
}

function isZero(value) {
  const parsed = parseDecimal(value);
  return !parsed || parsed.scaled === 0n;
}

function compareByMagnitude(left, right, key) {
  const magnitude = (row) => {
    const parsed = parseDecimal(row[key]);
    if (!parsed) return 0n;
    // Compared at a common scale so 1250.0000 and 80.00 sort against each other.
    const lifted = parsed.scaled * 10n ** BigInt(8 - Math.min(parsed.scale, 8));
    return lifted < 0n ? -lifted : lifted;
  };
  const first = magnitude(left);
  const second = magnitude(right);
  return first === second ? 0 : first > second ? -1 : 1;
}

/**
 * `keyOf` decides what counts as one item. Quantities include the unit, because
 * adding hours to kilograms would produce a number that means nothing — if a
 * resource ever arrives with two units they stay two rows, visibly, rather than
 * being silently summed.
 */
function rollup(rows, { valueKey, sumKeys = [], keyOf }) {
  const groups = new Map();
  (rows ?? []).forEach((row) => {
    const key = keyOf(row);
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, {
        ...row,
        // A folded row is not a line, and must not pretend to link to one.
        estimateLineId: null,
        activityExternalId: null,
        activityTitle: null,
        wbsCode: null,
        lineCount: 1,
      });
      return;
    }
    existing[valueKey] = addExactDecimal(existing[valueKey], row[valueKey]);
    sumKeys.forEach((name) => {
      if (row[name] != null) existing[name] = addExactDecimal(existing[name], row[name]);
    });
    existing.lineCount += 1;
    if (row.priceAvailable === false) existing.priceAvailable = false;
  });
  return [...groups.values()]
    .filter((row) => !isZero(row[valueKey]))
    .sort((left, right) => compareByMagnitude(left, right, valueKey))
    .map((row) => Object.freeze(row));
}

export function rollupPriceVariances(rows = []) {
  return rollup(rows, {
    valueKey: "varianceIrr",
    // Rial, so the item's unit does not enter into it.
    keyOf: (row) => row.resourceId ?? row.resourceCode ?? row.resourceTitle ?? "",
    sumKeys: ["actualCostIrr", "remainingPhysicalCostIrr", "forecastFinalIrr", "revisedQuantity", "remainingQuantity"],
  });
}

export function rollupQuantityVariances(rows = []) {
  return rollup(rows, {
    valueKey: "varianceQuantity",
    keyOf: (row) => `${row.resourceId ?? row.resourceCode ?? row.resourceTitle ?? ""}::${row.baseUnit ?? ""}`,
    sumKeys: ["initialQuantity", "revisedQuantity", "executedQuantity", "remainingQuantity", "actualCostIrr", "remainingPhysicalCostIrr", "forecastFinalIrr"],
  });
}
