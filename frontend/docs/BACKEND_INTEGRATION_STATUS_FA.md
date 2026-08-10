# وضعیت اتصال Frontend به Backend مالی

تاریخ: 2026-08-09

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
| قیمت | `GET price-history`، `GET/POST resource prices` |
| تبدیل واحد | `GET/POST unit-conversions` |
| ورود اکسل قیمت | `POST preview/commit` |
| پیشرفت | `GET progress-snapshots`، `GET feed`، `POST progress-override` |
| فاکتور | List/Get/Create/Patch/Confirm/Void/Corrective |
| فایل | `POST files` و فهرست موقت همان نشست |
| استخراج | Retry و Confirm برای Draft موجود |
| خلاصه مالی زنده | `GET reports/live` با تاریخ گزارش و Snapshot پیشرفت انتخاب‌شده |

## روند داینامیک قیمت

نمودار هر قلم از کل خروجی واقعی `GET /price-history` ساخته می‌شود:

1. فقط نسخه‌های همان `resourceId` و تا تاریخ امروز انتخاب می‌شوند.
2. قیمت پروژه در صورت وجود بر قیمت سازمان اولویت دارد.
3. نمودار فقط تاریخچه همان Scope انتخاب‌شده را نمایش می‌دهد.
4. ترتیب نقاط با `effectiveFrom` و سپس `version` قطعی می‌شود.
5. جهت روند با مقایسه دقیق Decimal string دو نسخه آخر و بدون Floating Point محاسبه می‌شود.
6. نقاط ناقص حذف می‌شوند و کل صفحه را متوقف نمی‌کنند.

## محدودیت‌های Backend که مانع اتصال کامل‌اند

- فهرست فایل‌ها، شروع استخراج، Get/List استخراج و Reject وجود ندارد.
- `ExtractionDraftResponse.version` وجود ندارد.
- تاریخچه Revision تنظیمات و خطوط برآورد Endpoint مستقل ندارد؛ Frontend فقط وضعیت جاری واقعی را نمایش می‌دهد.
- فهرست Invoice و Audit در Backend Pagination/Filter سروری ندارد؛ فیلتر فاکتور فعلاً پس از دریافت لیست انجام می‌شود.
- Preview Import فقط خطاها را برمی‌گرداند و ردیف‌های معتبر را برای نمایش پیش‌نمایش کامل برنمی‌گرداند.
- Catalog فعالیت‌های پروژه برای ساخت خط متره Endpoint ندارد؛ Frontend فقط فعالیت‌های موجود در خطوط دریافت‌شده را می‌شناسد.
- مبلغ مستقیم هزینه عمومی در `InvoiceLineCreate` قابل ارسال نیست و محاسبه Backend آن را صفر می‌کند.
- کنترل Duplicate در `prepare_extracted` اجرا نمی‌شود.

جزئیات File/AI در `docs/BACKEND_GAPS_FILE_AI_FA.md` ثبت شده است.
