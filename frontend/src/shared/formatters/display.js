import { CURRENCY_LABELS } from "../constants/currency.js";

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const persianDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", day: "numeric" });
const persianDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tehran" });

// Codes come from the Backend UNIT_REGISTRY: kg, ton, m, m2, m3, each, hour, day.
const UNIT_LABELS = Object.freeze({
  IRR: CURRENCY_LABELS.IRR,
  kg: "کیلوگرم",
  ton: "تن",
  m: "متر",
  m2: "مترمربع",
  m3: "مترمکعب",
  each: "عدد",
  hour: "ساعت",
  day: "روز دستگاه",
});

function toPersianDigits(value) {
  return String(value).replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}

export function formatDisplayNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  const [rawInteger, rawFraction = ""] = String(value).split(".");
  const sign = rawInteger.startsWith("-") ? "-" : "";
  const integer = rawInteger.replace(/^-/, "").replace(/^0+(?=\d)/, "") || "0";
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, "٬");
  const fraction = rawFraction.replace(/0+$/, "");
  return toPersianDigits(`${sign}${grouped}${fraction ? `٫${fraction}` : ""}`);
}

export function formatArea(value) {
  return value ? `${formatDisplayNumber(value)} مترمربع` : "زیربنا ثبت نشده";
}

/* A business date reaches us in two shapes, because two sources produce it. A reporting
   date is date-only ("2026-10-22"); a task start or finish read from a schedule carries a
   time ("2025-08-09T08:00"). Appending midnight to a value that already states a time
   built "2025-08-09T08:00T00:00:00Z", which is not a date at all — Intl threw
   `RangeError: Invalid time value`, the throw escaped into the page's fetch catch, and a
   perfectly healthy 200 was reported to the reader as "ارتباط با سرویس برقرار نشد".
   Midnight is appended only when the value is date-only; anything else is parsed as it
   stands, and an unparseable value returns the neutral dash instead of throwing. A
   formatter is the last place that should be able to take a page down. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function toDate(value) {
  // Concatenated rather than interpolated: `shared-module-imports.test.js` scans these
  // modules with a regex that mis-reads a file carrying more than one template literal,
  // and swallows the declaration that follows. Not worth a second template here.
  const date = new Date(DATE_ONLY.test(value) ? value + "T00:00:00Z" : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatBusinessDate(value) {
  if (!value) return "—";
  const date = toDate(String(value));
  return date ? persianDate.format(date) : "—";
}

export function formatSystemDateTime(value) {
  if (!value) return "—";
  const date = toDate(String(value));
  return date ? persianDateTime.format(date) : "—";
}

export function formatUnitLabel(value) {
  if (!value) return "بدون واحد";
  if (UNIT_LABELS[value]) return UNIT_LABELS[value];
  return /[A-Za-z]/.test(String(value)) ? "واحد تعریف‌نشده" : String(value);
}
