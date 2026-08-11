# سند اسکیما و تنظیمات دیتابیس ماژول مالی BAMBO

تاریخ استخراج/بازبینی: ۱۴۰۵/۰۵/۲۰ — 2026-08-11  
منبع: Migrationهای SQL، Repositoryهای Psycopg، PRD و Integration Kit نسخه ۱.۱

## ۱. وضعیت دیتابیس

```text
DBMS: PostgreSQL
Minimum compatibility: PostgreSQL 16
Driver: psycopg
Schema source: SQL migrations
Migration sequence: 0001 تا 0004
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

`id`, `organization_id`, `project_id`, `resource_id`, `activity_external_id`, `assignment_external_id`, `original_quantity`, `original_unit_price_irr`, `source`, `created_by`, `created_at`, `deleted_at`, `deleted_by`.

- `original_quantity`: مقدار اولیه با `numeric(18,4)`
- `original_unit_price_irr`: قیمت یا مبلغ اولیه با `numeric(18,0)`
- `source`: یکی از `progress_feed`، `excel_import` یا `manual_entry`
- فیلدهای Original با Trigger قابل بازنویسی نیستند.

### estimate_revisions

`id`, `organization_id`, `project_id`, `estimate_line_id`, `revision`, `previous_quantity`, `new_quantity`, `reason`, `created_by`, `created_at`.

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

`id`, `organization_id`, `project_id`, `scope_kind`, `version`, `source_unit`, `target_unit`, `dimension`, `factor`, `effective_from`, `reason`, `created_by`, `created_at`.

- `factor`: عدد Decimal مثبت
- تبدیل مبدأ و مقصد یکسان ممنوع است.
- Scope می‌تواند سازمانی یا Override پروژه باشد.
- تاریخچه تبدیل واحد Append-only است.

## ۸. پیشرفت پروژه

### progress_snapshot_refs

`id`, `organization_id`, `project_id`, `progress_snapshot_id`, `source_file_version_id`, `source_file_name_safe`, `imported_at`, `imported_by`, `snapshot_status`, `reporting_date`.

این جدول فقط مرجع Snapshot پیشرفت سیستم میزبان را نگهداری می‌کند و داده میزبان را بازنویسی نمی‌کند.

### progress_overrides

`id`, `organization_id`, `project_id`, `estimate_line_id`, `progress_snapshot_ref_id`, `computed_value`, `override_value`, `reason`, `created_by`, `created_at`.

Override پیشرفت همراه مقدار محاسبه‌شده، مقدار جایگزین، دلیل و actor به‌صورت Append-only ثبت می‌شود.

## ۹. فاکتورها

### invoices

```text
id
organization_id
project_id
invoice_number
invoice_date
vendor_name
description
source
status
discount_irr
tax_irr
shipping_irr
other_costs_irr
final_amount_irr
financial_effect_sign
idempotency_key
confirmation_idempotency_key
original_invoice_id
version
submitted_by
confirmed_by
confirmed_at
created_at
updated_at
```

وضعیت‌ها شامل `draft`، `awaitingConfirmation`، `confirmed`، `voided` و `corrected` هستند. Source شامل ورود دستی، تصویر، صوت، corrective و reversal است.

قواعد اصلی:

- `idempotency_key` در Scope پروژه یکتا است.
- `confirmation_idempotency_key` با Index جزئی یکتا محافظت می‌شود.
- برای هر فاکتور اصلی فقط یک reversal مجاز است.
- فاکتور تأییدشده با Trigger در برابر تغییر مستقیم محافظت می‌شود.

### invoice_lines

`id`, `organization_id`, `project_id`, `invoice_id`, `estimate_line_id`, `resource_id`, `quantity`, `unit`, `unit_price_snapshot_irr`, `raw_amount_irr`, `allocated_discount_irr`, `allocated_tax_irr`, `allocated_shipping_irr`, `allocated_other_costs_irr`, `final_line_amount_irr`, `price_version_id`, `description`, `created_at`.

مبلغ خط، Snapshot قیمت و سهم تعدیلات در زمان ثبت نگهداری می‌شوند. هزینه عمومی می‌تواند بدون مقدار فیزیکی و با مبلغ مستقیم ثبت شود.

## ۱۰. فایل‌های مالی

### finance_attachments

```text
id
organization_id
project_id
invoice_id
logical_type
original_name_safe
stored_name
mime_type
size_bytes
sha256
storage_key
processing_status
uploaded_by
uploaded_at
deleted_at
deleted_by
```

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

`id`, `organization_id`, `project_id`, `attachment_id`, `version`, `review_status`, `provider_adapter`, `extracted_fields`, `confirmed_fields`, `financial_effect_irr`, `submitted_by`, `confirmed_by`, `confirmed_at`, `created_at`, `updated_at`.

- `extracted_fields` و `confirmed_fields` به‌صورت JSONB ذخیره می‌شوند.
- Review status شامل `awaitingReview`، `accepted` و `rejected` است.
- اثر مالی Draft همیشه صفر است.
- تنها تأیید انسانی می‌تواند فاکتور مؤثر ایجاد کند.

## ۱۲. گزارش مالی

### report_snapshots

```text
id
organization_id
project_id
reporting_date
progress_snapshot_ref_id
finance_settings_id
resource_version_ids
estimate_revision_ids
price_version_ids
unit_conversion_ids
invoice_ids
calculated_metrics
snapshot_payload
issued_by
issued_at
```

گزارش Live از داده‌های جاری محاسبه می‌شود و جدول جداگانه ندارد. گزارش رسمی صادرشده در `report_snapshots` ثبت می‌شود.

Snapshot شامل نسخه تنظیمات، Revisionهای برآورد، قیمت‌ها، تبدیل‌ها، فاکتورها، Snapshot پیشرفت و Payload کامل زمان صدور است. Trigger مانع UPDATE یا DELETE گزارش صادرشده می‌شود.

## ۱۳. رویدادهای ممیزی

### finance_audit_events

`id`, `organization_id`, `project_id`, `actor_user_id`, `action`, `entity_type`, `entity_id`, `reason`, `before_values`, `after_values`, `occurred_at`.

مقادیر قبل و بعد به‌صورت JSONB ثبت می‌شوند. Audit میان امور مالی و گزارش مالی مشترک و Append-only است.

API مشاهده Audit از همین جدول و با Scope دوگانه خوانده می‌شود. در سطح Repository، مرتب‌سازی پایدار `occurred_at DESC, id DESC` و صفحه‌بندی واقعی دیتابیس با `LIMIT/OFFSET` اعمال می‌شود؛ بنابراین مشاهده رویدادها باعث بارگذاری کامل تاریخچه در حافظه برنامه نمی‌شود.

## ۱۴. ورود گروهی اطلاعات

### finance_import_batches

`id`, `organization_id`, `project_id`, `import_kind`, `currency_unit`, `file_sha256`, `normalized_rows`, `validation_errors`, `status`, `created_by`, `created_at`, `committed_at`.

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
```

کار هر Migration:

| Migration | توضیح |
|---|---|
| `0001_finance_core` | ایجاد ۱۵ جدول، FKها، Constraintها، Indexهای Scope و Triggerها |
| `0002_invoice_confirmation` | افزودن Idempotency تأیید فاکتور و Unique Index |
| `0003_invoice_linked_documents` | تضمین یک Reversal برای هر فاکتور اصلی |
| `0004_report_snapshot_payload` | افزودن Payload کامل و شناسه نسخه‌های Pin‌شده گزارش |

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
