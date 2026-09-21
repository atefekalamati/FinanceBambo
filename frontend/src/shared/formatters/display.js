import { CURRENCY_LABELS } from "../constants/currency.js";

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
/* Pinned to Tehran, like persianDateTime below it. Without a zone this read the
   viewer's clock: "2026-10-22" is 30 Mehr in Tehran and 29 Mehr west of UTC, so
   the same business date printed as two different days depending on who was
   looking. A reporting date is a calendar day this project already agreed on. */
const persianDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Tehran" });
const persianDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tehran" });

// Codes come from the Backend UNIT_REGISTRY, and EVERY code in it must appear here.
//
// This table had eight of the registry's fifteen. The other seven were added to the
// backend when the material-price units were coordinated, and a resource carrying one of
// them rendered as «واحد تعریف‌نشده» -- the page calling a unit undefined that the backend
// defines, validates `finance_resources.base_unit` against, and publishes on
// `/unit-registry`. A missing label is indistinguishable on screen from a genuinely
// unknown unit, which is the one thing this label exists to tell apart.
//
// `tests/contract/unit-labels-cover-the-registry.test.js` reads the backend registry and
// fails if a code here is missing, so the two lists cannot drift apart again. The wording
// stays this file's own: `day` is «روز دستگاه» here because the page shows equipment days,
// while the registry calls it «روز».
const UNIT_LABELS = Object.freeze({
  IRR: CURRENCY_LABELS.IRR,
  // mass
  g: "گرم",
  kg: "کیلوگرم",
  ton: "تن",
  // length
  mm: "میلی‌متر",
  cm: "سانتی‌متر",
  m: "متر",
  // area
  cm2: "سانتی‌مترمربع",
  m2: "مترمربع",
  // volume
  liter: "لیتر",
  m3: "مترمکعب",
  // count
  each: "عدد",
  branch: "شاخه",
  bag: "کیسه",
  // time
  hour: "ساعت",
  day: "روز دستگاه",
});

function toPersianDigits(value) {
  return String(value).replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}

/**
 * Persian digits with nothing else touched. For a CODE rather than a quantity.
 *
 * «۱.۱۰» is a WBS path, and `formatDisplayNumber` reads it as one and a tenth: it strips
 * the trailing zero and writes the decimal separator, so stage «۱.۱۰» and stage «۱.۱»
 * both came out «۱٫۱» -- two different stages of the project wearing one label, in the
 * menu where somebody chooses which one an invoice is for.
 */
export function toPersianCode(value) {
  if (value === null || value === undefined || value === "") return "";
  return toPersianDigits(String(value));
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
