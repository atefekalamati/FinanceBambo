import { formatDisplayNumber } from "./display.js";
import { normalizeDecimalInput } from "../validation/decimal-validation.js";
import { getDisplayCurrencyCode, getDisplayCurrencyLabel } from "../preferences/currency-preference.js";

const RTL_ISOLATE_START = "\u2067";
const DIRECTIONAL_ISOLATE_END = "\u2069";

function isolateRtlMoney(text) {
  return `${RTL_ISOLATE_START}${text}${DIRECTIONAL_ISOLATE_END}`;
}

export function irrToToman(value) {
  if (!/^-?\d+$/.test(String(value ?? ""))) return null;
  const amount = BigInt(value);
  const whole = amount / 10n;
  const remainder = amount < 0n ? -(amount % 10n) : amount % 10n;
  return remainder === 0n ? String(whole) : `${amount < 0n && whole === 0n ? "-" : ""}${whole}.${remainder}`;
}

export function formatTomanFromIrr(value, { withCurrency = true, fallback = "—" } = {}) {
  const displayValue = irrToDisplayValue(value);
  if (displayValue === null) return fallback;
  const formatted = formatDisplayNumber(displayValue);
  return withCurrency ? isolateRtlMoney(`${formatted} ${getDisplayCurrencyLabel()}`) : formatted;
}

const COMPACT_MONEY_SCALES = Object.freeze([
  { threshold: 1_000_000_000_000n, label: "تریلیون" },
  { threshold: 1_000_000_000n, label: "میلیارد" },
  { threshold: 1_000_000n, label: "میلیون" },
]);

function formatRoundedHundredths(value) {
  const whole = value / 100n;
  const fraction = String(value % 100n).padStart(2, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}

export function compactMoneyFromIrr(value) {
  if (!/^-?\d+$/.test(String(value ?? ""))) return null;
  const canonical = BigInt(value);
  const negative = canonical < 0n;
  const absolute = negative ? -canonical : canonical;
  const currencyCode = getDisplayCurrencyCode();
  const currencyDivisor = currencyCode === "IRR" ? 1n : 10n;
  let selectedIndex = COMPACT_MONEY_SCALES.findIndex(({ threshold }) => absolute >= threshold * currencyDivisor);

  if (selectedIndex < 0) {
    const exactValue = irrToDisplayValue(value);
    return Object.freeze({
      amount: formatDisplayNumber(exactValue),
      unit: getDisplayCurrencyLabel(),
      exact: formatTomanFromIrr(value),
      compact: false,
    });
  }

  let scale = COMPACT_MONEY_SCALES[selectedIndex];
  let denominator = scale.threshold * currencyDivisor;
  let roundedHundredths = ((absolute * 100n) + (denominator / 2n)) / denominator;
  if (roundedHundredths >= 100_000n && selectedIndex > 0) {
    selectedIndex -= 1;
    scale = COMPACT_MONEY_SCALES[selectedIndex];
    denominator = scale.threshold * currencyDivisor;
    roundedHundredths = ((absolute * 100n) + (denominator / 2n)) / denominator;
  }

  const asciiAmount = `${negative ? "-" : ""}${formatRoundedHundredths(roundedHundredths)}`;
  return Object.freeze({
    amount: formatDisplayNumber(asciiAmount),
    unit: `${scale.label} ${getDisplayCurrencyLabel()}`,
    exact: formatTomanFromIrr(value),
    compact: true,
  });
}

export function formatCompactMoneyFromIrr(value, { fallback = "—" } = {}) {
  const result = compactMoneyFromIrr(value);
  return result ? isolateRtlMoney(`${result.amount} ${result.unit}`) : fallback;
}

export function irrToDisplayValue(value) {
  if (!/^-?\d+$/.test(String(value ?? ""))) return null;
  return getDisplayCurrencyCode() === "IRR" ? String(value) : irrToToman(value);
}

export function tomanInputToIrr(value) {
  const normalized = normalizeDecimalInput(value);
  if (getDisplayCurrencyCode() === "IRR") return /^\d+$/.test(normalized) ? normalized : "";
  const match = normalized.match(/^(\d+)(?:\.(\d))?$/);
  if (!match) return "";
  return (BigInt(match[1]) * 10n + BigInt(match[2] ?? "0")).toString();
}
