import test from "node:test";
import assert from "node:assert/strict";

import { summarizeReportWarnings } from "../../src/features/finance-home/finance-home-page.js";
import { formatDisplayNumber } from "../../src/shared/formatters/display.js";
import { reportWarningText } from "../../src/shared/warnings/finance-warning-labels.js";

test("repeated report warnings render once with their count and keep first-seen order", () => {
  const progress = { code: "PROGRESS_MISSING" };
  const price = { code: "CURRENT_PRICE_MISSING" };
  const warnings = [progress, price, progress, progress];

  assert.deepEqual(summarizeReportWarnings(warnings), [
    `${reportWarningText(progress)} (برای ${formatDisplayNumber(3)} مورد)`,
    reportWarningText(price),
  ]);
  assert.equal(warnings.length, 4, "the source warnings are not changed");
});

test("warnings are grouped by displayed text, even when their codes differ", () => {
  const warnings = [
    { code: "NEW_CODE_A", message: "هشدار یکسان" },
    { code: "NEW_CODE_B", message: "هشدار یکسان" },
    { code: "NEW_CODE_C", message: "هشدار دیگر" },
  ];

  assert.deepEqual(summarizeReportWarnings(warnings), [
    `هشدار یکسان (برای ${formatDisplayNumber(2)} مورد)`,
    "هشدار دیگر",
  ]);
  assert.deepEqual(summarizeReportWarnings([]), []);
});
