# بسته Review مهاجرت Production ماژول مالی BAMBO

## منابع و محدوده

- PRD: `BAMBO_FINANCE_MVP_PRD_FA_v1.1`
- قرارداد فنی: `BAMBO_FINANCE_INTEGRATION_KIT_v1.1`
- PostgreSQL پایه Production: 16؛ هدف سازگاری: 18
- Migration Production در این محیط اجرا نشده است.

## ترتیب اجرا

1. `0001_finance_core.up.sql`
2. `0002_invoice_confirmation.up.sql`
3. `0003_invoice_linked_documents.up.sql`
4. `0004_report_snapshot_payload.up.sql`

هر فایل transaction مستقل دارد و باید با `ON_ERROR_STOP=1` اجرا شود. Upها از نظر ساختاری rerunnable طراحی شده‌اند.

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

### Indexهای افزوده‌شده پس از Migration پایه

- `ux_invoices_confirmation_idempotency_scope`
- `ux_invoices_one_reversal_per_original`

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
