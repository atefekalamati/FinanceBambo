# Backend ماژول مالی BAMBO

این Backend براساس PRD و Integration Kit نسخه ۱.۱، به‌صورت مستقل از پیاده‌سازی داخلی میزبان BAMBO ساخته شده است. هیچ Mock Header، مسیر مستقیم MPP، آدرس Production یا منطق احراز هویت میزبان در آن وجود ندارد.

## پیش‌نیازها

- Python 3.12
- PostgreSQL 16؛ سازگاری SQL با PostgreSQL 18 نیز باید در محیط BAMBO تأیید شود
- Adapterهای میزبان برای Auth، Scope، Permission، File Storage، Progress Snapshot و AI Extraction

نصب وابستگی‌ها از ریشه Repository:

```powershell
python -m pip install -r backend/requirements.txt
```

## تست‌ها

```powershell
python -m pytest backend/tests -q
```

Contract Testهای Integration Kit باید با runner داخل همان Kit اجرا شوند:

```powershell
python tests/run_contract_tests.py
```

بررسی امنیت وابستگی‌ها:

```powershell
python -m pip_audit -r backend/requirements.txt
```

## Migration

**Alembic تنها مرجع Schema است.** پیش‌تر فایل‌های `migrations/*.sql` با یک اجراکننده دستی
اعمال می‌شدند؛ آن مکانیزم حذف شد، چون دو سیستم Migration روی یک Schema می‌توانند درباره
«چه چیزی اعمال شده» اختلاف داشته باشند و فقط یکی‌شان چیزی ثبت می‌کند. تاریخچه SQL قبلی در
Git باقی است.

زنجیره Revisionها، به‌ترتیب تاریخی:

```text
0001_finance_core
  → 0002_invoice_confirmation
    → 0003_invoice_linked_documents
      → 0004_report_snapshot_payload
        → 0005_progress_snapshot_source_type   (head)
```

دستورها از پوشه `backend/` اجرا می‌شوند:

```powershell
alembic upgrade head     # تا آخرین Revision
alembic current          # Revision فعلی این دیتابیس
alembic history          # کل زنجیره
alembic downgrade -1     # فقط یک قدم به عقب
```

اتصال از `FINANCE_MIGRATION_DSN` خوانده می‌شود — نقش Owner که مجاز به DDL است. `alembic.ini`
هیچ رشته اتصالی ندارد و اگر این متغیر تنظیم نشده باشد، Alembic با خطای صریح متوقف می‌شود و
هیچ دیتابیسی را حدس نمی‌زند.

> **Downgrade جایگزین Restore نیست.** `alembic downgrade base` تمام جدول‌های مالی را حذف
> می‌کند و داده را از بین می‌برد. برای بازیابی، به `docs/RECOVERY_RUNBOOK_FA.md` مراجعه کنید.

اجرای Production فقط بعد از Backup، Review تیم BAMBO و آزمون روی PostgreSQL 16 و 18 مجاز است.

## OpenAPI

پس از ساخت برنامه، قرارداد OpenAPI استاندارد FastAPI از `/openapi.json` قابل دریافت است. تمام مسیرهای مالی زیر پیشوند زیر قرار دارند:

```text
/api/projects/{projectId}/finance
```

جزئیات Adapterها، State موردنیاز برنامه و Permissionها در `INTEGRATION_GUIDE_FA.md` آمده است.
