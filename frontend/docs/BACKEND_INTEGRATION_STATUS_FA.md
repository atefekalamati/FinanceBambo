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
| قیمت | `GET price-history`، `GET prices/current`، `GET/POST resource prices` |
| تبدیل واحد | `GET/POST unit-conversions` |
| ورود اکسل قیمت | `POST preview/commit` |
| پیشرفت | `GET progress-snapshots`، `GET feed`، `POST progress-override` |
| فاکتور | List/Get/Create/Patch/Confirm/Void/Corrective |
| فایل | `POST files` و فهرست موقت همان نشست |
| استخراج | Retry و Confirm برای Draft موجود |
| خلاصه مالی زنده | `GET reports/live` با تاریخ گزارش و Snapshot پیشرفت انتخاب‌شده |

## روند داینامیک قیمت

نمودار هر قلم از Read Model مرجع `GET /prices/current` ساخته می‌شود و تاریخچه کامل همچنان از `GET /price-history` دریافت می‌شود:

1. Frontend تاریخ امروز را به‌عنوان `asOf` ارسال می‌کند.
2. Backend قیمت پایه سازمان، Override پروژه، قیمت جاری و تاریخ اثر هرکدام را برمی‌گرداند.
3. `scopeKind` و اولویت قیمت پروژه در Backend تعیین می‌شود.
4. `trendPoints`، جهت روند و درصد آخرین تغییر مستقیماً از Read Model مرجع مصرف می‌شوند.
5. Frontend تاریخچه Append-only را برای جدول جزئیات جداگانه نگه می‌دارد.
6. مقادیر پولی همچنان Decimal string هستند و با Floating Point محاسبه نمی‌شوند.

## محدودیت‌های Backend که مانع اتصال کامل‌اند

- فهرست فایل‌ها، شروع استخراج، Get/List استخراج و Reject وجود ندارد.
- `ExtractionDraftResponse.version` وجود ندارد.
- تاریخچه Revision تنظیمات Endpoint مستقل ندارد؛ تاریخچه خطوط برآورد اکنون داخل Read Model هر خط دریافت و نمایش داده می‌شود.
- فهرست Invoice و Audit در Backend Pagination/Filter سروری ندارد؛ فیلتر فاکتور فعلاً پس از دریافت لیست انجام می‌شود.
- Catalog فعالیت‌های پروژه برای ساخت خط متره Endpoint ندارد؛ Frontend فقط فعالیت‌های موجود در خطوط دریافت‌شده را می‌شناسد.
- مبلغ مستقیم هزینه عمومی در `InvoiceLineCreate` قابل ارسال نیست و محاسبه Backend آن را صفر می‌کند.
- کنترل Duplicate در `prepare_extracted` اجرا نمی‌شود.

جزئیات File/AI در `docs/BACKEND_GAPS_FILE_AI_FA.md` ثبت شده است.
