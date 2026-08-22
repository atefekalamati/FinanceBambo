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
