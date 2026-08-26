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

Alembic زنجیره را به‌ترتیب اجرا می‌کند و روی اولین خطا متوقف می‌شود؛ ترتیب دیگر دستی نیست.
از پوشه `backend/`:

```powershell
alembic current          # پیش از هر چیز: این دیتابیس الان کجاست؟
alembic upgrade head
alembic current          # پس از اجرا: باید 0005 باشد
```

`FINANCE_MIGRATION_DSN` باید به همان دیتابیسی اشاره کند که از آن Backup گرفته‌اید. Alembic
هیچ Fallbackی ندارد؛ اگر این متغیر تنظیم نشده باشد متوقف می‌شود، که عمدی است — یک رشته
اتصال حدس‌زده‌شده همان چیزی است که Migration را روی دیتابیس اشتباه اجرا می‌کند.

## Restore در دیتابیس جداگانه

دستور زیر فقط باید روی دیتابیس Recovery اختصاصی اجرا شود، نه روی Production فعال:

```powershell
pg_restore --exit-on-error --clean --if-exists --no-owner --no-privileges --dbname=$env:BAMBO_RECOVERY_DATABASE_URL bambo_finance_pre_migration.dump
```

پس از Restore، تعداد رکوردهای جدول‌های مالی، FKها، indexها و چند Snapshot/Invoice شناخته‌شده با مبدأ مقایسه شوند.

## Migration Rollback

**Down migration با Restore یکسان نیست.** Down فقط تغییرات Schema را به‌ترتیب معکوس
برمی‌گرداند؛ Revision پایه (`0001`) تمام جدول‌های مالی را حذف می‌کند و داده‌شان با آن‌ها
می‌رود. بنابراین اجرای Down کامل روی Production دارای داده **روش بازیابی قابل قبول نیست**.
راه بازیابی، Restore از Backup است — همان بخش بالا.

برای تمرین روی دیتابیس disposable:

```powershell
alembic downgrade -1        # یک قدم، قابل بازبینی
alembic current             # تأیید اینکه کجا ایستاده‌ایم
alembic downgrade base      # تمام Schema مالی را حذف می‌کند؛ فقط روی disposable
```

`alembic downgrade -1` عمداً به‌جای پرش مستقیم پیشنهاد شده: هر قدم قابل بازبینی است و
اشتباه در یک قدم کمتر از اشتباه در چهار قدم هزینه دارد.

## وضعیت Validation این محیط

- Backup test: **BLOCKED** — `pg_dump` و PostgreSQL در دسترس نیست.
- Restore test: **BLOCKED** — `pg_restore` و دیتابیس Recovery در دسترس نیست.
- Migration rollback test: **BLOCKED** — PG16/PG18 در دسترس نیست.
- اجرای Production: فقط توسط تیم اصلی BAMBO پس از Backup و Restore rehearsal.
