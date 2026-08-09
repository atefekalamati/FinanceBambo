# راهنمای آموزشی و خلاصه اجرایی Frontend مالی BAMBO

مبنای این سند فقط «BAMBO Finance MVP PRD FA نسخه ۱.۰» و «BAMBO Finance Integration Kit نسخه ۱.۰.۰» است. در اختلاف، PRD مقدم است. مسیرهای PRD قرارداد محصولی پیشنهادی‌اند؛ مسیرهای `/mock/...` فقط قرارداد توسعه محلی‌اند و Endpoint تولید نیستند.

## ۱. معرفی پروژه

### هدف، مسئله، کاربر و ارزش

ماژول مالی، «پول روی واقعیت پروژه» را به کنترل پروژه BAMBO وصل می‌کند. داده متره/برنامه از خوراک گزارش پیشرفت یا Excel/ورود دستی، مصرف و اجرا از Snapshot پیشرفت، هزینه واقعی از فاکتور تأییدشده و هزینه آینده از قیمت روز می‌آید.

مسئله اصلی این است که مالک معمولاً برآورد اولیه، هزینه واقعی، ارزش روز کار انجام‌شده و پول لازم تا تکمیل را یکجا ندارد؛ قیمت‌ها تغییر می‌کنند و فاکتورهای پراکنده ورود داده را کند می‌کنند.

کاربران اصلی:

- رئیس سازمان/مالک: دید کامل و عملیات حساس.
- کارشناس مالی: مدیریت کامل داده مالی و گزارش.
- مدیر پروژه: مشاهده پروژه، ثبت فاکتور و تأیید Draft ارسالی خودش.
- کارشناس کنترل پروژه: مشاهده خوراک و Override ممیزی‌شده پیشرفت.
- Finance Viewer: مشاهده داشبورد/گزارش و داده استخراج‌شده؛ بدون فایل اصلی.
- مهمان: بدون دسترسی مالی.

ارزش ایجادشده سه‌لایه است: واقعیت گذشته با هزینه واقعی فاکتورها، ارزش امروز با قیمت روز کار انجام‌شده، و تصمیم آینده با پول لازم تا تکمیل و Forecast نهایی.

## ۲. معماری کلی سیستم

```text
Microsoft Project
  → ماژول گزارش پیشرفت BAMBO
  → Progress Snapshot نسخه‌دار و فقط‌خواندنی
  → ماژول مالی (Backend محاسبات/تاریخچه/API)
  → Frontend مالی (نمایش/ورودی/تأیید/چاپ)
  → Shell و Context میزبان BAMBO
```

- Frontend الزاماً HTML/CSS/JavaScript وانیلا با ES Modules، RTL، بدون Build، Framework، CDN یا درخواست خارجی مرورگر است.
- ارتباط با Backend از URL نسبی Same-Origin و Adapter انجام می‌شود. JSON محصول camelCase و Decimalها رشته ASCII هستند.
- Integration Kit محیط مستقل و پاک‌سازی‌شده برای Context، Scope، Permission، Progress Feed، File/AI، Schema، نمونه داده، Mock Host و Contract Test است؛ خود ماژول مالی یا API واقعی BAMBO نیست.
- میزبان، AuthContext معتبر، سازمان، پروژه و mountهای sidebar/project context/live region/`finance-module-root` را می‌دهد. تیم اصلی BAMBO Adapterهای واقعی Auth/Scope/File/Progress، permission seed، migration، merge و deploy را انجام می‌دهد.
- هر داده و Query مالی با هر دو Scope سازمان و پروژه محدود می‌شود. `organizationId` از نوع UUID و `projectId` متن پایدار با الگوی `^[A-Za-z0-9_-]+$` است.
- Frontend حق پیاده‌سازی login/session میزبان یا استفاده Production-like از `X-Mock-User` را ندارد.

## ۳. محدوده MVP

### داخل MVP

- چهار نوع قلم مالی: متریال، نیروی انسانی، دستگاه/تجهیزات و هزینه عمومی.
- خطوط مستقل Activity + Resource؛ ورود از Progress Feed، Excel و دستی.
- مقدار اولیه قفل‌شده، مقدار اصلاح‌شده و Revisionهای append-only.
- قیمت پایه سازمان، Override پروژه، تاریخچه قیمت و Import با Preview/Commit.
- تبدیل واحد نسخه‌دار در سطح سازمان و Override پروژه.
- مصرف Snapshot پیشرفت، fallback اجرا و Override ممیزی‌شده.
- فاکتور چندردیفی دستی/عکس/ویس، Draft AI، Confidence، تأیید انسانی، Void/Reversal/Corrective.
- داشبورد، گزارش زنده، Snapshot گزارش تغییرناپذیر، HTML چاپی A4، PDF مرورگر و CSV با BOM.
- زیربنای کل و هزینه واقعی/Forecast هر مترمربع.
- Audit، Scope/Permission، فایل امن، Idempotency و Optimistic Concurrency.

### خارج از MVP و ممنوع برای توسعه

- انبار/موجودی؛ خریداری‌شده و مصرف‌شده فقط دو مقدار مستقل‌اند.
- خزانه‌داری، پرداخت جزئی، بانک، چک و تسویه؛ هر فاکتور تأییدشده هزینه واقعی است.
- حسابداری دوبل، دفتر کل، ترازنامه، مالیات سازمانی و حقوق.
- بازکردن یا Parse مستقیم MPP در Finance.
- قیمت آنلاین اینترنتی، XLSX اجباری، PDF سمت سرور و گزارش زمان‌بندی‌شده.
- فروش/پیش‌فروش، ماژول انبار، Earned Value و Forecast پیشرفته.
- ساخت سازمان/پروژه یا هویت مالک جدید.
- Framework، ORM Frontend، chart library خارجی، CDN یا Browser-to-AI Provider.

## ۴. ماژول‌های مالی

| ماژول | هدف/کاربرد | ورودی | خروجی و ارتباط |
|---|---|---|---|
| داشبورد | تصمیم سریع مالک با ۸ KPI و نمودار/هشدار | Summary، قیمت روز، اجرا، فاکتور Confirmed، زیربنا | نمای زنده و رفتن به جزئیات/صدور گزارش |
| اقلام مالی | تعریف قلم مشترک | type، code، title، baseUnit، dimension، externalResourceId | مرجع قیمت، خطوط برآورد و Invoice Line |
| برآورد | اتصال هر Activity+Resource | شناسه فعالیت/Assignment، قلم، مقدار/منبع | original/revised quantity، خرید/اجرا، انحراف و Revision |
| قیمت‌ها | ارزش‌گذاری اولیه و جاری | قیمت پایه سازمان یا Override پروژه، تاریخ اثر، واحد | PriceVersion؛ ورودی KPI و Forecast، بدون تغییر گذشته |
| تبدیل واحد | هم‌مقیاس‌کردن مقدار | from/to، factor، Scope، تاریخ اثر | Conversion version برای خرید/مقدار/گزارش؛ ابعاد ناسازگار رد می‌شوند |
| Snapshot پیشرفت | دریافت واقعیت اجرا | Snapshot و Assignmentهای read-only | executed quantity، sourceMethod، quality/warning؛ بدون write-back |
| فاکتورها | ثبت هزینه واقعی | Header، Lines، adjustments، source و attachment | Draft/Confirmed/Void/Corrective؛ فقط Confirmed روی Actual اثر دارد |
| AI | تسریع ورود عکس/ویس | فایل امن، hints و Provider adapter | ExtractionDraft چندفیلدی/چندخطی با Confidence؛ اثر مالی قبل Confirm صفر |
| گزارش‌ها | نمایش زنده و تثبیت گزارش دوره‌ای | تاریخ، Progress Snapshot و نسخه تمام ورودی‌ها | Live report یا immutable ReportSnapshot، print/PDF browser/CSV |
| Audit | قابلیت ردیابی عملیات حساس | actor، action، before/after، reason، scope، time | تاریخچه append-only و جزئیات قابل فیلتر |
| تنظیمات | داده مالی پروژه | زیربنا، currency/display و conversionها | revision زیربنا و مبنای شاخص هر مترمربع |

## ۵. Workflow کامل سیستم

```text
انتخاب پروژه و Context معتبر
→ ثبت زیربنای کل
→ ورود اقلام/متره از Progress Feed یا Excel یا دستی
→ تأیید واحد پایه و بُعد
→ ثبت قیمت اولیه
→ دریافت Snapshotهای پیشرفت و تعیین مقدار اجرا با fallback
→ به‌روزرسانی قیمت روز با نسخه جدید
→ ثبت فاکتور دستی یا Upload عکس/ویس
→ برای AI: processing → awaiting confirmation → اصلاح و Confirm همان ارسال‌کننده
→ محاسبه Actual، ارزش روز، باقی‌مانده و Forecast
→ مشاهده Dashboard/گزارش زنده
→ انتخاب تاریخ و Progress Snapshot
→ Pin نسخه مقادیر، قیمت‌ها، تبدیل‌ها، فاکتورها و زیربنا
→ صدور ReportSnapshot تغییرناپذیر
→ چاپ A4/PDF مرورگر یا CSV
```

fallback مقدار اجرا به‌ترتیب: `actualQuantity/Actual Work سازگار`، سپس `Assignment Work % × planned`، سپس `Task Progress % × planned`، و در آخر Override دستی. مقدار گمشده `null` است نه صفر؛ عبور مقدار از برنامه Clamp نمی‌شود و هشدار/Audit می‌خواهد.

## ۶. صفحات Frontend

نام Endpointها مطابق PRD پیشنهادی است و پیش از اتصال تولید باید Adapter تیم اصلی آن‌ها را تثبیت کند.

| صفحه | نمایش و عملیات | API پیشنهادی | State و Validation کلیدی |
|---|---|---|---|
| Dashboard | ۸ KPI، نمودارها، هشدارها، آخرین Snapshot/Invoice؛ فیلتر تاریخ و صدور گزارش | `GET finance/summary`, `GET finance/reports/live`, `POST finance/report-snapshots` | loading/empty/error/denied/content؛ N/A برای زیربنای خالی/صفر؛ modal صدور |
| اقلام و متره | Activity+Resource، original/revised/executed/purchased، source/quality؛ import/edit/revision/override | resources، estimate-lines، revisions، import estimate preview/commit، progress override | UUID پایدار؛ general_cost می‌تواند unit/quantity نداشته باشد؛ Revision/Override دلیل می‌خواهد؛ overrun هشدار |
| قیمت‌ها | پایه/Override، current/history، انحراف؛ ثبت و Import | resource prices، price-history، import prices preview/commit | عدد صحیح ریال/تاریخ/واحد/Scope صریح؛ اصلاح هم‌تاریخ به‌صورت نسخه جدید؛ Preview قبل Commit؛ تاریخچه هم‌زمان دیده شود |
| تبدیل واحد | تبدیل‌های سازمان/پروژه و تاریخ اثر؛ ثبت/اصلاح نسخه | unit-conversions GET/POST/PATCH | factor مثبت Decimal؛ بُعد یکسان؛ Scope و effective date؛ history/Audit |
| Snapshot پیشرفت | Metadata، Assignment، sourceMethod، quality/warnings و computed/override | progress-snapshots، feed، progress-override | read-only؛ null≠0؛ percent 0..100؛ override با reason/version/permission و modal |
| فهرست فاکتورها | status/source/vendor/date/amount/duplicate؛ فیلتر، ثبت، Confirm/Void/Corrective | invoices list/create/detail/confirm/void/corrective | pagination 50 و max 200؛ permission؛ status؛ duplicate warning؛ request conflict |
| فرم فاکتور | Header و خطوط و تخصیص adjustment؛ preview/confirm | invoices POST/PATCH/confirm | سه مرحله؛ Line به estimate/general cost؛ currency صریح؛ جمع خطوط/گردکردن؛ idempotency؛ Confirm modal |
| Upload و بررسی AI | فایل کنار extracted/confirmed values و Confidence؛ edit/reject/retry/confirm | files POST/GET، extractions retry/confirm | نوع/اندازه مجاز؛ upload/processing/awaiting/failed؛ low confidence highlight؛ confirmer همان submitter؛ expected version |
| گزارش | KPI، نمودار، جداول انحراف/ریز؛ print/CSV/issue | reports/live، report-snapshots POST/GET/CSV | live در برابر issued واضح؛ issued read-only؛ A4؛ جدول جایگزین نمودار؛ modal صدور |
| Audit | actor/action/entity/time/reason/before-after؛ فیلتر/جزئیات | audit-events | read-only، pagination، Scope و permission؛ نمایش UTC به جلالی محلی |
| تنظیمات | زیربنا، واحد پول نمایشی و دسترسی به تبدیل‌ها؛ Revision | settings GET/PATCH، unit-conversions | grossBuiltArea مثبت؛ فقط رئیس/کارشناس مالی؛ reason/effective date؛ currency ذخیره IRR و نمایش پیش‌فرض تومان |

برای Empty/Error/Permission صفحه، API اختصاصی در منابع تعریف نشده است؛ این حالت‌ها از نتیجه همان درخواست و AuthContext ساخته می‌شوند. جزئیات queryهای فیلتر/sort/pagination هر Endpoint در PRD نهایی نشده است.

## ۷. ساختار داده‌ها

| Entity | مفهوم و فیلدهای مهم | ارتباط/قاعده |
|---|---|---|
| FinanceProjectSettings | organizationId، projectId، grossBuiltArea، currency، revision | یک تنظیم مالی برای پروژه؛ مقدارهای گزارش Pin می‌شوند |
| FinanceResource | type، code، title، baseUnit، dimension، externalResourceId | قلم مشترک برای خطوط/قیمت‌ها؛ عنوان «اقلام مالی» در UI |
| EstimateLine | activity/assignment IDs، resourceId، original/revisedQuantity، source | هر Assignment یک خط مستقل؛ Original immutable |
| EstimateRevision | before/after، reason، actor، timestamp | فرزند خط برآورد و append-only |
| PriceVersion | Scope، resourceId، unitPriceIRR، effectiveFrom/To | سازمان یا Override پروژه؛ بازه‌ها هم‌پوشانی ندارند |
| UnitConversion | from/to، factor، Scope، effectiveDate | سازمانی یا project override؛ versioned |
| ProgressSnapshotRef | snapshotId، sourceFileVersionId، reportingDate، status | مرجع immutable با status `ready/superseded` |
| ResourceAssignment | external IDs، resource/type/unit، planned/actual/remaining، work، sourceMethod، quality، task | خوراک read-only؛ external identity برای تجمیع، نه عنوان |
| ProgressOverride | computedValue، overrideValue، reason، actor/time، snapshotId | مقدار اصلی حفظ می‌شود؛ append-only |
| Invoice | header، source، totals، status، idempotencyKey، confirmation fields | خطوط متعدد؛ Confirmed immutable؛ corrective link |
| InvoiceLine | estimateLine/generalCost، quantity/unit، unitPriceSnapshot، allocated adjustments | با Confirm قفل می‌شود؛ مبلغ قیمت تاریخی خودش را دارد |
| FinanceAttachment | scope، uploader، MIME، size، hash، safe/stored name، logicalType/status | فقط Endpoint مجوزدار؛ فایل Confirmed حذف خودکار ندارد |
| ExtractionDraft | file، providerAdapter، fields، confidence، edits، status/version | قبل Confirm، `financialEffect = 0.00` |
| ReportSnapshot | همه Version IDها، invoice set، metrics، issuedBy/At، immutable | گزارش صادرشده هرگز با داده جدید تغییر نمی‌کند |
| FinanceAuditEvent | actor/action/entity/before-after/reason/scope/time | append-only |

اصطلاحات: مقدار خریداری‌شده از Invoice Lineهای Confirmed پس از تبدیل واحد می‌آید؛ مقدار اجراشده از Progress Feed/Override؛ قیمت اولیه مبنای Estimate اولیه؛ قیمت روز آخرین PriceVersion معتبر با تقدم project override؛ هزینه واقعی جمع اثر اسناد Confirmed است و به پرداخت ربط ندارد.

## ۸. قراردادهای API

- Context میزبان: کاربر، سازمان و پروژه معتبر؛ OpenAPI Kit فقط Mock است.
- Summary/Settings: KPI و تنظیمات پروژه.
- Resources/Estimate Lines/Revisions: اقلام، اتصال فعالیت و تاریخچه مقدار.
- Imports: همیشه `preview` سپس `commit` برای متره و قیمت.
- Prices/Conversions: نسخه‌های قیمت و تبدیل واحد.
- Progress: فهرست Snapshot، feed read-only و Override.
- Invoices/Files/Extractions: چرخه فاکتور، Upload امن، Retry و Confirm Draft.
- Reports/Audit: گزارش زنده، Snapshot، CSV و رویدادها.

قاعده ارتباط: Prefix محصول `/api/projects/{projectId}/finance/...`، بدون `/v1`، Same-Origin، camelCase و Decimal string است. Scope از Path و AuthContext می‌آید، نه Body. خطاهای مهم شامل 403، 404 پنهان‌کننده وجود، 409 برای immutable/duplicate/stale، 422 برای validation/unit و 503 برای Provider است. Error envelope تولید نهایی و تمام payloadهای endpointهای محصول در منابع به‌طور کامل تعریف نشده‌اند؛ Schemaهای Kit فقط قراردادهای عمومی/Mock را پوشش می‌دهند.

## ۹. قوانین مهم Frontend

- ریشه `lang=fa` و `dir=rtl`؛ CSS logical properties، فونت محلی میزبان و بدون asset/CDN تأییدنشده.
- Responsive برای laptop/tablet/mobile؛ جدول موبایل scroll افقی کنترل‌شده دارد.
- هر صفحه Loading، Empty، recoverable Error با Retry، Permission Denied، Success/Normal مستقل و قابل تست دارد.
- UI permission فقط convenience است؛ پاسخ Server مرجع امنیت است. داده/فایل خارج Scope نباید افشا شود.
- چاپ A4 با `@media print`، انتظار برای font/image، عدم بریدگی جدول/عنوان؛ PDF از Browser Print.
- نمودار داخلی SVG/Canvas و جدول جایگزین برای چاپ و accessibility؛ رنگ تنها حامل معنا نباشد.
- API با ASCII digits؛ Persian digit فقط نمایش. Numeric column جهت LTR، align end و tabular digits.
- تاریخ سیستم UTC/ISO و business date؛ نمایش جلالی. جزئیات کتابخانه/الگوریتم تبدیل جلالی در منابع تعریف نشده است و dependency جدید نیازمند تأیید است.
- ذخیره رسمی IRR عدد صحیح؛ نمایش پیش‌فرض تومان با برچسب روشن. Import واحد پول را صریح می‌گیرد؛ حدس ممنوع.
- quantity و conversion با precision مستند Decimal هستند؛ پول و unit price رشته عدد صحیح ریال‌اند؛ Float ممنوع.
- Confirm/Void/Override/Issue با Modal دسترس‌پذیر، اثر عملیات، action صریح و cancel.
- label، focus-visible، keyboard، live region، متن خطای فارسی و ساختار معنایی لازم است.
- Componentها Context میزبان را از Adapter و URL نسبی دریافت کنند. ساختار feature-based و state محلی Feature رعایت شود.
- CSV UTF-8 با BOM؛ pagination پیش‌فرض ۵۰ و سقف ۲۰۰.

## ۱۰. قوانین مهم Business

- Snapshot پیشرفت و Snapshot گزارش immutable هستند؛ گزارش issued نسخه تمام ورودی‌ها و metrics را Pin می‌کند.
- قیمت روز فقط محاسبه زنده/آینده را تغییر می‌دهد، نه Invoice Confirmed یا گزارش قبلی.
- Original quantity/price بازنویسی نمی‌شود؛ Revision رکورد جدا با before/after/reason/actor/time است.
- Override پروژه بر قیمت/تبدیل سازمانی معتبر مقدم است. Override پیشرفت computed value را حذف نمی‌کند.
- AI فقط Draft می‌سازد؛ Auto-confirm ممنوع و اثر مالی تا Confirm صفر است.
- Confirm انتقال اتمیک و version-checked است؛ همان submitter Draft را در MVP تأیید می‌کند.
- Invoice draft قابل اصلاح است؛ Confirmed قابل PATCH/DELETE نیست و اصلاح فقط Void/Reversal/Corrective مرتبط است.
- تاریخچه قیمت Strict append-only است؛ اصلاح هم‌تاریخ نسخه جدید می‌سازد و جدیدترین ترتیب قطعی برنده است؛ Invoice Line snapshot قیمت خودش را نگه می‌دارد.
- Actual Cost جمع اثر Invoiceهای Confirmed است، مستقل از پرداخت.
- Forecast Final = Actual Registered Cost + Money Required to Continue.
- متریال: پول ادامه بر اساس مقدار خریدنشده؛ labor/equipment: مقدار اجرا‌نشده؛ general cost: `max(revisedAmount-actual,0)`.
- خرید ≠ مصرف/اجرا. مقدار گمشده `null` ≠ صفر. عبور از Estimate Clamp نمی‌شود و Warning/Reason/Audit دارد.
- Money/quantity/price با Decimal دقیق؛ line amount با ROUND_HALF_UP یک‌بار در خط؛ اختلاف یک ریال تخصیص تناسبی به آخرین خط.
- داده Confirmed و تاریخچه حذف فیزیکی نمی‌شود؛ Draft رها/ردشده بعد ۹۰ روز فقط با cleanup کنترل‌شده قابل حذف است.

## ۱۱. مسئولیت Frontend

- Shell و Navigation مالی RTL در mount میزبان، route و guard نمایشی.
- تمام صفحات، فرم‌ها، stateها، pagination/filter، Import Preview و خطاهای فارسی.
- مصرف Adapter/API، ارسال Decimal string/ASCII/ISO، cancellation و نمایش request ID/conflict.
- نمایش هم‌زمان original/revised و current/history؛ sourceMethod/quality/warning و low confidence.
- Validation تجربه کاربر برای واحد، مقدار، تاریخ، فایل، Draft و عملیات؛ بدون ادعای امنیت.
- Modalهای عملیات حساس، جلوگیری از کلیک مبهم و مدیریت optimistic version/idempotency key در درخواست مربوط.
- نمودار داخلی، جدول دسترس‌پذیر جایگزین، Print A4 و CSV trigger.
- Permission-based visibility همراه با مدیریت پاسخ 403/404.
- RTL/Responsive/Accessibility و تست UI/Contract مصرف‌شده.

Frontend مسئول محاسبه مرجع مالی، Auth واقعی، جداسازی tenant در Server، Provider AI، ذخیره فایل، Migration یا Parse MPP نیست.

## ۱۲. مسئولیت Backend

- API، Decimal calculation، rounding/allocation و KPI/Forecast مرجع.
- enforce چهار Gate: authentication، organization membership، project scope/membership و finance permission.
- Scope دوگانه در همه Queryها/رکوردها و 404 برای object/file نامرئی.
- تاریخچه append-only، immutability، transaction، idempotency، concurrency/version check و Audit.
- دریافت Progress Snapshot، fallback اجرا و conversion دقیق؛ بدون write-back.
- چرخه Invoice/File/AI provider-neutral، Upload validation/storage مجوزدار و Confirm اتمیک.
- تولید ReportSnapshot immutable و CSV/داده چاپ.
- SQL پیشنهادی PostgreSQL 16/18 و index؛ migration نهایی/Adapter تولید با تیم اصلی BAMBO است.

## ۱۳. نکات بسیار مهم قبل از شروع توسعه

- مسیر Mock، Header Mock یا داده نمونه را به Production-like کپی نکنید.
- `projectId` UUID نیست؛ `organizationId` UUID است. ID مالی UUID مستقل از عنوان است.
- «منابع» عنوان UI مجاز نیست؛ «اقلام مالی» یا «اقلام و متره» استفاده شود.
- پول را parseFloat/Number نکنید؛ تبدیل تومان فقط نمایشی است.
- Body نباید Scope را بسازد یا override کند.
- MPP را در Browser باز/Parse نکنید و به Progress Feed چیزی ننویسید.
- Current price را روی Invoice/Report تاریخی اعمال نکنید.
- purchased را consumed فرض نکنید و `null` را صفر نسازید.
- Draft AI یا low-confidence را خودکار Confirm نکنید؛ شکست Provider باید راه ورود دستی را باز بگذارد.
- Confirmed invoice/issued report را editable model نکنید؛ Correction سند جدید است.
- هشدار مقدار بیشتر از برنامه یا Invoice مشابه را پنهان/Clamp نکنید؛ ادامه مشابه با reason است.
- فایل اصلی برای Viewer مجاز نیست؛ Frontend URL عمومی فایل نسازد.
- permissionهای ریز proposed هستند؛ تا تصمیم رسمی fallback فرض نکنید، خصوصاً Confirm/Void/Override/Attachment/Issue.
- حدود قطعی PRD برای فایل: تصویر JPEG/PNG/WebP تا ۱۰ MiB و صوت MP3/M4A/WAV/OGG تا ۲۵ MiB؛ Kit اندازه‌های پیشنهادی داشت، اما PRD مقدم است. SVG ممنوع.
- Dependency جدید، مسیر Endpoint تولید، CSRF/headers، malware scanner و worker هنوز تصمیم تیم اصلی می‌خواهند.

## ۱۴. Roadmap توسعه Frontend

۱. قرارداد و پایه: تثبیت Adapter interface، Context/permission model، route map، API/error conventions، tokens RTL و state primitives؛ هنوز Endpoint تولید فرض نشود.

۲. Shell و کیفیت مشترک: Host mount، navigation، loading/empty/error/denied، modal، table/pagination، formatter تاریخ/پول/مقدار و print base.

۳. Settings و اقلام: زیربنا، واحد نمایشی، اقلام مالی، estimate lines و Revision؛ سپس Import Estimate Preview/Commit.

۴. قیمت و تبدیل واحد: base/override، history، import preview/commit و dimension validation.

۵. Progress Snapshot: feed read-only، fallback/source/quality/warnings و Override ممیزی‌شده.

۶. فاکتور دستی: list/detail، فرم سه‌مرحله‌ای چندردیفی، adjustments، duplicate warning، Confirm و corrective lifecycle.

۷. File و AI: upload، processing states، image/voice review، confidence/edit/retry/reject/confirm و راه fallback دستی.

۸. Dashboard: پس از تثبیت داده‌های بالا، ۸ KPI، warnings و SVG/Canvas با جدول جایگزین.

۹. Reports و Audit: live report، issue immutable snapshot، A4/PDF browser/CSV و audit filtering/detail.

۱۰. سخت‌سازی و پذیرش: RTL/mobile/keyboard/print، 403/404/409/422/503، stale/race/idempotency، قرارداد Mock Host، ATهای Frontend و Integration dry-run.

ترتیب بالا همان وابستگی منطقی و برنامه PRD را دنبال می‌کند و قابلیت خارج MVP اضافه نمی‌کند.
