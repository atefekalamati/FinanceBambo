import { formatDisplayNumber } from "./display.js";
import { normalizeDecimalInput } from "../validation/decimal-validation.js";
import { getDisplayCurrencyCode, getDisplayCurrencyLabel } from "../preferences/currency-preference.js";

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
  return withCurrency ? `${formatted} ${getDisplayCurrencyLabel()}` : formatted;
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
