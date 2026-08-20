# وضعیت اتصال Frontend به Backend مالی

تاریخ: 2026-08-20 — بازبینی‌شده مقابل `origin/master`

## انتخاب Runtime

- اگر Host مقدار معتبر `window.__BAMBO_FINANCE_CONTEXT__` را پیش از `bootstrap.js` قرار دهد، Runtime برابر `host` و تمام صفحات فعال از API واقعی Same-Origin استفاده می‌کنند.
- اگر Context وجود نداشته باشد، Runtime برابر `standalone` و فقط برای توسعه محلی از Mock Adapter استفاده می‌کند.
- Scope سازمان و پروژه هرگز در Body ارسال نمی‌شود؛ `projectId` فقط از Context معتبر وارد Path می‌شود و Backend سازمان را از Auth Context تعیین می‌کند.

## Endpointهای متصل‌شده

| بخش | Endpointهای فعال |
|---|---|
| تنظیمات | `GET/PATCH settings` |
| اقلام و متره | `GET/POST resources`، `GET/POST estimate-lines`، `POST revisions` |
| ورود اکسل برآورد | `POST preview/commit` |
| قیمت | `GET price-history`، `GET prices/current`، `GET/POST resource prices` |
| تبدیل واحد | `GET/POST unit-conversions` |
| ورود اکسل قیمت | `POST preview/commit` |
| پیشرفت | `GET progress-snapshots`، `GET feed`، `POST progress-override` |
| فاکتور | List/Get/Create/Patch/Confirm/Void/Corrective |
| فایل | `POST files`، `GET files` (صفحه‌بندی و فیلتر)، `GET files/{fileId}`، `GET files/{fileId}/content` |
| استخراج | `POST files/{fileId}/extractions`، `GET extractions`، `GET extractions/{draftId}`، Retry، Reject و Confirm |
| ممیزی | `GET audit-events` با `page`/`pageSize` |
| خلاصه مالی زنده | `GET reports/live` با تاریخ گزارش و Snapshot پیشرفت انتخاب‌شده |

## روند داینامیک قیمت

نمودار هر قلم از Read Model مرجع `GET /prices/current` ساخته می‌شود و تاریخچه کامل همچنان از `GET /price-history` دریافت می‌شود:

1. Frontend تاریخ امروز را به‌عنوان `asOf` ارسال می‌کند.
2. Backend قیمت پایه سازمان، Override پروژه، قیمت جاری و تاریخ اثر هرکدام را برمی‌گرداند.
3. `scopeKind` و اولویت قیمت پروژه در Backend تعیین می‌شود.
4. `trendPoints`، جهت روند و درصد آخرین تغییر مستقیماً از Read Model مرجع مصرف می‌شوند.
5. Frontend تاریخچه Append-only را برای جدول جزئیات جداگانه نگه می‌دارد.
6. مقادیر پولی همچنان Decimal string هستند و با Floating Point محاسبه نمی‌شوند.

## شکاف‌های واقعی Backend

بازبینی ۱۴۰۵/۰۵/۲۹ بند به بند مقابل `origin/master` انجام شد. **شش مورد از هفت محدودیتی که این سند قبلاً اعلام می‌کرد دیگر وجود ندارند** و نسخه قبلی این فهرست نباید مبنای برنامه‌ریزی قرار گیرد.

### آنچه واقعاً باقی مانده

- **تاریخچه بازنگری تنظیمات Endpoint ندارد.** `FinanceSettingsResponse` فقط بازنگری جاری را برمی‌گرداند و هیچ مسیر History وجود ندارد. Frontend به‌جای جدول خالی، مشخصات بازنگری جاری را نشان می‌دهد و برای سابقه کامل به صفحه ممیزی ارجاع می‌دهد.
- **`GET /audit-events` فیلتر سروری و پاکت صفحه‌بندی ندارد.** `page`/`pageSize` را می‌پذیرد ولی پاسخ آرایه خام است، پس تعداد کل قابل محاسبه نیست و فیلتر Client-side می‌ماند.
- **قرارداد استخراج مقدار، واحد و قیمت واحد ندارد.** `ExtractionConfirm` فقط یک مبلغ کل می‌دهد و `services/invoices.py` مبلغ مستقیم را تنها برای منبع `general_cost` می‌پذیرد؛ بنابراین تأیید استخراج روی قلم مقداری تا زمان توسعه قرارداد ممکن نیست.
- **Provider واقعی OCR/Voice انتخاب نشده است** (Gate باز PRD بند ۸.۷).

### آنچه غلط ثبت شده بود و اکنون موجود است

| ادعای قبلی | واقعیت روی `origin/master` |
|---|---|
| فهرست فایل‌ها وجود ندارد | `GET /files` با `page`، `pageSize`، `logicalType`، `fileCategory`، `processingStatus` و `uploaderId` |
| شروع/دریافت/فهرست/رد استخراج وجود ندارد | `POST /files/{fileId}/extractions`، `GET /extractions`، `GET /extractions/{draftId}`، `POST /extractions/{draftId}/reject` |
| `ExtractionDraftResponse.version` وجود ندارد | موجود است (`version: int = Field(ge=1)`)، به‌همراه `linkedInvoiceId` |
| فهرست Invoice صفحه‌بندی و فیلتر سروری ندارد | `GET /invoices` با `page`، `pageSize`، `query`، `status` و `source` |
| فهرست Audit صفحه‌بندی ندارد | `GET /audit-events` با `page` و `pageSize` |
| Catalog فعالیت پروژه Endpoint ندارد | `GET /activities` و `POST /activities` |
| مبلغ مستقیم هزینه عمومی قابل ارسال نیست و صفر می‌شود | `InvoiceLineCreate.lineAmountIrr` موجود است و `_calculate_lines` آن را محاسبه می‌کند |
| کنترل Duplicate در `prepare_extracted` اجرا نمی‌شود | اجرا می‌شود و بدون `duplicateReason` خطای `DuplicateInvoice` می‌دهد |

هشدار: `docs/BACKEND_GAPS_FILE_AI_FA.md` هنوز بر پایه همان ادعاهای غلط نوشته شده و بازنویسی نشده است. تا آن زمان، هر محدودیتی را مستقیماً مقابل `origin/master:backend/app/finance/router.py` و Schema مربوطه بررسی کنید، نه از روی این اسناد.
