# BAMBO Finance Module - Technical Handoff

> وضعیت سند: 2026-09-02  
> Branch بررسی‌شده: `backend-finance`  
> Commit مبنا: `f29a6443`  
> منابع مرجع: `BAMBO_FINANCE_MVP_PRD_FA_v1.1` و `BAMBO_FINANCE_INTEGRATION_KIT_v1.1`  
> نکته تحویل: Worktree در زمان تهیه این سند دارای تغییرات Commit‌نشده در Backend و Frontend بود. این سند وضعیت فایل‌های موجود را توصیف می‌کند و به‌معنی Release-ready بودن آن تغییرات نیست.

## 1. Overview

ماژول Finance لایه مالی داخلی BAMBO است و برای کاربران مجاز سازمان/پروژه، اقلام و خطوط برآورد، قیمت جاری و تاریخچه قیمت، اسناد مالی تأییدشده، واقعیت پیشرفت پروژه و گزارش‌های تصمیم‌گیری مالی را یکپارچه می‌کند. مشتری عمومی نباید به داده‌های داخلی نیرو، هزینه و اسناد این ماژول دسترسی داشته باشد؛ کنترل دسترسی به Context، Scope و Permission میزبان BAMBO متکی است.

مسیر مفهومی اصلی:

```text
Estimate / Quantity
        + Progress Reality
        + Confirmed Financial Documents
        + Current Price
        -> Financial Metrics and Immutable Report Snapshots
```

محدوده MVP شامل تنظیمات مالی پروژه، چهار نوع قلم `material`، `labor`، `equipment` و `general_cost`، خطوط و Revisionهای برآورد، Import اکسل تعریف‌شده، قیمت و تبدیل واحد نسخه‌دار، دریافت read-only پیشرفت، فاکتور چندردیفی و اصلاح/ابطال، فایل و Extraction Draft با تأیید انسانی، گزارش زنده و Snapshot و خروجی CSV/XLSX است. انبار، خزانه‌داری، پرداخت، حسابداری دوبل، حقوق و دستمزد، مالیات تخصصی، فروش، مدیریت سازمان/پروژه، Parse مستقیم MPP و Provider فعال قیمت آنلاین خارج از MVP هستند.

## 2. Current Architecture

### Backend

- **Framework:** Python 3.12+ و FastAPI؛ Composition Root عمومی در `backend/app/main.py` و Router مالی در `backend/app/finance/router.py`.
- **Database:** PostgreSQL 16 هدف اصلی است؛ سازگاری PostgreSQL 18 باید در Gate استقرار تأیید شود.
- **Migration:** Alembic تنها مرجع Schema است. زنجیره واقعی موجود `0001 -> ... -> 0006` و Head فعلی `0006_progress_snapshot_host_reference` است.
- **ORM:** ORM برای Persistence استفاده نشده است. Repositoryها با `psycopg` و SQL پارامتری کار می‌کنند. SQLAlchemy فقط برای اجرای DDL در Migrationهای Alembic استفاده شده است.
- **Domain/Service Layer:** مدل و قواعد Domain در `backend/app/finance/domain/`، orchestration در `services/`، قراردادهای ورودی/خروجی Pydantic در `schemas/` و SQL در `repositories/` قرار دارد.
- **API Structure:** تمام مسیرها زیر `/api/projects/{projectId}/finance` هستند؛ JSON به‌صورت camelCase است. `organizationId` از Auth Context گرفته می‌شود و از Body پذیرفته نمی‌شود.
- **Adapters:** قراردادهای Auth، Scope، Permission، Progress، Activity، File Storage و Extraction در مرز Adapter تعریف شده‌اند. اتصال Core در `backend/coreint/` و Host محلی در `backend/devhost/` قرار دارد.
- **Money:** پول رسمی IRR در API به‌صورت Decimal string و در DB به‌صورت `numeric(18,0)` نگه‌داری می‌شود؛ محاسبه پول با float مجاز نیست.

### Frontend

- **Framework:** HTML/CSS و JavaScript وانیلا با ES Modules؛ بدون Framework، Build Step، CDN یا درخواست مستقیم مرورگر به Provider خارجی.
- **Runtime:** داخل Shell اصلی BAMBO از Adapter میزبان/Same-Origin استفاده می‌شود. اجرای مستقل روی پورت `43127` عمدتاً برای UI و Mock است و Persistence واقعی Backend را تضمین نمی‌کند.
- **صفحات Finance:** `finance-home`، `settings`، `financial-items`، `estimate-lines`، `prices`، `unit-conversions`، `progress`، `progress-snapshots`، `invoices`، `ai-review`، `reports`، `period-report`، `report-builder` و `audit`. پوشه‌های جدید `level-one` و `work-areas` در Worktree وجود دارند اما Commit/Release آن‌ها در این Audit تأیید نشده است.
- **Components اصلی:** Adapterهای `src/adapters/api/` و `src/adapters/mock/`، اجزای نمودار و گزارش در `src/shared/charts/` و `src/shared/components/`، نمایش پول Decimal-safe، Price Trend، Cost Curve، Dialogها و Stateهای Loading/Empty/Error.

## 3. Database Schema

Schema فعال Finance شامل 15 جدول زیر است. همه Queryهای مالی باید هم‌زمان با `organization_id` و `project_id` Scope شوند. جدول‌های تاریخچه‌ای توسط Trigger در برابر `UPDATE` و `DELETE` محافظت می‌شوند.

### `finance_project_settings`

- **هدف:** Revisionهای تنظیمات مالی پروژه مانند مساحت ناخالص و ارز.
- **ستون‌های مهم:** `id`, `organization_id`, `project_id`, `revision`, `gross_built_area numeric(18,4)`, `currency='IRR'`, `effective_from`, `reason`, `created_by`, `created_at`.
- **ارتباط:** توسط `report_snapshots.finance_settings_id` Pin می‌شود؛ append-only و immutable است.

### `finance_resources`

- **هدف:** کاتالوگ اقلام مالی پایدار پروژه.
- **ستون‌های مهم:** `id`, Scope، `resource_type`, `code`, `title`, `base_unit`, `dimension`, `external_resource_id`, اطلاعات ایجاد و soft-delete.
- **ارتباط:** والد `estimate_lines`, `price_versions` و `invoice_lines`. نوع فقط یکی از `material/labor/equipment/general_cost` است؛ `general_cost` الزام واحد/بعد فیزیکی ندارد.

### `estimate_lines`

- **هدف:** اتصال یک Resource به یک Activity/Assignment و نگه‌داری مقدار و قیمت اولیه.
- **ستون‌های مهم:** `id`, Scope، `resource_id`, `activity_external_id`, `assignment_external_id`, `original_quantity numeric(18,4)`, `original_unit_price_irr numeric(18,0)`, `source`, اطلاعات ایجاد و soft-delete.
- **ارتباط:** FK به `finance_resources`؛ والد `estimate_revisions` و `progress_overrides`؛ مرجع اختیاری در `invoice_lines`. فیلدهای original و شناسه‌های اتصال توسط Trigger غیرقابل بازنویسی‌اند.

### `estimate_revisions`

- **هدف:** تاریخچه append-only اصلاح مقدار/مبلغ برآورد.
- **ستون‌های مهم:** `estimate_line_id`, `revision`, `previous_quantity`, `new_quantity`, `reason`, `created_by`, `created_at`.
- **ارتباط:** FK مرکب scoped به `estimate_lines`; هر Revision برای هر خط یکتا است.

### `price_versions`

- **هدف:** تاریخچه Strict Append-only قیمت هر Resource و Resolve قیمت سازمان/Override پروژه.
- **ستون‌های مهم:** `resource_id`, `scope_kind`, `version`, `unit_price_irr numeric(18,0)`, `effective_from`, `reason`, `created_by`, `created_at`.
- **ارتباط:** FK به `finance_resources`; در `invoice_lines.price_version_id` و JSON مربوط به `report_snapshots` Pin می‌شود.

### `unit_conversions`

- **هدف:** تبدیل واحد نسخه‌دار و قابل Audit.
- **ستون‌های مهم:** `scope_kind`, `version`, `source_unit`, `target_unit`, `dimension`, `factor numeric(24,8)`, `effective_from`, `reason`, اطلاعات ایجاد.
- **ارتباط:** شناسه نسخه‌های استفاده‌شده در `report_snapshots.unit_conversion_ids` ذخیره می‌شود؛ append-only است.

### `progress_snapshot_refs`

- **هدف:** Reference محلی و immutable به Snapshot پیشرفت میزبان، بدون مالکیت یا Mutation داده Progress.
- **ستون‌های مهم:** `id`, Scope، `progress_snapshot_id uuid`, `source_file_version_id uuid nullable`, نام امن فایل، `reporting_date`, `snapshot_status`, `source_type`, `host_snapshot_id bigint`, `host_file_version_id bigint`, اطلاعات Import.
- **ارتباط:** والد `progress_overrides` و FK از `report_snapshots`. `host_snapshot_id` به‌صورت منطقی به Core اشاره می‌کند ولی عمداً FK بین‌دیتابیسی ندارد.

### `progress_overrides`

- **هدف:** ثبت append-only Override انسانی روی مقدار محاسبه‌شده پیشرفت.
- **ستون‌های مهم:** `estimate_line_id`, `progress_snapshot_ref_id`, `computed_value numeric(18,4)`, `override_value numeric(18,4)`, `reason`, `created_by`, `created_at`.
- **ارتباط:** FK scoped به `estimate_lines` و `progress_snapshot_refs`.

### `invoices`

- **هدف:** Header اسناد مالی و Lifecycle مستقل آن‌ها.
- **ستون‌های مهم:** `invoice_number`, `invoice_date`, `vendor_name`, `source`, `status`, تخفیف/مالیات/حمل/سایر هزینه‌ها و `final_amount_irr` با `numeric(18,0)`, `financial_effect_sign`, Idempotency keyها، `original_invoice_id`, `version`, اطلاعات Submit/Confirm.
- **ارتباط:** self-reference برای corrective/reversal؛ والد `invoice_lines` و اتصال اختیاری `finance_attachments`. سند Confirmed/Voided/Corrected مستقیم Update/Delete نمی‌شود.

### `invoice_lines`

- **هدف:** ردیف‌های چندگانه فاکتور و Snapshot مبلغ واقعی هر ردیف.
- **ستون‌های مهم:** `invoice_id`, `estimate_line_id`, `resource_id`, `quantity`, `unit`, `unit_price_snapshot_irr`, `raw_amount_irr`, allocationهای Header و `final_line_amount_irr`, `price_version_id`, `description`.
- **ارتباط:** FK scoped به `invoices`, `estimate_lines`, `finance_resources` و `price_versions`.

### `finance_attachments`

- **هدف:** Metadata فایل عکس/صوت فاکتور؛ Blob از طریق Storage Adapter نگه‌داری می‌شود.
- **ستون‌های مهم:** `invoice_id`, `logical_type`, نام امن، MIME، Size، SHA-256، `storage_key`, `processing_status`, اطلاعات Upload و soft-delete.
- **ارتباط:** FK اختیاری به `invoices`; والد `extraction_drafts`.

### `extraction_drafts`

- **هدف:** خروجی OCR/Voice AI برای Review انسانی، مستقل از File و Invoice.
- **ستون‌های مهم:** `attachment_id`, `version`, `review_status`, `provider_adapter`, `extracted_fields jsonb`, `confirmed_fields jsonb`, `financial_effect_irr=0`, اطلاعات Submit/Confirm.
- **ارتباط:** FK scoped به `finance_attachments`. Draft به‌تنهایی اثر مالی ندارد؛ Confirm service می‌تواند Invoice بسازد.

### `report_snapshots`

- **هدف:** گزارش صادرشده immutable با Pin کردن تمام ورودی‌های محاسبه.
- **ستون‌های مهم:** `reporting_date`, `progress_snapshot_ref_id`, `finance_settings_id`, JSON شناسه Resource/Estimate Revision/Price/Conversion/Invoice، `calculated_metrics`, `snapshot_payload`, `issued_by`, `issued_at`.
- **ارتباط:** FK به `progress_snapshot_refs` و `finance_project_settings`; تمام منابع دیگر با شناسه‌های Pin‌شده در JSON ثبت می‌شوند.

### `finance_audit_events`

- **هدف:** Audit trail append-only تغییرات مالی.
- **ستون‌های مهم:** Scope، `actor_user_id`, `action`, `entity_type`, `entity_id`, `reason`, `before_values`, `after_values`, `occurred_at`.
- **ارتباط:** رابطه منطقی با Entityهای مالی؛ FK عمومی ندارد تا Event تاریخی مستقل بماند.

### `finance_import_batches`

- **هدف:** Preview و Commit اتمیک Importهای `estimate` و `prices`.
- **ستون‌های مهم:** `import_kind`, `currency_unit`, `file_sha256`, `normalized_rows`, `validation_errors`, `status`, اطلاعات ایجاد و Commit.
- **ارتباط:** Commit در Repository، خطوط/قیمت‌ها را در همان Scope می‌سازد و Audit Event ثبت می‌کند.

### Schemaهای Core خارج از Finance

`msp_snapshots`, `msp_file_versions`, `msp_tasks`, `msp_resources` و `msp_resource_assignments` متعلق به Core/Progress Provider هستند و جزو 15 جدول Schema فعال Finance نیستند. کد Adapter می‌تواند در صورت وجود دو جدول resource/assignment در Core از آن‌ها بخواند، اما در زنجیره Alembic فعلی Finance Migration ایجادکننده آن‌ها وجود ندارد.

## 4. Integration With MSP / Progress

مسیر هدف داده:

```text
MSP Snapshot (owned and parsed by Core)
        ↓
msp_tasks
        ↓
msp_resources (when present in Core)
        ↓
msp_resource_assignments (when present in Core)
        ↓
activity_external_id / assignment_external_id on estimate_lines
        ↓
CoreProgressSnapshotProvider (read-only)
        ↓
Finance Calculation / Report Snapshot
```

- **Snapshot چیست؟** یک تصویر versioned و read-only از برنامه و پیشرفت در یک تاریخ گزارش است. Core فایل MPP را Parse می‌کند؛ Finance فایل MPP را مستقیم Parse یا داده Progress را Update نمی‌کند.
- **`hostSnapshotId` چیست؟** شناسه `bigint` واقعی `msp_snapshots.id` در Core است. Adapter با این شناسه Snapshot میزبان را پیدا می‌کند.
- **`progressSnapshotId` چیست؟** UUID عمومی و opaque متعلق به Finance در `progress_snapshot_refs.progress_snapshot_id` است که در API و Report Snapshot استفاده می‌شود. این UUID نباید با ID عددی Core یکی فرض شود.
- **Mapping چگونه انجام می‌شود؟** Finance هنگام Ingest یک Reference، UUID محلی را همراه `host_snapshot_id` و `host_file_version_id` ثبت می‌کند. `estimate_lines.activity_external_id` و `assignment_external_id` شناسه‌های پایدار Schedule را نگه می‌دارند. `CoreProgressSnapshotProvider` در `backend/coreint/progress.py` داده task/resource/assignment همان Snapshot و همان پروژه را خوانده و به Feed استاندارد تبدیل می‌کند. Overrideها در Finance جدا و append-only هستند.
- **Fallback:** اگر جداول `msp_resources` و `msp_resource_assignments` در Core وجود نداشته باشند، Adapter فقط داده‌ای را برمی‌گرداند که Contract و جداول موجود اجازه می‌دهند؛ نباید Quantity فیزیکی را حدس بزند.
- **مرز مالکیت:** نبود Foreign Key مستقیم از Finance به Core عمدی است تا حذف/چرخه عمر Core تاریخ مالی را Cascade نکند. اعتبار Reference در Adapter boundary کنترل می‌شود.

## 5. API Documentation

پیشوند همه مسیرهای زیر: `/api/projects/{projectId}/finance`. Responseها camelCase هستند و Errorها Envelope استاندارد دارند. وضعیت «DONE» یعنی route، schema، service و repository در کد موجود است؛ اتصال Production به Adapter واقعی جداگانه ارزیابی می‌شود.

| Method | Path | Request | Response | Purpose | Status |
|---|---|---|---|---|---|
| GET | `/settings` | Path scope | `FinanceSettingsResponse` | تنظیمات مؤثر مالی | DONE |
| PATCH | `/settings` | `FinanceSettingsPatch` | `FinanceSettingsResponse` | ثبت Revision جدید تنظیمات | DONE |
| GET | `/settings/revisions` | Path scope | `FinanceSettingsRevisionResponse[]` | تاریخچه immutable تنظیمات | DONE |
| GET | `/summary` | Path scope | `FinanceSummaryResponse` | خلاصه تنظیمات/آمادگی پروژه | DONE |
| GET | `/resources` | Path scope | `ResourceResponse[]` | فهرست اقلام مالی | DONE |
| POST | `/resources` | `ResourceCreate` | `ResourceResponse` (201) | ایجاد قلم | DONE |
| GET | `/resources/{resourceId}` | UUID | `ResourceResponse` | مشاهده قلم scoped | DONE |
| PATCH | `/resources/{resourceId}` | `ResourcePatch` | `ResourceResponse` | اصلاح metadata قلم | DONE |
| GET | `/unit-registry` | Path scope | `UnitRegistryResponse` | واژگان واحد/بعد مجاز | DONE |
| GET | `/activities` | query/status/page/pageSize | `ActivityListResponse` | Activityهای Provider پروژه | DONE (adapter-dependent) |
| POST | `/activities` | `ActivityCreate` | `ActivityResponse` (201) | Activity دستی از Provider مجاز | PARTIAL (host-dependent) |
| GET | `/estimate-lines` | Path scope | `EstimateLineResponse[]` | خطوط برآورد | DONE |
| POST | `/estimate-lines` | `EstimateLineCreate` | `EstimateLineResponse` (201) | ایجاد خط مستقل | DONE |
| POST | `/estimate-lines/{lineId}/revisions` | `EstimateRevisionCreate` | `EstimateLineResponse` (201) | ثبت Revision مقدار/مبلغ | DONE |
| GET | `/resources/{resourceId}/prices` | Resource UUID | `PriceResponse[]` | تاریخچه قیمت یک قلم | DONE |
| POST | `/resources/{resourceId}/prices` | `PriceCreate` | `PriceResponse` (201) | Append نسخه قیمت | DONE |
| GET | `/price-history` | Path scope | `PriceResponse[]` | تاریخچه قیمت کل پروژه | DONE |
| GET | `/prices/current` | `asOf` | `CurrentPriceTrendResponse[]` | قیمت مؤثر و Trend تاریخی | DONE |
| GET | `/unit-conversions` | Path scope | `ConversionResponse[]` | تاریخچه تبدیل‌ها | DONE |
| POST | `/unit-conversions` | `ConversionCreate` | `ConversionResponse` (201) | ثبت نسخه تبدیل | DONE |
| PATCH | `/unit-conversions/{conversionId}` | `ConversionPatch` | `ConversionResponse` | ساخت Revision تبدیل، نه overwrite | DONE |
| GET | `/progress-snapshots` | Path scope | `ProgressSnapshotResponse[]` | Snapshotهای Progress | DONE (provider-dependent) |
| GET | `/progress-snapshots/{snapshotId}` | Finance UUID | `ProgressSnapshotResponse` | Metadata یک Snapshot | DONE (provider-dependent) |
| GET | `/progress-snapshots/{snapshotId}/feed` | Finance UUID | `ProgressFeedResponse` | Feed read-only پیشرفت | DONE (provider-dependent) |
| GET | `/estimate-lines/{lineId}/progress-overrides` | Line UUID | `ProgressOverrideResponse[]` | تاریخچه Override | DONE |
| POST | `/estimate-lines/{lineId}/progress-override` | `ProgressOverrideCreate` | `ProgressOverrideResponse` (201) | Append Override | DONE |
| POST | `/imports/estimate/preview` | multipart `.xlsx` | `ImportPreviewResponse` | Preview بدون Mutation | DONE |
| POST | `/imports/prices/preview` | multipart `.xlsx` | `ImportPreviewResponse` | Preview قیمت بدون Mutation | DONE |
| POST | `/imports/estimate/commit` | `ImportCommit` | `ImportCommitResponse` | Commit scoped/atomic برآورد | DONE |
| POST | `/imports/prices/commit` | `ImportCommit` | `ImportCommitResponse` | Commit scoped/atomic قیمت | DONE |
| GET | `/invoices` | filter + pagination | `InvoiceListResponse` | فهرست و جستجوی فاکتور | DONE |
| POST | `/invoices` | `InvoiceCreate` | `InvoiceResponse` (201) | ثبت فاکتور چندردیفی | DONE |
| GET | `/invoices/{invoiceId}` | UUID | `InvoiceResponse` | مشاهده فاکتور | DONE |
| PATCH | `/invoices/{invoiceId}` | `InvoicePatch` | `InvoiceResponse` | اصلاح Draft مجاز | DONE |
| POST | `/invoices/{invoiceId}/confirm` | `InvoiceConfirm` | `InvoiceResponse` | Confirm idempotent | DONE |
| POST | `/invoices/{invoiceId}/void` | `InvoiceVoid` | `InvoiceResponse` (201) | سند Reversal/Void مرتبط | DONE |
| POST | `/invoices/{invoiceId}/corrective` | `CorrectiveInvoiceCreate` | `InvoiceResponse` (201) | سند اصلاحی مرتبط | DONE |
| POST | `/files` | multipart `logicalType,file` | `AttachmentResponse` (201) | آپلود عکس/صوت | DONE (storage adapter-dependent) |
| GET | `/files` | filters + pagination | `AttachmentListResponse` | فهرست فایل‌ها | DONE |
| GET | `/files/{fileId}` | UUID | `AttachmentResponse` | Metadata فایل | DONE |
| GET | `/files/{fileId}/content` | UUID | Binary response | محتوای امن فایل | DONE (storage adapter-dependent) |
| POST | `/files/{fileId}/extractions` | `ExtractionStart` | `ExtractionDraftResponse` (201) | Extraction همگام | PARTIAL (provider-dependent) |
| POST | `/files/{fileId}/extractions/async` | `ExtractionStart` | Queue status (202) | Extraction پس‌زمینه Local Host | PARTIAL (in-process queue) |
| GET | `/extractions` | filters + pagination | `ExtractionListResponse` | فهرست Draftها | DONE |
| GET | `/extractions/{draftId}` | UUID | `ExtractionDraftResponse` | مشاهده Draft | DONE |
| POST | `/extractions/{draftId}/reject` | `ExtractionReject` | `ExtractionDraftResponse` | رد انسانی | DONE |
| POST | `/extractions/{draftId}/retry` | `ExtractionRetry` | `ExtractionDraftResponse` (201) | نسخه Extraction جدید | PARTIAL (provider-dependent) |
| POST | `/extractions/{draftId}/confirm` | `ExtractionConfirm` | `InvoiceResponse` | Confirm انسانی و ساخت Invoice | DONE |
| GET | `/reports/live` | reportingDate, snapshot UUID optional | `LiveReportResponse` | محاسبه زنده مالی | DONE |
| GET | `/overview` | reportingDate, snapshot UUID optional | `OperationalOverviewResponse` | Overview صفحه مالی | DONE |
| GET | `/reports/live/by-wbs` | date/snapshot/level/parent | `WbsReportResponse` | Roll-up گزارش بر WBS | DONE (activity metadata-dependent) |
| GET | `/reports/live/variances` | filters/sort/page | `ReportVarianceListResponse` | تحلیل انحراف قیمت/مقدار | DONE |
| GET | `/reports/monthly` | reportingDate/monthCount | `MonthlyReportResponse` | سری زمانی ماه شمسی | DONE |
| POST | `/report-snapshots` | `ReportSnapshotCreate` | `ReportSnapshotReference` (201) | صدور Snapshot immutable | PARTIAL: Permission میزبان `finance_report.issue` حل نشده |
| GET | `/report-snapshots` | filters + pagination | `ReportSnapshotListResponse` | فهرست Snapshotها | DONE |
| GET | `/report-snapshots/{reportId}` | UUID | `ReportSnapshotReference` | بازیابی Snapshot | DONE |
| GET | `/report-snapshots/{reportId}/csv` | UUID | CSV | خروجی Snapshot | DONE |
| GET | `/report-snapshots/{reportId}/xlsx` | UUID | XLSX | خروجی Snapshot | DONE |
| GET | `/audit-events` | filters + pagination | `AuditEventListResponse` | Audit scoped | DONE |

OpenAPI پویا در `/openapi.json` تولید می‌شود. فایل OpenAPI مرجع Integration Kit باید در Contract Gate با این خروجی مقایسه شود.

## 6. Current Features

| Feature | Status | توضیح |
|---|---|---|
| Finance Settings و Revision | DONE | append-only و قابل Pin در گزارش |
| Finance Resources و Estimate Lines | DONE | چهار نوع قلم، ID پایدار و خطوط مستقل |
| Estimate Revision | DONE | original immutable و تاریخچه Revision |
| Import Estimate Excel | DONE | Header مستقل، Preview و Commit |
| Import Prices Excel | DONE | Header مستقل و مسیر جدا از Estimate |
| Price Versioning / Trend | DONE | تاریخچه append-only، Resolve Scope و Trend بدون Migration جدید |
| Unit Registry / Conversion | DONE | Decimal factor و نسخه‌بندی |
| Manual Multi-line Invoice | DONE | Draft، Confirm، Corrective و Reversal |
| Attachment Upload | PARTIAL | API و metadata آماده؛ Storage Production باید توسط Host وصل شود |
| Extraction Draft / Human Confirm | PARTIAL | Lifecycle آماده؛ Provider واقعی OCR/Voice و Queue پایدار Production خارجی است |
| Progress Integration | PARTIAL | Adapter read-only آماده؛ صحت Schema/دسترسی Core و resource assignments باید در محیط میزبان تأیید شود |
| Financial Calculations | DONE | estimate/actual/current/remaining/forecast و general cost در Domain موجود است |
| Live Reports / WBS / Variances / Monthly | DONE | Endpoint و Service موجود؛ کیفیت WBS به metadata Provider وابسته است |
| Immutable Report Snapshot | PARTIAL | پیاده‌سازی موجود؛ Permission صدور در Core فعلی شناخته نشده است |
| CSV/XLSX Export | DONE | بر پایه Snapshot صادرشده |
| Audit Events | DONE | scoped و append-only |
| Production Auth/Scope/Permission Wiring | PARTIAL | Ports و Core Adapter موجود؛ پذیرش نهایی Host لازم است |
| Active Online Price Provider | TODO / OUT OF MVP | در Schema فعال و API عمومی فعلی وجود ندارد؛ نباید بدون تصمیم محصول فعال شود |

## 7. Tests

### اجرای واقعی در زمان Handoff

فرمان Collection:

```powershell
cd backend
py -3.14 -m pytest tests --collect-only -q -p no:cacheprovider
```

نتیجه: **635 test collected و 1 collection error**. خطا در `backend/tests/test_migrations.py` است؛ تست به فایل‌های Migration `0007_msp_resources_and_assignments.py` و `0008_price_intelligence.py` ارجاع می‌دهد، اما زنجیره Migration فعلی فقط تا `0006` وجود دارد.

برای مشخص شدن وضعیت سایر تست‌ها، همان Suite با حذف موقت فایل خراب از فرمان اجرا شد؛ هیچ تستی در کد Skip/حذف/تضعیف نشد:

```powershell
cd backend
py -3.14 -m pytest tests --ignore=tests/test_migrations.py -q -p no:cacheprovider --disable-warnings
```

نتیجه: **634 passed، 1 failed، 0 skipped، 1566 subtests passed**. Failure باقیمانده:

- `tests/test_devhost_connection.py::FixtureIdentityTests::test_the_seed_mirrors_the_frontend_mock_line_for_line`
- علت: `backend/devhost/seed.py` چند خط `progress_feed` دارد، ولی `frontend/src/adapters/mock/financial-items-adapter.js` همان Fixtureها را به‌صورت line-for-line منعکس نمی‌کند و حداقل یک Source به `manual_entry` تغییر کرده است.

### دسته‌های تست

- **Backend Unit/Domain:** منابع و برآورد، Price، Invoice، General Cost، Conversion، Attachment، Extraction، Report و قواعد Decimal.
- **Backend Integration:** Repository SQL، Core alignment، Scope/IDOR، Route authorization، Devhost و Migration.
- **Progress/Core:** تست‌های `test_schedule_contract.py`, `test_core_alignment.py`, `test_core_integration.py`, `test_progress*.py` و `test_wbs_report.py`.
- **Contract Kit:** Runner رسمی داخل Integration Kit ZIP نگه‌داری می‌شود. آخرین اجرای ثبت‌شده در جریان توسعه: **29 passed، 0 failed، 0 errors، 0 skipped**؛ پس از رفع دو Blocker فوق باید روی Working Tree نهایی دوباره اجرا شود.
- **Frontend:** فرمان رسمی `npm test` و `npm run check` است؛ در تهیه این Handoff اجرا نشده و وضعیت فعلی آن **NOT VERIFIED** است.

در وضعیت فعلی Release Gate سبز نیست، چون Full Backend Regression کامل Pass نشده است.

## 8. Known Issues

1. **P0 — Migration chain inconsistency:** `test_migrations.py` انتظار `0007` و `0008` دارد، اما فایل‌های Alembic موجود فقط `0001..0006` هستند. پیش از هر Migration واقعی باید یا فایل‌های تأییدشده بازیابی شوند یا انتظار تست به Head مصوب برگردد؛ حدس و ساخت Migration جدید ممنوع است.
2. **P0 — Fixture drift:** Mock خطوط مالی Frontend با `backend/devhost/seed.py` هم‌راستا نیست و Regression را Fail می‌کند. باید منبع حقیقت Fixture مشخص و دو سمت هماهنگ شوند.
3. **P0 — Production adapters:** Storage، OCR/Voice Extraction، Session/Auth و دسترسی Core باید توسط Composition Root اصلی BAMBO با Adapter واقعی Wire شوند؛ `devhost` Production host نیست.
4. **P0 — Permission mapping:** Core فعلی Permission کد `finance_report.issue` را نمی‌شناسد و عمداً deny می‌کند. این Permission نباید به `finance_report.export` نگاشت حدسی شود؛ Contract تیم Host لازم است.
5. **P1 — MSP resource/assignment availability:** `CoreProgressSnapshotProvider` از `msp_resources` و `msp_resource_assignments` فقط در صورت وجودشان استفاده می‌کند. Migration سازنده آن‌ها در Finance Head فعلی نیست؛ مالکیت و استقرار آن‌ها باید با Core تثبیت شود.
6. **P1 — Async extraction durability:** `BackgroundTasks` برای Demo/Local مناسب است، اما Queue durable، Retry عملیاتی و monitoring Production در این Repository تثبیت نشده است.
7. **P1 — Frontend mixed state:** بخشی از صفحات از API adapter و بخشی از Mock استفاده می‌کنند. اجرای standalone روی `43127` الزاماً داده را در PostgreSQL ذخیره نمی‌کند؛ Integration واقعی باید از Host روی Same-Origin و Context معتبر انجام شود.
8. **P1 — Dirty worktree:** تغییرات متعدد Commit‌نشده وجود دارد. قبل از تحویل Release باید Diffها review، تست و بر اساس مالکیت تیم‌ها Commit شوند.
9. **P2 — README drift:** `backend/README_FA.md` هنوز زنجیره Migration را تا `0005` نشان می‌دهد، در حالی که فایل `0006` وجود دارد. این فقط نقص مستندات است.
10. **P2 — OpenAPI/Contract re-verification:** بعد از تثبیت Worktree، `/openapi.json` باید دوباره با OpenAPI/JSON Schema و Mockهای Kit تطبیق و Contract Suite اجرا شود.

## 9. Deployment

### Local

- **Backend + Frontend یکپارچه:** Devhost پیش‌فرض روی `http://127.0.0.1:8010` اجرا می‌شود و UI و API را Same-Origin ارائه می‌کند.
- **Frontend مستقل:** `http://127.0.0.1:43127` برای UI/Mock؛ برای Persistence واقعی انتخاب اصلی نیست.
- **Database:** PostgreSQL، با Role جدا برای Runtime و Owner Migration.
- **Migration:** Host هنگام Startup خودکار Migration اجرا نمی‌کند؛ Operator باید جداگانه `alembic upgrade head` را اجرا کند.

متغیرهای اصلی:

| Variable | Purpose |
|---|---|
| `FINANCE_DEV_DSN` | اتصال Runtime با حداقل سطح دسترسی |
| `FINANCE_MIGRATION_DSN` | اتصال Owner فقط برای Alembic/DDL |
| `FINANCE_CORE_DSN` | اتصال read-only/مجاز به Schema یا DB میزبان Core در Devhost |
| `APP_ENV` | محیط؛ production نباید Mock/Seed را فعال کند |
| `DEBUG` | کنترل Debug |
| `FINANCE_DEMO_PORT` | override پورت پیش‌فرض 8010 |
| `FINANCE_ALLOW_SEED` | فقط Local/Test و همراه APP_ENV صریح؛ در Staging/Production ممنوع |
| `FRONTEND_ORIGIN` | مستندکننده Origin Demo؛ Devhost Same-Origin است و CORS اتکاگاه نیست |

نمونه اجرای Local:

```powershell
cd backend
alembic current
alembic upgrade head
python -m devhost
```

### Staging / Production

در این Repository Pipeline نهایی Deploy میزبان تعریف نشده است. روش صحیح Integration این است که برنامه اصلی BAMBO، Router مالی و Serviceها را Mount و Portهای Auth/Scope/Permission/File/Progress/Extraction را Wire کند؛ Migration با Credential Owner در Job جدا و قبل از Startup اجرا شود. قبل از Production الزامی است: Backup و Restore drill، تست Alembic روی PostgreSQL 16/18، اجرای Full Regression و Contract Kit، tenant isolation/IDOR، بررسی Secretها، و تأیید Permission mapping. Seed و Mock header نباید فعال باشند.

## 10. Development Workflow

### اجرای Backend

```powershell
python -m pip install -r backend/requirements.txt
cd backend
python -m devhost
```

### اجرای Frontend مستقل

```powershell
cd frontend
python -m http.server 43127 --bind 127.0.0.1
```

برای تست Persistence از Devhost یکپارچه روی 8010 یا Host واقعی استفاده شود، نه صرفاً Mock standalone.

### اجرای Migration

```powershell
cd backend
alembic history
alembic current
alembic upgrade head
```

`alembic downgrade` عملیات عادی Restore نیست و می‌تواند داده را حذف کند؛ طبق Recovery Runbook عمل شود.

### اجرای Test

```powershell
python -m pytest backend/tests -q

cd frontend
npm test
npm run check
```

Contract Kit پس از Extract کنترل‌شده ZIP و از ریشه خود Kit:

```powershell
python tests/run_contract_tests.py
```

چرخه پیشنهادی هر تغییر: مطالعه PRD مرتبط -> Contract/Schema Kit -> Audit کد -> تغییر کوچک -> Targeted tests -> Contract tests -> Full Backend Regression -> Frontend tests -> Review Diff. Migration و API جدید فقط با Gap قطعی Contract ایجاد شود.

## 11. Pending Tasks

### P0 — مانع Release

1. تعیین Source of Truth زنجیره Alembic و رفع ناسازگاری تست با نبود `0007/0008`، بدون Migration حدسی یا destructive.
2. همگام‌سازی Fixtureهای `frontend` و `devhost/seed.py` و سبز کردن Full Backend Regression.
3. اجرای مجدد تمام Backend، Frontend و Contract Kit روی Working Tree تثبیت‌شده.
4. Wire و Acceptance Test کردن Auth/Scope/Permission، Storage، Progress و Extraction Adapterهای Production.
5. تصویب Permission واقعی برای `finance_report.issue` در Host.

### P1 — لازم پیش از Integration نهایی

1. تعیین مالکیت و Availability جداول Core مربوط به `msp_resources` و `msp_resource_assignments` و تست روی Snapshot واقعی.
2. تست end-to-end مسیر `Frontend -> API -> Backend -> PostgreSQL -> Read Back -> Frontend` برای Resource، Estimate، Price، Invoice، File و Snapshot.
3. جایگزینی Queue in-process Extraction با سازوکار durable مورد تأیید عملیات، اگر SLA Production آن را لازم می‌داند.
4. تثبیت اینکه هر صفحه Frontend در Host mode از API Adapter استفاده می‌کند و هیچ Mock در Production-like path وارد نمی‌شود.
5. اجرای Backup/Restore و Migration rehearsal روی نسخه‌های DB هدف.

### P2 — بهبود و نگه‌داری

1. اصلاح drift مستندات Migration در `backend/README_FA.md` بعد از تصمیم P0.
2. تولید و نگه‌داری Artifact نسخه‌دار OpenAPI از برنامه نهایی.
3. افزودن observability عملیاتی برای latency/error/provider failure بدون ثبت Secret یا محتوای حساس مالی.
4. پاک‌سازی و دسته‌بندی فایل‌های آزمایشی/Untracked پس از تأیید مالک آن‌ها.

## 12. Important Decisions

- **Strict append-only price history:** قیمت جدید یک `PriceVersion` جدید است؛ نسخه قبلی Update/Delete نمی‌شود.
- **Project override resolution:** قیمت Project نسبت به Organization base با قواعد مؤثر زمانی Resolve می‌شود.
- **Immutable originals:** `originalQuantity` و `originalUnitPriceIrr` overwrite نمی‌شوند؛ اصلاح از Revision عبور می‌کند.
- **Immutable confirmed documents:** Invoice تأییدشده مستقیم PATCH/DELETE نمی‌شود؛ Void/Corrective/Reversal سند مرتبط جدید است.
- **Actual cost source:** فقط اسناد مالی مؤثر Confirmed/اصلاحی وارد هزینه واقعی می‌شوند؛ وضعیت پرداخت مبنا نیست.
- **AI zero effect before confirmation:** File processing و Extraction Draft مستقل از Invoice هستند و Draft اثر مالی صفر دارد.
- **Immutable report snapshot:** گزارش صادرشده ورودی‌ها و Metrics را Pin می‌کند؛ قیمت یا Revision جدید گزارش قبلی را تغییر نمی‌دهد.
- **Progress provider read-only:** Finance نه MPP را Parse می‌کند و نه داده Progress میزبان را mutate می‌کند.
- **Core ID separation:** `hostSnapshotId bigint` شناسه واقعی Core و `progressSnapshotId uuid` شناسه عمومی Finance است؛ تبدیل یا یکی‌انگاری آن‌ها ممنوع است.
- **No direct Core FK:** Reference Core در Adapter اعتبارسنجی می‌شود تا Lifecycle Core تاریخ مالی را Cascade نکند.
- **Tenant isolation:** Scope سازمان از Auth Context و Project از Path+membership می‌آید؛ هر Query هر دو را اعمال می‌کند.
- **Exact numeric:** IRR با `numeric(18,0)` و Quantity/Factor با Numeric دقیق ذخیره و با Decimal محاسبه می‌شود.
- **General cost:** هزینه عمومی می‌تواند بدون Quantity فیزیکی و به‌صورت مبلغ مستقیم مدل شود.
- **Preview before commit:** Import Preview تغییر مالی نهایی ایجاد نمی‌کند؛ Commit scoped و transactionally atomic است.
- **Adapter-first integration:** Auth، Scope، Permission، File، Progress، Activity و AI بیرون Domain و پشت Port هستند.
- **Same-origin frontend:** Browser با Backend میزبان Same-Origin کار می‌کند؛ Provider خارجی مستقیم از Frontend فراخوانی نمی‌شود.
- **Alembic ownership:** فقط Alembic مالک Schema است؛ Migration runner موازی مجاز نیست.

## 13. Final Status

- **وضعیت فعلی:** پیاده‌سازی Domain و API بخش عمده MVP موجود است و Schema پایه Finance تا Alembic `0006` تعریف شده؛ اما Working Tree فعلی Release-clean نیست و Regression Gate دو مشکل قطعی دارد.
- **آماده برای:** ادامه توسعه کنترل‌شده، Review فنی، اجرای Local با PostgreSQL و Integration آزمایشی با Devhost/Host adapters.
- **نیازمند تکمیل:** حل Migration-chain inconsistency، Fixture drift، اتصال و تأیید Adapterهای واقعی، Permission صدور گزارش، اجرای مجدد Contract/Regression/Frontend tests و rehearsal استقرار.
- **نتیجه مدیریتی:** **قابلیت‌های اصلی Backend برای Integration آماده‌اند، اما نسخه فعلی برای Production Deploy تأیید نشده است.** تا بسته شدن P0ها و سبز شدن تمام Gateها، Deploy Production باید متوقف بماند.
