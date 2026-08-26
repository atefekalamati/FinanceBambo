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

### راهنمای ستون «نقش»

در جدول‌های زیر، ستون **نقش** می‌گوید هر ستون دیتابیس **برای چه ساخته شده**، جدا از اینکه
چه چیزی در آن است. دلیلش یک بار اینجا نوشته شده تا در ۲۰۴ ردیف تکرار نشود:

| نقش | یعنی | اگر نبود چه می‌شد |
|---|---|---|
| هویت | کلید اصلی ردیف | ردیف قابل ارجاع نبود |
| Scope | مرز سازمان و پروژه | داده یک مستأجر در گزارش مستأجر دیگر دیده می‌شد |
| پیوند | ارجاع به جدول مالی دیگر | رابطه بین برآورد، فاکتور و پیشرفت گم می‌شد |
| یکپارچه‌سازی | شناسه یا نام متعلق به **سیستم میزبان** | Finance نمی‌توانست داده خودش را به زمان‌بندی و فایل میزبان وصل کند؛ این ستون‌ها را Finance نمی‌سازد، فقط نگه می‌دارد |
| مبنای زمانی | تاریخی که تعیین می‌کند کدام نسخه معتبر است | گزارش تاریخ گذشته، قیمت و برآورد امروز را می‌دید |
| داده مالی | عددی که مستقیم وارد محاسبه می‌شود | شاخصی قابل محاسبه نبود |
| طبقه‌بندی | واژگان بسته و کنترل‌شده | مقدار آزاد وارد می‌شد و منطق شرطی بی‌صدا می‌شکست |
| ممیزی | چه کسی، کِی، چرا | تغییر مالی بدون رد قابل پیگیری می‌ماند |
| یکپارچگی | فقط برای جلوگیری از خرابی: تکرار، حذف، بازنویسی | ثبت دوباره یک فاکتور یا فایل تشخیص داده نمی‌شد |
| تثبیت | وضعیت منجمدشده در لحظه ثبت یا صدور | گزارش قدیمی با تغییر قیمت یا کد امروز بازنویسی می‌شد |
| توصیفی | متنی که انسان می‌خواند | ردیف برای کاربر قابل تشخیص نبود |


### finance_project_settings

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه نسخه تنظیمات |
| organization_id | UUID | Scope | Scope سازمان |
| project_id | Text | Scope | Scope پروژه |
| gross_built_area | Numeric(18,4) | داده مالی | زیربنای ناخالص پروژه |
| currency | Text | طبقه‌بندی | ارز ذخیره‌سازی؛ فقط `IRR` |
| revision | Integer | یکپارچگی | شماره Revision مثبت |
| effective_from | Date | مبنای زمانی | تاریخ اثر نسخه |
| reason | Text | ممیزی | دلیل ثبت یا اصلاح |
| created_by | UUID | ممیزی | کاربر ثبت‌کننده |
| created_at | Timestamptz | ممیزی | زمان ثبت |

ترکیب `organization_id + project_id + revision` یکتا است. نسخه‌های تنظیمات با Trigger در برابر UPDATE و DELETE محافظت می‌شوند.

## ۴. اقلام مالی

### finance_resources

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه قلم مالی |
| organization_id / project_id | UUID / Text | Scope | Scope سازمان و پروژه |
| resource_type | Text | طبقه‌بندی | `material`، `labor`، `equipment` یا `general_cost` |
| code | Text | توصیفی | کد یکتای قلم در پروژه |
| title | Text | توصیفی | عنوان قلم |
| base_unit | Text, Nullable | طبقه‌بندی | واحد پایه؛ برای هزینه عمومی اختیاری |
| dimension | Text, Nullable | طبقه‌بندی | بُعد فیزیکی؛ برای هزینه عمومی اختیاری |
| external_resource_id | Text, Nullable | یکپارچه‌سازی | شناسه قلم در سیستم میزبان |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان ثبت |
| deleted_at / deleted_by | Timestamptz / UUID | یکپارچگی | حذف منطقی |

کد قلم در Scope پروژه یکتا است. برای اقلام غیر از `general_cost`، واحد پایه و بُعد الزامی هستند.

## ۵. متره، برآورد و Revision

### estimate_lines

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه خط برآورد |
| organization_id / project_id | UUID / Text | Scope | Scope سازمان و پروژه |
| resource_id | UUID, FK | پیوند | قلم مالی؛ FK ترکیبی به `finance_resources(organization_id, project_id, id)` |
| activity_external_id | Text, Nullable | یکپارچه‌سازی | شناسه فعالیت در سیستم زمان‌بندی میزبان. بدون فرمت اجباری؛ قرارداد پیشنهادی `ACT-{TaskUID}` است |
| assignment_external_id | Text, Nullable | یکپارچه‌سازی | شناسه تخصیص در سیستم زمان‌بندی. ادعای مشخص‌تر است و در تطبیق پیشرفت بر `activity_external_id` مقدم می‌شود |
| original_quantity | Numeric(18,4), Nullable | داده مالی | مقدار اولیه متره. برای `general_cost` خالی است، چون هزینه عمومی مقدار فیزیکی ندارد |
| original_unit_price_irr | Numeric(18,0), Nullable | داده مالی | قیمت واحد اولیه به ریال صحیح. برای `general_cost` همین ستون **مبلغ مقطوع** را نگه می‌دارد، نه قیمت واحد |
| source | Text | طبقه‌بندی | `progress_feed`، `excel_import` یا `manual_entry`؛ با CHECK محدود شده |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان ثبت |
| deleted_at / deleted_by | Timestamptz / UUID, Nullable | یکپارچگی | حذف منطقی؛ CHECK تضمین می‌کند هر دو با هم پر یا هر دو خالی باشند |

- `id` علاوه بر PK، در ترکیب `organization_id + project_id + id` هم یکتاست تا FKهای ترکیبی بتوانند به آن ارجاع دهند و مرز چندمستأجری در سطح دیتابیس بسته بماند.
- فیلدهای Original با Trigger قابل بازنویسی نیستند.

### estimate_revisions

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه Revision |
| organization_id / project_id | UUID / Text | Scope | Scope |
| estimate_line_id | UUID, FK | پیوند | خط برآوردی که اصلاح شده |
| revision | Integer | یکپارچگی | شماره Revision؛ CHECK آن را مثبت نگه می‌دارد |
| previous_quantity | Numeric(18,4), Nullable | داده مالی | مقدار پیش از اصلاح |
| new_quantity | Numeric(18,4), Nullable | داده مالی | مقدار پس از اصلاح؛ مقدار جاری خط از آخرین Revision خوانده می‌شود، نه از `estimate_lines` |
| reason | Text | ممیزی | دلیل اصلاح؛ CHECK رشته خالی یا فقط‌فاصله را رد می‌کند |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان ثبت |

هر Revision یک رکورد Append-only است و ترکیب خط برآورد و شماره Revision یکتا است.

## ۶. قیمت‌ها

### price_versions

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه نسخه قیمت |
| organization_id / project_id | UUID / Text | Scope | Scope |
| resource_id | UUID, FK | پیوند | قلم مالی |
| scope_kind | Text | طبقه‌بندی | `organization` یا `project` |
| version | Integer | یکپارچگی | شماره نسخه قیمت در Scope |
| unit_price_irr | Numeric(18,0) | داده مالی | قیمت واحد به ریال صحیح |
| effective_from | Date | مبنای زمانی | تاریخ اثر |
| reason | Text | ممیزی | دلیل ثبت قیمت |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان ثبت |

تاریخچه قیمت Strict Append-only است و Trigger از UPDATE یا DELETE جلوگیری می‌کند. قیمت جاری از نسخه معتبر سازمانی یا Override پروژه Resolve می‌شود.

## ۷. تبدیل واحد

### unit_conversions

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه نسخه تبدیل |
| organization_id / project_id | UUID / Text | Scope | Scope |
| scope_kind | Text | طبقه‌بندی | `organization` یا `project`؛ نسخه پروژه بر نسخه سازمانی مقدم است |
| version | Integer | یکپارچگی | شماره نسخه در همان Scope؛ CHECK مثبت |
| source_unit | Text | طبقه‌بندی | واحد مبدأ، مثلاً `box` |
| target_unit | Text | طبقه‌بندی | واحد مقصد، مثلاً `each` |
| dimension | Text | طبقه‌بندی | بُعد فیزیکی؛ تبدیل فقط درون یک بُعد معنا دارد |
| factor | Numeric(24,8) | داده مالی | ضریب تبدیل؛ CHECK آن را اکیداً مثبت نگه می‌دارد. دقت ۸ رقم اعشار عمدی است تا ضرب‌های زنجیره‌ای گرد نشوند |
| effective_from | Date | مبنای زمانی | تاریخ اثر |
| reason | Text | ممیزی | دلیل ثبت؛ CHECK رشته خالی را رد می‌کند |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان ثبت |

- تبدیل مبدأ و مقصد یکسان با CHECK ممنوع است.
- ترکیب `organization_id + project_id + scope_kind + source_unit + target_unit + dimension + version` یکتاست.
- اگر تبدیل لازم پیدا نشود، مقدار خریداری‌شده از محاسبه کنار گذاشته می‌شود و هشدار `UNIT_CONVERSION_MISSING` صادر می‌شود؛ عدد حدس زده نمی‌شود.
- تاریخچه تبدیل واحد Append-only است.

## ۸. پیشرفت پروژه

### progress_snapshot_refs

این جدول فقط مرجع Snapshot پیشرفت سیستم میزبان را نگهداری می‌کند و داده میزبان را بازنویسی نمی‌کند.

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه ردیف مرجع در سمت Finance |
| organization_id / project_id | UUID / Text | Scope | Scope |
| progress_snapshot_id | UUID | یکپارچه‌سازی | شناسه Snapshot در سیستم میزبان؛ در Scope پروژه یکتاست. این همان شناسه‌ای است که API با آن Feed را از میزبان می‌خواهد |
| source_file_version_id | UUID | یکپارچه‌سازی | نسخه فایل زمان‌بندی مبدأ در سیستم میزبان |
| source_file_name_safe | Text | یکپارچه‌سازی | نام فایل مبدأ، پاک‌سازی‌شده برای نمایش |
| reporting_date | Date | مبنای زمانی | تاریخ گزارش‌گیری که این Snapshot به آن تعلق دارد |
| snapshot_status | Text | طبقه‌بندی | ⚠️ هیچ CHECK ندارد و متن آزاد است، ولی DTO مقدار `ready` یا `superseded` اعلام می‌کند. اگر Production مقدار سومی داشته باشد پاسخ API با خطای اعتبارسنجی می‌شکند — بند ۴ سند `PRODUCTION_MSP_AUDIT_FA.md` |
| imported_by | UUID | ممیزی | کاربر واردکننده |
| imported_at | Timestamptz | ممیزی | زمان ورود Snapshot در سیستم میزبان |
| created_at | Timestamptz | ممیزی | زمان ثبت ردیف مرجع در Finance |
| host_snapshot_id | Bigint, Nullable | یکپارچه‌سازی | شناسه واقعی Snapshot در Core (`msp_snapshots.id`). **Core مالک این مقدار است؛ Finance فقط نگهش می‌دارد.** `NULL` یعنی این ردیف هرگز به Snapshotی در Core وصل نبوده — که درباره هر ردیف پیش از این یکپارچه‌سازی درست است. هیچ FK فیزیکی به Core ندارد؛ اعتبارسنجی در لایه Adapter انجام می‌شود |
| host_file_version_id | Bigint, Nullable | یکپارچه‌سازی | شناسه واقعی نسخه فایل زمان‌بندی در Core (`msp_file_versions.id`) |
| source_type | Text, Nullable | یکپارچه‌سازی | ابزار مبدأ زمان‌بندی: `microsoft_project`، `primavera`، `manual` یا `other`؛ با CHECK محدود شده که `NULL` را هم می‌پذیرد. در Migration 0005 اضافه شد، **بدون DEFAULT** — ردیف‌های پیش از آن `NULL` می‌مانند، و `NULL` یعنی «ثبت نشده»، نه «نامعلوم است پس حدس بزن». پسوند فایل شاهدِ ابزار نیست |

> **مرجع Snapshot از کجا می‌آید؟** تا پیش از Revision 0006 هیچ مسیری جز Seed توسعه در این
> جدول نمی‌نوشت، یعنی روی یک دیتابیس واقعی این جدول همیشه خالی می‌ماند و هر گزارش زنده ۴۰۴
> می‌گرفت. حالا وقتی یک عملیات مالی باید به یک Snapshot مشخص Core گره بخورد — صدور گزارش،
> ثبت اصلاح دستی — Finance از طریق Adapter مرجع را می‌سازد یا مرجع موجود را دوباره استفاده
> می‌کند. **هیچ عملیات دستی کاربر لازم نیست**، و Index یکتای جزئی روی
> `(organization_id, project_id, host_snapshot_id)` تضمین می‌کند یک Snapshot از Core هرگز
> دو مرجع Finance نسازد.
>
> `progress_snapshot_id` همچنان شناسه عمومی خودِ Finance است (همان که در URL دیده می‌شود) و
> شناسه Core در `host_snapshot_id` می‌نشیند. برای گرفتن Feed، Finance با شناسه **میزبان**
> سؤال می‌کند، نه با UUID خودش — میزبان UUID فایننس را نمی‌شناسد.

> **نسخه‌بندی Snapshot ستون ندارد و لازم هم ندارد.** جدول با Trigger فقط-افزودنی است، پس ترتیب ردیف‌ها خودش تاریخچه است: `version` و `isLatest` در پاسخ API از روی جایگاه ردیف در تاریخچه همان پروژه محاسبه می‌شوند. نسخه ۱ همیشه قدیمی‌ترین می‌ماند، چون هیچ ورود بعدی نمی‌تواند خودش را جلوتر درج کند.

> تریگر تغییرناپذیری این جدول هر `UPDATE` را رد می‌کند، پس `source_type` فقط در لحظه `INSERT` نوشتنی است و هیچ Backfillی روی ردیف‌های موجود ممکن نیست.

### progress_overrides

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه Override |
| organization_id / project_id | UUID / Text | Scope | Scope |
| estimate_line_id | UUID, FK | پیوند | خط برآوردی که مقدار اجرایش اصلاح شده |
| progress_snapshot_ref_id | UUID, FK | پیوند | Snapshot پیشرفتی که Override نسبت به آن ثبت شده |
| computed_value | Numeric(18,4) | داده مالی | مقداری که سیستم خودش محاسبه کرده بود. **سمت سرور محاسبه می‌شود** و از Client پذیرفته نمی‌شود، وگرنه سابقه اصلاح قابل اتکا نبود |
| override_value | Numeric(18,4) | داده مالی | مقداری که کاربر جایگزین کرده |
| reason | Text | ممیزی | دلیل اصلاح؛ CHECK رشته خالی یا فقط‌فاصله را رد می‌کند |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان ثبت |

Override پیشرفت همراه مقدار محاسبه‌شده، مقدار جایگزین، دلیل و actor به‌صورت Append-only ثبت می‌شود. نگهداری هم‌زمان مقدار محاسبه‌شده و مقدار جایگزین عمدی است: بدون آن معلوم نمی‌شد اصلاح چقدر بوده.

## ۹. فاکتورها

### invoices

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه فاکتور |
| organization_id / project_id | UUID / Text | Scope | Scope |
| invoice_number | Text, Nullable | توصیفی | شماره فاکتور فروشنده؛ اختیاری، چون هر رسیدی شماره ندارد |
| invoice_date | Date | مبنای زمانی | تاریخ فاکتور. گزارش دوره‌ای بر همین ستون گروه‌بندی می‌شود، نه بر `created_at` |
| vendor_name | Text | توصیفی | نام فروشنده |
| description | Text, Nullable | توصیفی | شرح آزاد |
| source | Text | طبقه‌بندی | `manual`، `image`، `voice`، `corrective` یا `reversal`؛ با CHECK محدود شده |
| status | Text | طبقه‌بندی | `draft`، `awaitingConfirmation`، `confirmed`، `voided` یا `corrected`؛ با CHECK محدود شده |
| discount_irr | Numeric(18,0), default 0 | داده مالی | تخفیف کل فاکتور؛ CHECK نامنفی |
| tax_irr | Numeric(18,0), default 0 | داده مالی | مالیات کل؛ CHECK نامنفی |
| shipping_irr | Numeric(18,0), default 0 | داده مالی | حمل کل؛ CHECK نامنفی |
| other_costs_irr | Numeric(18,0), default 0 | داده مالی | سایر هزینه‌های کل؛ CHECK نامنفی |
| final_amount_irr | Numeric(18,0), Nullable | داده مالی | مبلغ نهایی؛ تا پیش از تأیید خالی است |
| financial_effect_sign | Smallint, default 1 | داده مالی | `1` برای فاکتور عادی و `-1` برای برگشتی؛ CHECK فقط همین دو مقدار را می‌پذیرد. تمام جمع‌های مالی در همین علامت ضرب می‌شوند، پس برگشت با درج ثبت می‌شود نه با حذف |
| idempotency_key | Text, Nullable | یکپارچگی | کلید Idempotency ثبت؛ در Scope پروژه یکتاست |
| source_file_sha256 | Text, Nullable | یکپارچگی | چکیده SHA-256 فایل مبدأ، برای تشخیص بارگذاری تکراری. `NULL` یعنی فاکتور از فایلی نیامده — مثلاً ورود دستی |
| original_invoice_id | UUID, FK, Nullable | پیوند | فاکتور اصلی، برای برگشتی و اصلاحی؛ FK به همین جدول |
| version | Integer, default 1 | یکپارچگی | نسخه فاکتور؛ CHECK مثبت |
| submitted_by | UUID | ممیزی | ثبت‌کننده |
| confirmed_by | UUID, Nullable | ممیزی | تأییدکننده |
| confirmed_at | Timestamptz, Nullable | ممیزی | زمان تأیید |
| created_at / updated_at | Timestamptz | ممیزی | زمان ثبت و آخرین تغییر |
| confirmation_idempotency_key | Text, Nullable | یکپارچگی | کلید Idempotency تأیید؛ با Index جزئی یکتا محافظت می‌شود |

> یک CHECK ترکیبی تضمین می‌کند فاکتور `confirmed` حتماً `confirmed_by` و `confirmed_at` دارد: وضعیت تأییدشده بدون رد ممیزی ممکن نیست.

وضعیت‌ها شامل `draft`، `awaitingConfirmation`، `confirmed`، `voided` و `corrected` هستند. Source شامل ورود دستی، تصویر، صوت، corrective و reversal است.

قواعد اصلی:

- `idempotency_key` در Scope پروژه یکتا است.
- `confirmation_idempotency_key` با Index جزئی یکتا محافظت می‌شود.
- برای هر فاکتور اصلی فقط یک reversal مجاز است.
- فاکتور تأییدشده با Trigger در برابر تغییر مستقیم محافظت می‌شود.

### invoice_lines

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه خط فاکتور |
| organization_id / project_id | UUID / Text | Scope | Scope |
| invoice_id | UUID, FK | پیوند | فاکتور دربردارنده |
| estimate_line_id | UUID, FK, Nullable | پیوند | خط برآورد متناظر. خالی بودنش مجاز است: خرید بدون خط برآورد مشخص، در سطح قلم مالی تجمیع می‌شود |
| resource_id | UUID, FK | پیوند | قلم مالی خریداری‌شده |
| quantity | Numeric(18,4), Nullable | داده مالی | مقدار خریداری‌شده؛ برای هزینه عمومی خالی است |
| unit | Text, Nullable | طبقه‌بندی | واحد خرید. اگر با `base_unit` قلم فرق کند، تبدیل واحد لازم می‌شود |
| unit_price_snapshot_irr | Numeric(18,0), Nullable | تثبیت | قیمت واحد در لحظه ثبت. Snapshot است تا تغییر بعدی قیمت، فاکتور گذشته را بازنویسی نکند |
| raw_amount_irr | Numeric(18,0) | داده مالی | مبلغ خط پیش از سرشکن‌کردن تعدیلات |
| allocated_discount_irr | Numeric(18,0), default 0 | داده مالی | سهم این خط از تخفیف کل فاکتور |
| allocated_tax_irr | Numeric(18,0), default 0 | داده مالی | سهم این خط از مالیات |
| allocated_shipping_irr | Numeric(18,0), default 0 | داده مالی | سهم این خط از حمل |
| allocated_other_costs_irr | Numeric(18,0), default 0 | داده مالی | سهم این خط از سایر هزینه‌ها |
| final_line_amount_irr | Numeric(18,0) | داده مالی | مبلغ نهایی خط پس از تعدیلات. **تمام شاخص‌های هزینه واقعی از همین ستون جمع می‌شوند** |
| price_version_id | UUID, FK, Nullable | پیوند | نسخه قیمتی که Snapshot از آن گرفته شده |
| description | Text, Nullable | توصیفی | شرح خط |
| created_at | Timestamptz | ممیزی | زمان ثبت |

مبلغ خط، Snapshot قیمت و سهم تعدیلات در زمان ثبت نگهداری می‌شوند. هزینه عمومی می‌تواند بدون مقدار فیزیکی و با مبلغ مستقیم ثبت شود.

سرشکن‌کردن تعدیلات در زمان ثبت انجام و ذخیره می‌شود، نه در زمان خواندن: گزارشی که ماه‌ها بعد گرفته می‌شود همان اعدادی را می‌بیند که آن روز ثبت شده‌اند.

### قاعده Hash فایل مبدأ

Hash همیشه **سمت سرور** از بایت‌های دریافتی محاسبه می‌شود و هرگز از Client پذیرفته نمی‌شود؛ در غیر این صورت یک Client می‌توانست با ارسال چکیده دلخواه، تشخیص تکراری را دور بزند یا وجود فایلی را در سازمان دیگر استنتاج کند. مقایسه نیز درون همان `organization_id` و `project_id` انجام می‌شود.

## ۱۰. فایل‌های مالی

### finance_attachments

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه فایل |
| organization_id / project_id | UUID / Text | Scope | Scope |
| invoice_id | UUID, FK, Nullable | پیوند | فاکتور مرتبط. خالی بودنش مجاز است، چون تصویر می‌تواند پیش از ساخته‌شدن فاکتور بارگذاری شود |
| logical_type | Text | طبقه‌بندی | `invoice_image` یا `invoice_voice`؛ با CHECK محدود شده |
| original_name_safe | Text | توصیفی | نام اصلی فایل، پاک‌سازی‌شده برای نمایش |
| stored_name | Text | یکپارچه‌سازی | نامی که فایل با آن در Storage ذخیره شده |
| mime_type | Text | توصیفی | نوع MIME تأییدشده |
| size_bytes | Bigint | یکپارچگی | اندازه فایل؛ CHECK آن را اکیداً مثبت نگه می‌دارد |
| sha256 | Text | یکپارچگی | چکیده محتوا؛ CHECK طول ۶۴ کاراکتر را الزام می‌کند. در Scope پروژه **یکتا** است و همین Unique است که بارگذاری تکراری را تشخیص می‌دهد |
| storage_key | Text | یکپارچه‌سازی | کلید فایل در Storage میزبان |
| processing_status | Text | طبقه‌بندی | `uploaded`، `processing`، `ready` یا `failed`؛ با CHECK محدود شده |
| uploaded_by / uploaded_at | UUID / Timestamptz | ممیزی | بارگذارنده و زمان بارگذاری |
| deleted_at / deleted_by | Timestamptz / UUID, Nullable | یکپارچگی | حذف منطقی؛ CHECK تضمین می‌کند هر دو با هم پر یا هر دو خالی باشند |

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

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه Draft استخراج |
| organization_id / project_id | UUID / Text | Scope | Scope |
| attachment_id | UUID, FK | پیوند | فایلی که از آن استخراج شده |
| version | Integer | یکپارچگی | نسخه استخراج برای همان فایل؛ CHECK مثبت. ترکیب فایل و نسخه یکتاست، پس استخراج دوباره نسخه قبلی را پاک نمی‌کند |
| review_status | Text | طبقه‌بندی | `awaitingReview`، `accepted` یا `rejected`؛ با CHECK محدود شده |
| provider_adapter | Text | یکپارچه‌سازی | نام Adapter استخراج‌کننده؛ ثبت می‌شود تا معلوم باشد کدام سرویس چه چیزی گفته |
| extracted_fields | JSONB | تثبیت | آنچه Adapter خوانده است |
| confirmed_fields | JSONB, Nullable | تثبیت | آنچه انسان تأیید یا اصلاح کرده؛ تا پیش از بازبینی خالی است |
| financial_effect_irr | Numeric(18,0), default 0 | داده مالی | **CHECK آن را به صفر قفل کرده است.** یک Draft هرگز اثر مالی ندارد؛ عدد استخراج‌شده تا وقتی انسان فاکتور نسازد در هیچ شاخصی دیده نمی‌شود |
| submitted_by | UUID | ممیزی | ثبت‌کننده |
| confirmed_by | UUID, Nullable | ممیزی | تأییدکننده |
| confirmed_at | Timestamptz, Nullable | ممیزی | زمان تأیید |
| created_at / updated_at | Timestamptz | ممیزی | زمان ثبت و آخرین تغییر |

- `extracted_fields` و `confirmed_fields` به‌صورت JSONB ذخیره می‌شوند.
- Review status شامل `awaitingReview`، `accepted` و `rejected` است.
- اثر مالی Draft همیشه صفر است.
- تنها تأیید انسانی می‌تواند فاکتور مؤثر ایجاد کند.

## ۱۲. گزارش مالی

### report_snapshots

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه گزارش صادرشده |
| organization_id / project_id | UUID / Text | Scope | Scope |
| reporting_date | Date | مبنای زمانی | تاریخ گزارش‌گیری |
| progress_snapshot_ref_id | UUID, FK | پیوند | Snapshot پیشرفتی که گزارش بر آن استوار است |
| finance_settings_id | UUID, FK | پیوند | نسخه تنظیمات مالی در لحظه صدور |
| resource_version_ids | JSONB | تثبیت | شناسه نسخه اقلام مالی Pin‌شده |
| estimate_revision_ids | JSONB | تثبیت | شناسه Revisionهای برآورد Pin‌شده |
| price_version_ids | JSONB | تثبیت | شناسه نسخه‌های قیمت Pin‌شده |
| unit_conversion_ids | JSONB | تثبیت | شناسه نسخه‌های تبدیل واحد Pin‌شده |
| invoice_ids | JSONB | تثبیت | شناسه فاکتورهای لحاظ‌شده |
| calculated_metrics | JSONB | تثبیت | شاخص‌های محاسبه‌شده، به‌صورت رشته‌های عددی دقیق |
| snapshot_payload | JSONB | تثبیت | **کل گزارش در لحظه صدور**، شامل ورودی‌ها، Breakdown، انحرافات و هشدارها. خروجی CSV و XLSX از همین Payload خوانده می‌شود، نه از محاسبه دوباره — به همین دلیل گزارش قدیمی هرگز با تغییر کد عوض نمی‌شود |
| issued_by / issued_at | UUID / Timestamptz | ممیزی | صادرکننده و زمان صدور |

> Pin‌کردن شناسه نسخه‌ها در کنار Payload، دو کار متفاوت می‌کند: Payload می‌گوید گزارش **چه چیزی نشان داد**، و شناسه‌های Pin‌شده می‌گویند **از کدام ردیف‌ها آمد**. اولی برای خواننده است و دومی برای ممیزی.

گزارش Live از داده‌های جاری محاسبه می‌شود و جدول جداگانه ندارد. گزارش رسمی صادرشده در `report_snapshots` ثبت می‌شود.

Snapshot شامل نسخه تنظیمات، Revisionهای برآورد، قیمت‌ها، تبدیل‌ها، فاکتورها، Snapshot پیشرفت و Payload کامل زمان صدور است. Trigger مانع UPDATE یا DELETE گزارش صادرشده می‌شود.

## ۱۳. رویدادهای ممیزی

### finance_audit_events

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه رویداد |
| organization_id / project_id | UUID / Text | Scope | Scope |
| actor_user_id | UUID | ممیزی | کاربری که عمل را انجام داده |
| action | Text | طبقه‌بندی | نوع عمل ثبت‌شده |
| entity_type | Text | طبقه‌بندی | نوع موجودیت هدف، مثلاً فاکتور یا خط برآورد |
| entity_id | UUID | پیوند | شناسه موجودیت هدف |
| reason | Text, Nullable | ممیزی | دلیل، وقتی عمل دلیل می‌طلبد |
| before_values | JSONB, Nullable | ممیزی | وضعیت پیش از تغییر |
| after_values | JSONB, Nullable | ممیزی | وضعیت پس از تغییر |
| occurred_at | Timestamptz | ممیزی | زمان وقوع؛ مرتب‌سازی پایدار بر `occurred_at DESC, id DESC` است |

مقادیر قبل و بعد به‌صورت JSONB ثبت می‌شوند. Audit میان امور مالی و گزارش مالی مشترک و Append-only است.

API مشاهده Audit از همین جدول و با Scope دوگانه خوانده می‌شود. در سطح Repository، مرتب‌سازی پایدار `occurred_at DESC, id DESC` و صفحه‌بندی واقعی دیتابیس با `LIMIT/OFFSET` اعمال می‌شود؛ بنابراین مشاهده رویدادها باعث بارگذاری کامل تاریخچه در حافظه برنامه نمی‌شود.

## ۱۴. ورود گروهی اطلاعات

### finance_import_batches

| ستون | نوع | نقش | توضیح |
|---|---|---|---|
| id | UUID, PK | هویت | شناسه Batch ورود گروهی |
| organization_id / project_id | UUID / Text | Scope | Scope |
| import_kind | Text | طبقه‌بندی | `estimate` یا `prices`؛ با CHECK محدود شده |
| currency_unit | Text, Nullable | طبقه‌بندی | `IRR` یا `TOMAN`؛ با CHECK محدود شده. تومان فقط در ورودی پذیرفته می‌شود و پیش از ذخیره به ریال تبدیل می‌گردد — در دیتابیس هیچ مبلغی به تومان نگهداری نمی‌شود |
| file_sha256 | Text | یکپارچگی | چکیده فایل ورودی؛ CHECK طول ۶۴ کاراکتر را الزام می‌کند |
| normalized_rows | JSONB | تثبیت | ردیف‌های نرمال‌شده حاصل Preview |
| validation_errors | JSONB | تثبیت | خطاهای اعتبارسنجی هر ردیف |
| status | Text | طبقه‌بندی | `previewed` یا `committed`؛ با CHECK محدود شده |
| created_by / created_at | UUID / Timestamptz | ممیزی | ثبت‌کننده و زمان Preview |
| committed_at | Timestamptz, Nullable | یکپارچگی | زمان Commit؛ یک CHECK ترکیبی تضمین می‌کند این ستون **دقیقاً وقتی** پر است که `status` برابر `committed` باشد |

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

Migrationها با **Alembic** مدیریت می‌شوند و Alembic تنها مرجع Schema است. بدنه هر Revision
همان SQL خام بازبینی‌شده است — تبدیل، بازنویسی Schema نبود — و Alembic ترتیب و ثبت را بر عهده
دارد. زنجیره، از پایه تا head:

```text
0001_finance_core
  → 0002_invoice_confirmation
    → 0003_invoice_linked_documents
      → 0004_report_snapshot_payload
        → 0005_progress_snapshot_source_type
          → 0006_progress_snapshot_host_reference   (head)
```

Revisionها در `backend/alembic/versions/` قرار دارند و از پوشه `backend/` با
`alembic upgrade head` اجرا می‌شوند.

کار هر Migration:

| Migration | توضیح |
|---|---|
| `0001_finance_core` | ایجاد ۱۵ جدول، FKها، Constraintها، Indexهای Scope و Triggerها |
| `0002_invoice_confirmation` | افزودن Idempotency تأیید فاکتور و Unique Index |
| `0003_invoice_linked_documents` | تضمین یک Reversal برای هر فاکتور اصلی |
| `0004_report_snapshot_payload` | افزودن Payload کامل و شناسه نسخه‌های Pin‌شده گزارش |
| `0005_progress_snapshot_source_type` | افزودن ستون `source_type` به `progress_snapshot_refs`؛ فقط تغییر Catalog، بدون DEFAULT و بدون بازنویسی هیچ ردیفی، تا تریگر تغییرناپذیری فعال نشود |

هر Revision هر دو جهت را دارد (`upgrade` و `downgrade`). **Down migration جایگزین
Backup/Restore نیست** — Revision پایه تمام جدول‌های مالی را حذف می‌کند و داده‌شان با آن‌ها
می‌رود؛ `docs/RECOVERY_RUNBOOK_FA.md` را ببینید.

اتصال از `FINANCE_MIGRATION_DSN` (نقش Owner) خوانده می‌شود، نه از `FINANCE_DEV_DSN` که نقش
برنامه است و عمداً اجازه DDL ندارد. `alembic.ini` هیچ رشته اتصالی ندارد.

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

- `backend/alembic/versions/` — هر پنج Revision
- `backend/alembic/env.py` — اتصال Alembic و اینکه چرا DSN حدس زده نمی‌شود
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
