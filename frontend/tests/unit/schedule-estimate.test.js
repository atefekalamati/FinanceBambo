import test from "node:test";
import assert from "node:assert/strict";
import {
  applyScheduleEstimate,
  buildScheduleEstimate,
  MAX_WINDOW_MONTHS,
  MINIMUM_TRAILING_MONTHS,
  SCHEDULE_ESTIMATE_SOURCE,
  scheduleWindow,
  withScheduleEstimate,
} from "../../src/shared/reports/schedule-estimate.js";
import { buildMonthlyTrend, TREND_MODES } from "../../src/shared/reports/monthly-trend.js";

/**
 * One assignment row, shaped the way GET /progress-snapshots/{id}/feed shapes it:
 * the task block is repeated verbatim on every assignment of the same task.
 */
function assignment(taskExternalId, { wbsCode, taskStart, taskCost }) {
  return {
    assignmentExternalId: `${taskExternalId}-${Math.random()}`,
    task: {
      taskExternalId,
      taskName: taskExternalId,
      wbsCode,
      taskStart,
      taskFinish: null,
      metrics: taskCost === undefined ? null : { taskCost },
    },
  };
}

// 2026-06-01 is خرداد ۱۴۰۵ and 2026-07-01 is تیر ۱۴۰۵.
const KHORDAD = "1405-03";
const TIR = "1405-04";

test("a task repeated on every assignment row is counted once", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
    ],
  });

  assert.equal(estimate.taskCount, 1, "four rows, one task");
  assert.equal(estimate.totalIrr, "1000", "not 4000 — the figure belongs to the task");
  assert.equal(estimate.byMonth.get(KHORDAD), 1000n);
});

test("a summary task is dropped, because MS Project already rolled its children into it", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      // The parent carries the subtree total; counting it too would double the branch.
      assignment("parent", { wbsCode: "1.5", taskStart: "2026-06-01", taskCost: "3000" }),
      assignment("child-a", { wbsCode: "1.5.1", taskStart: "2026-06-01", taskCost: "1000" }),
      assignment("child-b", { wbsCode: "1.5.2", taskStart: "2026-06-01", taskCost: "2000" }),
    ],
  });

  assert.equal(estimate.skipped.summary, 1);
  assert.equal(estimate.totalIrr, "3000", "the children, not the children plus their parent");
});

test("a sibling whose code merely starts with the same digits is not a child", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("task-5", { wbsCode: "1.5", taskStart: "2026-06-01", taskCost: "1000" }),
      assignment("task-50", { wbsCode: "1.50", taskStart: "2026-06-01", taskCost: "2000" }),
    ],
  });

  assert.equal(estimate.skipped.summary, 0, "\"1.50\" does not sit under \"1.5\"");
  assert.equal(estimate.totalIrr, "3000");
});

test("the whole cost lands in the month the task starts, never spread across its span", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      // Runs خرداد through مرداد; the rule puts all of it in خرداد.
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "900" }),
      assignment("task-2", { wbsCode: "1.2", taskStart: "2026-07-05", taskCost: "500" }),
    ],
  });

  assert.equal(estimate.byMonth.get(KHORDAD), 900n);
  assert.equal(estimate.byMonth.get(TIR), 500n);
  assert.equal(estimate.byMonth.size, 2);
});

test("two rows of one task that disagree about the cost contribute nothing", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "9999" }),
    ],
  });

  assert.equal(estimate.skipped.conflictingCost, 1);
  assert.equal(estimate.totalIrr, "0", "picking a side would present the choice as a fact");
});

test("a task with no start date, no cost, or a fractional cost is excluded and counted", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("no-start", { wbsCode: "1.1", taskStart: null, taskCost: "1000" }),
      assignment("no-cost", { wbsCode: "1.2", taskStart: "2026-06-01", taskCost: null }),
      assignment("no-metrics", { wbsCode: "1.3", taskStart: "2026-06-01" }),
      assignment("fractional", { wbsCode: "1.4", taskStart: "2026-06-01", taskCost: "12.5" }),
      assignment("zero", { wbsCode: "1.5", taskStart: "2026-06-01", taskCost: "0" }),
      assignment("good", { wbsCode: "1.6", taskStart: "2026-06-01", taskCost: "700" }),
    ],
  });

  assert.equal(estimate.skipped.noStart, 1);
  assert.equal(estimate.skipped.noCost, 4, "null, absent metrics, fractional and zero");
  assert.equal(estimate.taskCount, 1);
  assert.equal(estimate.totalIrr, "700");
});

test("the scale a numeric column carries is not a fraction of a rial", () => {
  // What the service actually sends. Reading only bare integers rejected every
  // row of the real schedule — all 266 of them — and drew no line at all.
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "3140000000.0" }),
      assignment("task-2", { wbsCode: "1.2", taskStart: "2026-06-01", taskCost: "12565115391.00" }),
    ],
  });

  assert.equal(estimate.taskCount, 2);
  assert.equal(estimate.totalIrr, "15705115391");
});

test("floating-point noise around a whole rial is read as that rial", () => {
  // Both are real values from the import, which converts to rials in floats.
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "83210999.99999997" }),
      assignment("task-2", { wbsCode: "1.2", taskStart: "2026-06-01", taskCost: "159486000.00000006" }),
    ],
  });

  assert.equal(estimate.byMonth.get(KHORDAD), 83211000n + 159486000n);
});

test("a real fraction of a rial is still declined, not rounded into money", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("half", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "12.5" }),
      assignment("tenth", { wbsCode: "1.2", taskStart: "2026-06-01", taskCost: "800.4" }),
      assignment("ninth", { wbsCode: "1.3", taskStart: "2026-06-01", taskCost: "800.9" }),
    ],
  });

  assert.equal(estimate.taskCount, 0, "nothing in this system means a fraction of a rial");
  assert.equal(estimate.skipped.noCost, 3);
});

test("a schedule date carrying a time is read as its calendar day", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01T08:00", taskCost: "100.0" }),
    ],
  });

  assert.equal(estimate.byMonth.get(KHORDAD), 100n);
});

test("a month inside the window with nothing starting in it is a real zero", () => {
  const estimate = buildScheduleEstimate({
    assignments: [assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "800" })],
  });
  const result = applyScheduleEstimate(
    [
      { persianYear: 1405, persianMonth: 3, actualCostIrr: "100" },
      { persianYear: 1405, persianMonth: 4, actualCostIrr: "200" },
    ],
    estimate,
  );

  assert.equal(result.applied, true);
  assert.equal(result.months[0].estimateIrr, "800");
  assert.equal(result.months[1].estimateIrr, "0", "a gap here would look like missing data");
  assert.equal(result.coveredIrr, "800");
  assert.equal(result.outsideIrr, "0");
});

test("a plan entirely outside the window is reported, not drawn as a flat zero baseline", () => {
  const estimate = buildScheduleEstimate({
    assignments: [assignment("task-1", { wbsCode: "1.1", taskStart: "2020-06-01", taskCost: "800" })],
  });
  const months = [{ persianYear: 1405, persianMonth: 3, actualCostIrr: "100" }];
  const result = applyScheduleEstimate(months, estimate);

  assert.equal(result.applied, false);
  assert.equal(result.months[0].estimateIrr, undefined, "the months are handed back untouched");
  assert.equal(result.outsideIrr, "800");
});

test("part of the plan outside the window is reported so the chart can say so", () => {
  const estimate = buildScheduleEstimate({
    assignments: [
      assignment("inside", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "800" }),
      assignment("outside", { wbsCode: "1.2", taskStart: "2020-06-01", taskCost: "200" }),
    ],
  });
  const result = applyScheduleEstimate([{ persianYear: 1405, persianMonth: 3, actualCostIrr: "0" }], estimate);

  assert.equal(result.coveredIrr, "800");
  assert.equal(result.outsideIrr, "200");
});

test("the service's own baseline wins whenever it reports one", () => {
  const reported = {
    estimateSource: "time_phased_baseline",
    months: [{ persianYear: 1405, persianMonth: 3, actualCostIrr: "100", estimateIrr: "5" }],
  };
  const feed = {
    assignments: [assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "800" })],
  };

  assert.equal(withScheduleEstimate(reported, feed), reported, "returned unchanged, by identity");
});

test("an absent or unusable feed leaves the trend exactly as the service reported it", () => {
  const reported = {
    estimateSource: "unavailable",
    months: [{ persianYear: 1405, persianMonth: 3, actualCostIrr: "100", estimateIrr: null }],
  };

  assert.equal(withScheduleEstimate(reported, null), reported);
  assert.equal(withScheduleEstimate(reported, { assignments: [] }), reported);
});

test("the derived months drive the chart's estimate line end to end", () => {
  const trend = withScheduleEstimate(
    {
      estimateSource: "unavailable",
      months: [
        { persianYear: 1405, persianMonth: 3, actualCostIrr: "300", estimateIrr: null },
        { persianYear: 1405, persianMonth: 4, actualCostIrr: "100", estimateIrr: null },
      ],
    },
    {
      assignments: [
        assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
        assignment("task-1", { wbsCode: "1.1", taskStart: "2026-06-01", taskCost: "1000" }),
        assignment("task-2", { wbsCode: "1.2", taskStart: "2026-07-05", taskCost: "400" }),
      ],
    },
  );

  assert.equal(trend.estimateSource, SCHEDULE_ESTIMATE_SOURCE);
  assert.equal(trend.scheduleEstimate.taskCount, 2);

  const view = buildMonthlyTrend({ months: trend.months, mode: TREND_MODES.PERIODIC });
  assert.equal(view.hasEstimate, true, "the line is drawn");
  assert.equal(view.estimatePartial, false, "and it is continuous across the window");
  assert.equal(view.points[0].estimateIrr, "1000");
  assert.equal(view.points[0].deviationIrr, "-700", "300 spent against 1000 planned");
  assert.equal(view.points[1].estimateIrr, "400");

  const cumulative = buildMonthlyTrend({ months: trend.months, mode: TREND_MODES.CUMULATIVE });
  assert.equal(cumulative.points[1].estimateIrr, "1400");
});

/** One assignment carrying only the schedule dates the window is derived from. */
function span(taskExternalId, taskStart, taskFinish) {
  return { task: { taskExternalId, wbsCode: taskExternalId, taskStart, taskFinish, metrics: null } };
}

test("the window is the project's own span, not a fixed twelve months", () => {
  // The real terrace schedule: 1404-05 .. 1405-05, read on 1405-06.
  const window = scheduleWindow(
    { assignments: [span("a", "2025-08-02", "2025-12-01"), span("b", "2026-01-10", "2026-07-23")] },
    "2026-09-15",
  );

  assert.equal(window.monthCount, 14, "مرداد ۱۴۰۴ through شهریور ۱۴۰۵ inclusive");
  assert.equal(window.anchorDate, "2026-09-15", "the plan ended before today, so today anchors it");
  assert.equal(window.trimmedMonths, 0);
});

test("a plan still running extends the window past today", () => {
  const window = scheduleWindow(
    { assignments: [span("a", "2025-08-02", "2027-12-20")] },
    "2026-09-15",
  );

  assert.equal(window.anchorDate, "2027-12-20", "the remaining plan is ahead, and the chart covers it");
  assert.equal(window.monthCount, 29, "two years and five months");
});

test("a plan that has not started yet still shows the recorded months behind it", () => {
  const window = scheduleWindow(
    { assignments: [span("a", "2027-01-10", "2027-06-10")] },
    "2026-09-15",
  );

  assert.equal(window.anchorDate, "2027-06-10");
  // شهریور ۱۴۰۵ back eleven months is مهر ۱۴۰۴; forward to خرداد ۱۴۰۶ is 21 months.
  assert.equal(window.monthCount, 21, "the plan ahead AND the twelve months up to today");
});

test("the window never narrows below the twelve months this chart always showed", () => {
  // A one-month schedule must not hide a year of invoices behind it.
  const window = scheduleWindow({ assignments: [span("a", "2026-09-01", "2026-09-20")] }, "2026-09-15");

  assert.equal(window.monthCount, MINIMUM_TRAILING_MONTHS);
  assert.equal(window.anchorDate, "2026-09-20");
});

test("a task with no finish still occupies the month it starts in", () => {
  const window = scheduleWindow({ assignments: [span("a", "2026-09-01", null)] }, "2026-09-15");

  assert.equal(window.anchorDate, "2026-09-15", "no finish, so today closes the window");
  assert.equal(window.monthCount, MINIMUM_TRAILING_MONTHS);
});

test("a long plan ahead does not push the recorded months off the chart", () => {
  const window = scheduleWindow({ assignments: [span("a", "2026-09-01", "2028-09-01")] }, "2026-09-15");
  const monthsBeforeToday = window.monthCount - 25;

  assert.equal(monthsBeforeToday, 11, "eleven months behind today, plus today, plus the plan");
});

test("a project longer than the service's ceiling is trimmed and says by how much", () => {
  const window = scheduleWindow(
    { assignments: [span("a", "2019-01-01", "2026-07-23")] },
    "2026-09-15",
  );

  assert.equal(window.monthCount, MAX_WINDOW_MONTHS, "never asks for a window the service rejects");
  assert.ok(window.requestedMonthCount > MAX_WINDOW_MONTHS);
  assert.equal(window.trimmedMonths, window.requestedMonthCount - MAX_WINDOW_MONTHS);
});

test("a feed that states no dates leaves the window to the caller", () => {
  assert.equal(scheduleWindow({ assignments: [] }, "2026-09-15"), null);
  assert.equal(scheduleWindow(null, "2026-09-15"), null);
  assert.equal(scheduleWindow({ assignments: [span("a", null, null)] }, "2026-09-15"), null);
});
