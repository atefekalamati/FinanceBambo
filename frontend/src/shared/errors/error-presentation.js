const STATUS_PRESENTATION = Object.freeze({
  0: { title: "ارتباط با سرویس برقرار نشد", fallback: "اتصال شبکه و وضعیت سرویس مالی را بررسی و دوباره تلاش کنید.", retryable: true },
  403: { title: "دسترسی به این عملیات وجود ندارد", fallback: "مجوز مالی یا دسترسی پروژه برای انجام این درخواست کافی نیست.", retryable: false },
  404: { title: "اطلاعات موردنظر پیدا نشد", fallback: "رکورد ممکن است حذف شده باشد یا به پروژه دیگری تعلق داشته باشد.", retryable: false },
  409: { title: "اطلاعات هم‌زمان تغییر کرده است", fallback: "اطلاعات جدید را دریافت و عملیات را دوباره بررسی کنید.", retryable: true },
  422: { title: "اطلاعات ارسالی معتبر نیست", fallback: "فیلدهای مشخص‌شده را اصلاح و دوباره تلاش کنید.", retryable: false },
  503: { title: "سرویس مالی موقتاً در دسترس نیست", fallback: "اطلاعات شما تغییر نکرده است؛ کمی بعد دوباره تلاش کنید.", retryable: true },
});

const CODE_PRESENTATION = Object.freeze({
  AI_EXTRACTION_FAILED: { title: "پردازش فایل انجام نشد", fallback: "فایل اصلی حفظ شده است و می‌توانید پردازش را دوباره اجرا کنید.", retryable: true },
  // Raised for a repeated import file and for a repeated invoice attachment.
  // Both carry an English developer message, so `override` keeps it off screen.
  DUPLICATE_IMPORT_FILE: { title: "این فایل قبلاً ثبت شده است", fallback: "همین فایل پیش‌تر برای این پروژه ثبت شده است. اگر تغییری داده‌اید، نسخه به‌روزشده را بارگذاری کنید.", retryable: false, override: true },
  FINANCE_FORBIDDEN: STATUS_PRESENTATION[403],
  FINANCE_NOT_FOUND: STATUS_PRESENTATION[404],
  INVOICE_ALREADY_CONFIRMED: { title: "فاکتور قبلاً تأیید شده است", fallback: "فاکتور تأییدشده قابل ویرایش مستقیم نیست.", retryable: false },
  PRICE_PERIOD_OVERLAP: { title: "بازه قیمت با نسخه دیگری تداخل دارد", fallback: "تاریخ اثر قیمت را بررسی کنید.", retryable: false },
  STALE_VERSION: { title: "نسخه جدیدتری ثبت شده است", fallback: "اطلاعات را به‌روزرسانی و تغییر خود را دوباره بررسی کنید.", retryable: true },
  UNIT_MISMATCH: { title: "واحدها با یکدیگر سازگار نیستند", fallback: "بُعد واحد یا تبدیل معتبر را بررسی کنید.", retryable: false },
  VALIDATION_ERROR: STATUS_PRESENTATION[422],
});

function normalizeDetail(detail, index) {
  if (typeof detail === "string") return detail;
  const field = detail?.field ?? detail?.loc?.at?.(-1) ?? null;
  const message = detail?.message ?? detail?.msg ?? "مقدار این فیلد معتبر نیست.";
  return field ? `${String(field)}: ${message}` : `خطای ${index + 1}: ${message}`;
}

/* Everything the API throws is an ApiError carrying a status and a code. Anything else
   reaching here came from OUR code while rendering what the API successfully returned —
   and telling the reader to "check the network" about a request that returned 200 sends
   them to look in the wrong place, and offers a retry button that can only fail the same
   way. Such a fault is named for what it is and is not retryable. */
function isApiError(error) {
  return error?.name === "ApiError" || error?.status !== undefined || error?.code !== undefined;
}

const DISPLAY_FAULT = Object.freeze({
  title: "نمایش اطلاعات انجام نشد",
  fallback: "اطلاعات از سرویس دریافت شد اما نمایش آن با خطا روبه‌رو شد. این مشکل با تلاش دوباره برطرف نمی‌شود.",
  retryable: false,
});

export function presentApiError(error) {
  if (error && !isApiError(error)) {
    return Object.freeze({
      title: DISPLAY_FAULT.title,
      message: DISPLAY_FAULT.fallback,
      retryable: false,
      code: "CLIENT_RENDER_ERROR",
      requestId: null,
      details: [],
    });
  }
  const status = Number(error?.status) || 0;
  const code = String(error?.code || "UNKNOWN_ERROR");
  const preset = CODE_PRESENTATION[code] ?? STATUS_PRESENTATION[status] ?? {
    title: status >= 500 ? "خطای سرویس مالی" : "انجام درخواست ممکن نشد",
    fallback: status >= 500 ? "سرویس با خطای پیش‌بینی‌نشده روبه‌رو شد." : "درخواست را بررسی و دوباره تلاش کنید.",
    retryable: status >= 500,
  };
  const serverMessage = String(error?.message ?? "").trim();
  const genericMessages = new Set(["خطای پیش‌بینی‌نشده", "دریافت اطلاعات مالی انجام نشد."]);
  const useServerMessage = !preset.override && serverMessage && !genericMessages.has(serverMessage);
  return Object.freeze({
    title: preset.title,
    message: useServerMessage ? serverMessage : preset.fallback,
    retryable: preset.retryable,
    code,
    requestId: error?.requestId ?? null,
    details: Array.isArray(error?.details) ? error.details.map(normalizeDetail) : [],
  });
}

export function formatApiErrorMessage(error, fallback = "عملیات انجام نشد.") {
  const presentation = presentApiError(error);
  const message = presentation.message || fallback;
  return `${message}${presentation.requestId ? ` · شناسه درخواست: ${presentation.requestId}` : ""}`;
}
