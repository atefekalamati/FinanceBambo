# BAMBO Finance Frontend

پوسته توسعه Frontend ماژول مالی BAMBO بر اساس PRD و Integration Kit نسخه ۱.۱ است؛ منابع قدیمی فقط در مواردی که نسخه ۱.۱ ساکت است استفاده می‌شوند.

پیش از شروع کدنویسی، `docs/FRONTEND_ONBOARDING_FA.md` و `docs/FRONTEND_ARCHITECTURE_FA.md` را بخوانید.

وضعیت لحظه‌ای، اولویت بعدی و برآورد پایان پروژه در `docs/PROJECT_PROGRESS_FA.md` ثبت می‌شود.

ترتیب منابع مرجع نسخه ۱.۱ و تفاوت‌های الزام‌آور در `docs/SOURCE_OF_TRUTH_FA.md` ثبت شده است.

محدودیت‌های قطعی:

- HTML/CSS و JavaScript وانیلا با ES Modules؛ بدون Build Step، Framework، CDN یا درخواست خارجی مرورگر.
- فارسی و RTL؛ مسیرهای Same-Origin و اتصال به میزبان فقط از طریق Adapter.
- هیچ استفاده‌ای از `X-Mock-User` در کد Production-like مجاز نیست.
- Decimalهای JSON رشته ASCII هستند؛ پول با `Number` یا float محاسبه نمی‌شود.
- مسیرهای `/mock/...` فقط محیط توسعه‌اند و Endpoint تولید BAMBO نیستند.
- فونت محلی پروژه `public/assets/fonts/Vazirmatn-Variable.woff2` است؛ CDN فونت استفاده نمی‌شود.

## اجرای محلی

پورت اختصاصی این پروژه `43127` است تا با پروژه‌های دیگر تداخل نداشته باشد. سرور را از پوشه `frontend` اجرا کنید:

```powershell
python -m http.server 43127 --bind 127.0.0.1
```

سپس `http://127.0.0.1:43127/` را باز کنید. Context نمایشی فقط برای Shell مستقل است و هیچ `X-Mock-User` یا API مالی ساختگی فراخوانی نمی‌کند.

آزمون‌های بدون Dependency:

```powershell
npm test
npm run check
```

مسیر تحویل در `docs/FRONTEND_DELIVERY_ROADMAP_FA.md` ثبت شده است. ماژول Sidebar یا Dashboard داخلی ندارد و داخل پوسته اصلی BAMBO mount می‌شود. Endpointهای مالی و اعداد KPI تا دریافت قرارداد Backend پیاده‌سازی/حدس زده نمی‌شوند.

## Featureهای قابل مشاهده

- امور مالی: `http://127.0.0.1:43127/#/finance`
- تنظیمات مالی: `http://127.0.0.1:43127/#/settings`
- اقلام و متره: `http://127.0.0.1:43127/#/financial-items`
- قیمت‌ها و تبدیل واحد: `http://127.0.0.1:43127/#/prices`
- خوراک پیشرفت مالی: `http://127.0.0.1:43127/#/progress`
- فاکتورها: `http://127.0.0.1:43127/#/invoices`

حالت‌های آزمایشی فاکتورها:

- Empty: `http://127.0.0.1:43127/?invoicesState=empty#/invoices`
- Error: `http://127.0.0.1:43127/?invoicesState=error#/invoices`

تنظیمات فعلاً از `src/adapters/mock/settings-adapter.js` تغذیه می‌شود. حالت‌های آزمایشی صفحه:

- حالت عادی: `http://127.0.0.1:43127/#/settings`
- Empty: `http://127.0.0.1:43127/?settingsState=empty#/settings`
- Error: `http://127.0.0.1:43127/?settingsState=error#/settings`

Loading هنگام هر بار ورود/Retry نمایش داده می‌شود و Permission Denied با نبود `finance.edit` در Context معتبر فعال خواهد شد. پارامترهای بالا فقط در runtime مستقل پذیرفته می‌شوند و در حالت Host نادیده گرفته خواهند شد.

حالت‌های آزمایشی اقلام و متره:

- Empty: `http://127.0.0.1:43127/?itemsState=empty#/financial-items`
- Error: `http://127.0.0.1:43127/?itemsState=error#/financial-items`
