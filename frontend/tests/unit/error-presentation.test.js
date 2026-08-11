import test from "node:test";
import assert from "node:assert/strict";
import { formatApiErrorMessage, presentApiError } from "../../src/shared/errors/error-presentation.js";

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
