# BAMBO Finance Frontend

پوسته توسعه Frontend ماژول مالی BAMBO بر اساس PRD و Integration Kit نسخه ۱.۱ است؛ منابع قدیمی فقط در مواردی که نسخه ۱.۱ ساکت است استفاده می‌شوند.

پیش از شروع کدنویسی، `docs/FRONTEND_ONBOARDING_FA.md` و `docs/FRONTEND_ARCHITECTURE_FA.md` را بخوانید.

وضعیت لحظه‌ای، اولویت بعدی و برآورد پایان پروژه در `docs/PROJECT_PROGRESS_FA.md` ثبت می‌شود. ترتیب منابع مرجع و تفاوت‌های الزام‌آور نیز در `docs/SOURCE_OF_TRUTH_FA.md` آمده است.

## محدودیت‌های قطعی

- HTML/CSS و JavaScript وانیلا با ES Modules؛ بدون Build Step، Framework، CDN یا درخواست خارجی مرورگر.
- فارسی و RTL؛ مسیرهای Same-Origin و اتصال به میزبان فقط از طریق Adapter.
- هیچ استفاده‌ای از `X-Mock-User` در کد Production-like مجاز نیست.
- Decimalهای JSON رشته ASCII هستند؛ پول با `Number` یا float محاسبه نمی‌شود.
- مسیرهای `/mock/...` فقط محیط توسعه‌اند و Endpoint تولید BAMBO نیستند.
- فونت محلی پروژه `public/assets/fonts/Vazirmatn-Variable.woff2` است؛ CDN فونت استفاده نمی‌شود.

## اجرای محلی

پورت اختصاصی پروژه `43127` است. دستور زیر را از همین پوشه `frontend` اجرا کنید:

```powershell
python -m http.server 43127 --bind 127.0.0.1
```

سپس `http://127.0.0.1:43127/` را باز کنید.

## آزمون‌ها

```powershell
npm test
npm run check
```

## صفحات فعال

- امور مالی: `#/finance`
- تنظیمات مالی: `#/settings`
- اقلام و متره: `#/financial-items`
- قیمت‌ها و تبدیل واحد: `#/prices`
- خوراک پیشرفت مالی: `#/progress`

مسیر تحویل در `docs/FRONTEND_DELIVERY_ROADMAP_FA.md` ثبت شده است. ماژول Sidebar یا Dashboard داخلی ندارد و داخل پوسته اصلی BAMBO mount می‌شود. Endpointهای مالی تا دریافت قرارداد Backend پیاده‌سازی یا حدس زده نمی‌شوند.
