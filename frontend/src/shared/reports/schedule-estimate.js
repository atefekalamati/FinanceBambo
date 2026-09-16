import { gregorianIsoToPersian } from "../dates/persian-date.js";
import { monthKey } from "./monthly-trend.js";

/**
 * The monthly estimate line, derived from the schedule the progress feed carries.
 *
 * WHERE THE NUMBERS COME FROM
 * `finance_mpp_rows`, reached through GET /progress-snapshots/{id}/feed. Each
 * assignment row repeats its task's block, so `task.taskStart` is the schedule's
 * start date and `task.metrics.taskCost` is the schedule's cost for that task —
 * `source_cost`, already converted to whole rials at import.
 *
 * WHAT IT IS NOT
 * Not Finance money. A Finance figure is a price a person entered against an
 * approved quantity; this is what the planners' file said the task would cost.
 * It is drawn as the baseline to compare spending against, never reported as
 * cost incurred, and it never reaches an invoice total.
 *
 * THE DISTRIBUTION RULE
 * A task's whole cost lands in the month it starts. The file states a start and
 * a finish but no time-phased curve, so spreading the figure across the span
 * would mean inventing a shape nobody planned. Placing it at the start is the
 * one rule that adds nothing: the total is right, and the month it is attributed
 * to is a date the file actually states.
 */

const ISO_DAY = /^(\d{4}-\d{2}-\d{2})/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
/**
 * How close to a whole rial a figure must land to be read as that rial.
 *
 * The schedule's costs are converted to rials during import, in floating point,
 * and a few of them come back a hair off: 83210999.99999997 where the file says
 * 83211000. A rial is the smallest unit this system has, so a fraction of one is
 * never an amount anybody stated — it is the round trip showing through. Three
 * digits is far wider than that noise and far narrower than any real fraction.
 */
const NOISE_DIGITS = 3;

/** The leading calendar day of a schedule date, which states no timezone. */
function isoDay(value) {
  const matched = ISO_DAY.exec(String(value ?? ""));
  return matched ? matched[1] : null;
}

/**
 * A schedule cost in whole rials, or null when the figure is not one.
 *
 * The feed serialises money from a `numeric` column, so a whole amount arrives
 * carrying the column's scale — "3140000000.0", never "3140000000". Reading only
 * bare integers rejected every row the schedule has: on the project this was
 * written against, all 266 of them.
 *
 * So a fraction is read rather than refused, but only where it cannot be an
 * amount: all zeros is the column's scale, and a run of 0s or 9s is the import's
 * floating-point noise around a whole rial. Anything else is a real fraction of
 * a rial, which nothing in this system can mean, and it is declined rather than
 * rounded into money nobody stated.
 */
function exactCost(value) {
  const matched = DECIMAL.exec(String(value ?? "").trim());
  if (!matched) return null;
  const [, sign, whole, fraction = ""] = matched;
  const magnitude = BigInt(whole);
  const negative = sign === "-";

  if (!fraction || /^0+$/.test(fraction)) {
    return negative ? -magnitude : magnitude;
  }
  // Compared on the leading digits alone: the noise is in the last of them, and
  // padding keeps a short fraction like ".9" from reading as a long run of nines.
  const leading = fraction.slice(0, NOISE_DIGITS).padEnd(NOISE_DIGITS, "0");
  // Away from zero for a run of nines, towards it for a run of zeros — which is
  // what rounding to the nearest rial means on each side.
  if (/^9+$/.test(leading)) return negative ? -(magnitude + 1n) : magnitude + 1n;
  if (/^0+$/.test(leading)) return negative ? -magnitude : magnitude;
  return null;
}

/**
 * The service's ceiling on a window, restated here so the request is never one
 * the service will reject. Sixty Persian months is five years; a project longer
 * than that gets its oldest months trimmed and is told so, which is a visible
 * shortfall rather than a 422 that takes the whole chart down.
 */
export const MAX_WINDOW_MONTHS = 60;

/**
 * The window every project got before it was read from the schedule, kept as a
 * floor. Widening the chart must never narrow it: a confirmed invoice dated
 * outside the schedule's span is still money this project spent, and a window
 * that hugged the schedule would drop it from the one chart that reports it.
 */
export const MINIMUM_TRAILING_MONTHS = 12;

/** Persian months since year 0, so two months can be compared and subtracted. */
function monthOrdinal(persian) {
  return persian.year * 12 + (persian.month - 1);
}

/**
 * True when some other task in the same feed sits underneath this one.
 *
 * MS Project rolls a summary task's children into its own cost, so a summary and
 * its children both carry the whole subtree's figure. Counting both would double
 * the estimate for every branch of the breakdown. The dot is part of the test:
 * "1.5" is the parent of "1.5.1" but not of "1.50".
 */
function hasDescendant(wbsCode, allCodes) {
  if (!wbsCode) return false;
  const prefix = `${wbsCode}.`;
  for (const candidate of allCodes) {
    if (candidate !== wbsCode && candidate.startsWith(prefix)) return true;
  }
  return false;
}

/**
 * One entry per task, from a feed that carries one row per assignment.
 *
 * Deduplication is the whole point of this pass. The schedule's cost belongs to
 * the task and the import copies it onto every assignment row: on the current
 * source version 215 of 328 tasks have more than one row, so summing the feed as
 * it arrives overstates the plan several times over.
 *
 * When two rows of one task disagree about the figure, the task is reported with
 * no cost rather than with whichever row was read first — the same rule the
 * activity catalogue applies in SQL. A disagreement means the import is not
 * saying one thing, and picking a side would present the choice as a fact.
 */
function collectTasks(feed) {
  const tasks = new Map();
  (feed?.assignments ?? []).forEach((assignment) => {
    const task = assignment?.task;
    const id = task?.taskExternalId;
    if (!id) return;
    const cost = exactCost(task?.metrics?.taskCost);
    const existing = tasks.get(id);
    if (!existing) {
      tasks.set(id, {
        wbsCode: String(task.wbsCode ?? "").trim(),
        startIso: isoDay(task.taskStart),
        cost,
        conflicting: false,
      });
      return;
    }
    if (!existing.conflicting && existing.cost !== cost) {
      existing.cost = null;
      existing.conflicting = true;
    }
  });
  return tasks;
}

/**
 * The schedule's cost per Persian month, plus what had to be left out.
 *
 * Every exclusion is counted rather than silently dropped: a caller that draws
 * this line is claiming to show the plan, and it can only say how complete that
 * claim is if it knows what the line does not contain.
 */
export function buildScheduleEstimate(feed) {
  const tasks = collectTasks(feed);
  const codes = new Set(
    [...tasks.values()].map((task) => task.wbsCode).filter((code) => code !== ""),
  );

  const byMonth = new Map();
  const skipped = { summary: 0, noStart: 0, noCost: 0, conflictingCost: 0 };
  let total = 0n;
  let taskCount = 0;

  tasks.forEach((task) => {
    if (hasDescendant(task.wbsCode, codes)) {
      skipped.summary += 1;
      return;
    }
    if (task.conflicting) {
      skipped.conflictingCost += 1;
      return;
    }
    if (task.cost === null || task.cost === 0n) {
      skipped.noCost += 1;
      return;
    }
    const persian = task.startIso ? gregorianIsoToPersian(task.startIso) : null;
    if (!persian) {
      skipped.noStart += 1;
      return;
    }
    const key = monthKey(persian.year, persian.month);
    byMonth.set(key, (byMonth.get(key) ?? 0n) + task.cost);
    total += task.cost;
    taskCount += 1;
  });

  return Object.freeze({
    byMonth,
    totalIrr: String(total),
    taskCount,
    skipped: Object.freeze(skipped),
    isEmpty: byMonth.size === 0,
  });
}

/**
 * Writes the derived estimate onto the months the report already returned.
 *
 * A month inside the window with nothing starting in it gets zero, not null:
 * under the start-month rule that is a statement the schedule makes — no task
 * begins then — and leaving it null would break the line into disconnected
 * segments that look like missing data.
 *
 * If the window and the schedule do not overlap at all, nothing is written. A
 * window of zeroes would draw a flat baseline along the axis, which reads as "no
 * budget" rather than "the plan lies outside the period you are looking at".
 */
export function applyScheduleEstimate(months = [], estimate) {
  if (!estimate || estimate.isEmpty || months.length === 0) {
    return { applied: false, months, coveredIrr: "0", outsideIrr: estimate?.totalIrr ?? "0" };
  }

  let covered = 0n;
  const filled = months.map((month) => {
    const amount = estimate.byMonth.get(monthKey(month.persianYear, month.persianMonth)) ?? 0n;
    covered += amount;
    return { ...month, estimateIrr: String(amount) };
  });

  if (covered === 0n) {
    return { applied: false, months, coveredIrr: "0", outsideIrr: estimate.totalIrr };
  }

  return {
    applied: true,
    months: filled,
    coveredIrr: String(covered),
    outsideIrr: String(BigInt(estimate.totalIrr) - covered),
  };
}

/**
 * How many months the chart must cover for THIS project, read from its schedule.
 *
 * The window used to be twelve months back from the reporting date for every
 * project alike, and a project is not twelve months long. On the schedule this
 * module was written against — a thirteen-month plan — that fixed window put
 * four fifths of the plan off the chart, including its two largest months, and
 * nothing on screen said a figure was missing.
 *
 * The span is the project's own: from the month its earliest task starts to the
 * month its latest task finishes. Months after today are part of it on purpose —
 * a project in flight has its remaining plan ahead of it, and a chart that stops
 * at today cannot be compared against that plan.
 *
 * The old fixed window is kept as a FLOOR rather than replaced. A schedule is not
 * a record of spending: an invoice can be dated before the first task or after
 * the last, and a window trimmed to the schedule would drop it. So the result
 * always covers both the schedule and the twelve months up to today, and can
 * only ever be wider than what this chart showed before.
 *
 * Returns null when the feed states no dates, and the caller then asks for
 * whatever it asked for before this existed.
 */
export function scheduleWindow(feed, todayIso, {
  maxMonths = MAX_WINDOW_MONTHS,
  minimumTrailingMonths = MINIMUM_TRAILING_MONTHS,
} = {}) {
  let earliestStart = null;
  let latestFinish = null;
  (feed?.assignments ?? []).forEach((assignment) => {
    const task = assignment?.task;
    const start = isoDay(task?.taskStart);
    // A task with no finish still occupies the month it starts in.
    const finish = isoDay(task?.taskFinish) ?? start;
    if (start && (earliestStart === null || start < earliestStart)) earliestStart = start;
    if (finish && (latestFinish === null || finish > latestFinish)) latestFinish = finish;
  });

  const today = isoDay(todayIso);
  if (!earliestStart || !today) return null;

  const firstPersian = gregorianIsoToPersian(earliestStart);
  const todayPersian = gregorianIsoToPersian(today);
  if (!firstPersian || !todayPersian) return null;

  // The window closes on a real day, not on a month: the service reports cost up
  // to the anchor, and the last bar is a partial month by design.
  const anchorDate = latestFinish && latestFinish > today ? latestFinish : today;
  const anchorPersian = gregorianIsoToPersian(anchorDate);
  if (!anchorPersian) return null;

  // The floor reaches back from TODAY, not from the anchor: a plan running two
  // years into the future must not push the twelve recorded months off the chart.
  const floor = monthOrdinal(todayPersian) - (minimumTrailingMonths - 1);
  const first = Math.min(monthOrdinal(firstPersian), floor);
  const requestedMonthCount = monthOrdinal(anchorPersian) - first + 1;
  if (requestedMonthCount < 1) return null;

  return {
    anchorDate,
    monthCount: Math.min(requestedMonthCount, maxMonths),
    requestedMonthCount,
    // The oldest months are the ones a clamp drops, because the service counts
    // back from the anchor. Said out loud so the panel can report the shortfall.
    trimmedMonths: Math.max(0, requestedMonthCount - maxMonths),
  };
}

/** What the estimate line is, once it is drawn from the schedule rather than the service. */
export const SCHEDULE_ESTIMATE_SOURCE = "mpp_schedule_start_month";

/**
 * Merges a derived estimate into a monthly trend payload.
 *
 * The service's own answer wins whenever it has one: `estimateSource` is
 * "unavailable" only while the Backend has no time-phased baseline, and the day
 * it has one, this derivation steps aside without anyone editing the page.
 */
export function withScheduleEstimate(trend, feed) {
  if (!trend || trend.estimateSource !== "unavailable") return trend;
  const estimate = buildScheduleEstimate(feed);
  const result = applyScheduleEstimate(trend.months ?? [], estimate);
  if (!result.applied) return trend;
  return {
    ...trend,
    months: result.months,
    estimateSource: SCHEDULE_ESTIMATE_SOURCE,
    scheduleEstimate: {
      taskCount: estimate.taskCount,
      skipped: estimate.skipped,
      totalIrr: estimate.totalIrr,
      coveredIrr: result.coveredIrr,
      outsideIrr: result.outsideIrr,
    },
  };
}
