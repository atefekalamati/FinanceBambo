# شواهد اعتبارسنجی انتشار — فاز ۴-ب

## بازبینی واقعی آماده‌سازی محلی — 2026-09-09 (نسخه دوم؛ جایگزین بازبینی پیشین همین روز)

این بخش وضعیت جاری را ثبت می‌کند. هر ردیف اینجا اجرا شده است؛ ادعای اجرانشده ثبت نشده.
Commit، Push و Deploy انجام نشد. سایت اصلی و Google Sheets لمس نشد.

### محیط و هویت دقیق

| مورد | مقدار |
|---|---|
| مخزن (worktree) | `E:\bamboo\FINANCE-bf` — با `git rev-parse --show-toplevel` تأیید شد |
| شاخه / HEAD | `backend-finance` / `715c1b90` |
| worktree مادر | `E:\bamboo\FINANCE\.git\worktrees\FINANCE-bf` (یک مخزن، دو worktree) |
| فایل منبع | `E:\bamboo\FINANCE\Sources\test_progress.mpp` — 1518592 بایت، SHA256 `9792d658…d8132520f3` |
| نسخه منبع فعال | `bf456698-894b-49a5-9402-12afd27a165e` — ready، 789 ردیف، Status Date فایل `2025-10-02` |
| دیتابیس کاری کاربر | `bambo_canonical_test` @ `127.0.0.1:5432` — **در این بازبینی نوشته نشد** |
| دیتابیس اعتبارسنجی | `bambo_release_verify_20260909` @ `127.0.0.1:5432` (کپی بازیابی‌شده، 74 جدول) |
| مرجع نصب تازه | `bambo_release_empty_20260909` @ `127.0.0.1:5432` (43 جدول، ledger 0016) |
| میزبان اعتبارسنجی | `http://127.0.0.1:8041` |
| میزبان دیگر (دست‌نخورده) | `http://127.0.0.1:8040` روی `bambo_canonical_test` |

هویت پورت 8041 مستقیماً از `pg_stat_activity` و `Get-NetTCPConnection` خوانده شد، نه از سند.
پیش از بازبینی، پروسه 8041 با مفسر سیستمی و بدون `--dsn` اجرا می‌شد؛ با دستور مستند این سند
(مفسر `ai-extraction-env`) دوباره راه‌اندازی شد تا کد جاری بارگذاری شود. پورت 8040 دست‌نخورده ماند.

### تغییرات همین بازبینی

- `app/finance/schemas/reports.py` — `TypeBreakdown.remainingPhysicalCostIrr` و `forecastFinalIrr`
  اکنون `Decimal | None` هستند. **این تنها حلقهٔ شکستهٔ زنجیرهٔ پوشش تاریخی بود**: قاعدهٔ
  `require_estimate_coverage` مقادیر null تولید می‌کرد ولی مدل پاسخ آن را نمی‌پذیرفت و
  `/overview` با `ResponseValidationError: 8 validation errors` پاسخ **500** می‌داد. یعنی به‌جای
  «—»، صفحهٔ خراب دیده می‌شد — نتیجه‌ای بدتر از همان صفرِ کاملی که قرار بود جایگزین شود.
  `LiveMetrics` و `WbsNode` از قبل همین nullability را داشتند؛ این ردیف حالا با آن‌ها هم‌راستاست.
- `tests/test_report_historical_coverage.py` — سه آزمون جدید روی همان مرز: null باید null بماند،
  صفر واقعی باید «0» بماند، و مقدار نامعتبر باید همچنان رد شود (nullable یعنی «نامعلوم»، نه «هرچیزی»).
- `frontend/scripts/layout-audit.mjs` — قاعدهٔ تشخیص سرریز از «نام کلاس» به «آیا با اسکرول قابل
  دسترسی است» تغییر کرد. دلیل و شواهد در بخش چیدمان.
- تغییرات بازبینی پیشین (`report_coverage.py`، cutoff در `estimate_basis.py`، `estimate_coverage_known`
  در `repositories/reports.py`، `scripts/reconcile_release_schema.py`، هم‌راستاسازی fixtureهای Mock)
  بازبینی و **حفظ** شدند؛ هیچ‌کدام بازنویسی نشد.

### زنجیرهٔ پوشش تاریخی — DB ← سرویس ← API ← آداپتور ← کارت/نمودار

گزارش در تاریخ فایل (`2025-10-02`) درخواست شد. پیش از این بازبینی، همین درخواست
`calculationStatus=complete` با همهٔ اعداد صفر برمی‌گرداند.

| لایه | پیش از اصلاح | اکنون |
|---|---|---|
| Repository | `estimate_coverage_known=false` (هیچ خط برآوردی تا آن تاریخ ثبت نشده) | همان |
| Domain | متریک‌های برآورد → None، وضعیت incomplete، هشدار `ESTIMATE_HISTORICAL_COVERAGE_UNKNOWN` | همان |
| API | **HTTP 500** (`ResponseValidationError`) | `calculationStatus=incomplete`، شش متریک `null`، `actualCostIrr=0` |
| UI — کارت‌ها | — | «برآورد اولیه: قابل محاسبه نیست — داده مبنا موجود نیست» |
| UI — کارت هزینهٔ واقعی | — | «هزینه واقعی ثبت‌شده: تومان ۰» (عدد واقعی، مستقل از برآورد) |
| UI — نمودار مراحل | — | `برآورد اولیه: —` در برابر `هزینه واقعی: ۰ تومان` |

یعنی «نامعلوم» و «صفر واقعی» روی صفحه از هم تفکیک می‌شوند. صفر واقعی همچنان صفر است
(`test_a_known_zero_still_serializes_as_zero`)، و هزینهٔ فاکتورهای واجد شرایط مستقل از برآورد دیده می‌شود.

گزارش‌های صادرشده (Issued) از این قاعده عبور نمی‌کنند: `require_estimate_coverage` فقط در مسیر
`live` و گره‌های WBS صدا زده می‌شود (`services/reports.py:210` و `:274`)، در حالی که خواندن گزارش
صادرشده از `snapshot_payload` انجام می‌شود (`:412`). سند تاریخی بازنویسی نمی‌شود.

### Migration — هدف واقعی، گاردها، و پیش‌نیاز

- **هدف واقعی از خودِ مخزن خوانده شد، نه از ادعا**: ۱۶ revision روی دیسک، زنجیرهٔ تک‌شاخهٔ
  `0001 → … → 0016`، و `heads = ['0016']`. پس 0016 هدف درست است.
- **0014 تا 0016 دقیقاً همان سه جدولی را تغییر می‌دهند که اسکریپت مقایسه می‌کند**:
  0014 ستون `reporting_date` را به `finance_mpp_source_versions` می‌افزاید؛ 0015 ستون‌های
  `source_assignment_*` را به `finance_mpp_rows`؛ 0016 ستون‌های `source_material_quantity`،
  `source_rate_basis` و `source_resource_rate_irr` را به همان جدول، به‌علاوهٔ ساخت
  `estimate_line_source_completions`. هیچ‌کدام جدولی به نام `finance_mpp_assignment_facts`
  نمی‌سازد — نام فایل، نام قابلیت است نه نام جدول. (تصحیح یک برداشت نادرست پیشین.)
- **گاردهای اسکریپت با اجرا آزموده شدند، نه با مطالعهٔ کد:**

| گارد | آزمون | نتیجه |
|---|---|---|
| اختلاف Schema | کپی ایزوله ساخته شد، ستون `source_rate_basis` حذف شد، ledger روی 0013 گذاشته شد، `--apply` اجرا شد | **امتناع** با چاپ دقیق اختلاف؛ ledger روی `0013` دست‌نخورده ماند |
| دیتابیس کاری کاربر | `--target-dsn …/bambo_canonical_test --apply` | **امتناع**: «only isolated bambo_release_* databases are allowed» |
| میزبان غیرمحلی | `--target-dsn …@192.168.100.200/…` | **امتناع**: «this recovery tool is local-only» |
| مرجع نامعتبر | مرجع باید ledger `0016` داشته باشد | در کد الزامی؛ در اجرای واقعی مرجع 0016 بود |
| بی‌اثری روی داده | اثرانگشت محتوای همهٔ جدول‌ها قبل و بعد | `{"schemaMatches": true, "unchangedTables": 73}` |

- **پیش‌نیاز نصب تازه، مستقل تأیید شد**: روی یک دیتابیس کاملاً خالی، `alembic upgrade head`
  تا `0008` پیش می‌رود و روی `0009` با پیام خودتوضیح متوقف می‌شود:
  «0009 requires the Core table `msp_tasks` to exist … create a compatible `msp_tasks`
  (and `msp_snapshots` for the trigger) first». پس Schema هسته پیش‌نیاز 0009 به بعد است.
- **ارتقا اتمیک است**: پس از آن شکست، دیتابیس **۰ جدول** داشت. یک ارتقای ناموفق، پایگاه دادهٔ
  نیمه‌مهاجرت‌شده باقی نمی‌گذارد.
- وضعیت فعلی: `bambo_release_verify_20260909` روی `0016`؛ `bambo_canonical_test` روی `0013`
  و **عمداً اصلاح نشد**. اسکریپت از نظر فنی هم نمی‌تواند آن را هدف بگیرد.

### شواهد عدد رندرشده — فایل ← DB ← API ← UI

| رکورد | فایل / DB | API | UI (رندرشده در مرورگر) |
|---|---|---|---|
| Assignment **9703** (`MPP-R155` تجهیز مستمر) | خط: هر دو ستون `original_*` برابر NULL؛ تکمیل: quantity=1، `unit_price_irr=125651153910` | `originalQuantity=1`، `originalUnitPriceIrr=125651153910`، `originalValueSource=source_completion` | «۱ ǀ ۱ ǀ ۱۲٬۵۶۵٬۱۱۵٬۳۹۱ ǀ ۱۲٬۵۶۵٬۱۱۵٬۳۹۱» |
| تبدیل ارز همان قلم | فایل: StandardRate برابر 12,565,115,391 تومان | DB و API: 125,651,153,910 **ریال** (ضرب در ۱۰، یک‌بار) | نمایش: ۱۲٬۵۶۵٬۱۱۵٬۳۹۱ (تقسیم بر ۱۰، یک‌بار) — **تبدیل دقیقاً یک‌بار** |
| نبودن قیمت روز | ۷۱۵ خط از ۸۳۵ هیچ `price_versions` ندارند | `currentUnitPriceIrr` غایب | ستون «قیمت روز» برابر «—» |
| صفر واقعی | هر دو فاکتور draft؛ هیچ سند تأییدشده‌ای نیست | `actualCostIrr=0` | «هزینه واقعی ثبت‌شده: تومان ۰» |
| چند Assignment زیر یک فعالیت | فعالیت `1.5.2.9`: ۷ خط، یک task (uid 1227)، هزینه‌های متمایز `0`، `32000000`، `65445773715` | جمع برابر 65,477,773,715 ریال | سرگروه: ۶٬۵۴۷٬۷۷۷٬۳۷۱٫۵ برابر جمع تقسیم بر ۱۰ — **بدون شمارش مضاعف** |
| پوشش تاریخی ناقص | هیچ خط برآوردی تا `2025-10-02` | `incomplete` به‌همراه شش `null` | کارت‌ها: «قابل محاسبه نیست» |
| برآورد بازنگری‌شده | **صفر بازنگری واقعی در داده** | — | فقط با fixture آزموده شد (`financial-items-adapter.test.js`) — **اعتبارسنجی fixture، نه دادهٔ واقعی** |

نکتهٔ منشأ: ردیف تکمیل Assignment 9703 به نسخهٔ منبع `afe50159` (ایمپورت قبلی، checksum
`b86b6373…`) منتسب است، نه به نسخهٔ فعال `bf456698`. اعداد یکسان‌اند (دو فایل از نظر مالی
اثبات‌شده یکسان‌اند) ولی منشأ ثبت‌شده نسخهٔ دیگری را نام می‌برد.

### چیدمان — ممیزی مرورگر

`npm run audit:layout` با `BAMBO_AUDIT_URL=http://127.0.0.1:8041`؛ ۱۹۰ اجرا در ۱۹ مسیر و ۱۰ عرض.

- **پیش از اصلاح: ۱۷ شکست.** ۱۴ موردش `level-one` در **همهٔ** عرض‌ها (۱۴۴۰ تا ۳۲۰) بود.
- **بررسی واقعی در مرورگر نشان داد این‌ها نقص چیدمان نبودند**: `pageOverflow = 0` در همهٔ
  عرض‌ها؛ `.vbars__viewport` یک ظرف اسکرول واقعی است (`overflow-x: auto`، نوار اسکرول
  ۱۱ پیکسلی، `scroll-snap`، tab stop مستقل)؛ و آزمون تجربی «هر گروه را به دید بیاور و اندازه
  بگیر» نشان داد **هر ۱۳ گروه قابل دسترسی‌اند و `unreachableCount = 0`**.
- ممیزی از قبل `.table-scroll` و `.breakdown-table-wrapper` را **با نام** معاف می‌کرد. نام فقط
  ظرف‌هایی را می‌بخشد که کسی به یادشان بوده. قاعده به همان ویژگی‌ای تغییر کرد که آن دو را
  امن می‌کرد: آیا این عنصر درون چیزی است که واقعاً روی این محور اسکرول می‌شود. ظرفی که
  **بدون اسکرول** ببُرد همچنان شکست می‌خورد — که همان موردِ ارزشمند است.
- **پس از اصلاح: ۲ شکست**، هر دو واقعی و بی‌ارتباط با نمودار: `period-report` در عرض ۳۶۰
  (`pageOverflow=4`) و ۳۲۰ (`pageOverflow=44`). علت اندازه‌گیری‌شده: `finance-page-header`،
  `period-builder` و `state-card` هر سه ۳۴۰ پیکسل عرض دارند در حالی که والدشان
  `period-report-page` ۲۷۲ پیکسل است. این مسیر در دامنهٔ درخواست‌شدهٔ این بازبینی نبود و تغییر نکرد.

**هیچ CSS، رنگ، فونت، ساختار صفحه یا RTL تغییر نکرد.** تنها فایل چیدمانی که لمس شد، اسکریپت
ممیزی توسعه است که اصلاً به مرورگر کاربر نمی‌رود.

### تست‌ها

| سوئیت | نتیجه |
|---|---|
| Backend (`pytest tests -q`) | **1184 passed، 0 failed، 0 errors، 0 skipped؛ 2229 subtests passed** |
| Frontend (`node --test`) | **457 passed، 0 failed، 0 skipped** |
| `npm run check` | bootstrap پارس می‌شود |
| `npm run audit:layout` روی 8041 | ۱۹۰ اجرا، ۲ شکست (`period-report` در ۳۶۰ و ۳۲۰) |

دو شکستی که بازبینی پیشین گزارش کرده بود اکنون هر دو سبزند و هیچ assertion ضعیف نشد:
`test_the_seed_mirrors_the_frontend_mock_line_for_line` (با هم‌راستاسازی fixtureهای Mock با Seed،
بدون تغییر دادهٔ واقعی) و `test_a_missing_snapshot_never_reaches_the_provider`.

دستور تست، از `E:\bamboo\FINANCE-bf\backend`:

```powershell
$env:MPP_JAVA_HOME='E:\bamboo\jre\jdk-17.0.20.1+1-jre'
& 'E:\bamboo\FINANCE\backend\ai-extraction-env\Scripts\python.exe' -m pytest tests -q -p no:cacheprovider
```

### راه‌اندازی و Health Check میزبان اعتبارسنجی

از `E:\bamboo\FINANCE-bf\backend`:

```powershell
$env:APP_ENV='development'
$env:FINANCE_ALLOW_SEED='false'
$env:FINANCE_DEV_DSN='postgresql://postgres@127.0.0.1:5432/bambo_release_verify_20260909'
$env:FINANCE_CORE_DSN=$env:FINANCE_DEV_DSN
$env:FINANCE_DEMO_USER_ID='53a1ac1b-d87f-4125-9ba9-a7d64166af88'
$env:FINANCE_DEMO_ORGANIZATION_ID='c4ee6a23-b2a8-4afe-94c8-63baba552ca4'
$env:FINANCE_DEMO_PROJECT_ID='terrace'
$env:MPP_IMPORT_ROOT='E:\bamboo\FINANCE\Sources'
$env:MPP_JAVA_HOME='E:\bamboo\jre\jdk-17.0.20.1+1-jre'
$env:MPP_IMPORT_ENABLED='false'
& 'E:\bamboo\FINANCE\backend\ai-extraction-env\Scripts\python.exe' -m devhost --port 8041
```

`MPP_IMPORT_ROOT` باید صریح داده شود: پیش‌فرض launcher به `FINANCE-bf\Sources` اشاره می‌کند
که **کپی دیگری از همان فایل** با checksum متفاوت است.

Health check به ترتیب:

```
GET /                                                      → 200
GET /openapi.json                                          → 200
GET /api/projects/terrace/finance/progress-snapshots       → یک ردیف با isActiveSource=true
GET /api/projects/terrace/finance/estimate-lines           → ۸۳۵ ردیف
GET /api/projects/terrace/finance/overview?reportingDate=<تاریخ نسخه>&progressSnapshotId=<شناسه>
```

### بازیابی و اصلاح ledger

```powershell
# ۱) بازیابی روی یک دیتابیس تازه، هرگز روی دیتابیس کاری
pg_restore --no-owner --no-privileges --exit-on-error -d bambo_release_<تاریخ> <backup>

# ۲) اگر ledger عقب بود، ابتدا بدون --apply (فقط گزارش)
python -m scripts.reconcile_release_schema `
  --reference-dsn postgresql://postgres@127.0.0.1:5432/bambo_release_empty_20260909 `
  --target-dsn   postgresql://postgres@127.0.0.1:5432/bambo_release_<تاریخ>

# ۳) فقط اگر خروجی schemaMatches=true بود: همان دستور با --apply
```

نصب تازه: ابتدا Schema هسته (`msp_tasks` و `msp_snapshots`)، سپس `alembic upgrade head`.
بدون آن، ارتقا روی 0009 متوقف می‌شود و — چون اتمیک است — چیزی باقی نمی‌گذارد.

### موانع باقی‌مانده

1. **P0 — تاریخ اثر تجاری خطوط برآورد.** فیلتر همچنان `created_at` است، یعنی «کِی ثبت شد»
   نه «از کِی معتبر بود». قاعدهٔ محافظه‌کارانهٔ فعلی پاسخ درست می‌دهد («نامعلوم») ولی جایگزین
   یک تاریخ اثر واقعی نیست. تصمیم تجاری لازم است؛ اعداد امروز به گذشته تزریق نشدند.
2. **P1 — برچسب ارز در `#/financial-items` غایب است.** ستون‌های پولی عدد خالی نشان می‌دهند و
   کلمهٔ «تومان» هیچ‌جای صفحه نیست (این وضع در HEAD هم هست؛ `withCurrency: false` روی همهٔ
   ستون‌های پولی). تبدیل درست است، ولی خواننده نمی‌تواند تومان را از ریال تشخیص دهد.
   کوچک‌ترین اصلاح: یک سطر عنوان «ارقام به تومان» یا پسوند واحد در سه عنوان ستون — تصمیم طراحی.
3. **P1 — سرریز `period-report` در عرض ۳۶۰ و کمتر.** اندازه‌گیری و مستند شد؛ خارج از دامنهٔ این بازبینی.
4. **P1 — واحد `MPP-R155` نامعلوم است** (`mppUnitConfidence=low`، `mppUnit=null`). حدس زده نشد.
5. **P2 — منشأ تکمیل Assignment 9703 نسخهٔ `afe50159` است، نه نسخهٔ فعال `bf456698`.**
   اعداد یکسان‌اند؛ فقط انتساب منشأ به نسخهٔ قدیمی‌تر است.
6. **P2 — سناریوی «برآورد بازنگری‌شده» دادهٔ واقعی ندارد** (صفر بازنگری در پروژه). فقط fixture.
7. **Host — احراز هویت، نگاشت مجوز و Providerهای واقعی میزبان.** DevHost با هویت صریح محلی
   جایگزین Auth تولید نیست. اطلاعات میزبان در دسترس این بازبینی نبود.

### حکم آمادگی — سه سطح جدا

| سطح | حکم | مبنا |
|---|---|---|
| **نمایش محلی** | ✅ آماده | هر دو سوئیت سبز؛ زنجیرهٔ پوشش تاریخی تا UI تأیید شد؛ عدد Assignment 9703 از فایل تا پیکسل ردیابی شد؛ بدون شمارش مضاعف؛ ممیزی چیدمان تنها ۲ شکست واقعی در یک مسیر خارج از دامنه |
| **Staging** | ❌ آماده نیست | Schema هسته به‌عنوان پیش‌نیاز 0009 باید در محیط فراهم شود؛ اصلاح ledger فقط روی کپی ایزوله آزموده شده؛ برچسب ارز و قاعدهٔ تاریخ اثر تجاری حل نشده‌اند |
| **Production** | ❌ آماده نیست | مانع P0 باز است؛ Auth و Providerهای میزبان آزموده نشده‌اند؛ هیچ تمرین انتشاری روی محیط مستقر انجام نشده؛ دیتابیس Production در تمام این بازبینی لمس نشد |


## جداسازی مجوز فاکتور — 2026-09-09

پیش از این، هر تغییر فاکتور همان `finance.edit` را می‌خواست که قیمت و ردیف برآورد را تغییر
می‌دهد. یعنی هرکس نگه‌داری ساختار هزینه را بر عهده داشت، بی‌آنکه گفته شود، می‌توانست فاکتور
تأمین‌کننده را تأیید کند و تصویر اصلی آن را باز کند. این دو کار متفاوت‌اند و در بیشتر سازمان‌ها
عمداً بر عهدهٔ دو نفر متفاوت.

**جداسازی سخت (STRICT) پیاده شد.** `finance.edit` هیچ مسیر فاکتوری را باز نمی‌کند و
`finance.manage_invoice` هیچ ویرایش غیرفاکتوری را. مسیر انتقالی
`manage_invoice OR edit` پیاده **نشد** و آزمون‌ها جلوی بازگشتش را می‌گیرند.

### ماتریس نهایی مسیر و مجوز

| مسیر | مجوز | یادداشت |
|---|---|---|
| `GET /invoices` · `GET /invoices/{id}` | `finance.view` | فراداده، بدون تغییر |
| `GET /files` · `GET /files/{id}` | `finance.view` | فراداده؛ نه بایت اصلی، نه لینک دانلود |
| `GET /extractions` · `GET /extractions/{id}` | `finance.view` | فراداده و وضعیت پردازش |
| `POST /invoices` | `finance.manage_invoice` | |
| `PATCH /invoices/{id}` | `finance.manage_invoice` | |
| `POST /invoices/{id}/confirm` | `finance.manage_invoice` | دیگر «فقط ثبت‌کننده» نیست |
| `POST /invoices/{id}/void` | `finance.manage_invoice` | بدون محدودیت ثبت‌کننده |
| `POST /invoices/{id}/corrective` | `finance.manage_invoice` | بدون محدودیت ثبت‌کننده |
| `POST /files` | `finance.manage_invoice` | |
| `POST /files/{id}/extractions` | `finance.manage_invoice` | |
| `POST /files/{id}/extractions/async` | `finance.manage_invoice` | صف پردازش هم پشت همین دروازه |
| `POST /extractions/{id}/reject` · `/retry` | `finance.manage_invoice` | |
| `POST /extractions/{id}/confirm` | `finance.manage_invoice` **و** قاعدهٔ آپلودکننده | FR-063 دست‌نخورده |
| `GET /files/{id}/content` | `finance.manage_invoice` | امتناع به‌صورت **404** پنهان می‌شود |
| گزارش‌ها (`view`/`export`/`issue`) | بدون تغییر | `finance_report.issue` همچنان fail-closed |

### تغییرات فایل‌به‌فایل

| فایل | تغییر |
|---|---|
| `app/finance/router.py` | ۱۱ مسیر تغییر از `finance.edit` به `finance.manage_invoice`؛ مسیر محتوا به `finance.manage_invoice` با تابع جدید `_conceal_unless_permitted` (تبدیل ۴۰۳ به ۴۰۴)؛ هدر `Cache-Control: private, no-store`؛ دروازهٔ تنظیمات به ثابت `SETTINGS_EDIT_PERMISSION` |
| `app/finance/services/settings.py` | حذف `settings_edit_permission` نقش‌محور؛ جایگزینی با ثابت `SETTINGS_EDIT_PERMISSION = "finance.edit"`؛ حذف import بلااستفادهٔ `AuthContext` |
| `app/finance/services/invoices.py` | حذف قاعدهٔ «فقط ثبت‌کننده تأیید می‌کند» و حذف کلاس بی‌استفادهٔ `InvoiceConfirmationForbidden` |
| `app/finance/repositories/invoices.py` | **حذف `AND submitted_by=%s` از UPDATE تأیید.** همان قاعده بار دوم در SQL نوشته شده بود؛ اگر فقط سرویس اصلاح می‌شد، قاعده باقی می‌ماند و به شکل خطای گمراه‌کنندهٔ «نسخهٔ کهنه» بروز می‌کرد |
| `contracts/openapi.json` | بازتولید؛ اختلاف فقط `ProgressSnapshotResponse`، `TypeBreakdown` و توضیح مسیر محتوا. `--check` اکنون سبز است |
| `tests/test_route_authorization.py` | واژگان + `ABSENT_IN_CORE` + استثنای مستند مسیر محتوا + سه آزمون جدید قرارداد |
| `tests/test_invoice_permission_separation.py` | **جدید** — ماتریس A تا H |
| `tests/test_settings.py` · `test_settings_api.py` | انتظار وارونه شد: نام نقش دیگر حق ویرایش نمی‌دهد |
| `tests/test_invoices.py` | آزمون «ثبت‌کنندهٔ اشتباه» جای خود را به «فاکتور دیگری هم قابل تأیید است» داد |
| `tests/test_demo_isolation.py` | چهار آزمون جدید دربارهٔ ادعاهای آینهٔ دمو |
| `scripts/demo/seed_core_mirror.py` | فهرست نقش میزبان با ذکر منشأ؛ فقط `bambo_admin` نگاشت دارد؛ ۱۱ نقش دیگر صریحاً بدون نگاشت؛ نقش‌های دمو با پیشوند `demo_`؛ `finance.manage_invoice` در واژگان و به هیچ نقشی داده نشده |
| `frontend/src/core/auth/capabilities.js` | افزودن `manageInvoice`؛ اصلاح توضیح `writeFinance`؛ افزودن پیام `MANAGE_INVOICE_NOTICE` |
| `frontend/src/features/invoices/invoices-page.js` | `canCreate` از `writeFinance` به `manageInvoice` + پیام توضیحی |
| `frontend/src/features/ai-review/invoice-files-page.js` | `canUpload` همان‌طور + پیام |
| `frontend/src/features/ai-review/ai-review-page.js` | `canEdit` همان‌طور؛ **پیش‌نمایش فایل اصلی بدون مجوز اصلاً درخواست نمی‌شود** |
| `frontend/tests/unit/capabilities.test.js` | شکل قابلیت‌ها + آزمون جداسازی دوطرفه |

### آنچه در فرانت واقعاً پیدا شد

قرارداد فرانت **برقرار نبود**. بررسی نشان داد `capabilitiesFor` هیچ قابلیت مدیریت فاکتور
نداشت، `writeFinance` در توضیح خودش صریحاً می‌گفت فاکتورها و بارگذاری‌ها را هم پوشش می‌دهد،
و رشتهٔ «نیازمند مجوز مدیریت فاکتورها» هیچ‌جای مخزن نبود. این همان mismatch باریکِ اتصال
مجوز است و فقط همان اصلاح شد: هیچ صفحه‌ای بازنویسی نشد و طراحی، چیدمان، RTL و ناوبری
دست‌نخورده ماند.

### راستی‌آزمایی روی میزبان واقعی (8041، کپی ایزوله)

کاربر واقعی این محیط `finance.view` و `finance.edit` دارد و `finance.manage_invoice` ندارد —
یعنی دقیقاً وضعیتی که میزبان امروز در آن است.

```
GET  /invoices                 -> 200
GET  /files                    -> 200
GET  /extractions              -> 200
POST /invoices                 -> 403  "permission finance.manage_invoice is required"
GET  /files/{id}/content       -> 404  FINANCE_NOT_FOUND
HEAD /files/{id}/content       -> 405  (مسیر فقط GET است؛ چیزی فاش نمی‌کند)
GET  /files/{id}/content  با Range -> 404، بدون هیچ بایتی
```

هیچ فاکتوری ساخته نشد: ۴۰۳ پیش از رسیدن به سرویس رخ می‌دهد.

در مرورگر (Chrome headless روی همان میزبان):

| صفحه | نتیجه |
|---|---|
| `#/invoices` | باز می‌شود، ۲ فاکتور خوانده می‌شود، پیام «نیازمند مجوز مدیریت فاکتورها» دیده می‌شود، دکمهٔ ایجاد فاکتور نیست |
| `#/invoice-files` | باز می‌شود، بارگذاری غیرفعال («بدون مجوز بارگذاری»)، دکمه‌های پردازش غیرفعال |
| `#/ai-review` | باز می‌شود، هر سه دکمهٔ تغییر غیرفعال، و **به‌جای پیش‌نمایش فایل اصلی، توضیح نمایش داده می‌شود** |
| هر سه صفحه | **هیچ عنصری به `/content` اشاره نمی‌کند** — بایت اصلی حتی درخواست هم نمی‌شود |

### تست‌ها

| سوئیت | پیش از این کار | پس از این کار |
|---|---|---|
| Backend | **1184 passed، 0 failed** | **1210 passed، 0 failed** (2355 subtest) |
| Frontend | **457 passed، 0 failed** | **458 passed، 0 failed** |
| `npm run check` | سبز | سبز |
| `export_openapi.py --check` | **قرمز** (قرارداد کهنه) | **سبز** |

هیچ آزمونی حذف، skip یا ضعیف نشد. آزمون‌هایی که تغییر کردند، انتظارِ قاعدهٔ حذف‌شده را
داشتند و اکنون انتظار قاعدهٔ جدید را دارند — و در دو مورد قوی‌تر از قبل شدند (جداسازی دوطرفه،
و «هیچ نام نقشی حق ویرایش نمی‌دهد»).

### آنچه میزبان باید انجام دهد (پیش‌نیاز فعال‌سازی)

1. **`finance.manage_invoice` را در Core ثبت کند** و آن را به نقش‌هایی که باید فاکتور بزنند
   **صریحاً تخصیص دهد**. تا آن زمان هر تغییر فاکتور برای همه رد می‌شود. این وضعیت **مورد
   انتظار** است، نه نقص، و راه‌حلش پذیرفتن `finance.edit` به‌جای آن نیست.
2. **`finance_report.issue`** جداگانه است و در این کار داده نشد. تا ثبت و تخصیص نشدن،
   `POST /report-snapshots` fail-closed می‌ماند.
3. **نگاشت نقش‌های میزبان نامعلوم است.** تنها شواهدی که به ما داده شد، مجوزهای مالی
   `bambo_admin` بود (`finance.view`, `finance.edit`, `finance_report.view`,
   `finance_report.export`). برای ۱۱ نقش دیگر (`org_chief`, `project_manager`,
   `site_supervisor`, `technical_expert`, `guest`, `project_definition_expert`,
   `project_control_expert`, `capture_expert`, `quantity_survey_expert`, `finance_expert`,
   `support`) هیچ نگاشتی حدس زده نشد و در آینهٔ دمو صریحاً بدون نگاشت ثبت شدند.
4. جدول‌های مجوز Core تغییر داده نشد و هیچ migration ساخته نشد.

### آنچه تغییر نکرد

Google Sheets، سایت اصلی، پورت 8040، دیتابیس کاری `bambo_canonical_test`، هیچ رکورد مالی،
هیچ کاربر یا نقش یا تخصیص مجوز واقعی. Seed پیش‌فرض همچنان خاموش است
(`FINANCE_ALLOW_SEED=false`). Commit، Push و Deploy انجام نشد. همهٔ اصل‌های موجود حفظ شدند:
احراز هویت، دامنهٔ سازمان/پروژه، مالکیت رکورد، چرخهٔ عمر فاکتور، تاریخچه و رویدادهای ممیزی،
و ثبت واقعی تأییدکننده.


## سه بهبود آماده‌سازی انتشار — 2026-09-09

### ۱) ارز نمایشی، صریح روی صفحه

ستون‌های پولی `#/financial-items` عمداً بدون کلمهٔ ارز قالب‌بندی می‌شوند
(`withCurrency: false`) تا ستون، ستونِ عدد بماند. نتیجه‌اش این بود که هیچ‌جای صفحه نمی‌گفت
۱۲٬۵۶۵٬۱۱۵٬۳۹۱ تومان است یا ریال — و فاصلهٔ این دو، ضریب ده در بودجهٔ کسی است.

**آنچه اضافه شد:** یک یادداشت در همان سبک `table-note` که جدول از قبل دارد، بالای جدول
«ریز برآورد پروژه»: «مبالغ به تومان».

**از قرارداد مشتق می‌شود، نوشته نشده.** برنامه دو ارز نمایشی پشتیبانی می‌کند
(`IRR` و `TOMAN`، پیش‌فرض تومان) که کاربر می‌تواند عوض کند. یادداشت از همان
`getDisplayCurrencyLabel()` می‌خواند که خودِ فرمت‌کننده می‌خواند، پس اگر کاربر به ریال
سوئیچ کند، برچسب هم «مبالغ به ریال» می‌شود. برچسب دستی تا لحظهٔ اولین سوئیچ درست بود و بعد
با اطمینان غلط می‌شد — که از سکوتِ قبلی بدتر است.

**جاهایی که تغییر نکردند، چون از قبل درست بودند:** پنجرهٔ «ثبت اصلاح مقدار برآورد» ارز خود
را با همان تابع برچسب می‌زند؛ جدول «اقلام مالی» هیچ ستون پولی ندارد؛ کارت‌های شمارش، شمارش‌اند
نه مبلغ. ستون‌های مقدار و واحد به‌عنوان مبلغ برچسب نخوردند.

**هیچ مبلغ ذخیره‌شده، فرمول، گِردکردن یا تبدیل ارزی تغییر نکرد.**

راستی‌آزمایی روی داده واقعی (Assignment 9703، پورت 8041):

| لایه | مقدار |
|---|---|
| API | `originalUnitPriceIrr = 125651153910` (ریال) |
| نمایش در حالت تومان | `۱۲٬۵۶۵٬۱۱۵٬۳۹۱` |
| نمایش در حالت ریال | `۱۲۵٬۶۵۱٬۱۵۳٬۹۱۰` |
| قیمت روز نداشته | `—` (بدون تغییر) |
| صفر واقعی | `۰` (بدون تغییر) |

در مرورگر: کلمهٔ «تومان» اکنون در متن صفحه هست (پیش از این آرایهٔ کلمات ارز روی این صفحه
خالی بود) و ردیف 9703 دقیقاً همان اعداد بالا را نشان می‌دهد.

آزمون `frontend/tests/unit/display-currency-note.test.js` وجودِ برچسب را چک نمی‌کند؛ چک
می‌کند که **برچسب و اعدادِ زیرش یک ارز را بگویند** — در هر دو ارز پشتیبانی‌شده — و اینکه
برچسب نام ارز دیگر را نبرد. یک برچسب دست‌نویس این آزمون را رد می‌کند.

### ۲) سرریز افقی `#/period-report`

**بازتولید شد** (پیش از اصلاح، ممیزی چیدمان روی 8041): `pageOverflow = 4` در عرض ۳۶۰ و
`44` در عرض ۳۲۰ — ۲ شکست در ۱۹۰ اجرا.

**علت، یک عنصر بود.** `<fieldset>` در همهٔ مرورگرها `min-inline-size: min-content` پیش‌فرض
دارد و هیچ `min-width: 0` روی نیاکانش آن را لغو نمی‌کند.
`fieldset.period-builder__sections` با ردیف `minmax(13rem, 1fr)` کفِ ۲۷۴ پیکسلی می‌ساخت؛
`.period-report-page` یک grid با یک ستون خودکار است که کفش را عریض‌ترین آیتم تعیین می‌کند،
پس **هر سه** خواهر — سربرگ، سازندهٔ گزارش و کارت وضعیت — به ۳۴۰ پیکسل داخل والد ۲۵۷ پیکسلی
کشیده می‌شدند.

**اصلاح، دو خاصیت روی همان یک انتخابگر:**

```css
grid-template-columns: repeat(auto-fit, minmax(min(13rem, 100%), 1fr));
min-inline-size: 0;
```

بالای ۱۳rem، تابع `min()` همان ۱۳rem را برمی‌گرداند — یعنی **گرید دسکتاپ دقیقاً همان
گرید قبلی است**. `overflow-x: hidden` عمداً استفاده نشد: چیدمان را خراب نگه می‌داشت و
فقط بیرون‌زده را می‌بُرید.

اندازه‌گیری در مرورگر (Chrome، با شبیه‌سازی ابعاد دستگاه):

| عرض | سرریز صفحه قبل | سرریز صفحه بعد |
|---|---|---|
| ۳۲۰ | ۴۴ | **۰** |
| ۳۶۰ | ۴ | **۰** |
| ۳۹۰ | ۰ | **۰** |
| ۷۶۸ | ۰ | **۰** |
| ۱۴۴۰ (دسکتاپ) | ۰ | **۰** |

در عرض ۳۲۰: هر **۲۰ کنترل** داخل viewport، هیچ‌کدام بیرون؛ هر پنج برچسب بخش‌های گزارش و
همهٔ عنوان‌ها خوانا؛ **هیچ متن بریده‌شده‌ای** نیست.

`npm run audit:layout` روی 8041: **۱۹۰ اجرا، ۰ شکست** (پیش از این کار ۲، و پیش از بازبینی
قبلی ۱۷).

`#/level-one` لمس نشد و اسکرول افقی عمدی و قابل‌دسترسش (`vbars__viewport`) سر جایش است.
رنگ، فونت، RTL، ناوبری و هیچ محتوایی تغییر نکرد.

### ۳) مسیر نصب وابسته به Core

**قرارداد واقعی، از خود DDL استخراج شد** (نه از متن توضیحات):

| وابستگی | چه کسی لازمش دارد |
|---|---|
| جدول `msp_tasks` با ستون `id` از نوع `bigint` | `0009`: `finance_task_resource_map.task_id` کلید خارجی به `msp_tasks(id)` با `ON DELETE CASCADE` |
| جدول `msp_snapshots` | تریگر دامنهٔ `0009` برای یافتن پروژهٔ یک task به آن join می‌زند |
| `GRANT REFERENCES ON msp_tasks TO <نقش مهاجرت>` | در محیطی که نقش مهاجرت محدود است؛ گام اپراتور، نه کاری که `0009` بتواند برای خودش بکند |

`msp_resources` و `msp_resource_assignments` وابستگی **نیستند**: خودِ `0007` آن‌ها را
می‌سازد. `0001` تا `0008` بدون هیچ جدول Core اجرا می‌شوند.

**ابزار نصب معتبر Core در این مخزن وجود ندارد.** تنها چیز موجود
`scripts/demo/core_mirror.sql` است که سربرگ خودش می‌گوید «آینهٔ محلی Core برای دموی
یکپارچگی… هرگز روی دیتابیس Main/Core اعمال نمی‌شود و یک revision آلمبیک نیست». استفاده از
آن به‌عنوان نصب‌کنندهٔ تولیدی یعنی Finance مالک schema تیم دیگری شود — و انجام نشد.

**آنچه ساخته شد:** `backend/scripts/install_preflight.py` — همان پرسش‌ها را **پیش از**
شروع مهاجرت می‌پرسد. تا امروز `0009` خودش این را چک می‌کرد و پیام روشنی هم می‌داد، اما
**زمان‌بندی‌اش** مشکل بود: `alembic upgrade head` اول `0001` تا `0008` را اجرا می‌کند، پس
اپراتور یک پیش‌شرط پنج‌ثانیه‌ای را بعد از چند دقیقه DDL روی دیتابیسی به اندازهٔ تولید
می‌فهمید. (ارتقا اتمیک است و چیزی نیمه‌کاره نمی‌ماند، ولی rollback یک ارتقای بزرگ رایگان نیست.)

ابزار **کاملاً فقط-خواندنی** است (`SET TRANSACTION READ ONLY`) و آزمونش این را از روی درخت
نحوی اثبات می‌کند: هر چیزی که `execute` می‌شود باید `SELECT` باشد.

کدهای خروج: `0` آماده · `1` پیش‌شرط ناقص · `2` دیتابیس در دسترس نیست.

#### دستورهای تکرارپذیر

```powershell
# ۱) پیش از هر چیز — فقط می‌خواند، هیچ‌جا چیزی تغییر نمی‌دهد
python -m scripts.install_preflight --dsn postgresql://<user>@<host>:<port>/<database>

# ۲) فقط اگر خروجی «Every prerequisite is present» بود
$env:FINANCE_MIGRATION_DSN='postgresql://<user>@<host>:<port>/<database>'
python -m alembic upgrade head

# ۳) دوباره preflight — باید بگوید already at head
python -m scripts.install_preflight --dsn postgresql://<user>@<host>:<port>/<database>
```

Health check و smoke test فقط-خواندنی:

```
GET /                                                → 200
GET /openapi.json                                    → 200
GET /api/projects/<project>/finance/resources        → 200
GET /api/projects/<project>/finance/estimate-lines   → 200
GET /api/projects/<project>/finance/invoices         → 200
GET /api/projects/<project>/finance/files            → 200
GET /api/projects/<project>/finance/extractions      → 200
GET /api/projects/<project>/finance/progress-snapshots → 200
GET /api/projects/<project>/finance/audit-events     → 200
GET /api/projects/<project>/finance/settings         → 404 روی نصب تازه (هنوز تنظیماتی ثبت نشده)
```

#### نتایج راستی‌آزمایی روی دیتابیس‌های ایزوله

| سناریو | نتیجه |
|---|---|
| دیتابیس خالی، بدون Core | preflight **exit 1**؛ هر دو جدول را نام برد و گام بعدی را گفت. هیچ مهاجرتی اجرا نشد |
| Core نیمه‌سازگار (`msp_tasks.id` از نوع uuid، `msp_snapshots` غایب) | **exit 1**؛ «is uuid; finance_task_resource_map.task_id is bigint» — schema نیمه‌سازگار کورکورانه پذیرفته نشد |
| پیش‌شرط‌ها موجود | **exit 0**، سپس `alembic upgrade head` هر ۱۶ نسخه را از `0001` تا `0016` اجرا کرد |
| اجرای دوبارهٔ نصب | **۰ نسخه** اعمال شد، ledger روی `0016`، ۴۳ جدول — بی‌خطر |
| Smoke test روی همان نصب تازه | ۱۲ مسیر `200`، هیچ `500`؛ `settings` صادقانه `404` |
| کپی بازیابی‌شده `bambo_release_verify_20260909` | preflight **exit 0**، ledger `0016`، «already at head» |
| دیتابیس کاری `bambo_canonical_test` | preflight **exit 0** (فقط خوانده شد)، ledger `0013` — **هیچ تغییری اعمال نشد** |
| محافظ‌های `reconcile_release_schema` | دست‌نخورده؛ اجرای dry-run: `{"schemaMatches": true, "unchangedTables": 73}` |

> پیش‌شرط‌های Core در تمرین بالا از **schema آینهٔ دمو** آمدند تا رفتار ابزار اثبات شود.
> این یک **تمرین** است، نه نصب تولیدی: آینه یک fixture است و در گزارش به‌جای آن حساب نمی‌شود.

#### مانع باقی‌مانده (خارج از دسترس این مخزن)

**نصب سرتاسری مسدود است.** آنچه از تیم میزبان لازم است، دقیقاً یکی از این دو:

1. **بستهٔ مهاجرت خودِ Core** (نام بسته و نسخه/revision) که `msp_tasks` و `msp_snapshots` را
   می‌سازد — تا در یک دیتابیس تازه اول Core نصب شود و بعد Finance؛ **یا**
2. **اتصال به دیتابیس مشترک BAMBO** که Core از قبل این جدول‌ها را در آن نگه می‌دارد.

به‌علاوه، اگر نقش مهاجرت محدود است: `GRANT REFERENCES ON msp_tasks TO <نقش>`.

هیچ جدول Core در Finance ساخته یا کپی نشد و هیچ migration جدیدی اضافه نشد.

### تاریخ اثر تجاری برآوردها — عمداً در این وصله نیست

هیچ رکوردی به عقب تاریخ‌گذاری نشد، هیچ فیلتر تاریخی حذف نشد، و تاریخ گزارش‌دهی MPP به
رکوردهای برآورد نسبت داده نشد. رفتار فعلی («نامعلوم» به‌جای صفرِ کامل، وقتی شواهد تاریخی
کافی نیست) دست‌نخورده ماند.

برای حل واقعی، سه چیز از سمت کسب‌وکار لازم است:

1. **مرجع معتبر تاریخ اثر برآورد اولیه** — امروز فیلتر `created_at` است، یعنی «کِی ثبت شد»
   نه «از کِی معتبر بود». این دو در دادهٔ فعلی سه ماه فاصله دارند.
2. **چگونگی اثرگذاری بازنگری‌ها** — یک بازنگری از تاریخ ثبتش معتبر است، یا از تاریخی که
   کاربر اعلام می‌کند؟ گزارش یک دورهٔ گذشته باید کدام را ببیند؟
3. **تفاوت «اصلاح» با «تغییر واقعاً بعدی»** — اصلاحِ یک اشتباه باید در گزارش دورهٔ گذشته هم
   دیده شود؛ یک تغییر واقعی نباید. امروز هیچ فیلدی این دو را از هم جدا نمی‌کند.

بدون این سه، هر مدل تاریخی‌ای که پیاده شود، حدس است.

### تست‌ها

| سوئیت | پیش از این کار | پس از این کار |
|---|---|---|
| Backend | **1210 passed، 0 failed** | **1217 passed، 0 failed** (۲۳۶۹ subtest) |
| Frontend | **458 passed، 0 failed** | **462 passed، 0 failed** |
| `npm run check` | سبز | سبز |
| `npm run audit:layout` (8041) | ۱۹۰ اجرا، **۲ شکست** | ۱۹۰ اجرا، **۰ شکست** |

رفتار مجوز فاکتور دست‌نخورده است: ماتریس جداسازی (`test_invoice_permission_separation.py`،
۱۹ آزمون و ۸۱ subtest) در همین اجراها سبز است. این کار هیچ فایل مشترک احراز هویت یا
پیکربندی راه‌اندازی را لمس نکرد.

### فایل‌به‌فایل

| فایل | تغییر |
|---|---|
| `frontend/src/shared/formatters/money.js` | تابع جدید `displayCurrencyNote()` کنار همان فرمت‌کننده‌ای که باید با آن یکی باشد |
| `frontend/src/features/financial-items/financial-items-page.js` | یک `table-note` بالای جدول ریز برآورد |
| `frontend/src/features/period-report/period-report.css` | `min-inline-size: 0` و `minmax(min(13rem, 100%), 1fr)` روی `.period-builder__sections` |
| `backend/scripts/install_preflight.py` | **جدید** — تشخیص پیش‌شرط‌های Core، فقط‌خواندنی |
| `backend/tests/test_install_preflight.py` | **جدید** — فهرست پیش‌شرط‌ها را از خودِ DDL بازمی‌سازد و با ابزار مقایسه می‌کند |
| `frontend/tests/unit/display-currency-note.test.js` | **جدید** — سازگاری برچسب و اعداد در هر دو ارز |

---

**تاریخ:** ۱۴۰۵-۰۶-۰۶ · **شاخه:** `backend-finance` · **Schema:** `0006`

> هر ردیف یکی از سه حالت است: **PASS** · **FAIL** · **NOT_AVAILABLE**.
> هیچ ردیفی بدون اجرا، PASS اعلام نشده.

---

## خلاصه

| # | مورد | وضعیت |
|---|---|---|
| ۱ | Python 3.12 — نصب و اجرای سوئیت | ✅ **PASS** |
| ۲ | PostgreSQL 18 — نصب محلی یک‌بارمصرف | ✅ **PASS** |
| ۳ | چرخه کامل Alembic روی PG18 | ✅ **PASS** |
| ۴ | مقایسه Schema بین PG16 و PG18 | ✅ **PASS** |
| ۵ | امتناع Downgrade نسخه 0006 روی PG18 | ✅ **PASS** |
| ۶ | مسیر پاک Downgrade روی PG18 | ✅ **PASS** |
| ۷ | پشتیبان‌گیری محلی | ✅ **PASS** |
| ۸ | بازیابی محلی | ✅ **PASS** |
| ۹ | برنامه روی دیتابیس بازیابی‌شده | ✅ **PASS** |
| ۱۰ | تست بک‌اند روی Python 3.12 | ✅ **PASS** |
| ۱۱ | تست فرانت‌اند | ✅ **PASS** |

---

## ۱. Python 3.12 — PASS

```
نصب        : winget install Python.Python.3.12 --scope user
نسخه       : Python 3.12.10
pip        : 26.2.1
محیط       : E:\bamboo\FINANCE\.venv312
وابستگی‌ها  : requirements.txt + requirements-test.txt، بدون تغییر نسخه
سوئیت      : 616 تست — OK
```

**۳٫۱۳ و ۳٫۱۴ حذف یا جایگزین نشدند.** پیش‌فرض سیستم دست‌نخورده ماند.

### یک نقص واقعی که ۳٫۱۲ لو داد

سوئیت روی ۳٫۱۲ با **۲ خطا** شروع شد: `ModuleNotFoundError: uvicorn`.

تست‌ها برای گرفتن یک تابع کوچک (`check_port`)، **نقطه ورود سرور** را import می‌کردند و
uvicorn را با خود می‌کشیدند. روی `.venv` قدیمی این دیده نمی‌شد چون uvicorn آنجا نصب بود.

> این یک وابستگی اعلام‌نشده در سوئیت تست بود. نگهبان فاز ۴-الف آن را نگرفت چون فقط
> import های مستقیمِ `tests/*.py` را می‌بیند و این یکی **گذری** بود.

**اصلاح:** `check_port` به `devhost/environment.py` منتقل شد — جایی که بقیه سیاست پورت
زندگی می‌کند. حالا خواندن سیاست پورت، یک وب‌سرور را با خودش نمی‌آورد.

---

## ۲. PostgreSQL 18 — PASS

نصب‌کننده winget دسترسی مدیر می‌خواست و این Shell ندارد. مسیر بهتری انتخاب شد:

```
روش       : باینری‌های رسمی ZIP (بدون نصب‌کننده، بدون سرویس، بدون دسترسی مدیر)
نسخه      : PostgreSQL 18.0
محل       : E:\bamboo\_local\pg18
Cluster   : E:\bamboo\_local\pg18\data  (تازه initdb شده)
شنود      : listen_addresses = '127.0.0.1'   port = 5440
```

**PG16 و PG17 دست‌نخورده ماندند.** هیچ سرویسی ثبت نشد؛ Cluster کاملاً یک‌بارمصرف است و
فقط روی loopback گوش می‌دهد.

دیتابیس‌های ساخته‌شده:

```
bambo_finance_pg18_validation
bambo_finance_pg18_restore
```

هیچ‌کدام `bambo` نام ندارند. پیش از ساخت، هویت سرور از خودش پرسیده شد:
`PostgreSQL 18.0 · 127.0.0.1:5440`.

---

## ۳. چرخه Alembic روی PG18 — PASS

روی `bambo_finance_pg18_validation`:

| گام | نتیجه |
|---|---|
| `base → head` | ۶ Revision اعمال شد · `0006 (head)` |
| `head → base` | ۶ Revision معکوس شد |
| `base → head` | ۶ Revision اعمال شد |
| `upgrade head` دوباره | **۰ Revision** — no-op درست |

زنجیره: `0001 → 0002 → 0003 → 0004 → 0005 → 0006` · تک‌شاخه · **هیچ 0007**.

---

## ۴. مقایسه Schema بین PG16 و PG18 — PASS

| مورد | PG16 :5432 | PG18 :5440 | |
|---|---|---|---|
| `finance_alembic_version` | 0006 | 0006 | یکسان |
| ستون‌ها | ۲۰۶ | ۲۰۶ | **اثر انگشت یکسان** |
| Indexها | ۵۷ | ۵۷ | **اثر انگشت یکسان** |
| تریگرها | ۱۰ | ۱۰ | **اثر انگشت یکسان** |
| قیدها (خام) | ۹۸ | ۲۶۱ | متفاوت — توضیح زیر |
| قیدها (بدون NOT NULL) | ۹۸ | ۹۸ | **اثر انگشت یکسان** |

Index جزئی روی PG18: هر سه موجودند —
`ux_invoices_confirmation_idempotency_scope` ·
`ux_invoices_one_reversal_per_original` ·
`ux_progress_snapshot_refs_host_snapshot`

### یافته PG18 که باید بدانید

> **PostgreSQL 18، قیدهای NOT NULL را در `pg_constraint` ثبت می‌کند.** روی PG16 صفر ردیف؛
> روی PG18، ۱۶۳ ردیف با `contype = 'n'`.
>
> **Schema ما تفاوتی ندارد** — CHECK ۴۶ به ۴۶، FK ۱۴ به ۱۴، PK ۱۵ به ۱۵، UNIQUE ۲۳ به ۲۳.
> ولی هر ابزاری که ردیف‌های `pg_constraint` را **بشمارد**، روی ۱۸ عدد دیگری می‌بیند.
>
> دو Revision ما (`0005` و `0006`) `pg_constraint` را می‌خوانند، ولی **با نام و محدود به
> `conrelid`** — نه با شمارش. پس تحت تأثیر نیستند، و اجرای موفقشان روی PG18 همین را نشان داد.

---

## ۵. امتناع Downgrade نسخه 0006 روی PG18 — PASS

یک ردیف دقیقاً شبیه آنچه Adapter هسته وارد می‌کند درج شد: نام‌برنده یک Snapshot هسته، بدون
`source_file_version_id`.

```
alembic downgrade 0005
  exit code : 1  → REFUSED
  پیام      : Downgrade to 0005 refused: 1 progress_snapshot_refs row(s)
              have no source_file_version_id
```

**همه‌چیز بعد از امتناع دست‌نخورده ماند:**

```
✅ نسخه هنوز 0006
✅ ردیف آزمایشی سر جایش
✅ host_snapshot_id = 9001
✅ host_file_version_id = 1001
✅ هر دو ستون کنار هم
✅ هر دو Index (ux_... و ix_...)
```

> این محافظ **ضعیف نشد** و نباید بشود. بدون آن، Downgrade سعی می‌کرد ستون قدیمی را دوباره
> اجباری کند، به ردیف خالی می‌خورد و **وسط کار** شکست می‌خورد — با دیتابیسی نیمه‌تغییریافته.

---

## ۶. مسیر پاک Downgrade روی PG18 — PASS

روی `bambo_finance_pg18_restore` (بدون ردیف وارد‌شده از هسته):

```
upgrade head    OK → 0006 (head)
downgrade 0005  OK → 0005
upgrade 0006    OK → 0006 (head)
downgrade base  OK → (خالی)
upgrade head    OK → 0006 (head)
```

یعنی امتناع بخش ۵ **مشروط** است، نه یک بن‌بست دائمی: وقتی داده‌ای برای از دست‌دادن نیست،
Downgrade کار می‌کند.

---

## ۷. پشتیبان‌گیری محلی — PASS

```
هدف         : 127.0.0.1:5432 / bambo_finance_integration_demo
تأیید هدف   : از خود PostgreSQL، قبل از دستور
Client      : pg_dump (PostgreSQL) 16.15
فرمت        : -Fc (سفارشی)
فایل        : backend/.release-validation/demo-20260826-235451.dump
حجم         : 116,329 بایت (۱۱۳ KB)
زمان        : 2026-08-27T06:54:52Z
```

بازرسی بدون بازیابی: **۲۱۷ ورودی آرشیو · ۳۰ جدول داده‌دار**.

**دیتابیس Production پشتیبان‌گیری نشد.**

---

## ۸. بازیابی محلی — PASS

```
مقصد    : bambo_finance_restore_test  (تازه ساخته‌شده، جدا از دمو)
دستور   : pg_restore --no-owner --no-privileges
exit    : 0
```

**روی `bambo_finance_integration_demo` بازنویسی نشد. روی `bambo` بازنویسی نشد.**

## اعتبارسنجی بازیابی — PASS

مقایسه قطعی، نه چشمی:

| بررسی | دمو | بازیابی‌شده | |
|---|---|---|---|
| `finance_alembic_version` | 0006 | 0006 | ✅ |
| تعداد جدول | ۳۰ | ۳۰ | ✅ |
| شمارش هر جدول | — | — | ✅ **هر ۳۰ جدول** |
| ردیف‌های اثر انگشت | ۱۵۱ | ۱۵۱ | ✅ |
| هزینه واقعی تأییدشده | ۲۲٬۹۸۱٬۵۳۲٬۰۰۰ | همان | ✅ |
| **اثر انگشت SHA-256** | `275dcc01af12…` | `275dcc01af12…` | ✅ **یکسان** |

اثر انگشت روی تنظیمات، خطوط برآورد، بازنگری‌ها، نسخه‌های قیمت، فاکتورها، ردیف‌های فاکتور و
ارجاع‌های Snapshot گرفته شد — با ترتیب قطعی.

> شمارش می‌گوید **چند** ردیف هست؛ اثر انگشت می‌گوید **همان** ردیف‌ها هستند.

---

## ۹. برنامه روی دیتابیس بازیابی‌شده — PASS

API واقعی، یک‌بار روی هر دیتابیس:

```
settings · resources · prices · estimates · invoices · overview · report
                     هر هفت مورد، هر دو دیتابیس → ۲۰۰
```

| مقدار | دمو | بازیابی‌شده |
|---|---|---|
| زیربنا | 4250.0000 | همان ✅ |
| منابع / قیمت‌ها / خطوط / فاکتورها | ۱۰ / ۱۰ / ۱۱ / ۵۳ | همان ✅ |
| برآورد اولیه | ۶۸٬۰۰۰٬۰۰۰٬۰۰۰ | همان ✅ |
| برآورد بازنگری | ۷۲٬۲۴۸٬۰۰۰٬۰۰۰ | همان ✅ |
| هزینه واقعی | ۲۲٬۹۸۱٬۵۳۲٬۰۰۰ | همان ✅ |
| کار باقی‌مانده | ۵۰٬۹۲۰٬۲۱۲٬۰۰۰ | همان ✅ |
| پیش‌بینی نهایی | ۷۱٬۴۹۳٬۲۰۴٬۰۰۰ | همان ✅ |

پیکربندی دمو بعدش به حالت عادی برگشت.

---

## ۱۰–۱۱. تست‌ها

| | |
|---|---|
| بک‌اند روی **Python 3.12.10** | **۶۱۶ تست · OK** |
| فرانت‌اند | **۲۸۲ تست · pass ۲۸۲ · fail ۰** |
| `alembic heads` | `0006 (head)` — تک‌شاخه |
| Revisionها روی دیسک | ۶ — **هیچ 0007** |

---

## شکاف‌هایی که بسته شدند

| شکاف فاز ۴-الف | حالا |
|---|---|
| اعتبارسنجی Python 3.12 | ✅ بسته — نصب و اجرا شد |
| اعتبارسنجی PostgreSQL 18 | ✅ بسته — چرخه کامل روی PG18 واقعی |
| تمرین پشتیبان‌گیری | ✅ بسته — گرفته و بازرسی شد |
| تمرین بازیابی | ✅ بسته — اثر انگشت یکسان |
| تمرین بازگشت روی PG18 | ✅ بسته — امتناع و مسیر پاک، هر دو |
| دستورالعمل استقرار | ✅ بسته — چهار Runbook نوشته شد |
| فهرست Smoke test | ✅ بسته — آماده، اجرا نشده |

## شکاف‌هایی که باز مانده‌اند

| شکاف | چرا |
|---|---|
| Smoke test روی محیط مستقر | محیط مستقری وجود ندارد |
| تمرین پشتیبان روی هدف واقعی | دسترسی به هدف واقعی نداریم و نباید داشته باشیم |
| Pipeline استقرار | ساخته نشد — تصمیم زیرساختی است |

---

## دیتابیس Production

**در تمام این فاز لمس نشد.** هیچ اتصالی به `192.168.100.200` برقرار نشد، DSNش ساخته نشد،
و رمزش خواسته نشد. هر عملیات دیتابیسی روی `127.0.0.1` بود — پورت ۵۴۳۲ یا ۵۴۴۰ — و پیش از
هر نوشتن، هویت سرور از خودش پرسیده و بررسی شد.
