# بررسی شواهد واقعی BAMBO Finance

زمان بررسی: ۲۰۲۶-۰۹-۰۹ UTC، شب ۲۰۲۶-۰۹-۰۸ در محیط کاربر. این گزارش فقط مأموریت ۱۱‌بخشی را پوشش می‌دهد؛ درصد پیشرفت کل پروژه نیست.

## محیط و اعتبار منابع

- Worktree: `E:\bamboo\FINANCE-bf`، branch: `backend-finance`، HEAD: `8a3c07660c081ef05a4e6f6d89c730781171ea8f`.
- تغییرات staged/unstaged موجود حفظ شدند؛ reset/restore/merge/commit/push اجرا نشد.
- DB جاری: `bambo_canonical_test` روی `127.0.0.1:5432`؛ هیچ backup روی آن restore نشد. معرفی DB جاری به‌عنوان baseline مطابق توضیح مستقیم کاربر است؛ فایل مستقلی با نام `BAMBO_FINANCE_BASELINE_2026-09-08.backup` پیدا نشد.
- فایل واقعاً خوانده‌شده با Reader/MPXJ: `E:\bamboo\FINANCE-bf\Sources\test_progress.mpp`، اندازه ۱٬۶۳۸٬۴۰۰ بایت.
- SHA-256: `b86b63738f592bfd90286ab08daedcea4374d815c02a7503adc18182cec6e908`؛ دقیقاً برابر `finance_mpp_source_versions.source_sha256` برای نسخه `afe50159-86e5-4e65-9f31-e0fd01ef29e7` و پروژه `terrace`/سازمان `c4ee6a23-b2a8-4afe-94c8-63baba552ca4`.
- `test_progress(1).mpp` در مسیرهای بررسی‌شده پیدا نشد؛ با فایل فوق معادل فرض نشده است. نسخه `FINANCE\Sources\test_progress.mpp` نیز اندازه متفاوت دارد و مرجع این بررسی محسوب نشد.
- `C:\Users\atefe\Downloads\BAMBO_FINANCE_CHAT_HANDOFFS_2026-09-07.zip` موجود است؛ فهرست و baseline داخل آن خوانده شد. اعداد آن صرفاً سابقه‌اند.
- پورت ۸۰۴۰ ابتدا PID=11468 با Python312 اصلی بود. پس از تست‌ها از طریق launcher موجود `scripts.test_only.run_devhost_terrace` روی همان DB و worktree بازراه‌اندازی شد: PID=16076؛ مفسر `E:\bamboo\FINANCE\backend\ai-extraction-env\Scripts\python.exe` دارای psycopg/JPype/MPXJ است.
- `MPP_IMPORT_ROOT=E:\bamboo\FINANCE-bf\Sources` و `MPP_JAVA_HOME=E:\bamboo\jre\jdk-17.0.20.1+1-jre`. Seed، اجرای Migration و Import دوره‌ای فعال نشدند. پوشه فایل‌های DevHost همان پیش‌فرض قبلی است.

## نتیجه ۱۱ بخش

| بخش | وضعیت قبل | شاهد | اقدام | نتیجه بررسی | باقی‌مانده |
|---|---|---|---|---|---|
| ۱. منابع ستون‌های برآورد | درست برای تصمیم فعلی | `repositories/resources.py:list_estimate_lines`، `repositories/reports.py:load`، `domain/reports.py:calculate_live_report`، Adapter اقلام | بدون تغییر | مقدار اولیه/Revision، قیمت مالی و هزینه اسناد مؤثر جدا؛ تست فاکتور و گزارش موفق | ستونی که UI ندارد اضافه نشد |
| ۲. خالی بودن قیمت | درست؛ فقدان قیمت مالی | API قیمت و EstimateLine برای R155/R94؛ دو Legacy دارای قیمت معتبر | بدون ساخت قیمت از Cost | null به Adapter و سلول می‌رسد؛ قیمت واقعی Legacy در جدول نمایان است؛ تست صفر موفق | تعیین قیمت مالی کاربر مستقل از MPP است |
| ۳. واحدها | نقص قطعی برای کد `m` | `normalize_unit('m')` پیش از اصلاح low می‌شد؛ `m` کد رجیستری است | تقدم کد معتبر بر بررسی حرف اختصاری | تست Exact/Alias/Low و m موفق؛ ابهام‌ها حدسی رفع نشدند | حروف اختصاری و واحدهای مبهم همچنان واحد معتبر محسوب نمی‌شوند |
| ۴. منبع MPP | قابل بررسی برای فایل موجود؛ هویت فایل (1) نامعلوم | MPXJ: ۳۲۸ Task، ۸۱ Resource، ۷۲۷ Assignment؛ تطابق hash با DB | تفکیک Units، Material و مقدار مصوب در این گزارش؛ Reader ارز خام را نیز منتقل می‌کند | ۷۲۷ Units، فقط ۲۸۹ Material، صفر مقدار مالی مصوب | برای ادعای تطابق با `test_progress(1).mpp` همان فایل یا hash لازم است |
| ۵. Sync و حفظ تخصیص | تفکیک Cost/Units درست؛ شمارنده نسخه کهنه | ۷۸۹ ردیف واقعی در برابر row_count=727؛ quantityRowCount پاسخ unchanged قبلاً ثابت صفر بود | شمارش داده ذخیره‌شده و اصلاح متادیتای کهنه در مسیر unchanged؛ به‌روزرسانی شمارنده در refresh موجود | دو Sync پیاپی unchanged؛ فقط یک متادیتا اصلاح شد؛ هش هشت جدول ثابت | مسیر refresh در این مأموریت اجرا نشد |
| ۶. ارز | تبدیل عمومی و بدون تشخیص فایل | `_file_rials` قبلاً همیشه ×۱۰؛ فایل واقعی symbol=تومان و code=IRR دارد | ارز خام در Reader؛ تصمیم تومان محدود به hash تأییدشده؛ IRR صریح ×۱؛ ارز مبهم رد می‌شود | Decimal، صفر/null، تبدیل یک‌بار و رد پیش از DB تست شد | فایل جدید با تعارض ارز نیازمند تصمیم مستقل است |
| ۷. Mapping | Scope دریافت source version در Mapper ناقص | `_SOURCE_ROWS` فقط version_id می‌پذیرفت | افزودن organization/project به همان Query و پارامترها | تست SQL با SQLite مستقل برای نسخه/پروژه/سازمان دیگر؛ مغایرت هویت جاری صفر | UID با نام تطبیق داده نشد؛ ۱۲ ردیف بدون Resource خطا نیستند |
| ۸. جدایی برنامه از برآورد | درست طبق تصمیم صریح جدید | `_INSERT_LINE` با مقدار/قیمت اولیه NULL؛ تست‌های اقلام و گزارش | بدون تغییر | نه Units و نه Cost جای برآورد مصوب قرار نمی‌گیرند | نتیجه قبلی «باید برآورد از MPP پر شود» مبنای اقدام نیست |
| ۹. Mapping Status | درست | `GET /api/projects/terrace/finance/mpp-mapping-status`، guard=finance.view، شمارش SQL | endpoint جدید ساخته نشد | 200 برای scope مجاز؛ 403 پروژه دیگر؛ 715+74+0=789 | هیچ شمارنده‌ای hard-code نشد |
| ۱۰. Dataset قیمت | Backend=71، Adapter/جدول=189 | `prices-api-adapter.js:buildWorkspace` از تمام resources ردیف می‌ساخت | محدودکردن currentPrices به شناسه‌های پاسخ prices/current | در Chrome از ۱۸۹ به ۷۱؛ منابع عمومی همچنان ۱۸۹، دو Legacy مؤثر محفوظ | ظاهر و تاریخچه جدول ثابت |
| ۱۱. Price Intelligence | متوقف‌شده | هفت جدول در information_schema موجودند | فقط مطالعه ساختار | هیچ Collector/زمان‌بندی/Provider فعال یا ایجاد نشد | توقف این مرحله برقرار است؛ نقص فنی انجام‌نشده شمرده نمی‌شود |

برای ۱۰ بخش فعال: ۹ بخش در محدوده محلی تأیید شد؛ بخش ۴ برای فایل موجود بررسی شد اما تطابق با فایل نام‌برده `(1)` تأییدنشده است. بخش ۱۱ فقط بررسی ساختارِ مرحله متوقف‌شده است. این نتیجه ادعای پذیرش Production یا همه نسخه‌های MPP نیست.

## شمارنده‌های واقعی

| شاخص | مقدار |
|---|---:|
| ردیف‌های Finance MPP | 789 |
| Assignment | 727 |
| عنوان Task بدون Assignment | 62 |
| Assignment بدون Resource | 12 |
| Assignment متصل به EstimateLine | 715 |
| Activity Only | 74 = 62 + 12 |
| Unclassified در Mapping Status | 0 |
| EstimateLine فعال | 835 = 715 MPP + 120 قدیمی |
| Resource فعال در کاتالوگ | 189 |
| Dataset عملیاتی قیمت | 71 = 68 MPP + 1 دستی + 2 Legacy دارای فاکتور |
| Exact در داده ذخیره‌شده | 0 |
| Alias در داده ذخیره‌شده | 283 |
| Low در همه Assignmentها | 444 |
| Low با Resource موجود | 432 |
| عنوان‌های بدون واحد/Confidence | 62 |
| مقدار مالی مصوب در finance_mpp_rows | 0 |

اختلاف ۴۴۴ با عدد تاریخی ۴۳۲ از احتساب ۱۲ Assignment فاقد Resource می‌آید. حروف اختصاری منابع WORK، واحدهای نامشخص «اصل/واحد»، واحد غایب و «دسیمترمکعب» علت‌های low هستند؛ به نام منبع تکیه نشد. Material برنامه‌ای ۲۸۹ تخصیص از فیلد مستقل MPXJ است؛ ادعای «۷۲۷ تخصیص دارای Quantity مصوب» صحیح نیست.

مقایسه نهایی خروجی Reader و `finance_rows` با هر ۷۸۹ ردیف DB، با کلید Task/Assignment/Resource و نسخه/سازمان/پروژه مشخص، برای `source_assignment_units`, `source_assignment_cost_irr`, `source_cost`, `quantity`, `quantity_unit`, `normalized_unit`, `unit_source`, `unit_confidence` هیچ اختلافی نشان نداد. بنابراین بازنویسی داده خام MPP لازم نبود.

## نمونه ردیابی مبلغ و مقدار

R155 / Task 1212 / Assignment 9703:

- Reader: Units=100، Material=1، StandardRate=12565115391 و Assignment Cost=12565115391؛ ارز خام تومان/IRR متعارض، تصمیم همین فایل تومان است.
- DB: `source_assignment_units=1` طبق نمایش Units موجود؛ `source_assignment_cost_irr=125651153910`؛ `source_cost=12565115391` خام Task، جدا از ستون ریالی Assignment.
- API/Adapter: `mppTaskCostIrr=125651153910`؛ صفحه فعالیت: ۱۲٬۵۶۵٬۱۱۵٬۳۹۱ تومان، دقیقاً تبدیل نمایشی برگشت از IRR.
- `originalQuantity`, `revisedQuantity`, `originalUnitPriceIrr`, `currentPriceIrr` همگی null‌اند. `mppQuantity` فعلی فکت Units برنامه‌ای است و به مقدار مصوب bind نشده است.
- R94 نیز در چند Assignment مستقل بررسی شد؛ مثلاً 9449 دارای Material=98935.41 و Cost=6544577371.5 خام است. Resource 94 یک قیمت واحد و چند تخصیص دارد؛ کل مقدار Resource روی خطوط مختلف تکرار نشد.
- دو منبع Legacy عملیاتی `MSP-T253` و `MSP-T10726` در جدول قیمت مانده‌اند و قیمت معتبر ۱۰۰٬۰۰۰ تومان نمایش می‌دهند؛ نرخ برنامه‌ای MPP جایگزین PriceVersion نشد.

## تغییر دقیق داده و امکان بازگشت

تنها تغییر داده: یک رکورد `finance_mpp_source_versions` با ID فوق، `row_count: 727 → 789`. مسیر اجرا همان `FinanceMppSyncService.sync(refresh=False, file_name='test_progress.mpp')` بود؛ دو بار اجرا شد و بار دوم تغییر شمارنده لازم نبود. هیچ Refresh حذف/بازایجادکننده ردیف اجرا نشد.

پیش و پس از اجرا، count و MD5 از JSON مرتب‌شده تمام ردیف‌های هشت جدول یکسان بود:

| جدول | تعداد | MD5 بدون تغییر |
|---|---:|---|
| finance_mpp_rows | 789 | f95940c37b6fd97c7ab3f703cb6d926e |
| finance_resources | 189 | c3f6bc47b0d6b29c81ac965bfbfc85ff |
| estimate_lines | 835 | 0184e53baba2357b94fd952d878b4313 |
| estimate_revisions | 0 | d41d8cd98f00b204e9800998ecf8427e |
| price_versions | 123 | b5290cd60eadf41e9680e5f9e42d65f3 |
| invoices | 2 | d669fe53f30ddc1ef06475754c543ce4 |
| invoice_lines | 2 | 535cffc8ee0929f437920ed80e4aa6ba |
| report_snapshots | 16 | e7370ecbf955f5b2bbe8843a5ad28964 |

نسخه پیش از تغییر فایل‌ها و SQL برگشت شمارنده در `E:\bamboo\FINANCE-audit-recovery-20260909-0605` است. آن SQL فایل بازیابی است و Migration پروژه نیست. تغییر Schema انجام نشد. لاگ DevHost و تصاویر همان‌جا ذخیره شدند.

## فایل‌های واقعاً تغییرکرده

- `backend/coreint/mpp_units.py`: کد رجیستری یک‌حرفی پیش از قاعده Initials.
- `backend/coreint/mpp_reader.py`: افزودن متادیتای خام ارز به خروجی داخلی؛ عدد خام تغییر نکرد.
- `backend/coreint/finance_mpp_sync.py`: تصمیم ارز وابسته به منبع و اصلاح شمارنده‌های پاسخ/نسخه.
- `backend/coreint/finance_mpp_mapping.py`: Scope صریح در Query منبع Mapper.
- `backend/tests/test_mpp_units.py`: تست کد m و ضریب صریح تبدیل.
- `backend/tests/test_finance_mpp_sync.py`: شمارش واقعی unchanged و اصلاح فقط متادیتا.
- `backend/tests/test_finance_mpp_audit_integrity.py`: تست جدید تبدیل، تفکیک مقادیر، رد پیش از DB و Scope SQL با دیتابیس حافظه‌ای مستقل.
- `frontend/src/adapters/api/prices-api-adapter.js`: Dataset جدول از prices/current.
- `frontend/tests/unit/prices-api-adapter.test.js`: تست Dataset، Legacy، null، صفر و پاسخ خالی.
- `frontend/docs/PROJECT_PROGRESS_FA.md`: ثبت نتیجه همین اصلاح.
- همین گزارش شواهد.

تغییرات قبلی دیگران در Repository جزو این فهرست محسوب نشده‌اند.

## آزمون‌ها و اجرا

از پوشه backend؛ اجرای اول با `.venv312` و PYTHONDONTWRITEBYTECODE=1:

```powershell
python -m pytest tests/test_finance_mpp_audit_integrity.py tests/test_finance_mpp_sync.py tests/test_finance_mpp_fields.py tests/test_finance_mpp_mapping.py tests/test_mpp_units.py tests/test_mpp_mapping_status.py tests/test_finance_activities.py tests/test_active_price_dataset.py tests/test_report_null_semantics.py -q -p no:cacheprovider
```

نتیجه: ۱۱۶ passed، ۳ subtests passed.

با مفسر `FINANCE\backend\ai-extraction-env\Scripts\python.exe` و MPP_JAVA_HOME:

```powershell
python -m pytest tests/test_mpp_reader_real_file.py tests/test_invoices.py tests/test_reports.py -q -p no:cacheprovider
```

نتیجه: ۹۰ passed، ۴۲ subtests passed. هنگام شروع JVM، runtime پیام Windows access violation از faulthandler چاپ کرد، ولی اجرای تست ادامه یافت و exit code=0 و نتیجه نهایی فوق بود؛ این خروجی پنهان نشده است. پیام Log4j نبود logging provider نیز در probe MPXJ دیده شد.

با `.venv312`:

```powershell
python -m pytest tests/test_architecture_modes.py tests/test_mpp_import_service.py tests/test_mpp_files.py -q -p no:cacheprovider
```

نتیجه: ۷۷ passed، ۱۰ subtests passed.

از پوشه frontend:

```powershell
node --test tests/unit/prices-api-adapter.test.js tests/unit/prices-adapter.test.js tests/unit/financial-items-dataset.test.js tests/unit/financial-items-presentation.test.js tests/unit/display-date-safety.test.js
```

نتیجه: ۵۱ passed. مجموع تست‌های هدفمند: Backend=283 و Frontend=51، جمع 334 passed، به‌علاوه 55 subtests؛ failed=0، skipped=0. Full Suite نامرتبط اجرا نشد.

تلاش نخست Sync عملیاتی پیش از دسترسی DB به علت ProactorEventLoop ویندوز متوقف شد؛ اجرای مجدد با WindowsSelectorEventLoopPolicy موفق بود. هیچ تستی حذف/Skip/ضعیف نشد.

## بررسی صفحه و حفظ ظاهر

- Chrome headless در viewport=1440×1000 روی پورت ۸۰۴۰؛ تصاویر بازبینی شدند.
- برای baseline قیمت، نسخه واقعی Adapter از backup با interception فقط در مرورگر آزمایش بارگذاری شد؛ فایل سرور و داده‌ها برای این مقایسه تغییر نکردند. سپس Adapter اصلاح‌شده از خود سرور بارگذاری شد.
- جدول قبل ۱۸۹ و بعد ۷۱ ردیف؛ جدول تاریخچه در هر دو ۲ ردیف. تعداد/نام/عرض تمام headerها و عرض جدول یکسان بود؛ JavaScript exceptions=0.
- صفحه financial-items بارگذاری شد؛ هزینه MSP در ردیف فعالیت و مقدار/قیمت مالی خالی حفظ شد. فایل UI این صفحه و CSSها در این مأموریت تغییر نکردند.
- تصاویر: `prices-before.png`، `prices-after.png`، `financial-items-after.png` در پوشه بازیابی.
- تصویر مرجع پیوست جدید در دسترس نبود؛ ادعای مقایسه با آن نشده است. بررسی بصری این اجرا فقط viewport مذکور و حالت‌های مشاهده‌شده را پوشش می‌دهد.

## ساختار Price Intelligence — فقط خواندن

همه دارای `id uuid`, `organization_id uuid`, `project_id text` هستند:

| جدول | ستون‌ها | ساختارهای مهم مشاهده‌شده |
|---|---:|---|
| price_providers | 12 | name/domain/provider_type/crawl_method، active، default_interval_minutes |
| provider_items | 11 | provider_id، external_id/name، source_unit، metadata jsonb |
| price_collection_runs | 11 | provider_id، status، شروع/پایان، شمارنده آیتم‌ها |
| price_observations | 23 | raw_price text، normalized_price_irr numeric، source_currency/unit، validation_reasons/raw_data jsonb، price_version_id |
| price_collection_schedules | 10 | provider_id، interval_minutes، enabled، next_run_at |
| provider_resource_mappings | 10 | provider_item_id، finance_resource_id، confidence_score numeric، approved/approved_by |
| price_resolution_policies | 11 | resource_id، strategy، preferred_provider_id، provider_weights jsonb، آستانه/عمر |

وجود ستون enabled/active اثبات فعال‌بودن Collector نیست؛ این مأموریت صرفاً وجود و ساختار را خوانده و هیچ فعال‌سازی انجام نداده است.

## تصمیم‌های باقی‌مانده، جدا از نقص فنی

۱. برای تأیید همسانی فایل `(1)`، همان فایل یا hash واقعی لازم است؛ اصلاحات مستقل انجام‌شده به این فرض متکی نیستند.
۲. فایل‌های آینده با ارز مبهم/متعارض باید تصمیم صریح داشته باشند؛ تصمیم تومان فایل حاضر به hashهای جدید تسری داده نمی‌شود.
۳. واحدهای low و مقدار/قیمت مصوب تعیین‌نشده، تصمیم داده‌ای هستند. از نام منبع یا مقدار Cost برای تکمیل آن‌ها استفاده نشد.
۴. Price Intelligence همچنان خارج از اجرای این مأموریت است.
