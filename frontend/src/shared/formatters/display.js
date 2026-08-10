import { CURRENCY_LABELS } from "../constants/currency.js";

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const persianDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "long", day: "numeric" });
const persianDateTime = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tehran" });

const UNIT_LABELS = Object.freeze({
  IRR: CURRENCY_LABELS.IRR,
  m2: "مترمربع",
  kg: "کیلوگرم",
  hour: "ساعت",
  person_hour: "نفر-ساعت",
  equipment_day: "روز دستگاه",
  ton: "تن",
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

export function formatBusinessDate(value) {
  if (!value) return "—";
  return persianDate.format(new Date(`${value}T00:00:00Z`));
}

export function formatSystemDateTime(value) {
  if (!value) return "—";
  return persianDateTime.format(new Date(value));
}

export function formatUnitLabel(value) {
  if (!value) return "بدون واحد";
  if (UNIT_LABELS[value]) return UNIT_LABELS[value];
  return /[A-Za-z]/.test(String(value)) ? "واحد تعریف‌نشده" : String(value);
}
