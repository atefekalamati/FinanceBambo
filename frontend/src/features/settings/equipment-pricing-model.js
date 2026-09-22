/* What the equipment pricing section shows, decided without touching the DOM.
 *
 * WHY EQUIPMENT IS PRICED BY HAND AND MATERIALS ARE NOT
 * A material has a market: the sheet quotes rebar per kilogram and the price moves on its
 * own. A machine does not. «بیل مکانیکی» costs what this project agreed with whoever owns
 * it, it changes when that agreement changes, and no feed will ever say so. So the price
 * is typed, and the only question the interface has to answer well is «per what».
 *
 * PER WHAT IS NOT A CHOICE
 * The unit comes from the schedule file and nowhere else. If the file assigns کامیون by
 * the hour then the price is per hour; if it assigns جرثقیل by the day then that one is
 * per day, on the same screen, in the same list. Offering a unit picker here would invite
 * somebody to price a machine in a unit the estimate never asks for, and the row would
 * then need a conversion rule to undo a choice that should never have been made. The unit
 * is shown, never asked.
 *
 * THESE ARE THE SAME NUMBERS AS EVERY OTHER PRICE
 * A resource price is a `price_versions` row: scope, version, effective date, author. The
 * material prices on the prices page are the same rows. Nothing here is a special case in
 * the data — only in how the number arrives.
 */

/** The resource type the schedule gives machines. */
export const EQUIPMENT_TYPE = "equipment";

export const FILTERS = Object.freeze([
  { value: "all", label: "همه" },
  { value: "priced", label: "قیمت‌گذاری‌شده" },
  { value: "unpriced", label: "بدون قیمت" },
]);

/**
 * One row of the section: a machine, its unit, and what it currently costs.
 *
 * `currentPrice` is whatever the service resolved for today — a project price when there
 * is one, otherwise the organization's. Both are carried separately as well, because
 * «قیمت سازمان، ۵۲٬۱۰۰٬۰۰۰» and «قیمت این پروژه، ۴۸٬۰۰۰٬۰۰۰» are different facts and a
 * person revising one needs to see the other.
 */
export function equipmentRows(workspace) {
  return (workspace?.currentPrices ?? [])
    .filter((entry) => entry?.resource?.type === EQUIPMENT_TYPE)
    .map((entry) => ({
      resourceId: entry.resource.resourceId,
      title: entry.resource.title ?? "—",
      code: entry.resource.code ?? null,
      /* The file's own unit. Null is a real state: a machine the schedule named without
         saying how it is measured cannot be priced until somebody says. */
      unit: entry.resource.baseUnit ?? null,
      unitPriceIRR: entry.currentPrice?.unitPriceIRR ?? null,
      priceScope: entry.currentPrice?.scope ?? null,
      effectiveFrom: entry.currentPrice?.effectiveFrom ?? null,
      projectPrice: entry.projectPrice ?? null,
      organizationPrice: entry.organizationPrice ?? null,
    }));
}

/** Whether this machine has a price today. The filter and the count both read it. */
export function isPriced(row) {
  return row?.unitPriceIRR !== null && row?.unitPriceIRR !== undefined;
}

/**
 * Rows matching the search text and the filter.
 *
 * Search is over the name and the code, folded to a comparable form — Persian keyboards
 * produce both «ی» and «ي», and both «ک» and «ك», so a list searched literally loses rows
 * to a character the reader cannot see.
 */
export function selectRows(rows, { search = "", filter = "all" } = {}) {
  const needle = foldPersian(search).trim();
  return (rows ?? []).filter((row) => {
    if (filter === "priced" && !isPriced(row)) return false;
    if (filter === "unpriced" && isPriced(row)) return false;
    if (!needle) return true;
    return foldPersian(`${row.title ?? ""} ${row.code ?? ""}`).includes(needle);
  });
}

/** Arabic and Persian spellings of the same letters, and the two digit sets, made equal. */
export function foldPersian(value) {
  return String(value ?? "")
    .replace(/[يى]/g, "ی")   // ي ى -> ی
    .replace(/ك/g, "ک")           // ك -> ک
    .replace(/[​-‍‏‪-‮]/g, "")
    .replace(/[۰-۹]/g, (d) => String.fromCharCode(d.charCodeAt(0) - 0x06F0 + 48))
    .replace(/[٠-٩]/g, (d) => String.fromCharCode(d.charCodeAt(0) - 0x0660 + 48))
    .toLowerCase();
}

/**
 * The rows grouped by the unit the file measures them in.
 *
 * Grouping by unit rather than alphabetically because the unit is the thing that changes
 * how the number under it is read: a column of prices where some are per hour and some per
 * day, interleaved, is a column somebody will misread. Under a heading that says «ساعتی»,
 * every figure means the same thing.
 *
 * Machines the file gave no unit come last, in their own group, because they cannot be
 * priced at all until that is answered and burying them among the rest hides that.
 */
export function groupByUnit(rows) {
  const groups = new Map();
  (rows ?? []).forEach((row) => {
    const key = row.unit ?? "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  return [...groups.entries()]
    .map(([unit, items]) => ({
      unit: unit || null,
      rows: [...items].sort((a, b) => String(a.title).localeCompare(String(b.title), "fa")),
      pricedCount: items.filter(isPriced).length,
    }))
    .sort((a, b) => {
      if ((a.unit === null) !== (b.unit === null)) return a.unit === null ? 1 : -1;
      return String(a.unit).localeCompare(String(b.unit));
    });
}

/** «۱۲ از ۱۹ قیمت‌گذاری شده» — the one number that says whether this job is done. */
export function pricingProgress(rows) {
  const total = (rows ?? []).length;
  return { total, priced: (rows ?? []).filter(isPriced).length };
}


/* ------------------------------------------------------- the working day */

/**
 * What this project says a machine-day is worth in hours, or null when nobody has said.
 *
 * WHY THIS SECTION CARES
 * A price per hour is half a cost; the other half is how many hours. The schedule states
 * a machine's span in days, so for every machine the file measures in HOURS the two only
 * meet through one number: «ساعت هر روز دستگاه». Eighteen of this project's nineteen
 * machines are hourly, so without that number the entire section produces prices that
 * multiply by nothing.
 *
 * It is a project's decision and not a fact — a working day is not twenty-four hours and
 * not eight either — which is why it lives in the project's own conversion rules beside
 * «نفرروز», and why `unit_conversion.py` says in as many words that day↔hour "stays in
 * `unit_conversions`, where a project records its own with a reason and a date".
 *
 * Read from the workspace this section already has, so knowing costs no request.
 */
export function workingDayRule(workspace) {
  const entry = (workspace?.currentConversions ?? []).find(
    (item) => item?.sourceUnit === "day" && item?.targetUnit === "hour");
  const applied = entry?.currentConversion ?? null;
  if (!applied || !applied.factor) return null;
  return { factor: String(applied.factor), scope: applied.scope ?? entry.scope ?? null };
}

/** Whether any machine on screen is measured in a unit that needs that rule. */
export function needsWorkingDayRule(rows) {
  return (rows ?? []).some((row) => row?.unit === "hour");
}


/* ------------------------------------------------------ price revisions */

/**
 * One machine's price revisions, newest first.
 *
 * WHY A MACHINE NEEDS ITS OWN HISTORY AND A MATERIAL LESS SO
 * A material price is a market fact: it moved because the market moved, and the prices
 * page shows the whole project's movements together. A machine's rate is an AGREEMENT —
 * it changed because somebody renegotiated it — so the question is never «what happened
 * to prices» but «what happened to THIS one, and who changed it». Answering that from a
 * project-wide list means reading past every other machine.
 *
 * The service publishes every version for the project at once, so this is a filter rather
 * than a request: opening one machine's history costs nothing after the first.
 *
 * Ordered by the version the service assigned, not by date. Two revisions can share an
 * effective date — a correction made the same day — and only the version separates them.
 */
export function historyFor(history, resourceId) {
  if (!resourceId) return [];
  return (history ?? [])
    .filter((entry) => entry?.resourceId === resourceId)
    .sort((a, b) => Number(b?.sequence ?? 0) - Number(a?.sequence ?? 0));
}
