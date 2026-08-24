/**
 * One Persian wording per Backend warning code.
 *
 * The finance domain emits eight codes, and they arrive in two different
 * shapes: the report's `warnings` array carries the full ReportWarning record
 * (code, message, estimateLineId, affectedMetricKeys, …), while the progress
 * feed carries only `{code, message}` per assignment. The message on both is
 * written for a developer and in English, so the code is what the UI reads.
 *
 * This lives in one place because it had already drifted: the overview said
 * «برای یکی از خطوط برآورد…» and the report page said «برای یکی از ردیف‌های
 * برآورد…» for the very same PROGRESS_MISSING.
 *
 * Two of the codes the UI would like do not exist in the Backend, and no
 * wording is invented for them here:
 *   — there is no code distinguishing "this line is not mapped to an activity"
 *     from "it is mapped but has no usable quantity". Both arrive as
 *     PROGRESS_MISSING, so the wording below deliberately covers both and does
 *     not claim which one it is.
 *   — nothing is emitted when a value has been overridden manually, or when its
 *     quality is low. Those are read from `sourceMethod` and `quality` instead.
 */

const REPORT_WARNINGS = Object.freeze({
  UNIT_CONVERSION_MISSING: "تبدیل واحد لازم برای بخشی از محاسبات تعریف نشده است.",
  GENERAL_COST_OVERRUN: "هزینه واقعی ثبت‌شده عمومی پروژه از آخرین برآورد هزینه‌های عمومی بیشتر است.",
  PROGRESS_MISSING: "برای یکی از ردیف‌های برآورد، مقدار معتبر پیشرفت موجود نیست؛ یا به فعالیت کنترل پروژه متصل نشده یا مقدار قابل استفاده‌ای ندارد.",
  QUANTITY_OVERRUN: "مقدار انجام‌شده یکی از ردیف‌ها از آخرین مقدار برآورد بیشتر است.",
  CURRENT_PRICE_MISSING: "قیمت روز یکی از اقلام ثبت نشده و آن ردیف از محاسبات زنده کنار گذاشته شده است.",
  GROSS_AREA_MISSING: "زیربنای کل پروژه ثبت نشده و شاخص‌های هر مترمربع قابل محاسبه نیستند.",
  MONTHLY_ESTIMATE_UNAVAILABLE: "برآورد ماهانه برای این بازه در دسترس نیست.",
});

/**
 * The feed speaks about a single assignment, so the same codes are worded in the
 * singular and about that row rather than about "one of the lines".
 */
const FEED_WARNINGS = Object.freeze({
  PROGRESS_MISSING: "مقدار معتبر پیشرفت برای این تخصیص موجود نیست.",
  TASK_PROGRESS_FALLBACK: "مقدار اجرا از درصد پیشرفت فعالیت به دست آمده است، نه از مقدار واقعی تخصیص.",
});

export function describeReportWarning(code) {
  return REPORT_WARNINGS[String(code ?? "")] ?? null;
}

export function describeFeedWarning(code) {
  return FEED_WARNINGS[String(code ?? "")] ?? null;
}

/**
 * A code with no wording is still shown, because silence about a warning the
 * Backend raised is worse than an unfamiliar code on screen.
 */
export function feedWarningText(warning) {
  const code = String(warning?.code ?? "").trim();
  if (!code) return null;
  return describeFeedWarning(code) ?? `هشدار سرویس مالی: ${code}`;
}

export function reportWarningText(warning) {
  const code = String(warning?.code ?? "").trim();
  return describeReportWarning(code) ?? warning?.message ?? "هشدار بدون توضیح از سرویس مالی دریافت شد.";
}

export const REPORT_WARNING_CODES = Object.freeze(Object.keys(REPORT_WARNINGS));
export const FEED_WARNING_CODES = Object.freeze(Object.keys(FEED_WARNINGS));
