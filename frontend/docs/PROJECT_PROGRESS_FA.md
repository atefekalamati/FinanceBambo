# وضعیت و برنامه پیشرفت Frontend مالی BAMBO

آخرین به‌روزرسانی: ۱۴۰۵/۰۵/۱۸ — 2026-08-09

این سند مرجع زنده وضعیت توسعه Frontend است و بعد از هر Feature یا تغییر Scope به‌روزرسانی می‌شود. درصدها براساس وزن قابلیت‌های محصول و Gateهای پذیرش هستند، نه تعداد فایل‌ها.

منابع فعال از این تاریخ PRD و Integration Kit نسخه ۱.۱ هستند؛ ترتیب دقیق و اصلاحات در `docs/SOURCE_OF_TRUTH_FA.md` ثبت شده است.

## خلاصه مدیریتی

| شاخص | وضعیت فعلی |
|---|---|
| پیشرفت وزنی Frontend تا نسخه Mock-complete | حدود ۶۲٪ |
| فاز فعال | فاز ۵ — فاکتور دستی و چرخه عمر سند |
| کار بعدی قطعی | Idempotency Key و expected version در مرز Adapter فاکتور |
| تست‌های فعلی | ۶۷ تست موفق |
| صفحات فعال | امور مالی، تنظیمات مالی، اقلام و متره، قیمت‌ها، خوراک پیشرفت و فاکتورها |
| وابستگی مسدودکننده فعلی | ندارد؛ توسعه با Adapter آزمایشی ادامه دارد |
| وابستگی نهایی | دسترسی GitHub/OpenAPI و محیط Backend برای Integration |

## مقیاس وضعیت

- `کامل`: تمام معیارهای Definition of Done فاز بسته شده است.
- `در حال انجام`: بخشی قابل استفاده است اما Gate کامل نشده است.
- `شروع‌نشده`: هنوز پیاده‌سازی محصولی انجام نشده است.
- `وابسته`: اجرای نهایی به Backend یا تصمیم تیم اصلی BAMBO نیاز دارد.

## فازهای اصلی و وزن پیشرفت

| فاز | وزن | وضعیت | پیشرفت فاز | سهم کسب‌شده |
|---|---:|---|---:|---:|
| ۱. Foundation، Shell و Design Integration | ۱۲٪ | کامل | ۱۰۰٪ | ۱۲٪ |
| ۲. Settings، اقلام، متره، Revision و Import | ۱۸٪ | کامل | ۱۰۰٪ | ۱۸٪ |
| ۳. قیمت‌ها و تبدیل واحد | ۱۲٪ | کامل | ۱۰۰٪ | ۱۲٪ |
| ۴. Progress Snapshot و Override | ۱۰٪ | کامل | ۱۰۰٪ | ۱۰٪ |
| ۵. فاکتور دستی و چرخه عمر سند | ۱۶٪ | در حال انجام | حدود ۶۰٪ | حدود ۱۰٪ |
| ۶. فایل، OCR/Voice و AI Review | ۱۰٪ | شروع‌نشده | ۰٪ | ۰٪ |
| ۷. خلاصه مالی، گزارش و Snapshot | ۱۲٪ | شروع‌نشده | ۰٪ | ۰٪ |
| ۸. Audit، Accessibility و سخت‌سازی | ۵٪ | شروع‌نشده | ۰٪ | ۰٪ |
| ۹. Integration با Backend و Acceptance | ۵٪ | وابسته | ۰٪ | ۰٪ |
| **مجموع** | **۱۰۰٪** |  |  | **حدود ۶۲٪** |

## فاز ۱ — Foundation و اتصال بصری

وضعیت: `کامل`

- [x] ساختار Feature-based و ES Modules بدون Build Step
- [x] Shell مستقل و Host Context Adapter
- [x] Router و Permission visibility
- [x] Same-Origin API Client و Error Envelope پایه
- [x] Loading/Empty/Error/Denied primitives
- [x] RTL، Responsive و Print base
- [x] Tokenهای Dark/Light اصلی BAMBO
- [x] فونت محلی Vazirmatn Variable
- [x] Date Picker مشترک جلالی با تاریخ امروز براساس منطقه زمانی ایران
- [x] تبدیل تاریخ جلالی انتخاب‌شده به تاریخ استاندارد فقط در مرز Adapter/API
- [x] Asset و لوگوی رسمی
- [x] صفحه یکپارچه امور مالی بدون Dashboard/Sidebar داخلی
- [x] پورت ثابت توسعه `43127`

## فاز ۲ — تنظیمات، اقلام و متره

وضعیت: `کامل`

### تکمیل‌شده

- [x] زیربنای کل با Decimal string دقیق
- [x] سیاست IRR و نمایش پیش‌فرض تومان
- [x] دلیل و تاریخ اثر تغییر زیربنا
- [x] Revision append-only تنظیمات
- [x] Permission و Stateهای کامل تنظیمات
- [x] چهار نوع قلم مالی
- [x] واحد پایه و بُعد
- [x] هزینه عمومی بدون الزام واحد فیزیکی
- [x] خطوط مستقل Activity + Resource
- [x] نمایش مقدار اولیه و اصلاح‌شده
- [x] فرم ثبت قلم و خط متره
- [x] Table alignment/RTL/responsive مشترک
- [x] Revision عملیاتی مقدار خط با before/after/reason/actor/time
- [x] تاریخچه append-only هر خط بدون بازنویسی Original
- [x] هشدار مقدار اصلاح‌شده بیشتر از مقدار اولیه
- [x] کنترل STALE_VERSION و جلوگیری از Revision بدون تغییر

- [x] Estimate Import Preview با خطاهای ردیفی
- [x] Estimate Import Commit فقط پس از Preview معتبر و Modal تأیید
- [x] Stateها، Permission، Responsive و تست‌های مثبت/منفی Import
- [x] حفظ مقدار اولیه خطوط واردشده و ثبت Source فایل اکسل
- [x] عدم اختراع قالب ستون‌ها؛ قرارداد دقیق قالب در منابع تعریف نشده است

معیار پایان فاز: Original هرگز قابل ویرایش مستقیم نباشد؛ Revision و Import Preview/Commit با تمام Stateها و تست‌های مثبت/منفی کامل باشند.

## فاز ۳ — قیمت و تبدیل واحد

وضعیت: `کامل`

- [x] `P0` فهرست قیمت جاری اقلام
- [x] `P0` قیمت پایه سازمان و Override پروژه
- [x] `P0` تاریخچه append-only و تاریخ اثر
- [x] `P0` نمایش هم‌زمان قیمت پایه/اختصاصی/جاری/تاریخچه
- [x] `P1` Price Import Preview/Commit با واحد پول و Scope صریح
- [x] `P0` تبدیل واحد سازمانی و Override پروژه
- [x] `P0` اعتبارسنجی بُعد و UNIT_MISMATCH
- [x] اصلاح هم‌تاریخ قیمت با Strict Append-only و انتخاب قطعی جدیدترین نسخه
- [x] `P1` نمایش خطاهای Conflict/Validation از Adapter؛ ثبت قیمت و تبدیل طبق نسخه ۱.۱ append-only است و ویرایش درجا ندارد

## فاز ۴ — Progress Snapshot

وضعیت: `کامل`

- [x] `P0` فهرست Snapshotها و Metadata کامل قرارداد
- [x] `P0` Feed فقط‌خواندنی Assignmentها و جزئیات Task/Resource/Work
- [x] `P0` نمایش fallback sourceMethod و quality/warning
- [x] `P0` نمایش null به‌عنوان Missing، نه صفر
- [x] `P0` Manual Override با دلیل، Modal تأیید، Permission عمومی موجود و ثبت ممیزی‌شده Append-only
- [x] `P0` نمایش computed value کنار override value موجود در Feed
- [x] `P1` هشدار، مقدار و درصد انحراف هنگام اجرای بیشتر از برآورد، بدون Clamp و با دلیل ممیزی

## فاز ۵ — فاکتور دستی

وضعیت: `در حال انجام`

- [x] `P0` فهرست، فیلتر ترکیبی، Pagination پیش‌فرض ۵۰/سقف ۲۰۰ و جزئیات فقط‌خواندنی فاکتور
- [x] `P0` فرم سه‌مرحله‌ای سربرگ → خطوط → پیش‌نمایش و ثبت Draft بدون اثر مالی
- [x] `P0` خطوط چندگانه و اتصال به خط برآورد یا هزینه عمومی
- [x] `P0` تخفیف، مالیات، حمل و سایر هزینه‌ها با مبالغ صحیح ریال
- [x] `P0` هشدار شباهت فروشنده، شماره، تاریخ و مبلغ؛ نمایش سند مشابه و دلیل ممیزی اجباری برای ادامه
- [ ] `P0` Idempotency و expected version در مرز Adapter
- [ ] `P0` Confirm با Modal و immutable state
- [ ] `P0` Void/Reversal/Corrective linked flow

## فاز ۶ — فایل و AI Review

وضعیت: `شروع‌نشده`

- [ ] `P0` Upload عکس و ویس با محدودیت نوع/اندازه
- [ ] `P0` uploaded/processing/awaiting/failed states
- [ ] `P0` صفحه Review فایل و فیلدهای استخراج‌شده
- [ ] `P0` Confidence و Highlight کم‌اطمینان
- [ ] `P0` اصلاح فیلدها، Retry و Reject
- [ ] `P0` Confirm فقط توسط submitter مجاز
- [ ] `P0` اثر مالی صفر تا قبل از Confirm
- [ ] `P1` fallback ورود دستی در شکست Provider

## فاز ۷ — خلاصه مالی و گزارش‌ها

وضعیت: `شروع‌نشده`

- [ ] `P0` هشت KPI مالی PRD در صفحه امور مالی
- [ ] `P0` Warningها و N/A زیربنای صفر/خالی
- [ ] `P1` نمودارهای SVG/Canvas داخلی
- [ ] `P0` جدول جایگزین قابل چاپ/دسترس‌پذیر
- [ ] `P0` گزارش Live
- [ ] `P0` صدور Report Snapshot با Modal
- [ ] `P0` نمایش Snapshot صادرشده به‌صورت immutable
- [ ] `P0` چاپ A4 و PDF مرورگر
- [ ] `P0` CSV UTF-8 با BOM

## فاز ۸ — Audit و سخت‌سازی

وضعیت: `شروع‌نشده`

- [ ] `P0` فهرست و جزئیات Audit Event
- [ ] `P0` فیلتر actor/action/entity/time
- [ ] `P0` UX خطاهای 403/404/409/422/503
- [ ] `P0` QA کامل Keyboard/Focus/Screen Reader
- [ ] `P0` QA موبایل، تبلت، لپ‌تاپ و Print
- [ ] `P0` Race/Stale/Idempotency UX
- [ ] `P1` Performance فهرست‌ها و Pagination 50/200
- [ ] `P0` Contract و Regression tests نهایی Frontend

## فاز ۹ — Backend Integration و پذیرش

وضعیت: `وابسته به دسترسی Backend`

- [ ] دریافت OpenAPI و نمونه Payload واقعی
- [ ] ماتریس اختلاف Mock Adapter و Backend
- [ ] پیاده‌سازی Host/Production Adapterها
- [ ] تطبیق Permission mapping مصوب
- [ ] تست Scope، Error، Decimal، Version و Idempotency
- [ ] حذف Mock از Runtime تولید و حفظ Fixture در Test
- [ ] Integration QA روی Staging خصوصی
- [ ] اجرای Acceptance Testهای مرتبط Frontend
- [ ] Handoff و Known Limitations

## اولویت اجرای قطعی از این نقطه

```text
Estimate Import Preview/Commit
→ قیمت پایه و Override + تاریخچه
→ تبدیل واحد
→ Progress Snapshot + Override
→ فاکتور دستی end-to-end
→ File/AI Review
→ KPI و گزارش Snapshot/Print/CSV
→ Audit و Hardening
→ Backend Integration و Acceptance
```

## برآورد زمانی

برآورد زیر برنامه کاری است و بخشی از قرارداد محصول نیست. فرض آن Scope ثابت، بازخورد سریع و ادامه توسعه تمام‌وقت است.

| نقطه تحویل | زمان تقریبی از وضعیت فعلی |
|---|---:|
| پایان فاز ۲ | ۱ تا ۲ روز کاری |
| پایان فاز ۳ | ۳ تا ۴ روز کاری تجمعی |
| پایان فاز ۴ | ۴ تا ۵ روز کاری تجمعی |
| پایان فاز ۵ | ۷ تا ۹ روز کاری تجمعی |
| پایان فاز ۶ | ۹ تا ۱۱ روز کاری تجمعی |
| Mock-complete تا پایان فاز ۸ | ۱۲ تا ۱۵ روز کاری تجمعی |
| Integration و Acceptance پس از دسترسی Backend | ۳ تا ۵ روز کاری اضافه |

پس پایان Frontend مستقل تقریباً ۱۲ تا ۱۵ روز کاری و پایان نسخه متصل و قابل پذیرش تقریباً ۱۵ تا ۲۰ روز کاری از وضعیت فعلی برآورد می‌شود. تأخیر در Backend/OpenAPI، تصمیم Permissionهای حساس یا تغییر Scope این تاریخ را جابه‌جا می‌کند.

## Definition of Done هر Feature

هر Feature فقط در صورت تحقق همه موارد زیر `کامل` است:

- رفتار عادی و سناریوی اصلی
- Loading، Empty، Error، Denied و Success
- Permission visibility و مدیریت پاسخ Server
- Validation فارسی و نمایش request ID/conflict
- Decimal/Date/Currency مطابق قرارداد
- RTL و Responsive در موبایل، تبلت و دسکتاپ
- Keyboard، Focus و Accessibility
- Print در صفحات مرتبط
- Adapter آزمایشی منطبق با قرارداد و قابل جایگزینی
- تست مثبت، منفی و Regression
- مستندات و به‌روزرسانی همین فایل

## موارد خارج از برنامه Frontend

Backend، محاسبات مرجع مالی، Auth واقعی، Tenant isolation سمت Server، Migration، Provider واقعی AI، ذخیره فایل و Parse فایل MPP مسئولیت این مخزن نیستند.
