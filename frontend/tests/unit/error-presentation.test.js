import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { formatApiErrorMessage, presentApiError } from "../../src/shared/errors/error-presentation.js";

const FEATURES_DIR = fileURLToPath(new URL("../../src/features", import.meta.url));

function featureSources() {
  return readdirSync(FEATURES_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .flatMap((entry) => {
      const directory = join(FEATURES_DIR, entry.name);
      return readdirSync(directory)
        .filter((name) => name.endsWith(".js"))
        .map((name) => [`${entry.name}/${name}`, readFileSync(join(directory, name), "utf8")]);
    });
}

test("presents stale-version conflicts as recoverable without hiding request identity", () => {
  const result = presentApiError({ status: 409, code: "STALE_VERSION", message: "نسخه رکورد تغییر کرده است.", requestId: "req-409" });
  assert.equal(result.title, "نسخه جدیدتری ثبت شده است");
  assert.equal(result.retryable, true);
  assert.equal(result.requestId, "req-409");
});

test("normalizes Backend field details for accessible display", () => {
  const result = presentApiError({ status: 422, code: "VALIDATION_ERROR", details: [{ field: "reason", message: "دلیل الزامی است." }, { loc: ["body", "amount"], msg: "مبلغ معتبر نیست." }] });
  assert.deepEqual(result.details, ["reason: دلیل الزامی است.", "amount: مبلغ معتبر نیست."]);
  assert.equal(result.retryable, false);
});

test("formats compact mutation feedback with request id", () => {
  assert.equal(formatApiErrorMessage({ status: 503, message: "سرویس موقتاً در دسترس نیست.", requestId: "req-503" }), "سرویس موقتاً در دسترس نیست. · شناسه درخواست: req-503");
});

test("maps status and code to curated Persian copy instead of echoing the raw server message", () => {
  const forbidden = presentApiError({ status: 403, code: "FINANCE_FORBIDDEN" });
  assert.equal(forbidden.title, "دسترسی به این عملیات وجود ندارد");
  assert.equal(forbidden.retryable, false);

  const generic = presentApiError({ status: 500, message: "خطای پیش‌بینی‌نشده" });
  assert.equal(generic.message, "سرویس با خطای پیش‌بینی‌نشده روبه‌رو شد.", "a generic server string is replaced by the curated fallback");
});

test("no feature page rebuilds the request-id suffix by hand", () => {
  const offenders = featureSources()
    .filter(([, source]) => source.includes("شناسه درخواست"))
    .map(([name]) => name);
  assert.deepEqual(
    offenders,
    [],
    "inline `${error.message} · شناسه درخواست: …` bypasses presentApiError, so page-level and action-level errors disagree; call formatApiErrorMessage instead",
  );
});

test("the two report-page 404s are told apart by the sentence the service sent", () => {
  /* Both arrive as FINANCE_NOT_FOUND / 404, and the 404 preset talks about a deleted
     record -- wrong about a report page, where nothing was deleted. On the first host
     deployment گزارش مالی opened on that generic card, and the two causes it could have
     had need two different people: one wires a progress provider, the other fixes a
     status date. The service already distinguishes them on `message`. */
  const dated = presentApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "progress snapshot not found for reporting date", requestId: "req-1" });
  assert.equal(dated.title, "تاریخ نسخهٔ پیشرفت جلوتر از تاریخ گزارش است");
  assert.match(dated.message, /تاریخ وضعیت/);
  assert.equal(dated.retryable, false);
  assert.equal(dated.requestId, "req-1", "the request id still travels");

  const unserved = presentApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "progress snapshot not found" });
  assert.equal(unserved.title, "فید پیشرفت این پروژه در دسترس نیست");
  assert.match(unserved.message, /provider/);
  assert.doesNotMatch(unserved.message, /progress snapshot not found/, "the English original stays off the screen");
});

test("a sentence that merely resembles a known one keeps the generic 404 wording", () => {
  /* Matched on the exact text, not a substring: a future refusal that happens to contain
     these words must not be silently handed their meaning. */
  const other = presentApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "progress snapshot not found: archived" });
  assert.equal(other.title, "اطلاعات موردنظر پیدا نشد");
});
