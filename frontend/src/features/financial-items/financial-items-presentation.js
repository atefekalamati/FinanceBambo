import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { isSeedTaskResource } from "../../shared/finance/active-resources.js";

/**
 * Which activity, which cost item, and which WBS code — kept apart.
 *
 * Three identities meet on one row of ریز برآورد: the activity a line belongs
 * to, the cost item it consumes, and the WBS code of that activity. Every
 * confusion this module exists to prevent came from one of them standing in for
 * another — a task name printed as a cost item, a WBS code printed twice, an
 * activity id printed where a title was missing. So nothing here falls back
 * from one identity to a different one. A value that is absent renders absent.
 */

/** Printed where a value is genuinely missing. Never a value in its own right. */
export const ABSENT = "—";

/** A WBS code as this project writes them: numbers separated by dots. */
const WBS_SHAPE = /^\d+(?:\.\d+)*$/;

/**
 * True for a row this page should withhold: made by the seed out of a schedule
 * TASK, and never used by anybody since.
 *
 * The whole rule lives in `shared/finance/active-resources.js` so that this page
 * and قیمت روز cannot come to different answers about the same row. It is
 * re-exported here under the name this feature has always called it.
 */
export function isLegacyTaskResource(resource) {
  return isSeedTaskResource(resource) && resource?.hasOperationalRecords !== true;
}

/**
 * True for a line that is part of the schedule the project is running on.
 *
 * Both halves of the identity are required: an item read from the file, and an
 * assignment read from the file. `assignmentExternalId` is not consulted — it
 * is free text that happens to hold the same digits on this data, and a rule
 * resting on that coincidence would break the first time it did not.
 */
export function isScheduleBackedLine(line, resource) {
  return Boolean(resource) && resource.sourceResourceUid != null
    && line?.sourceAssignmentUid != null;
}

/**
 * The one WBS code to print for a line, or `ABSENT`.
 *
 * One activity has one WBS code, so this returns one string — the caller cannot
 * print `— · 1.8.2.3` or `1.8.2.3 · 1.8.2.3` because it never receives two
 * values to join. `wbsCode` is what the catalogue says. `activityExternalId` is
 * an identity rather than a code, and is read only when it is shaped like a WBS
 * code — which it is on schedule-derived lines, where the two are the same
 * string and printing both is what produced the duplicate.
 */
export function canonicalWbs(line) {
  const declared = String(line?.wbsCode ?? "").trim();
  if (declared && declared !== ABSENT) return declared;
  const external = String(line?.activityExternalId ?? "").trim();
  if (WBS_SHAPE.test(external)) return external;
  return ABSENT;
}

/** The activity's own title, or a stated absence — never its id, never its WBS. */
export function activityLabel(line) {
  const title = String(line?.activityTitle ?? "").trim();
  return title || "فعالیت بدون عنوان";
}

/** The cost item's own title, or a stated absence — never the activity's. */
export function resourceLabel(resource) {
  const title = String(resource?.title ?? "").trim();
  return title || ABSENT;
}

/** Cost items to list, and how many legacy task-derived rows were left out. */
export function selectVisibleResources(resources = []) {
  const rows = [];
  let hiddenLegacyCount = 0;
  resources.forEach((resource) => {
    if (isLegacyTaskResource(resource)) hiddenLegacyCount += 1;
    else rows.push(resource);
  });
  return { rows, hiddenLegacyCount };
}

/**
 * Estimate rows to show: the current schedule's items, plus genuine manual ones.
 *
 * A line whose resource is missing from the catalogue is left out rather than
 * labelled from whatever else the row happens to carry — there is no cost item
 * to name, and naming the activity there is the bug this page exists to fix.
 * Legacy task-derived rows are left out too: hidden, never deleted, and counted
 * so no reader mistakes the table for the whole of the data.
 *
 * A row that is neither — a hand-made item with no schedule identity — stays.
 * Somebody entered it deliberately and it is as real as any other Finance item;
 * only rows that claim to be schedule items without being any are refused.
 */
export function selectEstimateRows(lines = [], resources = []) {
  const byId = new Map(resources.map((resource) => [resource.resourceId, resource]));
  const rows = [];
  let hiddenLegacyCount = 0;
  let orphanCount = 0;
  let scheduleBackedCount = 0;
  let manualCount = 0;
  lines.forEach((line) => {
    const resource = byId.get(line.resourceId);
    if (!resource) {
      orphanCount += 1;
      return;
    }
    if (isLegacyTaskResource(resource)) {
      hiddenLegacyCount += 1;
      return;
    }
    if (isScheduleBackedLine(line, resource)) scheduleBackedCount += 1;
    else manualCount += 1;
    rows.push(line);
  });
  return { rows, hiddenLegacyCount, orphanCount, scheduleBackedCount, manualCount };
}

/** What to tell the reader about withheld rows, or null when nothing was withheld. */
export function withheldRowsNotice({ hiddenLegacyCount = 0, orphanCount = 0 } = {}) {
  const parts = [];
  if (hiddenLegacyCount > 0) {
    parts.push(`${formatDisplayNumber(String(hiddenLegacyCount))} ردیف قدیمی با کد MSP-T نمایش داده نشده است؛ این ردیف‌ها از فایل برنامه زمانی جاری خوانده نشده‌اند و حذف هم نشده‌اند.`);
  }
  if (orphanCount > 0) {
    parts.push(`${formatDisplayNumber(String(orphanCount))} ردیف بدون قلم هزینه معتبر نمایش داده نشده است.`);
  }
  return parts.length ? parts.join(" ") : null;
}

/**
 * Order two WBS codes the way a project reads them, not the way a string sorts.
 *
 * `1.9.10` comes after `1.9.2` because the segments are numbers; alphabetic
 * order puts it before, which is what scattered the table. Segments that are
 * not numbers (a project that letters its phases) compare as text, and a code
 * that is a prefix of another comes first — `1.9` before `1.9.1`. `ABSENT`
 * sorts last, so rows with no code collect at the end instead of at the top.
 */
export function compareWbs(left, right) {
  const a = String(left ?? "").trim();
  const b = String(right ?? "").trim();
  if (a === b) return 0;
  if (a === ABSENT || a === "") return 1;
  if (b === ABSENT || b === "") return -1;
  const first = a.split(".");
  const second = b.split(".");
  for (let index = 0; index < Math.max(first.length, second.length); index += 1) {
    const one = first[index];
    const two = second[index];
    if (one === undefined) return -1;
    if (two === undefined) return 1;
    const oneNumber = /^\d+$/.test(one) ? Number(one) : null;
    const twoNumber = /^\d+$/.test(two) ? Number(two) : null;
    if (oneNumber !== null && twoNumber !== null) {
      if (oneNumber !== twoNumber) return oneNumber - twoNumber;
    } else if (one !== two) {
      // A number sorts before a word, so a mixed scheme still has one order.
      if (oneNumber !== null) return -1;
      if (twoNumber !== null) return 1;
      return one < two ? -1 : 1;
    }
  }
  return 0;
}

function identityOf(value) {
  const text = String(value ?? "").trim();
  if (text === "") return null;
  return /^\d+$/.test(text) ? Number(text) : text;
}

function compareIdentity(left, right) {
  const a = identityOf(left);
  const b = identityOf(right);
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a) < String(b) ? -1 : 1;
}

/**
 * Estimate rows in reading order: every item of one activity together, and the
 * activities themselves in WBS order.
 *
 * Ordered by the activity first and the item last, which is the whole point —
 * ordering by item title first is what put five items of one activity in five
 * different places. The task id is the tie-break between two activities that
 * somehow share a code, and the assignment id between two rows of one activity,
 * so the order is stable across reloads rather than merely grouped.
 */
export function sortEstimateRows(lines = [], resources = []) {
  const byId = new Map(resources.map((resource) => [resource.resourceId, resource]));
  return [...lines].sort((left, right) =>
    compareWbs(canonicalWbs(left), canonicalWbs(right))
    || compareIdentity(left.taskExternalId ?? left.sourceTaskUid, right.taskExternalId ?? right.sourceTaskUid)
    || compareIdentity(left.activityExternalId, right.activityExternalId)
    || compareIdentity(left.sourceAssignmentUid ?? left.assignmentExternalId,
                       right.sourceAssignmentUid ?? right.assignmentExternalId)
    || String(resourceLabel(byId.get(left.resourceId)))
         .localeCompare(String(resourceLabel(byId.get(right.resourceId))), "fa"));
}

/**
 * True when this row opens a new activity block — the row a header is written
 * above, the ones after it belonging to the same activity.
 *
 * The activity's name, its code and the schedule's cost for it are facts about
 * the activity, not about any one of its items, so they are written once in a
 * header row that spans the table rather than repeated down a column. (An
 * earlier shape repeated them on every row and hid the copies from sight; a
 * spanning header says the same thing to a reader and to a screen reader.)
 */
export function activityBlockStarts(lines = []) {
  let previous = null;
  return lines.map((line) => {
    const key = `${canonicalWbs(line)}\u0000${line.activityExternalId ?? ""}`;
    const starts = key !== previous;
    previous = key;
    return starts;
  });
}

/** What the stored `source` enum calls each origin. */
const SOURCE_LABELS = Object.freeze({
  progress_feed: "پیشرفت اجرایی",
  excel_import: "اکسل",
  manual_entry: "ورود دستی",
});

/** Read from the schedule, whatever the stored enum was able to say. */
const SCHEDULE_SOURCE = "فایل برنامه زمانی (MPP)";

/** The same question about a cost item, answered from the same kind of evidence. */
export function resourceSourceLabel(resource) {
  if (resource?.sourceResourceUid != null) return SCHEDULE_SOURCE;
  return SOURCE_LABELS[resource?.source] ?? "منبع تعریف‌نشده";
}

/**
 * The schedule's own cost for a line's activity, or null.
 *
 * It is the ACTIVITY's figure, never the item's: the schedule stores one cost
 * per task and Finance stores no per-assignment cost at all, so attributing it
 * to one of an activity's items would invent a number, and showing it on each
 * of them would count it as many times as the activity has items. It is not a
 * Finance price either — that lives in `price_versions` and a person enters it.
 */
export function scheduleCostOf(line) {
  const value = line?.mppTaskCostIrr;
  return value === null || value === undefined || value === "" ? null : value;
}

/**
 * The money an estimate line comes to, or null.
 *
 * An amount is a product and never a figure of its own: no quantity or no unit
 * price means no amount, and the page says so rather than showing a zero or
 * borrowing the schedule's cost for the activity. Decimal strings are
 * multiplied exactly — a rial figure large enough to matter is large enough for
 * a float to round it.
 */
export function estimateAmount(quantity, unitPrice) {
  const left = exactDecimal(quantity);
  const right = exactDecimal(unitPrice);
  if (left === null || right === null) return null;
  const scaled = left.value * right.value;
  const scale = left.scale + right.scale;
  return scale === 0 ? String(scaled) : withDecimalPoint(scaled, scale);
}

/** The change between two amounts, or null when either is unknown. */
export function amountChange(initial, current) {
  const before = exactDecimal(initial);
  const after = exactDecimal(current);
  if (before === null || after === null) return null;
  const scale = Math.max(before.scale, after.scale);
  const lift = (part) => part.value * 10n ** BigInt(scale - part.scale);
  const difference = lift(after) - lift(before);
  return scale === 0 ? String(difference) : withDecimalPoint(difference, scale);
}

function exactDecimal(value) {
  const text = String(value ?? "").trim();
  if (!/^-?\d+(?:\.\d+)?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  return { value: BigInt(whole + fraction), scale: fraction.length };
}

function withDecimalPoint(value, scale) {
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(scale + 1, "0");
  const whole = digits.slice(0, digits.length - scale);
  const fraction = digits.slice(digits.length - scale).replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}
