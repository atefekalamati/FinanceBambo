import test from "node:test";
import assert from "node:assert/strict";
import { isIsoDate, openingDateFor, periodDayCount, validatePeriod } from "../../src/shared/dates/reporting-periods.js";
import { loadReportData } from "../../src/features/report-builder/report-data.js";

/**
 * A date that does not exist must not be treated as one.
 *
 * `2026-06-31` was accepted here, turned into the 1st of July by `Date.UTC`, and printed
 * in a finished report's heading as the day the period closed. The service refused it with
 * a 422 the whole time; the refusal was caught and discarded. These hold each link of that
 * chain separately, because any one of them alone would let it happen again.
 */

test("a day that is not on the calendar is not a date", () => {
  for (const impossible of ["2026-06-31", "2026-02-29", "2026-04-31", "2026-13-01",
                            "2026-00-10", "2026-01-32", "2026-01-00"]) {
    assert.equal(isIsoDate(impossible), false, `${impossible} was accepted`);
  }
});

test("the last day of every month is a date, and so is a real leap day", () => {
  for (const real of ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31",
                      "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30", "2026-10-31",
                      "2026-11-30", "2026-12-31", "2028-02-29", "2024-02-29"]) {
    assert.equal(isIsoDate(real), true, `${real} was rejected`);
  }
  // A century that is not a leap year, and one that is.
  assert.equal(isIsoDate("2100-02-29"), false);
  assert.equal(isIsoDate("2000-02-29"), true);
});

test("a shape that is not a date at all is refused before the calendar is consulted", () => {
  for (const nonsense of ["", null, undefined, "not-a-date", "2026-1-1", "26-01-01",
                          "2026/01/01", "2026-01-01T00:00:00Z"]) {
    assert.equal(isIsoDate(nonsense), false, `${String(nonsense)} was accepted`);
  }
});

test("each way a period can be wrong gets its own sentence", () => {
  // Telling somebody who typed 2026-06-31 to "choose an end date" is not an answer: they
  // chose one. What they need to hear is that the day does not exist, and which one it was.
  const impossible = validatePeriod({ from: "2026-01-01", to: "2026-06-31" });
  assert.equal(impossible.valid, false);
  assert.match(impossible.errors.to, /وجود ندارد/);
  assert.match(impossible.errors.to, /2026-06-31/);

  const malformed = validatePeriod({ from: "01-01-2026", to: "2026-06-30" });
  assert.equal(malformed.valid, false);
  assert.match(malformed.errors.from, /خوانا نیست/);

  const absent = validatePeriod({ from: "", to: "2026-06-30" });
  assert.equal(absent.valid, false);
  assert.match(absent.errors.from, /انتخاب کنید/);
  assert.ok(!/وجود ندارد/.test(absent.errors.from), "an empty field is not an impossible day");
});

test("a period that ends before it starts is refused, and one that ends on its start is not", () => {
  const reversed = validatePeriod({ from: "2026-06-30", to: "2026-01-01" });
  assert.equal(reversed.valid, false);
  assert.match(reversed.errors.to, /پیش از شروع/);
  assert.equal(validatePeriod({ from: "2026-06-30", to: "2026-06-30" }).valid, true);
  assert.equal(periodDayCount({ from: "2026-06-30", to: "2026-06-30" }), 1);
});

test("a valid period is still accepted, including across a month boundary", () => {
  assert.equal(validatePeriod({ from: "2026-01-01", to: "2026-06-30" }).valid, true);
  assert.equal(validatePeriod({ from: "2028-02-29", to: "2028-03-01" }).valid, true);
  assert.equal(periodDayCount({ from: "2026-05-31", to: "2026-06-01" }), 2);
  // The opening picture is the day before the period opens, and it must be a real day.
  assert.equal(openingDateFor("2026-03-01"), "2026-02-28");
  assert.equal(openingDateFor("2028-03-01"), "2028-02-29");
  assert.equal(openingDateFor("2026-06-31"), null);
});

/** A fake service. `overview` answers according to what the date is. */
function adaptersAnswering(onOverview) {
  const fail = (status) => Object.assign(new Error("refused"), { status });
  return {
    reports: {
      async getOverview({ reportingDate }) { return onOverview(reportingDate, fail); },
      async getWbsReport() { return { items: [] }; },
      async getMonthly() { return { months: [] }; },
    },
    progress: { async getSnapshots() { return [{ snapshotId: "s1", status: "ready", reportingDate: "2026-06-30" }]; } },
  };
}

test("a day the project cannot report on leaves one end empty, as it always has", async () => {
  const data = await loadReportData({
    adapters: adaptersAnswering((date, fail) => {
      if (date === "2025-12-31") throw fail(404);
      return { reportingDate: date, metrics: {} };
    }),
    selection: ["periodMetrics"],
    period: { from: "2026-01-01", to: "2026-06-30" },
    today: "2026-06-30",
  });
  assert.equal(data.periodOverview.opening, null, "the absent end should be reported as absent");
  assert.ok(data.periodOverview.closing, "the end that answered should still be there");
});

test("a refusal of the request itself is not mistaken for a day with no data", async () => {
  // This is the whole defect: a 422 was swallowed exactly like a 404, and the document was
  // drawn anyway -- for a period the reader had not asked for.
  await assert.rejects(
    loadReportData({
      adapters: adaptersAnswering((date, fail) => { throw fail(422); }),
      selection: ["periodMetrics"],
      period: { from: "2026-01-01", to: "2026-06-30" },
      today: "2026-06-30",
    }),
    (error) => error.status === 422,
  );
});
