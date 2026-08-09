# BAMBO Finance

پیاده‌سازی ماژول مالی BAMBO شامل Backend و Frontend مستقل، بر اساس PRD و Integration Kit نسخه ۱.۱.

## ساختار مخزن

- کد و مستندات Backend در `backend/`
- کد، دارایی‌ها، آزمون‌ها و مستندات Frontend در `frontend/`
- منابع مرجع پروژه در `Sources/`

## Backend

راهنمای اجرا و معماری Backend در `backend/README_FA.md` نگه‌داری می‌شود.

- راهنمای Backend و تست: [`backend/README_FA.md`](backend/README_FA.md)
- راهنمای اتصال به میزبان: [`backend/INTEGRATION_GUIDE_FA.md`](backend/INTEGRATION_GUIDE_FA.md)
- Migrationها: [`backend/migrations`](backend/migrations)

## Frontend

Frontend با HTML، CSS و JavaScript وانیلا و ES Modules توسعه یافته و Build Step، Framework، CDN یا درخواست خارجی مرورگر ندارد.

مستندات اصلی Frontend در `frontend/docs/` و راهنمای اختصاصی آن در `frontend/README.md` قرار دارند.

### اجرای محلی Frontend

```powershell
cd frontend
python -m http.server 43127 --bind 127.0.0.1
```

سپس `http://127.0.0.1:43127/` را باز کنید.

### آزمون Frontend

```powershell
cd frontend
npm test
npm run check
```

## منابع مرجع

فایل‌های PRD و Integration Kit نسخه ۱.۱ در پوشه `Sources/` قرار دارند. در تعارض، PRD نسخه ۱.۱ و سپس Contractهای Integration Kit نسخه ۱.۱ مقدم هستند.
