# سند اسکیما و تنظیمات دیتابیس ماژول مالی BAMBO

تاریخ استخراج/بازبینی: ۱۴۰۵/۰۶/۰۲ — 2026-08-24  
منبع: Migrationهای SQL، Repositoryهای Psycopg، PRD و Integration Kit نسخه ۱.۱

## ۱. وضعیت دیتابیس

```text
DBMS: PostgreSQL
Minimum compatibility: PostgreSQL 16
Driver: psycopg
Schema source: SQL migrations
Migration sequence: 0001 تا 0005
Tables: 15
Currency storage: IRR
Money type: numeric(18,0)
Tenant scope: organization_id + project_id
Latest backend audit: PRD Sections 8.10, 8.11, 9, 10
```

مقادیر Host، Port، Database، User، Password و SSL توسط BAMBO Host در زمان Integration تزریق می‌شوند و مقدار Production در این Repository نگهداری نشده است.

قالب مفهومی رشته اتصال:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require
```

ماژول مالی یک Finance bounded context و یک منبع حقیقت دارد. «امور مالی» و «گزارش مالی» از یک دیتابیس استفاده می‌کنند و دیتابیس گزارش‌گیری موازی وجود ندارد.

## ۲. نمای کلی ارتباط جداول

```text
finance_project_settings
 └── report_snapshots

finance_resources
 ├── estimate_lines
 │    ├── estimate_revisions
 │    ├── progress_overrides
 │    └── invoice_lines
 ├── price_versions
 ├── invoice_lines
 └── report_snapshots (pinned resource/version IDs)

progress_snapshot_refs
 ├── progress_overrides
 └── report_snapshots

invoices
 ├── invoice_lines
 ├── finance_attachments
 └── invoices (original_invoice_id برای reversal/corrective)

finance_attachments
 └── extraction_drafts

finance_import_batches

finance_audit_events

report_snapshots
 └── snapshot_payload + pinned version/reference IDs
```

تعداد جداول Schema فعلی: **۱۵ جدول**.

## ۳. تنظیمات مالی پروژه

### finance_project_settings

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه نسخه تنظیمات |
| organization_id | UUID | Scope سازمان |
| project_id | Text | Scope پروژه |
| gross_built_area | Numeric(18,4) | زیربنای ناخالص پروژه |
| currency | Text | ارز ذخیره‌سازی؛ فقط `IRR` |
| revision | Integer | شماره Revision مثبت |
| effective_from | Date | تاریخ اثر نسخه |
| reason | Text | دلیل ثبت یا اصلاح |
| created_by | UUID | کاربر ثبت‌کننده |
| created_at | Timestamptz | زمان ثبت |

ترکیب `organization_id + project_id + revision` یکتا است. نسخه‌های تنظیمات با Trigger در برابر UPDATE و DELETE محافظت می‌شوند.

## ۴. اقلام مالی

### finance_resources

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه قلم مالی |
| organization_id / project_id | UUID / Text | Scope سازمان و پروژه |
| resource_type | Text | `material`، `labor`، `equipment` یا `general_cost` |
| code | Text | کد یکتای قلم در پروژه |
| title | Text | عنوان قلم |
| base_unit | Text, Nullable | واحد پایه؛ برای هزینه عمومی اختیاری |
| dimension | Text, Nullable | بُعد فیزیکی؛ برای هزینه عمومی اختیاری |
| external_resource_id | Text, Nullable | شناسه قلم در سیستم میزبان |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان ثبت |
| deleted_at / deleted_by | Timestamptz / UUID | حذف منطقی |

کد قلم در Scope پروژه یکتا است. برای اقلام غیر از `general_cost`، واحد پایه و بُعد الزامی هستند.

## ۵. متره، برآورد و Revision

### estimate_lines

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه خط برآورد |
| organization_id / project_id | UUID / Text | Scope سازمان و پروژه |
| resource_id | UUID, FK | قلم مالی؛ FK ترکیبی به `finance_resources(organization_id, project_id, id)` |
| activity_external_id | Text, Nullable | شناسه فعالیت در سیستم زمان‌بندی میزبان. بدون فرمت اجباری؛ قرارداد پیشنهادی `ACT-{TaskUID}` است |
| assignment_external_id | Text, Nullable | شناسه تخصیص در سیستم زمان‌بندی. ادعای مشخص‌تر است و در تطبیق پیشرفت بر `activity_external_id` مقدم می‌شود |
| original_quantity | Numeric(18,4), Nullable | مقدار اولیه متره. برای `general_cost` خالی است، چون هزینه عمومی مقدار فیزیکی ندارد |
| original_unit_price_irr | Numeric(18,0), Nullable | قیمت واحد اولیه به ریال صحیح. برای `general_cost` همین ستون **مبلغ مقطوع** را نگه می‌دارد، نه قیمت واحد |
| source | Text | `progress_feed`، `excel_import` یا `manual_entry`؛ با CHECK محدود شده |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان ثبت |
| deleted_at / deleted_by | Timestamptz / UUID, Nullable | حذف منطقی؛ CHECK تضمین می‌کند هر دو با هم پر یا هر دو خالی باشند |

- `id` علاوه بر PK، در ترکیب `organization_id + project_id + id` هم یکتاست تا FKهای ترکیبی بتوانند به آن ارجاع دهند و مرز چندمستأجری در سطح دیتابیس بسته بماند.
- فیلدهای Original با Trigger قابل بازنویسی نیستند.

### estimate_revisions

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه Revision |
| organization_id / project_id | UUID / Text | Scope |
| estimate_line_id | UUID, FK | خط برآوردی که اصلاح شده |
| revision | Integer | شماره Revision؛ CHECK آن را مثبت نگه می‌دارد |
| previous_quantity | Numeric(18,4), Nullable | مقدار پیش از اصلاح |
| new_quantity | Numeric(18,4), Nullable | مقدار پس از اصلاح؛ مقدار جاری خط از آخرین Revision خوانده می‌شود، نه از `estimate_lines` |
| reason | Text | دلیل اصلاح؛ CHECK رشته خالی یا فقط‌فاصله را رد می‌کند |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان ثبت |

هر Revision یک رکورد Append-only است و ترکیب خط برآورد و شماره Revision یکتا است.

## ۶. قیمت‌ها

### price_versions

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه نسخه قیمت |
| organization_id / project_id | UUID / Text | Scope |
| resource_id | UUID, FK | قلم مالی |
| scope_kind | Text | `organization` یا `project` |
| version | Integer | شماره نسخه قیمت در Scope |
| unit_price_irr | Numeric(18,0) | قیمت واحد به ریال صحیح |
| effective_from | Date | تاریخ اثر |
| reason | Text | دلیل ثبت قیمت |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان ثبت |

تاریخچه قیمت Strict Append-only است و Trigger از UPDATE یا DELETE جلوگیری می‌کند. قیمت جاری از نسخه معتبر سازمانی یا Override پروژه Resolve می‌شود.

## ۷. تبدیل واحد

### unit_conversions

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه نسخه تبدیل |
| organization_id / project_id | UUID / Text | Scope |
| scope_kind | Text | `organization` یا `project`؛ نسخه پروژه بر نسخه سازمانی مقدم است |
| version | Integer | شماره نسخه در همان Scope؛ CHECK مثبت |
| source_unit | Text | واحد مبدأ، مثلاً `box` |
| target_unit | Text | واحد مقصد، مثلاً `each` |
| dimension | Text | بُعد فیزیکی؛ تبدیل فقط درون یک بُعد معنا دارد |
| factor | Numeric(24,8) | ضریب تبدیل؛ CHECK آن را اکیداً مثبت نگه می‌دارد. دقت ۸ رقم اعشار عمدی است تا ضرب‌های زنجیره‌ای گرد نشوند |
| effective_from | Date | تاریخ اثر |
| reason | Text | دلیل ثبت؛ CHECK رشته خالی را رد می‌کند |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان ثبت |

- تبدیل مبدأ و مقصد یکسان با CHECK ممنوع است.
- ترکیب `organization_id + project_id + scope_kind + source_unit + target_unit + dimension + version` یکتاست.
- اگر تبدیل لازم پیدا نشود، مقدار خریداری‌شده از محاسبه کنار گذاشته می‌شود و هشدار `UNIT_CONVERSION_MISSING` صادر می‌شود؛ عدد حدس زده نمی‌شود.
- تاریخچه تبدیل واحد Append-only است.

## ۸. پیشرفت پروژه

### progress_snapshot_refs

این جدول فقط مرجع Snapshot پیشرفت سیستم میزبان را نگهداری می‌کند و داده میزبان را بازنویسی نمی‌کند.

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه ردیف مرجع در سمت Finance |
| organization_id / project_id | UUID / Text | Scope |
| progress_snapshot_id | UUID | شناسه Snapshot در سیستم میزبان؛ در Scope پروژه یکتاست. این همان شناسه‌ای است که API با آن Feed را از میزبان می‌خواهد |
| source_file_version_id | UUID | نسخه فایل زمان‌بندی مبدأ در سیستم میزبان |
| source_file_name_safe | Text | نام فایل مبدأ، پاک‌سازی‌شده برای نمایش |
| reporting_date | Date | تاریخ گزارش‌گیری که این Snapshot به آن تعلق دارد |
| snapshot_status | Text | ⚠️ هیچ CHECK ندارد و متن آزاد است، ولی DTO مقدار `ready` یا `superseded` اعلام می‌کند. اگر Production مقدار سومی داشته باشد پاسخ API با خطای اعتبارسنجی می‌شکند — بند ۴ سند `PRODUCTION_MSP_AUDIT_FA.md` |
| imported_by | UUID | کاربر واردکننده |
| imported_at | Timestamptz | زمان ورود Snapshot در سیستم میزبان |
| created_at | Timestamptz | زمان ثبت ردیف مرجع در Finance |
| source_type | Text, Nullable | ابزار مبدأ زمان‌بندی: `microsoft_project`، `primavera`، `manual` یا `other`؛ با CHECK محدود شده که `NULL` را هم می‌پذیرد. در Migration 0005 اضافه شد، **بدون DEFAULT** — ردیف‌های پیش از آن `NULL` می‌مانند، و `NULL` یعنی «ثبت نشده»، نه «نامعلوم است پس حدس بزن». پسوند فایل شاهدِ ابزار نیست |

> **نسخه‌بندی Snapshot ستون ندارد و لازم هم ندارد.** جدول با Trigger فقط-افزودنی است، پس ترتیب ردیف‌ها خودش تاریخچه است: `version` و `isLatest` در پاسخ API از روی جایگاه ردیف در تاریخچه همان پروژه محاسبه می‌شوند. نسخه ۱ همیشه قدیمی‌ترین می‌ماند، چون هیچ ورود بعدی نمی‌تواند خودش را جلوتر درج کند.

> تریگر تغییرناپذیری این جدول هر `UPDATE` را رد می‌کند، پس `source_type` فقط در لحظه `INSERT` نوشتنی است و هیچ Backfillی روی ردیف‌های موجود ممکن نیست.

### progress_overrides

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه Override |
| organization_id / project_id | UUID / Text | Scope |
| estimate_line_id | UUID, FK | خط برآوردی که مقدار اجرایش اصلاح شده |
| progress_snapshot_ref_id | UUID, FK | Snapshot پیشرفتی که Override نسبت به آن ثبت شده |
| computed_value | Numeric(18,4) | مقداری که سیستم خودش محاسبه کرده بود. **سمت سرور محاسبه می‌شود** و از Client پذیرفته نمی‌شود، وگرنه سابقه اصلاح قابل اتکا نبود |
| override_value | Numeric(18,4) | مقداری که کاربر جایگزین کرده |
| reason | Text | دلیل اصلاح؛ CHECK رشته خالی یا فقط‌فاصله را رد می‌کند |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان ثبت |

Override پیشرفت همراه مقدار محاسبه‌شده، مقدار جایگزین، دلیل و actor به‌صورت Append-only ثبت می‌شود. نگهداری هم‌زمان مقدار محاسبه‌شده و مقدار جایگزین عمدی است: بدون آن معلوم نمی‌شد اصلاح چقدر بوده.

## ۹. فاکتورها

### invoices

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه فاکتور |
| organization_id / project_id | UUID / Text | Scope |
| invoice_number | Text, Nullable | شماره فاکتور فروشنده؛ اختیاری، چون هر رسیدی شماره ندارد |
| invoice_date | Date | تاریخ فاکتور. گزارش دوره‌ای بر همین ستون گروه‌بندی می‌شود، نه بر `created_at` |
| vendor_name | Text | نام فروشنده |
| description | Text, Nullable | شرح آزاد |
| source | Text | `manual`، `image`، `voice`، `corrective` یا `reversal`؛ با CHECK محدود شده |
| status | Text | `draft`، `awaitingConfirmation`، `confirmed`، `voided` یا `corrected`؛ با CHECK محدود شده |
| discount_irr | Numeric(18,0), default 0 | تخفیف کل فاکتور؛ CHECK نامنفی |
| tax_irr | Numeric(18,0), default 0 | مالیات کل؛ CHECK نامنفی |
| shipping_irr | Numeric(18,0), default 0 | حمل کل؛ CHECK نامنفی |
| other_costs_irr | Numeric(18,0), default 0 | سایر هزینه‌های کل؛ CHECK نامنفی |
| final_amount_irr | Numeric(18,0), Nullable | مبلغ نهایی؛ تا پیش از تأیید خالی است |
| financial_effect_sign | Smallint, default 1 | `1` برای فاکتور عادی و `-1` برای برگشتی؛ CHECK فقط همین دو مقدار را می‌پذیرد. تمام جمع‌های مالی در همین علامت ضرب می‌شوند، پس برگشت با درج ثبت می‌شود نه با حذف |
| idempotency_key | Text, Nullable | کلید Idempotency ثبت؛ در Scope پروژه یکتاست |
| source_file_sha256 | Text, Nullable | چکیده SHA-256 فایل مبدأ، برای تشخیص بارگذاری تکراری. `NULL` یعنی فاکتور از فایلی نیامده — مثلاً ورود دستی |
| original_invoice_id | UUID, FK, Nullable | فاکتور اصلی، برای برگشتی و اصلاحی؛ FK به همین جدول |
| version | Integer, default 1 | نسخه فاکتور؛ CHECK مثبت |
| submitted_by | UUID | ثبت‌کننده |
| confirmed_by | UUID, Nullable | تأییدکننده |
| confirmed_at | Timestamptz, Nullable | زمان تأیید |
| created_at / updated_at | Timestamptz | زمان ثبت و آخرین تغییر |
| confirmation_idempotency_key | Text, Nullable | کلید Idempotency تأیید؛ با Index جزئی یکتا محافظت می‌شود |

> یک CHECK ترکیبی تضمین می‌کند فاکتور `confirmed` حتماً `confirmed_by` و `confirmed_at` دارد: وضعیت تأییدشده بدون رد ممیزی ممکن نیست.

وضعیت‌ها شامل `draft`، `awaitingConfirmation`، `confirmed`، `voided` و `corrected` هستند. Source شامل ورود دستی، تصویر، صوت، corrective و reversal است.

قواعد اصلی:

- `idempotency_key` در Scope پروژه یکتا است.
- `confirmation_idempotency_key` با Index جزئی یکتا محافظت می‌شود.
- برای هر فاکتور اصلی فقط یک reversal مجاز است.
- فاکتور تأییدشده با Trigger در برابر تغییر مستقیم محافظت می‌شود.

### invoice_lines

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه خط فاکتور |
| organization_id / project_id | UUID / Text | Scope |
| invoice_id | UUID, FK | فاکتور دربردارنده |
| estimate_line_id | UUID, FK, Nullable | خط برآورد متناظر. خالی بودنش مجاز است: خرید بدون خط برآورد مشخص، در سطح قلم مالی تجمیع می‌شود |
| resource_id | UUID, FK | قلم مالی خریداری‌شده |
| quantity | Numeric(18,4), Nullable | مقدار خریداری‌شده؛ برای هزینه عمومی خالی است |
| unit | Text, Nullable | واحد خرید. اگر با `base_unit` قلم فرق کند، تبدیل واحد لازم می‌شود |
| unit_price_snapshot_irr | Numeric(18,0), Nullable | قیمت واحد در لحظه ثبت. Snapshot است تا تغییر بعدی قیمت، فاکتور گذشته را بازنویسی نکند |
| raw_amount_irr | Numeric(18,0) | مبلغ خط پیش از سرشکن‌کردن تعدیلات |
| allocated_discount_irr | Numeric(18,0), default 0 | سهم این خط از تخفیف کل فاکتور |
| allocated_tax_irr | Numeric(18,0), default 0 | سهم این خط از مالیات |
| allocated_shipping_irr | Numeric(18,0), default 0 | سهم این خط از حمل |
| allocated_other_costs_irr | Numeric(18,0), default 0 | سهم این خط از سایر هزینه‌ها |
| final_line_amount_irr | Numeric(18,0) | مبلغ نهایی خط پس از تعدیلات. **تمام شاخص‌های هزینه واقعی از همین ستون جمع می‌شوند** |
| price_version_id | UUID, FK, Nullable | نسخه قیمتی که Snapshot از آن گرفته شده |
| description | Text, Nullable | شرح خط |
| created_at | Timestamptz | زمان ثبت |

مبلغ خط، Snapshot قیمت و سهم تعدیلات در زمان ثبت نگهداری می‌شوند. هزینه عمومی می‌تواند بدون مقدار فیزیکی و با مبلغ مستقیم ثبت شود.

سرشکن‌کردن تعدیلات در زمان ثبت انجام و ذخیره می‌شود، نه در زمان خواندن: گزارشی که ماه‌ها بعد گرفته می‌شود همان اعدادی را می‌بیند که آن روز ثبت شده‌اند.

### قاعده Hash فایل مبدأ

Hash همیشه **سمت سرور** از بایت‌های دریافتی محاسبه می‌شود و هرگز از Client پذیرفته نمی‌شود؛ در غیر این صورت یک Client می‌توانست با ارسال چکیده دلخواه، تشخیص تکراری را دور بزند یا وجود فایلی را در سازمان دیگر استنتاج کند. مقایسه نیز درون همان `organization_id` و `project_id` انجام می‌شود.

## ۱۰. فایل‌های مالی

### finance_attachments

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه فایل |
| organization_id / project_id | UUID / Text | Scope |
| invoice_id | UUID, FK, Nullable | فاکتور مرتبط. خالی بودنش مجاز است، چون تصویر می‌تواند پیش از ساخته‌شدن فاکتور بارگذاری شود |
| logical_type | Text | `invoice_image` یا `invoice_voice`؛ با CHECK محدود شده |
| original_name_safe | Text | نام اصلی فایل، پاک‌سازی‌شده برای نمایش |
| stored_name | Text | نامی که فایل با آن در Storage ذخیره شده |
| mime_type | Text | نوع MIME تأییدشده |
| size_bytes | Bigint | اندازه فایل؛ CHECK آن را اکیداً مثبت نگه می‌دارد |
| sha256 | Text | چکیده محتوا؛ CHECK طول ۶۴ کاراکتر را الزام می‌کند. در Scope پروژه **یکتا** است و همین Unique است که بارگذاری تکراری را تشخیص می‌دهد |
| storage_key | Text | کلید فایل در Storage میزبان |
| processing_status | Text | `uploaded`، `processing`، `ready` یا `failed`؛ با CHECK محدود شده |
| uploaded_by / uploaded_at | UUID / Timestamptz | بارگذارنده و زمان بارگذاری |
| deleted_at / deleted_by | Timestamptz / UUID, Nullable | حذف منطقی؛ CHECK تضمین می‌کند هر دو با هم پر یا هر دو خالی باشند |

قواعد فایل:

- `logical_type`: تصویر یا صوت فاکتور
- وضعیت پردازش: `uploaded → processing → ready` و مسیر `failed`
- تصویر: JPEG/PNG/WebP تا ۱۰ MiB
- صوت: MP3/M4A/WAV/OGG تا ۲۵ MiB
- Hash فایل در Scope پروژه یکتا است.
- فایل باینری در PostgreSQL قرار نمی‌گیرد؛ فقط Metadata و `storage_key` ذخیره می‌شود.
- Storage واقعی از طریق File Adapter میزبان تأمین می‌شود.

## ۱۱. استخراج تصویر و صوت

### extraction_drafts

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه Draft استخراج |
| organization_id / project_id | UUID / Text | Scope |
| attachment_id | UUID, FK | فایلی که از آن استخراج شده |
| version | Integer | نسخه استخراج برای همان فایل؛ CHECK مثبت. ترکیب فایل و نسخه یکتاست، پس استخراج دوباره نسخه قبلی را پاک نمی‌کند |
| review_status | Text | `awaitingReview`، `accepted` یا `rejected`؛ با CHECK محدود شده |
| provider_adapter | Text | نام Adapter استخراج‌کننده؛ ثبت می‌شود تا معلوم باشد کدام سرویس چه چیزی گفته |
| extracted_fields | JSONB | آنچه Adapter خوانده است |
| confirmed_fields | JSONB, Nullable | آنچه انسان تأیید یا اصلاح کرده؛ تا پیش از بازبینی خالی است |
| financial_effect_irr | Numeric(18,0), default 0 | **CHECK آن را به صفر قفل کرده است.** یک Draft هرگز اثر مالی ندارد؛ عدد استخراج‌شده تا وقتی انسان فاکتور نسازد در هیچ شاخصی دیده نمی‌شود |
| submitted_by | UUID | ثبت‌کننده |
| confirmed_by | UUID, Nullable | تأییدکننده |
| confirmed_at | Timestamptz, Nullable | زمان تأیید |
| created_at / updated_at | Timestamptz | زمان ثبت و آخرین تغییر |

- `extracted_fields` و `confirmed_fields` به‌صورت JSONB ذخیره می‌شوند.
- Review status شامل `awaitingReview`، `accepted` و `rejected` است.
- اثر مالی Draft همیشه صفر است.
- تنها تأیید انسانی می‌تواند فاکتور مؤثر ایجاد کند.

## ۱۲. گزارش مالی

### report_snapshots

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه گزارش صادرشده |
| organization_id / project_id | UUID / Text | Scope |
| reporting_date | Date | تاریخ گزارش‌گیری |
| progress_snapshot_ref_id | UUID, FK | Snapshot پیشرفتی که گزارش بر آن استوار است |
| finance_settings_id | UUID, FK | نسخه تنظیمات مالی در لحظه صدور |
| resource_version_ids | JSONB | شناسه نسخه اقلام مالی Pin‌شده |
| estimate_revision_ids | JSONB | شناسه Revisionهای برآورد Pin‌شده |
| price_version_ids | JSONB | شناسه نسخه‌های قیمت Pin‌شده |
| unit_conversion_ids | JSONB | شناسه نسخه‌های تبدیل واحد Pin‌شده |
| invoice_ids | JSONB | شناسه فاکتورهای لحاظ‌شده |
| calculated_metrics | JSONB | شاخص‌های محاسبه‌شده، به‌صورت رشته‌های عددی دقیق |
| snapshot_payload | JSONB | **کل گزارش در لحظه صدور**، شامل ورودی‌ها، Breakdown، انحرافات و هشدارها. خروجی CSV و XLSX از همین Payload خوانده می‌شود، نه از محاسبه دوباره — به همین دلیل گزارش قدیمی هرگز با تغییر کد عوض نمی‌شود |
| issued_by / issued_at | UUID / Timestamptz | صادرکننده و زمان صدور |

> Pin‌کردن شناسه نسخه‌ها در کنار Payload، دو کار متفاوت می‌کند: Payload می‌گوید گزارش **چه چیزی نشان داد**، و شناسه‌های Pin‌شده می‌گویند **از کدام ردیف‌ها آمد**. اولی برای خواننده است و دومی برای ممیزی.

گزارش Live از داده‌های جاری محاسبه می‌شود و جدول جداگانه ندارد. گزارش رسمی صادرشده در `report_snapshots` ثبت می‌شود.

Snapshot شامل نسخه تنظیمات، Revisionهای برآورد، قیمت‌ها، تبدیل‌ها، فاکتورها، Snapshot پیشرفت و Payload کامل زمان صدور است. Trigger مانع UPDATE یا DELETE گزارش صادرشده می‌شود.

## ۱۳. رویدادهای ممیزی

### finance_audit_events

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه رویداد |
| organization_id / project_id | UUID / Text | Scope |
| actor_user_id | UUID | کاربری که عمل را انجام داده |
| action | Text | نوع عمل ثبت‌شده |
| entity_type | Text | نوع موجودیت هدف، مثلاً فاکتور یا خط برآورد |
| entity_id | UUID | شناسه موجودیت هدف |
| reason | Text, Nullable | دلیل، وقتی عمل دلیل می‌طلبد |
| before_values | JSONB, Nullable | وضعیت پیش از تغییر |
| after_values | JSONB, Nullable | وضعیت پس از تغییر |
| occurred_at | Timestamptz | زمان وقوع؛ مرتب‌سازی پایدار بر `occurred_at DESC, id DESC` است |

مقادیر قبل و بعد به‌صورت JSONB ثبت می‌شوند. Audit میان امور مالی و گزارش مالی مشترک و Append-only است.

API مشاهده Audit از همین جدول و با Scope دوگانه خوانده می‌شود. در سطح Repository، مرتب‌سازی پایدار `occurred_at DESC, id DESC` و صفحه‌بندی واقعی دیتابیس با `LIMIT/OFFSET` اعمال می‌شود؛ بنابراین مشاهده رویدادها باعث بارگذاری کامل تاریخچه در حافظه برنامه نمی‌شود.

## ۱۴. ورود گروهی اطلاعات

### finance_import_batches

| ستون | نوع | توضیح |
|---|---|---|
| id | UUID, PK | شناسه Batch ورود گروهی |
| organization_id / project_id | UUID / Text | Scope |
| import_kind | Text | `estimate` یا `prices`؛ با CHECK محدود شده |
| currency_unit | Text, Nullable | `IRR` یا `TOMAN`؛ با CHECK محدود شده. تومان فقط در ورودی پذیرفته می‌شود و پیش از ذخیره به ریال تبدیل می‌گردد — در دیتابیس هیچ مبلغی به تومان نگهداری نمی‌شود |
| file_sha256 | Text | چکیده فایل ورودی؛ CHECK طول ۶۴ کاراکتر را الزام می‌کند |
| normalized_rows | JSONB | ردیف‌های نرمال‌شده حاصل Preview |
| validation_errors | JSONB | خطاهای اعتبارسنجی هر ردیف |
| status | Text | `previewed` یا `committed`؛ با CHECK محدود شده |
| created_by / created_at | UUID / Timestamptz | ثبت‌کننده و زمان Preview |
| committed_at | Timestamptz, Nullable | زمان Commit؛ یک CHECK ترکیبی تضمین می‌کند این ستون **دقیقاً وقتی** پر است که `status` برابر `committed` باشد |

- `import_kind`: متره یا قیمت
- `status`: `previewed` یا `committed`
- ردیف‌های نرمال‌شده و خطاها در JSONB ذخیره می‌شوند.
- Commit تنها پس از Preview معتبر انجام می‌شود.

## ۱۵. Indexها

برای تمام جداول مالی Index مبتنی بر `organization_id + project_id` وجود دارد. Indexهای اصلی:

- تنظیمات براساس تاریخ اثر
- منابع براساس نوع قلم
- خطوط متره براساس قلم
- Revisionها براساس خط متره
- قیمت‌ها براساس قلم و تاریخ اثر
- تبدیل واحد براساس واحدها و تاریخ اثر
- پیشرفت براساس تاریخ گزارش
- فاکتورها براساس تاریخ و وضعیت
- پیوست‌ها براساس فاکتور
- Extraction براساس فایل و نسخه
- Report Snapshot براساس تاریخ گزارش
- Audit براساس زمان رخداد
- Import براساس وضعیت و زمان

Indexهای یکتای تکمیلی:

- `ux_invoices_confirmation_idempotency_scope`
- `ux_invoices_one_reversal_per_original`

## ۱۶. Immutability و Triggerها

Triggerهای زیر از بازنویسی تاریخچه جلوگیری می‌کنند:

```text
finance_project_settings_immutable
estimate_revisions_immutable
price_versions_immutable
unit_conversions_immutable
progress_snapshot_refs_immutable
progress_overrides_immutable
report_snapshots_immutable
finance_audit_events_immutable
estimate_original_fields_immutable
confirmed_invoice_immutable
```

این Triggerها مانع UPDATE/DELETE رکوردهای تاریخی یا فاکتورهای تأییدشده می‌شوند.

## ۱۷. Scope و امنیت داده

هر Query مالی به‌صورت هم‌زمان با موارد زیر محدود می‌شود:

```text
organization_id
project_id
```

داشتن UUID یک رکورد برای دسترسی کافی نیست. چهار Gate امنیتی عبارت‌اند از:

1. Authentication
2. Organization membership
3. Project membership
4. Finance permission

مجوزهای اصلی:

```text
finance.view
finance.edit
finance_report.view
finance_report.export
finance_report.issue  # Host-dependent
```

کاربر Report-only به فاکتور خام، قیمت عملیاتی، متره، فایل، Extraction یا Audit داخلی دسترسی ندارد.

## ۱۸. تنظیمات Database Engine

Repository فقط Driver و قرارداد اتصال را مشخص می‌کند و تنظیمات Production به میزبان واگذار شده است:

```text
Driver: psycopg
Transaction support: required
Row mapping: psycopg.rows.dict_row
JSON binding: psycopg.types.json.Jsonb
Timezone fields: timestamptz / UTC
Financial arithmetic: Decimal
Autocommit policy: Host configuration
Connection pool: Host configuration
SSL mode: Host configuration
```

این Repository مقدار قطعی برای Pool Size، Host، Port، Password یا Secret Manager تعریف نمی‌کند؛ بنابراین چنین مقادیری نباید براساس حدس در سند Production درج شوند.

## ۱۹. تنظیمات Development

نمونه مفهومی و غیرعملیاتی:

```env
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/DATABASE
APP_ENV=development
```

نام دیتابیس، User، Password و Port نهایی باید توسط محیط میزبان تعیین شوند. Secret نباید داخل Git ذخیره شود.

## ۲۰. تنظیمات Production

نمونه مفهومی:

```env
APP_ENV=production
DATABASE_URL=postgresql://RUNTIME_USER@DB_HOST:5432/DATABASE?sslmode=require
```

الزامات Production:

- Credential از Secret Manager یا سازوکار میزبان دریافت شود.
- ارتباط دیتابیس در شبکه خصوصی انجام شود.
- Backup معتبر پیش از Migration وجود داشته باشد.
- Migrationها پیش از شروع نسخه جدید اجرا و بررسی شوند.
- Restore rehearsal مطابق Runbook انجام شود.
- تنظیمات Pool، Timeout و SSL توسط BAMBO Host تعیین شوند.

## ۲۱. Migrationها

Migrationها Raw SQL هستند و به‌ترتیب زیر اجرا می‌شوند:

```text
0001_finance_core.up.sql
0002_invoice_confirmation.up.sql
0003_invoice_linked_documents.up.sql
0004_report_snapshot_payload.up.sql
0005_progress_snapshot_source_type.up.sql
```

کار هر Migration:

| Migration | توضیح |
|---|---|
| `0001_finance_core` | ایجاد ۱۵ جدول، FKها، Constraintها، Indexهای Scope و Triggerها |
| `0002_invoice_confirmation` | افزودن Idempotency تأیید فاکتور و Unique Index |
| `0003_invoice_linked_documents` | تضمین یک Reversal برای هر فاکتور اصلی |
| `0004_report_snapshot_payload` | افزودن Payload کامل و شناسه نسخه‌های Pin‌شده گزارش |
| `0005_progress_snapshot_source_type` | افزودن ستون `source_type` به `progress_snapshot_refs`؛ فقط تغییر Catalog، بدون DEFAULT و بدون بازنویسی هیچ ردیفی، تا تریگر تغییرناپذیری فعال نشود |

برای هر Migration فایل Down متناظر وجود دارد. Down migration جایگزین Backup/Restore نیست.

## ۲۲. وضعیت سازگاری پس از آخرین بازبینی

آخرین بازبینی Backend براساس PRD و Integration Kit نسخه ۱.۱ انجام شده و نتیجه‌های مرتبط با دیتابیس به شرح زیر است:

| حوزه | وضعیت | توضیح |
|---|---|---|
| Schema پایه Integration Kit | حفظ‌شده | Migration جدید برای مراحل اخیر لازم نبود. |
| Audit History | حفظ‌شده | جدول `finance_audit_events` append-only و scoped باقی مانده است. |
| Audit List Performance | به‌روز شده | خواندن Audit در API با pagination دیتابیس انجام می‌شود. |
| Report Snapshot | حفظ‌شده | `snapshot_payload` و شناسه‌های Pin‌شده immutable هستند. |
| Money/Decimal | تأیید شده | پول با `numeric(18,0)` و محاسبات Backend با `Decimal` انجام می‌شود. |
| Rounding | تأیید شده | گردکردن مبلغ خط با `ROUND_HALF_UP` و تست 1000-line پوشش داده شده است. |
| Frontend/API Contract | سازگار | تغییرات اخیر additive بوده و قرارداد camelCase حفظ شده است. |

## ۲۳. فایل‌های مرجع

- `backend/migrations/0001_finance_core.up.sql`
- `backend/migrations/0002_invoice_confirmation.up.sql`
- `backend/migrations/0003_invoice_linked_documents.up.sql`
- `backend/migrations/0004_report_snapshot_payload.up.sql`
- `backend/app/finance/repositories/`
- `backend/app/finance/domain/`
- `backend/app/finance/schemas/`
- `backend/docs/PRODUCTION_MIGRATION_REVIEW_FA.md`
- `backend/docs/RECOVERY_RUNBOOK_FA.md`
- `backend/docs/PERMISSION_MATRIX_FA.md`
- `Sources/BAMBO_FINANCE_MVP_PRD_FA_v1.1.html`
- `Sources/BAMBO_FINANCE_INTEGRATION_KIT_v1.1.zip`

## ۲۴. نکات مهم نگهداری داده

- مبالغ و قیمت‌ها به ریال صحیح و بدون Float ذخیره می‌شوند.
- زمان‌ها با `timestamptz` و UTC مدیریت می‌شوند؛ نمایش شمسی مسئولیت Frontend است.
- فایل باینری در Storage قرار می‌گیرد و PostgreSQL فقط Metadata آن را نگهداری می‌کند.
- تاریخچه قیمت، Revision، Override، Snapshot و Audit بازنویسی نمی‌شود.
- Draft فاکتور و Extraction اثر مالی ندارند.
- فقط فاکتورهای مؤثر در گزارش مالی محاسبه می‌شوند.
- Live Report از داده جاری استفاده می‌کند؛ Snapshot صادرشده ثابت باقی می‌ماند.
- Foreign Keyها و کلیدهای ترکیبی Scope مانع اتصال داده بین پروژه‌ها می‌شوند.
- Permission Seed و تنظیمات اتصال Production مسئولیت BAMBO Host است.
- امور مالی و گزارش مالی یک منبع حقیقت و یک موتور محاسبه مشترک دارند.
