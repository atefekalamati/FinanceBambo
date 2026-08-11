import { CURRENCY_LABELS, DEFAULT_DISPLAY_CURRENCY_CODE } from "../constants/currency.js";

const STORAGE_KEY = "bambo.finance.displayCurrency";
const SUPPORTED_CODES = new Set(["IRR", "TOMAN"]);
let memoryPreference = null;

export const DISPLAY_CURRENCY_CHANGED_EVENT = "finance:display-currency-changed";

export function getDisplayCurrencyCode() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return SUPPORTED_CODES.has(stored) ? stored : memoryPreference ?? DEFAULT_DISPLAY_CURRENCY_CODE;
  } catch {
    return memoryPreference ?? DEFAULT_DISPLAY_CURRENCY_CODE;
  }
}

export function getDisplayCurrencyLabel() {
  return CURRENCY_LABELS[getDisplayCurrencyCode()];
}

export function setDisplayCurrencyCode(code) {
  if (!SUPPORTED_CODES.has(code)) throw new TypeError("Unsupported display currency code.");
  memoryPreference = code;
  try {
    window.localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // The preference still applies to the current render when storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent(DISPLAY_CURRENCY_CHANGED_EVENT, { detail: { code } }));
}
