const STATUS_PRESENTATION = Object.freeze({
  0: { title: "ارتباط با سرویس برقرار نشد", fallback: "اتصال شبکه و وضعیت سرویس مالی را بررسی و دوباره تلاش کنید.", retryable: true },
  // `override`, because every 403 this service sends carries an English developer string
  // naming the internal code -- "permission finance_report.view is required". Preferring
  // the server message put that on screen in Persian text, in front of a reader who
  // cannot act on a permission code and should not be shown one. The sentence below says
  // the same thing in the language the page is written in.
  // The host confirmed the session is a cookie it sets and the browser sends: there is
  // no token here to refresh and nothing this module can do to recover one. A 401 means
  // the session ended, so it is not offered a retry -- pressing it would fail the same
  // way -- and bootstrap.js turns it into a page that says so.
  401: { title: "نشست شما پایان یافته است", fallback: "برای ادامه، دوباره وارد سایت اصلی شوید.", retryable: false, override: true },
  403: { title: "دسترسی به این عملیات وجود ندارد", fallback: "مجوز مالی یا دسترسی پروژه برای انجام این درخواست کافی نیست.", retryable: false, override: true },
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

/* Keyed on the SENTENCE the service sends, for the handful of refusals whose status and
   code say too little. Every one of these arrives as `FINANCE_NOT_FOUND` / 404, and the
   404 preset above reads «رکورد ممکن است حذف شده باشد» -- true of a deleted invoice, and
   wrong about a report page: nothing was deleted, the host's progress provider could not
   serve a snapshot it had just listed, or that snapshot is dated after today.

   MEASURED ON THE FIRST HOST DEPLOYMENT. گزارش مالی opened on a red card carrying the
   generic sentence, and the two causes it could have had need two different people --
   one wires a provider, the other fixes a status date. The service already tells them
   apart, in English, on `message`; this is that distinction in the language of the page.
   Matched on the exact text and not on a substring, so a future sentence that merely
   resembles one of these is not silently given its meaning. `override` keeps the English
   original off the screen. */
const MESSAGE_PRESENTATION = Object.freeze({
  "progress snapshot not found for reporting date": {
    title: "تاریخ نسخهٔ پیشرفت جلوتر از تاریخ گزارش است",
    fallback: "نسخهٔ پیشرفت انتخاب‌شده تاریخ وضعیتی بعد از امروز دارد. گزارش زنده روی تاریخ امروز محاسبه می‌شود و نمی‌تواند از پیشرفتی که هنوز گزارش نشده استفاده کند. تاریخ وضعیت زمان‌بندی را بررسی کنید یا نسخهٔ قدیمی‌تری را انتخاب کنید.",
    retryable: false, override: true,
  },
  "progress snapshot not found": {
    title: "فید پیشرفت این پروژه در دسترس نیست",
    fallback: "نسخهٔ پیشرفت در فهرست هست اما سرویس نتوانست محتوای آن را بخواند. این یعنی providerِ پیشرفت روی میزبان با منبعی که فهرست از آن ساخته شده هم‌خوانی ندارد، یا جدول‌های تفصیلی زمان‌بندی برای این نسخه خالی‌اند. مشکل با تلاش دوباره برطرف نمی‌شود؛ به تیم استقرار اطلاع دهید.",
    retryable: false, override: true,
  },
  "report snapshot not found": {
    title: "گزارش صادرشده پیدا نشد",
    fallback: "گزارشی با این شناسه برای این پروژه صادر نشده است، یا به پروژهٔ دیگری تعلق دارد.",
    retryable: false, override: true,
  },
  "estimate line not found": {
    title: "ردیف برآورد پیدا نشد",
    fallback: "ردیف برآوردی که به آن اشاره شده در این پروژه وجود ندارد یا حذف شده است.",
    retryable: false, override: true,
  },
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
  const serverMessage = String(error?.message ?? "").trim();
  // The sentence first: it is the most specific thing the service said, and the code
  // beneath it (`FINANCE_NOT_FOUND`) is shared by refusals that need different people.
  const preset = MESSAGE_PRESENTATION[serverMessage] ?? CODE_PRESENTATION[code] ?? STATUS_PRESENTATION[status] ?? {
    title: status >= 500 ? "خطای سرویس مالی" : "انجام درخواست ممکن نشد",
    fallback: status >= 500 ? "سرویس با خطای پیش‌بینی‌نشده روبه‌رو شد." : "درخواست را بررسی و دوباره تلاش کنید.",
    retryable: status >= 500,
  };
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
