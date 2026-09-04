# بسته Review مهاجرت Production ماژول مالی BAMBO

## منابع و محدوده

- PRD: `BAMBO_FINANCE_MVP_PRD_FA_v1.1`
- قرارداد فنی: `BAMBO_FINANCE_INTEGRATION_KIT_v1.1`
- PostgreSQL پایه Production: 16؛ هدف سازگاری: 18
- Migration Production در این محیط اجرا نشده است.

## ترتیب اجرا

ترتیب دیگر دستی نیست: Alembic زنجیره را نگه می‌دارد و اجرا می‌کند.

1. `0001_finance_core`
2. `0002_invoice_confirmation`
3. `0003_invoice_linked_documents`
4. `0004_report_snapshot_payload`
5. `0005_progress_snapshot_source_type`
6. `0006_progress_snapshot_host_reference`
7. `0007_msp_resources_and_assignments`
8. `0008_price_intelligence`
9. `0009_finance_task_resource_map` (head)

```powershell
alembic current      # این دیتابیس کجاست
alembic upgrade head
alembic current      # باید 0009 باشد
```

## 0008 — Price Intelligence Provider/Observation Layer

این Revision فقط ساختار افزایشی هسته قیمت آنلاین را ایجاد می‌کند. داده خام Provider ابتدا
در `price_observations` ثبت می‌شود و هیچ مسیر مستقیمی برای بازنویسی `price_versions` ندارد.
Observationها immutable هستند و تنها نتیجه Validation/Resolution تأییدشده می‌تواند از مسیر
سرویس موجود قیمت، یک PriceVersion جدید و append-only بسازد.

جداول افزوده‌شده:

- `price_providers`
- `provider_items`
- `provider_resource_mappings`
- `price_collection_runs`
- `price_observations`
- `price_collection_schedules`
- `price_resolution_policies`

تمام داده‌های عملیاتی Scope دوگانه سازمان/پروژه، FKهای `RESTRICT`، Decimal دقیق، وضعیت‌های
Text + CHECK و Indexهای Scope دارند. Up migration هیچ جدول یا رکورد قبلی را تغییر نمی‌دهد.
Downgrade جداول همین Revision را حذف می‌کند و بنابراین فقط با Backup و مجوز صریح قابل اجراست.

هر Revision داخل transaction خودش اجرا می‌شود (`env.py` آن را باز می‌کند) و اجرا روی اولین
خطا متوقف می‌شود. بدنه‌ها از نظر ساختاری rerunnable طراحی شده‌اند: `IF NOT EXISTS` روی جدول‌ها
و Indexها، `DROP TRIGGER IF EXISTS` پیش از هر `CREATE TRIGGER`، و برای 0005 یک بررسی صریح
`pg_constraint` که `ADD CONSTRAINT` نمی‌تواند بیان کند.

**نکته مهم برای دیتابیسی که Schema دارد ولی جدول `alembic_version` ندارد:** چون هر پنج
Revision rerunnable هستند، `alembic upgrade head` روی چنین دیتابیسی بدون خطا اجرا می‌شود و
در پایان `0005` را ثبت می‌کند. `alembic stamp` لازم نیست — و `stamp` روی دیتابیسی که وضعیت
واقعی‌اش تأیید نشده، خطرناک‌تر است، چون بدون اجرای چیزی ادعا می‌کند Migration انجام شده.

## 0009 — پیوند Task زمان‌بندی Core به Resource مالی

این Revision جدول `finance_task_resource_map` را می‌سازد: دقیقاً سه ستون
(`id uuid PK`، `task_id bigint`، `resource_id uuid`) با `UNIQUE (task_id, resource_id)`
و Index معکوس روی `resource_id`. دامنه سازمان/پروژه عمداً در این جدول تکرار نمی‌شود؛
هر دو سرِ پیوند آن را دارند و هر خواندنی از مسیر `finance_resources` عبور می‌کند.

**تصمیم ثبت‌شده — اولین FK به جدول Core:** `task_id` با
`REFERENCES msp_tasks (id) ON DELETE CASCADE` و `resource_id` با
`REFERENCES finance_resources (id) ON DELETE RESTRICT` تحمیل می‌شوند. این تصمیم صریح
مالک پروژه است و قاعده «صفر FK به Core» (مستند 0007) را فقط برای همین یک جفت برمی‌دارد؛
تست `test_core_alignment.py::test_exactly_the_sanctioned_key_reaches_into_core` همان
یک استثنا را پین می‌کند.

**پیش‌نیاز عملیاتی Production:** نقش Migration تولیدی طبق مستند 0007 امتیاز
`REFERENCES` روی جداول Core ندارد. پیش از اجرای 0009 در چنین محیطی الزامی است:

```sql
GRANT REFERENCES ON msp_tasks TO <migration role>;
```

بدون این GRANT، اجرای 0009 با خطای privilege متوقف می‌شود (و هیچ چیزی تغییر نمی‌کند؛
Revision داخل Transaction اجرا می‌شود).

**حفاظت Cross-Project:** یک Constraint Trigger
(`finance_task_resource_map_scope`) هنگام INSERT/UPDATE مسیر
`task → msp_snapshots.project_id` را با `finance_resources.project_id` مقایسه می‌کند و
در صورت اختلاف یا حل‌نشدن پروژه Task با SQLSTATE `23514`/`23503` رد می‌کند (fail-closed).
برابری سازمان — که سمت MSP ستونی برای آن ندارد — در لایه سرویس Import از روی Auth
Context تحمیل می‌شود.

**پیش‌بررسی وجود Core و قفل ضد-race:** ‏Revision ابتدا با `to_regclass('msp_tasks')`
fail-fast می‌کند (روی دیتابیس بدون Core، پیام دستورالعمل‌دار؛ آزموده: DB خام کاملاً
دست‌نخورده ماند) و سپس `LOCK TABLE finance_resources IN SHARE ROW EXCLUSIVE MODE`
می‌گیرد تا بین شمارش تکراری‌ها و ساخت Index یکتا هیچ نویسنده‌ای نلغزد.

**Index یکتای جزئی روی `finance_resources`:**
`ux_finance_resources_external_identity` روی
`(organization_id, project_id, external_resource_id)` فقط برای ردیف‌های زنده
(`external_resource_id IS NOT NULL AND deleted_at IS NULL`). پیش از ساخت، یک DO-block
داده تکراری را می‌شمارد و در صورت وجود با پیام شمارش‌دار متوقف می‌شود — این Migration
هرگز خودش ردیفی را merge یا حذف نمی‌کند.

**Downgrade:** فقط Trigger، Function، جدول پیوند و Index یکتا را حذف می‌کند؛ هیچ ردیفی
از `finance_resources` یا جداول Core لمس نمی‌شود. چون Downgrade جدولِ داده‌دار را حذف
می‌کند، اجرای آن در Production فقط با Backup و مجوز صریح مجاز است.

**نتیجه اجرا (محلی):** چرخه up/down/up روی دیتابیس خراشه سبز؛ ده رفتار runtime
(یکتایی جفت، دو شاخه رد Trigger، CASCADE/RESTRICT، رد NULL، Index جزئی با
soft-delete) با SQLSTATE مورد انتظار تأیید شد؛ `bambo_canonical_test` بدون خطا به 0009
ارتقا یافت (صفر گروه تکراری در پیش‌بررسی).

## نتیجه Validation

| Gate | نتیجه واقعی |
|---|---|
| تست ساختاری Migration | PASS — 15/15 |
| PostgreSQL 16 | BLOCKED — Docker daemon/سرور محلی موجود نیست |
| PostgreSQL 18 | BLOCKED — Docker daemon/سرور محلی موجود نیست |
| Rollback واقعی | BLOCKED |
| نبود `ON DELETE CASCADE` تاریخچه | PASS |
| `numeric(18,0)` پول و Decimal quantity | PASS |
| Scope indexها | PASS |
| Triggerهای immutable/append-only | PASS |

## 0005 — منبع نسخه پیشرفت

یک ستون `source_type text` به `progress_snapshot_refs` اضافه می‌کند تا مبدأ نسخه
پیشرفت به‌جای حدس‌زدن از پسوند نام فایل، صریح ثبت شود.

| مورد | وضعیت |
|---|---|
| `ADD COLUMN` بدون `DEFAULT` | PASS — تغییر فقط در Catalog، هیچ ردیفی بازنویسی نمی‌شود |
| اجرا روی PostgreSQL 16.4 واقعی | PASS — اجرا شد |
| اجرای دوباره (idempotent) | PASS — دو بار اجرا شد، نتیجه یکسان |
| Rollback واقعی | PASS — اجرا شد، ستون و CHECK حذف شد، سپس دوباره اعمال شد |
| Rollback دوباره (idempotent) | PASS |
| ردیف‌های موجود | PASS — هر ۳ ردیف `NULL` ماندند، هیچ Backfill انجام نشد |
| CHECK روی مقادیر مجاز | PASS — چهار مقدار مجاز و `NULL` پذیرفته؛ `msp`، `Microsoft Project` و `''` رد شد (همه در Transaction و Rollback) |
| سازگاری با Trigger تغییرناپذیری | PASS — `ALTER TABLE` Trigger را فعال نمی‌کند |

**نکته مهم برای Production:** Trigger `progress_snapshot_refs_immutable` هر `UPDATE`
را رد می‌کند (روی داده واقعی آزموده شد). یعنی `source_type` فقط در لحظه `INSERT`
قابل تعیین است و ردیف‌های موجود هرگز مقدار نمی‌گیرند مگر آنکه نسخه دوباره Import شود.
این عمدی است: تاریخچه پیشرفت append-only است و باید بماند.

**Backfill انجام نشد و نباید انجام شود.** مبدأ واقعی ردیف‌های موجود در هیچ‌جا ثبت
نشده است؛ `NULL` یعنی «ثبت نشده» که درست است، و `'other'` یعنی «ثبت شد که ابزاری
بیرون از فهرست بوده» که ادعایی بدون پشتوانه است.

## 0006 — مرجع Snapshot در Core

**مشکلی که حل می‌کند:** تا پیش از این، تنها چیزی که در `progress_snapshot_refs` می‌نوشت
Seed توسعه بود. روی یک دیتابیس واقعی — که Seed در آن ممنوع است — این جدول همیشه خالی
می‌ماند، هر گزارش زنده ۴۰۴ می‌گرفت و هیچ گزارشی هرگز صادر نمی‌شد.

**راه‌حل:** وقتی یک عملیات مالی باید به یک Snapshot مشخص Core گره بخورد، Finance از طریق
Adapter مرجع می‌سازد یا مرجع موجود را دوباره استفاده می‌کند. بدون هیچ عملیات دستی کاربر.

| موضوع | تصمیم |
|---|---|
| نوع شناسه Core | `bigint` — مطابق `msp_snapshots.id` و `msp_file_versions.id` |
| FK فیزیکی به Core | **ندارد.** Core با حذف پروژه، Snapshotها را CASCADE می‌کند؛ کلید RESTRICT حذف پروژه را در Core مسدود می‌کرد و CASCADE تاریخچه مالی را از بین می‌برد. اعتبارسنجی در Adapter انجام می‌شود |
| Idempotency | Index یکتای جزئی؛ یک Snapshot از Core هرگز دو مرجع Finance نمی‌سازد |
| ستون‌های قدیمی UUID | حذف **نشدند** و بازنویسی نشدند. `progress_snapshot_id` حالا شناسه عمومی خودِ Finance است؛ حذفش هر Route و هر گزارش صادرشده تغییرناپذیر را می‌شکست |
| Backfill | ندارد. `NULL` یعنی «به Snapshotی در Core وصل نبوده» که درباره هر ردیف قدیمی درست است |
| تریگر تغییرناپذیری | فعال نمی‌شود: `ADD COLUMN` بدون DEFAULT فقط تغییر Catalog است و `DROP NOT NULL` هم DDL است، نه UPDATE ردیف |

> **جدول نسخه Migration:** Alembic از `finance_alembic_version` استفاده می‌کند، نه
> `alembic_version` عمومی. Finance فقط مالک زنجیره Migration خودش است، نه مالک Migration
> کل دیتابیس مشترک BAMBO؛ اگر Core بعداً Alembic بگیرد، دو ماژول روی یک ردیف `version_num`
> برخورد نمی‌کنند.

## Expected Schema Diff

### جدول‌های جدید در Migration پایه

- `finance_project_settings`
- `finance_resources`
- `estimate_lines`
- `estimate_revisions`
- `price_versions`
- `unit_conversions`
- `progress_snapshot_refs`
- `progress_overrides`
- `invoices`
- `invoice_lines`
- `finance_attachments`
- `extraction_drafts`
- `report_snapshots`
- `finance_audit_events`
- `finance_import_batches`

تمام جدول‌ها هر دو کلید `organization_id` و `project_id` و index دامنه دارند.

### ستون‌های افزوده‌شده پس از Migration پایه

- `invoices.confirmation_idempotency_key`
- `report_snapshots.snapshot_payload`
- `report_snapshots.resource_version_ids`
- `progress_snapshot_refs.source_type`
- `progress_snapshot_refs.host_snapshot_id` — `bigint`, Nullable, بدون DEFAULT
- `progress_snapshot_refs.host_file_version_id` — `bigint`, Nullable, بدون DEFAULT
- `progress_snapshot_refs.source_file_version_id` — `NOT NULL` برداشته شد (ستون حذف نشد)

### Indexهای افزوده‌شده پس از Migration پایه

- `ux_invoices_confirmation_idempotency_scope`
- `ux_invoices_one_reversal_per_original`
- `ux_progress_snapshot_refs_host_snapshot` — یکتای **جزئی** روی
  `(organization_id, project_id, host_snapshot_id) WHERE host_snapshot_id IS NOT NULL`
- `ix_progress_snapshot_refs_host_file_version`

### Constraint و حفاظت تاریخچه

- FKهای تاریخچه با `ON DELETE NO ACTION`
- Price/Estimate revision/Conversion/Progress reference/Override/Report/Audit با trigger غیرقابل‌تغییر
- فاکتور Confirmed با trigger محافظ
- unique scoped برای idempotency تأیید و یک reversal برای هر original

تغییر destructive در Up migration: **NONE**. فایل `0004` برای رکوردهای Snapshot قبلی backfill کنترل‌شده انجام می‌دهد.

## Runtime و Configuration

- Python و dependencyهای pin‌شده در `requirements.txt`
- connection PostgreSQL از Composition Root میزبان
- Adapterهای Auth، Scope، Permission، File، Progress و AI از میزبان
- هیچ Secret، Mock Header یا Production URL در ماژول وجود ندارد

## Permission/Seed

Matrix کامل در `PERMISSION_MATRIX_FA.md` است. تصویب و Seed `finance_report.issue` و تصمیم fallback برای Confirm/Void/Progress/File توسط تیم BAMBO الزامی است.

## Backup و Recovery

Backup معتبر و Restore rehearsal پیش‌نیاز Migration است. دستورها و تفاوت Restore با Down migration در `RECOVERY_RUNBOOK_FA.md` ثبت شده‌اند.

## ریسک

ریسک فعلی: **MEDIUM / NOT CLEARED FOR PRODUCTION EXECUTION**، به‌دلیل اجرا نشدن چرخه Migration روی PG16/18، Restore rehearsal و تأیید نشدن Permission mapping میزبان. پس از موفقیت این Gateهای خارجی، ریسک فنی Migration قابل بازبینی مجدد است.

## Post-migration Verification

```powershell
python -m pytest backend/tests/test_migrations.py -q
python -m pytest backend/tests -q
python -m pip_audit -r backend/requirements.txt
```

در دیتابیس، وجود ۱۵ جدول، scope indexها، FKهای `NO ACTION`، triggerهای immutable و ستون/indexهای Migrationهای 0002 تا 0004 باید با catalog PostgreSQL تأیید شود.
