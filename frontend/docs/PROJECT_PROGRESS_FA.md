# وضعیت و برنامه پیشرفت Frontend مالی BAMBO

آخرین به‌روزرسانی: ۱۴۰۵/۰۵/۲۹ — 2026-08-20

این سند مرجع زنده وضعیت توسعه Frontend است و بعد از هر Feature یا تغییر Scope به‌روزرسانی می‌شود. درصدها براساس وزن قابلیت‌های محصول و Gateهای پذیرش هستند، نه تعداد فایل‌ها.

منابع فعال از این تاریخ PRD و Integration Kit نسخه ۱.۱ هستند؛ ترتیب دقیق و اصلاحات در `docs/SOURCE_OF_TRUTH_FA.md` ثبت شده است.

## خلاصه مدیریتی

| شاخص | وضعیت فعلی |
|---|---|
| پیشرفت وزنی Frontend تا نسخه Mock-complete و اتصال فعلی | حدود ۹۵٪ |
| فاز فعال | فاز ۸ — Audit، Accessibility و سخت‌سازی |
| کار بعدی قطعی | QA کامل Keyboard/Focus/Screen Reader و Responsive/Print |
| تست‌های فعلی | ۱۵۰ تست موفق |
| صفحات فعال | امور مالی، تنظیمات مالی، اقلام و متره، قیمت‌ها، خوراک پیشرفت، فاکتورها، ورود تصویر/صدا، بررسی هوشمند، گزارش مالی و تاریخچه تغییرات |
| وابستگی مسدودکننده فعلی | ندارد. قراردادهایی که پیش‌تر مسدودکننده اعلام شده بودند روی `origin/master` وجود دارند؛ فهرست دقیق در «شکاف‌های واقعی Backend» پایین همین سند |
| وابستگی نهایی | محیط اجرایی Backend برای Integration. دسترسی به کد و قرارداد از طریق `origin/master` برقرار است |

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
| ۵. فاکتور دستی و چرخه عمر سند | ۱۶٪ | کامل | ۱۰۰٪ | ۱۶٪ |
| ۶. فایل، OCR/Voice و AI Review | ۱۰٪ | کامل در Mock | ۱۰۰٪ | ۱۰٪ |
| ۷. خلاصه مالی، گزارش و Snapshot | ۱۲٪ | در حال انجام | ۹۰٪ | ۱۰٪ |
| ۸. Audit، Accessibility و سخت‌سازی | ۵٪ | در حال انجام | ۶۵٪ | ۳٪ |
| ۹. Integration با Backend و Acceptance | ۵٪ | در حال انجام | ۶۰٪ | ۳٪ |
| **مجموع** | **۱۰۰٪** |  |  | **حدود ۹۵٪** |

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
- [x] ستون روند منطبق با قرارداد Backend شامل `trendDirection`، درصد آخرین تغییر و `trendPoints` همان Scope معتبر

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

وضعیت: `کامل`

- [x] `P0` فهرست، فیلتر ترکیبی، Pagination پیش‌فرض ۵۰/سقف ۲۰۰ و جزئیات فقط‌خواندنی فاکتور
- [x] `P0` فرم سه‌مرحله‌ای سربرگ → خطوط → پیش‌نمایش و ثبت Draft بدون اثر مالی
- [x] `P0` خطوط چندگانه و اتصال به خط برآورد یا هزینه عمومی
- [x] `P0` تخفیف، مالیات، حمل و سایر هزینه‌ها با مبالغ صحیح ریال
- [x] `P0` هشدار شباهت فروشنده، شماره، تاریخ و مبلغ؛ نمایش سند مشابه و دلیل ممیزی اجباری برای ادامه
- [x] `P0` Idempotency ساخت Draft، Conflict برای Payload متفاوت، نسخه اولیه و انتقال به awaitingConfirmation با expected version
- [x] `P0` Confirm با Modal، expected version، Idempotency، کنترل submitter و immutable state
- [x] `P0` Void/Reversal/Corrective linked flow با دلیل، Idempotency، اثر علامت‌دار و حفظ immutable سند اصلی

## فاز ۶ — فایل و AI Review

وضعیت: `کامل در Mock؛ اتصال واقعی وابسته به Backend`

- [x] `P0` Upload عکس و ویس با Allowlist دقیق نسخه ۱.۱ و سقف ۱۰/۲۵ مگابایت
- [x] `P0` کنترل مجوز و Stateهای Loading/Empty/Error/Denied/Success برای فضای فایل
- [x] `P0` نگهداری مستقل Metadata فایل و تأکید بر اثر مالی صفر
- [x] `P1` fallback ورود دستی در کنار مسیر بارگذاری
- [x] `P0` uploaded/processing/ready/failed فایل و awaitingReview/accepted/rejected بازبینی
- [x] `P0` صفحه Review فایل و فیلدهای استخراج‌شده
- [x] `P0` Confidence و Highlight کم‌اطمینان زیر ۸۰ درصد
- [x] `P0` اصلاح فیلدها، Retry نسخه‌دار و Reject بدون حذف فایل
- [x] `P0` Confirm فقط توسط submitter مجاز با expected version و Idempotency
- [x] `P0` اثر مالی صفر تا قبل از Confirm و جداسازی سه چرخه وضعیت
- [x] `P0` حفظ فایل در شکست Provider، نمایش خطا، Retry و مسیر ورود دستی
- [x] `P0` درج فاکتور تصویر/صدا در فهرست فاکتورها پس از Confirm انسانی

یادداشت Integration: Backend نسخه فعلی `POST /files` و `GET /files/{fileId}` و عملیات `retry/confirm` استخراج را دارد، اما موارد زیر برای اتصال واقعی Frontend وجود ندارند:

- Endpoint فهرست فایل‌های پروژه با Pagination/Filter
- Endpoint شروع استخراج از `fileId`، با وجود پیاده‌سازی متد `start` در Service
- Endpoint دریافت یک Draft و فهرست Draftهای استخراج
- Endpoint رد استخراج بدون حذف فایل
- فیلد `version` در `ExtractionDraftResponse`؛ درحالی‌که Confirm به `expectedVersion` نیاز دارد

این موارد فقط در Adapter آزمایشی شبیه‌سازی شده‌اند و هیچ فایل Backend تغییر نکرده است.

## فاز ۷ — خلاصه مالی و گزارش‌ها

وضعیت: `در حال انجام`

- [x] `P0` هشت KPI مالی PRD در صفحه یکپارچه امور مالی
- [x] `P0` Warningها و N/A زیربنای صفر/خالی
- [x] `P1` نمودار SVG داخلی Breakdown چهار نوع قلم با مقیاس مشترک دقیق
- [x] `P0` جدول جایگزین قابل چاپ/دسترس‌پذیر برای داده‌های نمودار
- [x] `P0` گزارش Live با تاریخ گزارش جلالی و تاریخ استاندارد در API
- [x] `P0` صدور Report Snapshot با Modal صریح
- [x] `P0` نمایش مرجع، شاخص‌ها و شناسه‌های Snapshot صادرشده به‌صورت immutable
- [x] `P0` چاپ A4 و PDF مرورگر
- [x] `P0` CSV UTF-8 با BOM از Endpoint واقعی Backend

محدودیت قرارداد: پاسخ فعلی `GET /report-snapshots/{reportId}` فقط مرجع Snapshot و `calculatedMetrics` را بازمی‌گرداند و Endpoint فهرست Snapshotهای صادرشده نیز تعریف نشده است. در نتیجه نمایش مجدد تمام Breakdown، انحراف‌ها و ریز ورودی‌های Pin‌شده پس از Refresh، بدون تغییر قرارداد Backend ممکن نیست و در Frontend شبیه‌سازی نشده است.

## فاز ۸ — Audit و سخت‌سازی

وضعیت: `در حال انجام`

- [x] `P0` فهرست و جزئیات Audit Event منطبق با `origin/master@91d8380`
- [x] `P0` فیلتر actor/action/entity/time روی آرایه دریافتی Backend
- [x] `P0` UX مشترک خطاهای 403/404/409/422/503 با کد، request ID، جزئیات فیلدی، Retry کنترل‌شده و Focus قابل دسترس
- [x] زیرساخت مشترک Dialog برای نام قابل‌خواندن، Focus اولیه و بازگرداندن Focus به کنترل بازکننده
- [ ] `P0` QA کامل Keyboard/Focus/Screen Reader
- [ ] `P0` QA موبایل، تبلت، لپ‌تاپ و Print
- [ ] `P0` Race/Stale/Idempotency UX
- [x] `P1` Pagination 50/200 روی فهرست‌های Audit، فاکتور، فایل و استخراج
- [ ] `P0` Contract و Regression tests نهایی Frontend

یادداشت قرارداد (اصلاح‌شده ۱۴۰۵/۰۵/۲۹): برخلاف آنچه پیش‌تر در همین سند نوشته شده بود، `GET /audit-events` پارامترهای `page` و `pageSize` را می‌پذیرد (`page ge 1`، `pageSize` بین ۱ و ۲۰۰ با پیش‌فرض ۵۰). آنچه ندارد **فیلتر سروری** و **پاکت صفحه‌بندی** است: پاسخ یک `list[AuditEventResponse]` خام است، نه `{items, page, totalCount, totalPages}` مثل `/invoices`، `/files` و `/extractions`. بنابراین تعداد کل رویدادها قابل محاسبه نیست و تنها نشانه «رویداد بیشتری هست» این است که صفحه دریافتی کامل باشد. Frontend همین رفتار را پیاده کرده و شمارنده صفحه به‌جای «کل رویدادها» می‌گوید «رویدادهای بارگذاری‌شده». فیلتر همچنان Client-side است و برای حجم بالا باید به OpenAPI افزوده شود.

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
