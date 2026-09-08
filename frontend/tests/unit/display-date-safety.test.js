import test from "node:test";
import assert from "node:assert/strict";

import { formatBusinessDate, formatSystemDateTime } from "../../src/shared/formatters/display.js";
import { presentApiError } from "../../src/shared/errors/error-presentation.js";
import { ApiError } from "../../src/core/api/api-error.js";

/* The progress page rendered nothing and reported a service outage while every request
   returned 200. The cause was a formatter, and the symptom was an error message that sent
   the reader to look at the network. These tests hold both ends of that shut. */

test("a date-only business date still formats as it always did", () => {
  // 1 Mehr 1405 is 2026-09-23, so 2026-10-22 is 30 Mehr. It read 29 only because
  // the formatter had no time zone and the machine that wrote this sits west of
  // UTC; in Tehran the same call has always returned 30.
  assert.equal(formatBusinessDate("2026-10-22"), "۳۰ مهر ۱۴۰۵");
});

test("a business date carrying a time formats instead of throwing", () => {
  // The exact value that broke the page: a task start from the schedule feed. Midnight
  // used to be appended to it, producing "2025-08-09T08:00T00:00:00Z" — not a date.
  assert.equal(formatBusinessDate("2025-08-09T08:00"), "۱۸ مرداد ۱۴۰۴");
});

test("an offset timestamp formats too", () => {
  assert.equal(formatBusinessDate("2026-09-05T04:28:15.465690-07:00"), "۱۴ شهریور ۱۴۰۵");
});

test("nothing a source can send makes a formatter throw", () => {
  for (const value of [null, undefined, "", "garbage", "0000", {}, [], NaN, "2026-13-45"]) {
    assert.doesNotThrow(() => formatBusinessDate(value), `formatBusinessDate(${String(value)})`);
    assert.doesNotThrow(() => formatSystemDateTime(value), `formatSystemDateTime(${String(value)})`);
  }
});

test("an unreadable value is the neutral dash, never an invented date", () => {
  assert.equal(formatBusinessDate("garbage"), "—");
  assert.equal(formatSystemDateTime("garbage"), "—");
});

test("a render fault is not reported as a lost connection", () => {
  // A RangeError from our own rendering has no status, and used to fall through to
  // status 0 — "ارتباط با سرویس برقرار نشد", with a retry button that could only fail
  // the same way. It is named for what it is, and is not retryable.
  const presented = presentApiError(new RangeError("Invalid time value"));
  assert.equal(presented.code, "CLIENT_RENDER_ERROR");
  assert.equal(presented.retryable, false);
  assert.notEqual(presented.title, "ارتباط با سرویس برقرار نشد");
});

test("a genuine transport failure is still reported as one", () => {
  const presented = presentApiError(new ApiError({ status: 0, code: "UNKNOWN_ERROR" }));
  assert.equal(presented.title, "ارتباط با سرویس برقرار نشد");
  assert.equal(presented.retryable, true);
});

test("an API error keeps its own presentation", () => {
  const denied = presentApiError(new ApiError({ status: 403, code: "FINANCE_FORBIDDEN" }));
  assert.equal(denied.retryable, false);
  assert.equal(denied.title, "دسترسی به این عملیات وجود ندارد");
});
