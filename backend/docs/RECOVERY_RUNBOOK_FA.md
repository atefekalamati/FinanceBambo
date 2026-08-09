# Runbook پشتیبان‌گیری، Restore و Rollback

این Runbook برای تمرین Local/Staging و اجرای کنترل‌شده توسط تیم اصلی BAMBO است. در این Repository هیچ Credential یا دسترسی Production وجود ندارد و هیچ Backup واقعی Production اجرا نشده است.

## پیش‌نیاز

- ابزارهای هم‌نسخه سرور: `psql`، `pg_dump` و `pg_restore`
- متغیر محیطی `BAMBO_DATABASE_URL` برای دیتابیس مبدأ
- متغیر محیطی `BAMBO_RECOVERY_DATABASE_URL` برای دیتابیس بازیابی جداگانه و خالی
- محل امن و رمزنگاری‌شده برای فایل Backup

## Backup پیش از Migration

```powershell
pg_dump --format=custom --no-owner --no-privileges --file=bambo_finance_pre_migration.dump $env:BAMBO_DATABASE_URL
```

صحت اولیه فایل:

```powershell
pg_restore --list bambo_finance_pre_migration.dump
```

## اجرای Migration

هر فایل Up با توقف روی اولین خطا و به‌ترتیب اجرا شود:

```powershell
psql $env:BAMBO_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0001_finance_core.up.sql
psql $env:BAMBO_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0002_invoice_confirmation.up.sql
psql $env:BAMBO_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0003_invoice_linked_documents.up.sql
psql $env:BAMBO_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0004_report_snapshot_payload.up.sql
```

## Restore در دیتابیس جداگانه

دستور زیر فقط باید روی دیتابیس Recovery اختصاصی اجرا شود، نه روی Production فعال:

```powershell
pg_restore --exit-on-error --clean --if-exists --no-owner --no-privileges --dbname=$env:BAMBO_RECOVERY_DATABASE_URL bambo_finance_pre_migration.dump
```

پس از Restore، تعداد رکوردهای جدول‌های مالی، FKها، indexها و چند Snapshot/Invoice شناخته‌شده با مبدأ مقایسه شوند.

## Migration Rollback

Down migration با Restore یکسان نیست. Down فقط تغییرات Schema را به‌ترتیب معکوس برمی‌گرداند و `0001_finance_core.down.sql` تمام جدول‌های مالی را حذف می‌کند؛ بنابراین اجرای Down کامل روی Production دارای داده روش بازیابی قابل قبول نیست.

برای تمرین روی دیتابیس disposable:

```powershell
psql $env:BAMBO_RECOVERY_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0004_report_snapshot_payload.down.sql
psql $env:BAMBO_RECOVERY_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0003_invoice_linked_documents.down.sql
psql $env:BAMBO_RECOVERY_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0002_invoice_confirmation.down.sql
psql $env:BAMBO_RECOVERY_DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/0001_finance_core.down.sql
```

## وضعیت Validation این محیط

- Backup test: **BLOCKED** — `pg_dump` و PostgreSQL در دسترس نیست.
- Restore test: **BLOCKED** — `pg_restore` و دیتابیس Recovery در دسترس نیست.
- Migration rollback test: **BLOCKED** — PG16/PG18 در دسترس نیست.
- اجرای Production: فقط توسط تیم اصلی BAMBO پس از Backup و Restore rehearsal.
