/* What the reader could not do, said in Persian on the review card.
 *
 * WHY THIS EXISTS
 * The extraction contract carries six warning fields, and every one of them holds an
 * ARRAY OF OBJECTS -- `[{source, message}]`, or `[{code, message, evidence}]` for the
 * parser's own. The review card rendered any field it did not recognise as a text input
 * and assigned the value straight to `input.value`, so each of them appeared as an
 * editable box reading «[object Object]», under the label «اطلاعات خوانده‌شده», at
 * «۱۰۰ درصد اطمینان». Measured on a rendered card, not reasoned about.
 *
 * WHY IT MATTERS MORE THAN IT LOOKS
 * `currencyWarnings` is the one that made this urgent. The service now refuses to record a
 * currency the document does not state -- a vision model answered TOMAN for a page
 * printing neither word, at a confidence above the review threshold, and the two
 * candidates are a FACTOR OF TEN apart. The refusal is correct and the warning is how a
 * reviewer learns of it. This page then converts every amount as تومان regardless, so the
 * one sentence standing between a rial invoice and a tenfold error was «[object Object]».
 *
 * WHY THE CODE AND NOT THE MESSAGE
 * The messages are written for a developer and in English. The `code` (parser) and the
 * `source` (every other family) are stable identifiers, so they are what is read here --
 * the same rule `finance-warning-labels.js` follows for the report's warnings, and for the
 * same reason: a wording kept in two places drifts.
 *
 * WHAT IS NOT DONE
 * Nothing is suppressed. A warning whose identifier has no Persian wording is still shown,
 * carrying the service's own sentence, because silence about a warning the service raised
 * is worse than an unfamiliar sentence on screen. And nothing here is editable: these are
 * the reader's report on itself, not a field anybody fills in.
 */

/** The field keys whose value is a list of warnings rather than a reading. */
export const WARNING_KEYS = Object.freeze(new Set([
  "currencyWarnings", "parserWarnings", "aiWarnings",
  "ocrWarnings", "layoutWarnings", "fusionWarnings",
]));

/* `source`, for the families the adapters raise. `layout-*` is built from a diagnosis
   name, so the ones that cannot be listed exhaustively fall through to the message. */
const BY_SOURCE = Object.freeze({
  "currency-unevidenced":
    "واحد پول روی سند نوشته نشده بود، پس ثبت نشد. "
    + "اگر این فاکتور به ریال است، عدد را خودتان به تومان تبدیل کنید.",
  "ocr-empty": "هیچ متنی از این فایل خوانده نشد.",
  "ai-unavailable": "خوانندهٔ هوشمند در دسترس نبود؛ فقط آنچه به‌صورت قطعی خوانده شد ثبت شده است.",
  "ai-failed": "خوانندهٔ هوشمند خطا داد؛ فقط آنچه به‌صورت قطعی خوانده شد ثبت شده است.",
  "ai-low-confidence":
    "اطمینان خوانندهٔ هوشمند کمتر از حد لازم بود، پس فیلدهای آن استفاده نشد.",
  "ai-review-required": "اطمینان خوانندهٔ هوشمند پایین است؛ پیش از استفاده باید بررسی شود.",
  "layout-low-confidence":
    "جدولی در صفحه بازسازی شد اما اطمینان سلول‌هایش پایین بود و استفاده نشد.",
  "fusion-requires-review": "خواندهٔ تصویر و خواندهٔ متن با هم نمی‌خوانند و باید بررسی شوند.",
});

/* `code`, for the deterministic parser. Its messages carry figures filled in at runtime,
   and a Persian sentence cannot reproduce them -- so where the numbers matter the sentence
   says WHAT happened and the card itself already shows the figures: the lines total and
   the stated total sit a few rows below, and disagreeing is exactly what they show. */
const BY_CODE = Object.freeze({
  INVOICE_TEXT_EMPTY: "هیچ متنی شناسایی نشد، پس هیچ فیلدی خوانده نشد.",
  INVOICE_TABLE_NOT_RECOGNISED:
    "سطر عنوان ستون‌ها پیدا نشد، پس هیچ ردیفی خوانده نشد. متن شناسایی‌شده برای بررسی نگه داشته شده است.",
  INVOICE_ROW_AMBIGUOUS:
    "یک بلوک از جدول با نقش ستون‌ها نخواند، پس از آن ردیفی ساخته نشد.",
  INVOICE_ROW_INCOMPLETE:
    "بعد از آخرین ردیف کامل، چند سلول باقی ماند که به‌عنوان قلم خوانده نشد.",
  INVOICE_TOTAL_UNREADABLE:
    "سطر مبلغ نهایی پیدا شد اما ارقامش عدد نمی‌سازند؛ استفاده نشد.",
  INVOICE_TOTAL_NOT_POSITIVE: "مبلغ نهایی خوانده‌شده مثبت نیست؛ استفاده نشد.",
  INVOICE_TOTAL_AMBIGUOUS: "سند بیش از یک مبلغ نهایی دارد؛ هیچ‌کدام انتخاب نشد.",
  INVOICE_TOTAL_MISSING:
    "اقلام خوانده شدند اما سند مبلغ نهایی قابل‌خواندنی ندارد، پس جمع با چیزی سنجیده نشد.",
  INVOICE_TOTAL_UNCHECKED:
    "مبلغ نهایی خوانده شد اما همهٔ اقلام مبلغ ندارند، پس این دو با هم تطبیق داده نشدند.",
  INVOICE_TOTAL_MISMATCH:
    "جمع اقلام با مبلغ نهایی سند نمی‌خواند. هر دو همان‌طور که خوانده شدند گزارش شده‌اند و هیچ‌کدام اصلاح نشده است.",
  INVOICE_CURRENCY_ALTERNATIVE:
    "سند واحد پول دیگری را هم نام می‌برد؛ واحد خودِ مبلغ نهایی استفاده شد.",
  INVOICE_ITEM_ARITHMETIC_MISMATCH:
    "در یکی از اقلام، مقدار × قیمت واحد با مبلغ نوشته‌شده برابر نیست. هر دو همان‌طور که خوانده شدند گزارش شده‌اند.",
});

/**
 * One warning entry as a sentence, or null when it carries nothing at all.
 *
 * The identifier decides the wording; the service's own message is the fallback rather
 * than a supplement, so a translated warning does not print an English sentence beside it.
 */
export function warningText(entry) {
  if (typeof entry === "string") return entry.trim() || null;
  const code = String(entry?.code ?? "").trim();
  const source = String(entry?.source ?? "").trim();
  const known = BY_CODE[code] ?? BY_SOURCE[source] ?? null;
  if (known) return known;
  const message = String(entry?.message ?? "").trim();
  if (message) return message;
  return code || source || null;
}

/**
 * The evidence a warning carries, when it carries any.
 *
 * Only the parser sets it, and what it holds is DATA -- `2 x 500 != 1200` -- not English
 * prose, so it survives translation and is the part a reviewer can act on.
 */
export function warningEvidence(entry) {
  const evidence = String(entry?.evidence ?? "").trim();
  return evidence || null;
}

/**
 * Every warning on a draft, flattened and de-duplicated, in the order the fields arrived.
 *
 * De-duplicated on the sentence: the same situation can reach two families -- a total the
 * parser could not check and a fusion result that says the two readings disagree -- and a
 * reviewer reading the same line twice learns nothing the second time.
 */
export function draftWarnings(draft) {
  const seen = new Set();
  const rows = [];
  for (const field of draft?.fields ?? []) {
    if (!WARNING_KEYS.has(field?.key)) continue;
    const entries = Array.isArray(field.extractedValue)
      ? field.extractedValue
      : [field.extractedValue];
    for (const entry of entries) {
      const text = warningText(entry);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      rows.push({ key: field.key, text, evidence: warningEvidence(entry) });
    }
  }
  return rows;
}
