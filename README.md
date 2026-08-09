# BAMBO Finance

پیاده‌سازی ماژول مالی BAMBO شامل Backend و Frontend مستقل، بر اساس PRD و Integration Kit نسخه ۱.۱.

## Backend

کد Backend در پوشه `backend/` قرار دارد. راهنمای اجرا و معماری آن در `backend/README_FA.md` نگه‌داری می‌شود.

## Frontend

Frontend با HTML، CSS و JavaScript وانیلا و ES Modules توسعه یافته و Build Step، Framework، CDN یا درخواست خارجی مرورگر ندارد.

مستندات اصلی Frontend:

- راهنمای شروع: `docs/FRONTEND_ONBOARDING_FA.md`
- معماری: `docs/FRONTEND_ARCHITECTURE_FA.md`
- وضعیت و اولویت توسعه: `docs/PROJECT_PROGRESS_FA.md`
- ترتیب منابع نسخه ۱.۱: `docs/SOURCE_OF_TRUTH_FA.md`
- Roadmap تحویل: `docs/FRONTEND_DELIVERY_ROADMAP_FA.md`

### اجرای محلی Frontend

```powershell
python -m http.server 43127 --bind 127.0.0.1
```

سپس `http://127.0.0.1:43127/` را باز کنید.

### آزمون Frontend

```powershell
npm test
npm run check
```

### صفحات فعال Frontend

- امور مالی: `#/finance`
- تنظیمات مالی: `#/settings`
- اقلام و متره: `#/financial-items`
- قیمت‌ها و تبدیل واحد: `#/prices`
- خوراک پیشرفت مالی: `#/progress`

## منابع مرجع

فایل‌های PRD و Integration Kit نسخه ۱.۱ در پوشه `Sources/` قرار دارند. در تعارض، PRD نسخه ۱.۱ و سپس Contractهای Integration Kit نسخه ۱.۱ مقدم هستند.
