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

Migrationها به‌ترتیب عددی اجرا می‌شوند:

1. `0001_finance_core.up.sql`
2. `0002_invoice_confirmation.up.sql`
3. `0003_invoice_linked_documents.up.sql`
4. `0004_report_snapshot_payload.up.sql`

Rollback با فایل‌های هم‌نام `.down.sql` و به‌ترتیب معکوس انجام می‌شود. اجرای Production فقط بعد از Backup، Review تیم BAMBO و آزمون روی PostgreSQL 16 و 18 مجاز است.

## OpenAPI

پس از ساخت برنامه، قرارداد OpenAPI استاندارد FastAPI از `/openapi.json` قابل دریافت است. تمام مسیرهای مالی زیر پیشوند زیر قرار دارند:

```text
/api/projects/{projectId}/finance
```

جزئیات Adapterها، State موردنیاز برنامه و Permissionها در `INTEGRATION_GUIDE_FA.md` آمده است.
