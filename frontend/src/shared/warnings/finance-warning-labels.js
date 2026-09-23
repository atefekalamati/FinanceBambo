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
 * The Backend can now tell three situations apart that used to arrive as one
 * PROGRESS_MISSING, and each is fixed by a different person, so each gets its
 * own sentence:
 *   PROGRESS_UNMAPPED + progressStatus `unmapped_assignment` — the line names an
 *     assignment that matched nothing: a broken reference on the line itself.
 *   PROGRESS_UNMAPPED + progressStatus `unmapped_activity` — the line was only
 *     ever findable through its activity, and that matched nothing, or it named
 *     no identifier at all.
 *   PROGRESS_MISSING — the line did reach an assignment, which reported nothing.
 *
 * Still not expressed by the Backend, and still not invented here: nothing is
 * emitted when a value has been overridden manually, or when its quality is
 * low. Those are read from `sourceMethod` and `quality` instead.
 */

/** The `progressStatus` a progress warning carries alongside its code. */
export const PROGRESS_STATUS = Object.freeze({
  UNMAPPED_ASSIGNMENT: "unmapped_assignment",
  UNMAPPED_ACTIVITY: "unmapped_activity",
  UNAVAILABLE: "unavailable",
});

const REPORT_WARNINGS = Object.freeze({
  UNIT_CONVERSION_MISSING: "تبدیل واحد لازم برای بخشی از محاسبات تعریف نشده است.",
  GENERAL_COST_OVERRUN: "هزینه واقعی ثبت‌شده عمومی پروژه از آخرین برآورد هزینه‌های عمومی بیشتر است.",
  PROGRESS_MISSING: "یکی از ردیف‌های برآورد به تخصیص خود در نسخه پیشرفت رسیده، اما آن تخصیص هیچ مقداری گزارش نکرده است.",
  PROGRESS_UNMAPPED: "یکی از ردیف‌های برآورد به هیچ تخصیصی در نسخه پیشرفت انتخاب‌شده متصل نیست.",
  PROGRESS_WORK_NOT_QUANTITY: "مقدار اجرای یکی از ردیف‌ها از ساعت‌کار گزارش‌شده به دست آمده است، نه از مقدار اندازه‌گیری‌شده.",
  QUANTITY_OVERRUN: "مقدار انجام‌شده یکی از ردیف‌ها از آخرین مقدار برآورد بیشتر است.",
  CURRENT_PRICE_MISSING: "قیمت روز یکی از اقلام ثبت نشده و آن ردیف از محاسبات زنده کنار گذاشته شده است.",
  ESTIMATE_BASELINE_MISSING: "یکی از ردیف‌های برآورد مقدار اولیه یا قیمت اولیه ندارد و از جمع برآورد اولیه کنار گذاشته شده است.",
  GROSS_AREA_MISSING: "زیربنای کل پروژه ثبت نشده و شاخص‌های هر مترمربع قابل محاسبه نیستند.",
  MONTHLY_ESTIMATE_UNAVAILABLE: "برآورد ماهانه برای این بازه در دسترس نیست.",
});

/**
 * The feed speaks about a single assignment, so the same codes are worded in the
 * singular and about that row rather than about "one of the lines".
 */
const FEED_WARNINGS = Object.freeze({
  PROGRESS_MISSING: "این تخصیص هیچ مقدار قابل استفاده‌ای گزارش نکرده است.",
  TASK_PROGRESS_FALLBACK: "مقدار اجرا از درصد پیشرفت فعالیت به دست آمده است، نه از مقدار واقعی تخصیص.",
  PROGRESS_WORK_NOT_QUANTITY: "مقدار اجرا از ساعت‌کار گزارش‌شده به دست آمده است، نه از مقدار اندازه‌گیری‌شده.",
});

/**
 * PROGRESS_UNMAPPED covers two situations that read the same in a summary and
 * are fixed by different people, so the status decides the sentence.
 */
const UNMAPPED_BY_STATUS = Object.freeze({
  [PROGRESS_STATUS.UNMAPPED_ASSIGNMENT]: "این ردیف تخصیصی را نام می‌برد که در نسخه پیشرفت پیدا نشد؛ ارجاع روی خود ردیف نادرست است.",
  [PROGRESS_STATUS.UNMAPPED_ACTIVITY]: "این ردیف فقط از راه فعالیتش قابل یافتن بود و آن فعالیت در نسخه پیشرفت پیدا نشد.",
});

export function describeReportWarning(code, progressStatus) {
  const status = UNMAPPED_BY_STATUS[String(progressStatus ?? "")];
  if (String(code ?? "") === "PROGRESS_UNMAPPED" && status) return status;
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
  return describeReportWarning(code, warning?.progressStatus) ?? warning?.message ?? "هشدار بدون توضیح از سرویس مالی دریافت شد.";
}

export const REPORT_WARNING_CODES = Object.freeze(Object.keys(REPORT_WARNINGS));
export const FEED_WARNING_CODES = Object.freeze(Object.keys(FEED_WARNINGS));
