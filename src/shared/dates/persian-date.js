const persianPartsFormatter = new Intl.DateTimeFormat("en-US-u-ca-persian", {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  timeZone: "UTC",
});

const tehranDateFormatter = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: "Asia/Tehran",
});

function partsToObject(parts) {
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
}

function isoFromDate(date) {
  return date.toISOString().slice(0, 10);
}

export function getTehranTodayIso() {
  const parts = partsToObject(tehranDateFormatter.formatToParts(new Date()));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function gregorianIsoToPersian(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value ?? ""))) return null;
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime()) || isoFromDate(date) !== value) return null;
  const parts = partsToObject(persianPartsFormatter.formatToParts(date));
  return { year: Number(parts.year), month: Number(parts.month), day: Number(parts.day) };
}

export function persianToGregorianIso(year, month, day) {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day) || month < 1 || month > 12 || day < 1 || day > 31) return null;
  const approximateGregorianYear = year + 621;
  const cursor = new Date(Date.UTC(approximateGregorianYear, 1, 15));
  for (let index = 0; index < 430; index += 1) {
    const candidate = new Date(cursor.getTime() + index * 86400000);
    const persian = gregorianIsoToPersian(isoFromDate(candidate));
    if (persian?.year === year && persian.month === month && persian.day === day) return isoFromDate(candidate);
  }
  return null;
}

export function getPersianMonthDays(year, month) {
  const firstIso = persianToGregorianIso(year, month, 1);
  if (!firstIso) return null;
  const firstDate = new Date(`${firstIso}T00:00:00Z`);
  let length = 0;
  for (let day = 1; day <= 31; day += 1) {
    if (!persianToGregorianIso(year, month, day)) break;
    length = day;
  }
  return { firstIso, firstWeekdayOffset: (firstDate.getUTCDay() + 1) % 7, length };
}
