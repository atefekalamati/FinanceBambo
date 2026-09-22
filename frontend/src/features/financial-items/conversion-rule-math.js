/* What a conversion rule does to a price, worked out exactly, before anybody saves it.
 *
 * WHY THIS EXISTS AT ALL
 * A person writing «۱ شاخه = ۲۲ کیلوگرم» is making a claim they cannot check. The units
 * are right, the number is right, and the price that falls out the other end is either
 * twenty million rials or forty thousand, depending on which way round the module read
 * it. Telling them the resulting price BEFORE the rule is stored is the only way they can
 * confirm the claim is the one they meant — and it is what the whole feature is for, since
 * a rule exists so that a daily price appears.
 *
 * THE CONVENTION, WHICH IS THE SERVER'S AND IS NOT NEGOTIABLE HERE
 *
 *     a rule states     1 from_unit = factor × to_unit        (a QUANTITY statement)
 *     a price converts  price per from_unit ÷ factor          (its inverse)
 *
 * `daily_estimate.convert_daily_unit_price` is the one place the server decides this, and
 * the division is the whole of it. The two branches below are that same division, read
 * from whichever side the person chose to state:
 *
 *     stated source→selected   «۱ کیلوگرم = ۱٫۲ شاخه»   price ÷ 1.2
 *     stated selected→source   «۱ شاخه = ۲۲ کیلوگرم»    price × 22
 *
 * Both give a price per the LINE's unit, which is the only number the table wants.
 *
 * EXACT, NOT FLOATING POINT
 * `0.1 + 0.2` is famously not `0.3`, and these numbers are rials. Everything here is a
 * fraction of two BigInts, and rounding happens once, at the end, where it is visible.
 */

/**
 * A decimal string as an exact fraction. `null` for anything that is not one.
 *
 * Deliberately strict: no exponents, no separators, no signs. A price or a factor arrives
 * from the server as a plain decimal string, and a value that is not one is a value this
 * module has no business guessing at.
 */
export function rational(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  return { num: BigInt(whole + fraction), den: 10n ** BigInt(fraction.length) };
}

/** `a × b`, still exact. */
function times(a, b) {
  return { num: a.num * b.num, den: a.den * b.den };
}

/** `a ÷ b`, or null when b is zero — which is «no usable factor», never an error. */
function over(a, b) {
  if (b.num === 0n) return null;
  return { num: a.num * b.den, den: a.den * b.num };
}

/**
 * A fraction as an integer string, rounded half-up.
 *
 * Half-up rather than banker's rounding because this number is shown to a person beside a
 * price they are about to accept, and «نیم ریال به بالا» is the rule they would apply
 * themselves. The server keeps eight decimal places internally; the difference never
 * reaches a toman.
 */
export function roundToInteger(value) {
  if (!value || value.den === 0n) return null;
  const doubled = value.num * 2n + value.den;
  const floored = doubled / (value.den * 2n);
  // BigInt division truncates toward zero, which is floor for the non-negative numbers
  // this module accepts. Prices and factors are both positive by construction.
  return floored.toString();
}

/**
 * Today's price per the LINE's unit, given a rule stated in either direction.
 *
 * Returns a decimal string of rials, or null when the rule does not bridge these two
 * units at all — which is a real answer and not a failure: it is how the dialog knows the
 * person has described a crossing other than the one in front of them.
 */
export function convertedUnitPriceIRR({ priceIRR, sourceUnit, selectedUnit,
                                        statedFrom, statedTo, factor }) {
  const price = rational(priceIRR);
  const ratio = rational(factor);
  if (!price || !ratio || ratio.num === 0n) return null;
  if (!sourceUnit || !selectedUnit || sourceUnit === selectedUnit) return null;

  let converted = null;
  if (statedFrom === sourceUnit && statedTo === selectedUnit) {
    // «۱ کیلوگرم = ۱٫۲ شاخه» against a price per kilogram: divide.
    converted = over(price, ratio);
  } else if (statedFrom === selectedUnit && statedTo === sourceUnit) {
    // «۱ شاخه = ۲۲ کیلوگرم» against a price per kilogram: the same statement read
    // backwards, which is a multiplication. Done as a multiplication rather than as a
    // division by 1/22, so no rounding is introduced by inverting first.
    converted = times(price, ratio);
  }
  return converted === null ? null : roundToInteger(converted);
}

/** That price times the line's own quantity: what this row would cost today. */
export function lineCostIRR({ unitPriceIRR, quantity }) {
  const price = rational(unitPriceIRR);
  const amount = rational(quantity);
  if (!price || !amount) return null;
  return roundToInteger(times(price, amount));
}

/* ------------------------------------------------------------------ existing rules */

/* Which identifier each scope is ABOUT. A `category` rule and another `category` rule for
   a different category do not occupy the same place, so replacing one would not replace
   the other. Mirrors the database's own uniqueness key, which is what decides whether a
   second rule can be approved beside the first. */
const SCOPE_KEY = Object.freeze({
  provider_item: "providerItemId",
  provider: "providerId",
  category: "category",
});

/**
 * Every live rule already occupying the scope this person is about to write into.
 *
 * NOT a re-implementation of the server's precedence. That decides which of several rules
 * WINS, and doing it twice would be two sources of truth that will eventually disagree.
 * This asks a narrower and purely local question: is this exact slot taken? — because that
 * is the one the person can act on, by replacing what is there.
 *
 * Either direction counts. `branch→kg` and `kg→branch` at one scope are two live answers
 * to one question, and 22 and 0.05 are not each other's inverse; the server refuses the
 * second, and finding it here means the refusal never has to happen.
 *
 * PLURAL, BECAUSE THE DATA IS. Measured on the live project, one listing held an approved
 * `kg→branch` and an approved `branch→kg` at the same scope — written before the server
 * started refusing the pair, and both still in force. Returning one of them would let a
 * replacement close half the problem and then be refused by the unique index when the new
 * rule was approved beside the survivor.
 *
 * Approved first: those are what is actually producing numbers, and what has to be closed.
 */
export function occupantsOf(rules, { scopeType, fromUnit, toUnit, providerItemId = null,
                                     providerId = null, category = null }) {
  const wanted = { providerItemId, providerId, category };
  const key = SCOPE_KEY[scopeType];
  return (rules ?? []).filter((rule) => {
    if (!rule || rule.scopeType !== scopeType) return false;
    if (rule.status !== "approved" && rule.status !== "draft") return false;
    if (rule.effectiveTo) return false;
    if (key && String(rule[key] ?? "") !== String(wanted[key] ?? "")) return false;
    const stated = [rule.fromUnit, rule.toUnit].join(">");
    return stated === [fromUnit, toUnit].join(">")
        || stated === [toUnit, fromUnit].join(">");
  }).sort((a, b) => (a.status === "approved" ? 0 : 1) - (b.status === "approved" ? 0 : 1));
}

/** The one to name in the message and to record as superseded: the approved one, if any. */
export function occupiedBy(rules, query) {
  return occupantsOf(rules, query)[0] ?? null;
}

/** Every live rule that crosses these two units, either way round, narrowest first. */
export function rulesForCrossing(rules, { fromUnit, toUnit }) {
  const order = ["provider_item", "provider", "category", "project", "organization", "global"];
  return (rules ?? [])
    .filter((rule) => {
      if (!rule || rule.effectiveTo) return false;
      const stated = [rule.fromUnit, rule.toUnit].join(">");
      return stated === [fromUnit, toUnit].join(">")
          || stated === [toUnit, fromUnit].join(">");
    })
    .sort((a, b) => order.indexOf(a.scopeType) - order.indexOf(b.scopeType));
}
