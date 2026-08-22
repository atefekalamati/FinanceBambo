# نواقص Backend برای فایل و بازبینی هوشمند فاکتور

> **`SUPERSEDED` — ۱۴۰۵/۰۵/۲۹ / 2026-08-20.** بازبینی مقابل `origin/master` نشان داد
> Endpointهایی که این سند «مسدودکننده» اعلام کرده — فهرست فایل، شروع/دریافت/فهرست/رد
> استخراج و فیلد `version` — همگی پیاده‌سازی شده‌اند. متن زیر فقط سابقه درخواست است و
> مبنای برنامه‌ریزی نیست. وضعیت معتبر در `docs/BACKEND_INTEGRATION_STATUS_FA.md`
> بخش «شکاف‌های واقعی Backend» ثبت شده است.

تاریخ بررسی: ۱۴۰۵/۰۵/۱۸ — 2026-08-09

مبنای بررسی: PRD نسخه ۱.۱، Integration Kit نسخه ۱.۱ و کد فعلی شاخه `master`. این سند درخواست تغییر Frontend نیست و هیچ فایل Backend توسط تیم Frontend تغییر نکرده است.

## P0 — مسدودکننده اتصال Frontend

### ۱. فهرست فایل‌های مالی پروژه

مسیر پیشنهادی هم‌راستا با ساختار فعلی:

```text
GET /api/projects/{projectId}/finance/files?page=1&pageSize=50&logicalType=&processingStatus=
```

نیازمندی‌ها:

- Scope فقط از Context معتبر Host استخراج شود.
- Pagination پیش‌فرض ۵۰ و سقف ۲۰۰ داشته باشد.
- خروجی شامل `items`, `page`, `pageSize`, `totalItems`, `totalPages` باشد.
- فیلتر نوع منطقی و وضعیت پردازش اختیاری باشد.
- رکوردهای حذف‌شده برگردانده نشوند.
- Cross-scope مانند رکورد ناموجود، پاسخ ۴۰۴ بدهد.

### ۲. شروع پردازش فایل

متد `FinanceExtractionService.start` وجود دارد، اما Route عمومی ندارد.

```text
POST /api/projects/{projectId}/finance/files/{fileId}/extractions
Content-Type: application/json

{"hints": {}}
```

پاسخ باید `ExtractionDraftResponse` نسخه‌دار باشد. فقط بارگذار فایل با `finance.edit` مجاز است. درخواست هم‌زمان روی فایل در حال پردازش باید Error Envelope پایدار برگرداند.

### ۳. دریافت Draft و فهرست بازبینی‌ها

Service فقط متد `get` دارد و هیچ Route دریافت یا List وجود ندارد.

```text
GET /api/projects/{projectId}/finance/extractions/{draftId}
GET /api/projects/{projectId}/finance/extractions?page=1&pageSize=50&reviewStatus=&fileId=
```

فهرست باید جدیدترین نسخه هر فایل را مشخص کند و Pagination استاندارد داشته باشد. دسترسی مشاهده با `finance.view` و Scope پروژه کنترل شود.

### ۴. افزودن Version به پاسخ استخراج

`ExtractionConfirm` به `expectedVersion` نیاز دارد، اما `ExtractionDraftResponse` فیلد `version` ندارد. بدون این فیلد Frontend امکان ارسال Confirm/Reject ایمن ندارد.

فیلدهای لازم در پاسخ:

```text
version: integer >= 1
createdAt: UTC datetime
```

در صورت پذیرش، `linkedInvoiceId` نیز برای رفتن از بازبینی به فاکتور لازم است؛ یا باید از پاسخ Confirm قابل نگهداری و بازیابی باشد.

### ۵. رد استخراج بدون حذف فایل

Domain مقدار `rejected` را می‌پذیرد، ولی Service، Repository و Route عملیات Reject وجود ندارد.

```text
POST /api/projects/{projectId}/finance/extractions/{draftId}/reject

{"expectedVersion": 1, "reason": "..."}
```

الزامات:

- فقط submitter/بارگذار مجاز باشد.
- فایل اصلی حذف یا تغییر نکند.
- مقدار `financialEffectIRR` صفر بماند.
- رویداد ممیزی با actor، reason، before/after و زمان UTC ثبت شود.
- نسخه قدیمی یا Draft غیرمنتظر با `STALE_VERSION` رد شود.

### ۶. قرارداد پایدار فیلدهای استخراج‌شده

در وضعیت فعلی `ExtractionFieldDto.key` هر رشته‌ای را می‌پذیرد. Frontend برای ساخت فرم و Payload فاکتور به Schema پایدار نیاز دارد. حداقل کلیدهای سربرگ، تعدیلات و خطوط باید نسخه‌بندی و مستند شوند:

```text
invoiceNumber
invoiceDate
vendorName
description
discountIRR
taxIRR
shippingIRR
otherCostsIRR
lines[]: resourceId, estimateLineId, quantity, unit, unitPriceIRR, description
```

برای هر فیلد باید نوع مقدار، nullable بودن، Confidence و مسیر آن در Invoice مشخص باشد. مبلغ و مقدار در مرز API باید Decimal string باشند؛ Confidence تنها مقدار عددی صفر تا یک است.

### ۷. دریافت امن محتوای فایل برای Preview/Playback

`GET /files/{fileId}` فقط Metadata برمی‌گرداند. برای نمایش تصویر اصلی یا پخش صدای اصلی در صفحه Review یک Endpoint محتوای Same-Origin و مجوزدار لازم است.

```text
GET /api/projects/{projectId}/finance/files/{fileId}/content
```

- مجوز و Scope قبل از خواندن Storage بررسی شود.
- `Content-Type` ثبت‌شده و Header امن دانلود/نمایش ارسال شود.
- SVG و محتوای اجرایی هرگز inline ارائه نشود.
- دسترسی موفق با `attachment.accessed` ممیزی شود.
- URL مستقیم Storage یا Credential به مرورگر داده نشود.

### ۸. مبلغ هزینه عمومی در InvoiceLineCreate

`InvoiceLineCreate` برای هزینه عمومی `quantity=null` و `unitPriceIrr=null` را می‌پذیرد، اما `_calculate_lines` این حالت را `1 × 0` محاسبه می‌کند و فیلدی برای مبلغ مستقیم خط وجود ندارد. در نتیجه هزینه عمومی واقعی از Frontend قابل ثبت نیست.

Backend باید مطابق قرارداد محصول یک فیلد مبلغ صحیح ریالی برای خط هزینه عمومی تعریف کند و محاسبه، Schema، Repository و Response را هماهنگ سازد. نام دقیق فیلد باید در OpenAPI نهایی تثبیت شود.

### ۹. کنترل فاکتور مشابه در مسیر Confirm استخراج

مسیر دستی از `repo.duplicate` استفاده می‌کند، اما `prepare_extracted` مستقیماً فاکتور تأییدشده می‌سازد و بررسی فاکتور مشابه را اجرا نمی‌کند. قانون شباهت فروشنده، شماره، تاریخ و مبلغ باید برای منبع تصویر و صدا نیز قبل از اثر مالی اعمال شود و در صورت ادامه، دلیل ممیزی دریافت شود.

## P1 — لازم برای رفتار کامل و قابل اتکا

### ۱۰. مدل اجرای Provider و وضعیت Processing

عملیات فعلی `start` تا پایان Provider منتظر می‌ماند؛ بنابراین Client عملاً وضعیت `processing` را از پاسخ جداگانه مشاهده نمی‌کند. Backend باید یکی از دو مدل را صریح کند:

- اجرای Job و پاسخ ۲۰۲ همراه شناسه پیگیری، سپس Poll؛ یا
- اجرای هم‌زمان با Timeout مصوب و بازیابی وضعیت فایل از Endpoint Metadata.

در هر دو حالت، شکست Provider باید فایل را `failed` کند، فایل را حفظ کند، Error Envelope شامل `AI_EXTRACTION_FAILED` و `requestId` بدهد و Retry را ممکن نگه دارد.

### ۱۱. Adapter واقعی تصویر و صدا

کد فعلی فقط Protocol و Fake تستی دارد و Provider تولیدی انتخاب/پیاده‌سازی نشده است. Adapterهای تصویر و صدای فارسی باید Backend-only باشند؛ Credential، Source فایل یا تماس مستقیم Provider نباید وارد Frontend شود. خروجی Provider قبل از ذخیره باید با قرارداد نسخه‌دار بند ۶ Validation شود.

### ۱۲. List Repository و Indexهای لازم

Repositoryهای فایل و استخراج فقط `get` دارند. برای List/Pagination باید Queryهای Scope‌شده و Indexهای مناسب حداقل روی ترکیب‌های زیر اضافه و تست شوند:

```text
(organization_id, project_id, uploaded_at)
(organization_id, project_id, processing_status)
(organization_id, project_id, review_status, created_at)
(organization_id, project_id, attachment_id, version)
```

## تست‌های پذیرش موردنیاز Backend

- Upload تمام قالب‌های مجاز و رد GIF/SVG/WebM، MIME ناسازگار، Magic Bytes ناسازگار و فایل بیش‌ازحد
- List و Get با Scope صحیح و Cross-scope برابر ۴۰۴
- شروع تصویر و صدا با Adapter مستقل و اثر مالی صفر
- مشاهده `uploaded → processing → ready` و `failed → processing → ready`
- Retry به‌صورت نسخه جدید و غیرقابل بازنویسی
- Reject با دلیل و Audit بدون حذف فایل
- Confirm فقط توسط submitter، با `expectedVersion` و Idempotency
- رد Confirm نسخه قدیمی و رقابت هم‌زمان
- ثبت اتمیک accepted extraction، confirmed invoice، اتصال فایل و دو Audit event
- اعمال تشخیص Duplicate در Confirm استخراجی
- ثبت مبلغ مستقیم هزینه عمومی بدون تبدیل آن به صفر
- دریافت امن محتوای فایل و ثبت Audit دسترسی
- عدم اثر مالی Upload، پردازش، Draft، Retry و Reject

## ترتیب پیشنهادی اجرای Backend

```text
اصلاح Response version و مبلغ هزینه عمومی
→ Start/Get/List extraction و List files
→ Reject ممیزی‌شده
→ Content endpoint امن
→ قرارداد نسخه‌دار Provider fields
→ Adapter واقعی و مدل Job/Retry
→ Duplicate gate استخراج
→ Contract/Integration tests
```
