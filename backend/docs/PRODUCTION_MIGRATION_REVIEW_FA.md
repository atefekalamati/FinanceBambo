# بسته Review مهاجرت Production ماژول مالی BAMBO

## منابع و محدوده

- PRD: `BAMBO_FINANCE_MVP_PRD_FA_v1.1`
- قرارداد فنی: `BAMBO_FINANCE_INTEGRATION_KIT_v1.1`
- PostgreSQL پایه Production: 16؛ هدف سازگاری: 18
- Migration Production در این محیط اجرا نشده است.

## ترتیب اجرا

ترتیب دیگر دستی نیست: Alembic زنجیره را نگه می‌دارد و اجرا می‌کند.

1. `0001_finance_core`
2. `0002_invoice_confirmation`
3. `0003_invoice_linked_documents`
4. `0004_report_snapshot_payload`
5. `0005_progress_snapshot_source_type`
6. `0006_progress_snapshot_host_reference`
7. `0007_msp_resources_and_assignments`
8. `0008_price_intelligence`
9. `0009_finance_task_resource_map`
10. `0010_msp_task_metrics`
11. `0011_finance_mpp_source`
12. `0012_finance_mpp_row_fields`
13. `0013_finance_mpp_source_identity`
14. `0014_mpp_reporting_date`
15. `0015_finance_mpp_assignment_facts`
16. `0016_finance_mpp_estimate_basis`
17. `0017_snapshot_status_check`
18. `0018_snapshot_status_vocabulary`
19. `0019_finance_mpp_fixed_cost` (head)

### گراف نهایی · ۲۰۲۶-۰۹-۱۲

```
0016 → 0017 → 0018 → 0019 (head)
```

**خطی، با یک head.** پیش‌تر ۰۰۱۸ در این شاخه نبود و ۰۰۱۹ از ۰۰۱۷ آویزان بود با شکافِ
مستندشده. فایل ۰۰۱۸ از `origin/backend-finance` آورده شد — **فقط همان یک فایل، بدون هیچ
تغییر فرانت‌اندی** — و `down_revision` روی ۰۰۱۹ اصلاح شد.

**چرا خطی و نه یک merge revision.** دو migration از نظر schema مستقل‌اند: ۰۰۱۸ قیدِ
`progress_snapshot_refs.snapshot_status` را جابه‌جا می‌کند و ۰۰۱۹ هیچ کاری با آن جدول
ندارد. پس ترتیب بینشان یک انتخاب دفتری است، نه یک الزام. سه چیز تصمیم را گرفت:

1. **هیچ دیتابیس مشترکی ۰۰۱۹ را ندارد.** سرشماری هر ۳۷ دیتابیس محلی: دیتابیس ارائه روی
   `0016` است و ۰۰۱۹ فقط در هفت کپی دورریختنی. اصلاح والدِ revisionی که هیچ‌جا اعمال نشده،
   بازنویسی تاریخی که کسی به آن وابسته است نیست.
2. این مخزن عمداً زنجیرهٔ خطی نگه می‌دارد و دو آزمون از آن دفاع می‌کنند، با دلیلِ ثبت‌شده:
   «یک head دوم یعنی دو شاخهٔ تاریخ schema و یک latest مبهم.»
3. خودِ docstring ۰۰۱۹ از قبل همین را قول داده بود.

### آزموده‌شده روی

| | PG16 (۱۶٫۱۵) | PG18 (۱۸٫۶) |
|---|---|---|
| نصب تازه با پیش‌شرط‌های Core → head | ✅ exit 0 | ✅ exit 0 |
| ارتقا از وضعیت موجود → head | ✅ از `0016` | ✅ از `0017` |
| اثرانگشت نصب تازه و ارتقا | **یکسان** `2988af3923c843584e4750b186b260c1` | **یکسان** `032ced91c3d123f3f5e77be44e9e0205` |
| اجرای دوم upgrade | بی‌تغییر | بی‌تغییر |
| نصب تازه vs ارتقا، شیء‌به‌شیء | **۰ اختلاف** | **۰ اختلاف** |
| downgrade تا ۰۰۱۷ و upgrade دوباره | اثرانگشت برمی‌گردد | اثرانگشت برمی‌گردد |

مقایسهٔ شیء‌به‌شیء روی PG16: ۳۶۴ ستون، ۱۷۷ قید، ۱۰۱ ایندکس، ۱۲ trigger (با بدنهٔ تابع).

**داده حفظ شد.** ارتقا از ۰۰۱۶ روی کپی دیتابیس واقعی: `finance_mpp_rows` ۱۵۷۸ → ۱۵۷۸ ·
`estimate_lines` ۸۳۵ → ۸۳۵ · `finance_resources` ۱۸۹ → ۱۸۹ · `report_snapshots` ۱۶ → ۱۶ ·
`progress_snapshot_refs` ۴ → ۴ · `estimate_line_source_completions` ۲۸۹ → ۲۸۹ ·
`invoices` ۲ → ۲ · `finance_mpp_source_versions` ۲ → ۲.

**ستون جدید روی ردیف‌های موجود NULL می‌ماند** (۱۵۷۸ ردیف، ۰ مقدار ریالی) و با یک sync از
نوع `refresh` پر می‌شود. همان ۱۶۴ ردیفی که هزینهٔ ثابت اعلام می‌کنند سر جایشان هستند.

### محدودیت downgrade — اثبات‌شده، نه فرض‌شده

هر دو اجرای بالا تا ۰۰۱۷ تمیز پایین آمدند، چون هیچ‌کدام ردیف `superseded` نداشتند — که
شاهدِ کارکردنِ نگهبان نیست، شاهدِ پرسیده‌نشدنش است. پس روی یک کپی دورریختنی یک ارجاعِ
`superseded` **افزوده** شد (نه UPDATE: این جدول با trigger `finance_reject_mutation`
فقط‌افزودنی است — «immutable finance history cannot be updated or deleted») و بعد:

```
snapshot_status values held: {'superseded': 1, 'ready': 4}
downgrade 0018 → 0017 : exit 1، ledger روی 0019 ماند
  «downgrading to 0017 would reinstate a CHECK that rejects 1 row(s) this database
   already holds -- almost certainly snapshot_status = superseded»
downgrade 0019 → 0018 : exit 0  (۰۰۱۹ به‌تنهایی برمی‌گردد)
upgrade head          : exit 0
```

پس **روی هر دیتابیسی که گزارشی روی تاریخ گذشته pin کرده، بازگشت به پایینِ ۰۰۱۸ ممکن نیست**
— و امتناع می‌کند نه اینکه وسط کار بشکند.


```powershell
alembic current      # این دیتابیس کجاست
alembic upgrade head
alembic current      # باید 0019 باشد
```






## 0018 — واژگانی که آن ستون واقعاً نگه می‌دارد

`0017` درست تشخیص داده بود که این ستون باید بسته شود، ولی قاعده را از
`finance_mpp_source_versions.status` قرض گرفت: `ready` و `failed`. نسبت دو جدول درست بود،
واژگانشان نه. واژگان این ستون `ready` و `superseded` است و چهار جای مستقل همین را می‌گویند —
`schemas/progress.py` با `Literal["ready","superseded"]`، `contracts/openapi.json`،
schema کیت (`progress-snapshot.schema.json`)، و `tests/test_core_integration.py` که صریحاً
ادعا می‌کند وضعیت به `superseded` تبدیل می‌شود. هیچ‌کدام `failed` نمی‌گویند.

**این یک نقص نظری نبود.** `coreint/progress.py` مقدار `superseded` را به‌معنای «snapshot
بعدی به این یکی اشاره می‌کند» می‌سازد و در هدر feed می‌فرستد؛ `reference_from_header` همان را
مستقیم در این ستون می‌نویسد. پس **هر گزارشی که روی تاریخ گذشته pin شود** snapshotی را حل
می‌کند که بعدی‌ها جایگزینش کرده‌اند، و ذخیرهٔ ارجاعش قید را نقض می‌کرد — یعنی ۵۰۰ روی
گزارش‌های تاریخی، از رفتار درستِ خودِ ماژول. در مقابل `failed` که 0017 اجازه‌اش می‌داد، در
این ستون توسط هیچ‌چیز نوشته نمی‌شود.

چرا نسخهٔ جدید و نه ویرایش 0017: آن migration منتشر شده و اجرا شده — کامیت خودش اثرانگشت
شِما را از یک اجرای PG16 و یک PG18 ثبت کرده. migrationی که جایی اجرا شده تاریخ است؛ اصلاحش
در جا یعنی آن دیتابیس‌ها قیدی داشته باشند که هیچ نسخه‌ای توصیفش نمی‌کند.

هر دو جهت روی دادهٔ ناسازگار **امتناع می‌کنند** نه اینکه وسط کار روی نقض قید بشکنند. downgrade
عمداً همان قاعدهٔ تنگ‌تر 0017 را برمی‌گرداند — downgrade وضعیت قبلی را بازمی‌گرداند، بهترش
نمی‌کند — و اگر ردیف زنده‌ای `superseded` داشته باشد امتناع می‌کند.

## 0019 — هزینه‌ای که فایل می‌گوید و هیچ‌کس نمی‌خواند

MS Project پول را در دو جای تسک می‌گذارد: روی تخصیص‌های آن، و روی خود تسک به‌عنوان
**Fixed Cost** — مبلغی که به فعالیت تعلق دارد، نه به هیچ منبعی روی آن. خواننده از 0012 به بعد
دومی را در `finance_mpp_rows.source_fixed_cost` ذخیره می‌کرده و **هیچ کدی در `app/finance/`
آن را نخوانده است**. در برنامهٔ همین پروژه ۵۱٫۴۸ میلیارد ریال در ستونی نشسته بود که هیچ محاسبه‌ای
بازش نمی‌کرد.

**یک ستون، به واحدی که Finance با آن حساب می‌کند.** `source_fixed_cost` عدد خود فایل است،
دقیقاً مثل `source_cost` و `source_actual_cost` — پیشوند می‌گوید عدد مال کیست و نبودِ `_irr`
می‌گوید ریال نیست. فایل این پروژه به تومان است، پس خواندن آن ستون به‌عنوان پول ×۱۰ اشتباه
می‌شد، در جهتی که کسی متوجه نمی‌شود. `source_fixed_cost_irr` همان رقم است از مسیر همان تصمیم
ارزی که هزینهٔ تخصیص از آن می‌گذرد (`_currency_scale`). ستون خام دست‌نخورده می‌ماند: جواب فایل
است و باید بعد از این هم خواندنی بماند.

صفر از این تصمیم معاف است و فقط صفر: هیچ در هر ارزی هیچ است، و MS Project روی تقریباً هر تسکی
`0.0` می‌نویسد. بدون این معافیت، یک ارز تصمیم‌نگرفته برای برنامه‌هایی که اصلاً پول تسکی ندارند
هم کشنده می‌شد.

**دو ایندکس، دو هویت.** هزینهٔ ثابت به **تسک** تعلق دارد نه به تخصیص، پس
`ux_estimate_lines_source_assignment` نمی‌تواند نگهش دارد؛
`ux_estimate_lines_source_task_fixed_cost` همتای اوست: یک خط برآورد به ازای هر تسک، میان
خط‌هایی که تسک را نام می‌برند و تخصیص را نه. امروز هیچ ردیفی در آن وضعیت نیست — هر خط نگاشته‌شده
هر دو uid را دارد و هر خط Excel هیچ‌کدام را — پس ایندکس خالی شروع می‌کند و فقط خط‌هایی را که این
تغییر می‌سازد محدود می‌کند. و چون هزینهٔ ثابت هیچ منبعی را نام نمی‌برد، یک «هزینه عمومی» به ازای
هر پروژه ساخته می‌شود که این خط‌ها به آن وصل شوند؛ `ux_finance_resources_schedule_fixed_cost`
همان است که ساختنش را idempotent می‌کند. عمداً باریک است — یک کد، در یک پروژه — نه یک قاعدهٔ
یکتایی روی همهٔ کدهای منابع، که ادعایی دربارهٔ دادهٔ موجود است و این تغییر کاری با آن ندارد.

**داده بازنویسی نمی‌شود.** ستون جدید روی ردیف‌های موجود NULL است و با یک sync از نوع `refresh`
پر می‌شود — که دقیقاً برای همین وجود دارد: فایل تغییرنکرده را دوباره می‌خواند و ردیف‌های همان
نسخه را جایگزین می‌کند، بدون دست زدن به سطر نسخه، پس هر `progress_snapshot_refs` و هر گزارشی که
آن نسخه را pin کرده هنوز resolve می‌شود. گزارش‌های صادرشده از اساس مصون‌اند:
`report_snapshots.snapshot_payload` کل تغذیه را در لحظهٔ صدور منجمد می‌کند.

**بازگشت:** `downgrade` هر دو ایندکس و ستون را برمی‌دارد. دادهٔ ستون از فایل خوانده شده و با یک
sync دوباره به دست می‌آید. خط‌های برآوردِ ساخته‌شده را برنمی‌دارد — رکورد مالی‌اند و حذفشان کار
migration نیست.

**والدش ۰۰۱۸ است.** برای مدتی ۰۰۱۸ در این شاخه نبود و این revision با شکافِ مستندشده از
۰۰۱۷ آویزان بود؛ فایل آورده شد و والد اصلاح شد. گراف نهایی و اجراهایی که آن را اثبات
می‌کنند در بند «گراف نهایی» بالای همین سند.

**تأیید شده روی هر دو نسخه.** PG16 و PG18، روی نسخهٔ کپی‌شدهٔ همان دیتابیس‌هایی که 0017 با
آن‌ها سنجیده شد: اعمال، اجرای دوم بدون تغییر، `downgrade 0017` و `upgrade head` دوباره.

| | PG16 | PG18 |
|---|---|---|
| پیش از 0019 (روی 0017) | `f652db5f2ec7e0a162b64582e9edafb2` | `40955a209760a7353d768dce9da2f0b7` |
| پس از 0019 | `c47d42d2692e3a1c46fb91b664e0284c` | `3cfe1d23898f87b4d777f68d2cf684e3` |
| اجرای دوم | همان | همان |
| پس از downgrade | دقیقاً برابر سطر اول | دقیقاً برابر سطر اول |
| پس از upgrade دوباره | دقیقاً برابر سطر دوم | دقیقاً برابر سطر دوم |

`alembic upgrade 0017:head --sql` هم ستون را می‌سازد، پس حالت offline کار می‌کند.

**و یک‌بار تا انتها اجرا شد.** روی یک کپی از دیتابیس آزمایشی که ردیف‌های واقعی فایل را دارد:
`refresh` هر ۷۸۹ ردیف را دوباره نوشت و هر ۷۸۹ رقم ریالی گرفتند؛ نگاشت سه خط «هزینه عمومی» ساخت
(۲۸٬۲۹۶٬۸۸۰٬۰۰۰ و ۲۹٬۷۲۱٬۶۰۰٬۰۰۰− و ۵۲٬۹۰۹٬۶۰۰٬۰۰۵ ریال، جمعاً ۵۱٬۴۸۴٬۸۸۰٬۰۰۵) و ۲۱ ردیف
ته‌ماندهٔ زیر یک تومان را کنار گذاشت و شمرد؛ اجرای دوم `created=0 matched=3` داد. آنچه Finance
از فایل می‌خواند حالا **۳٬۶۵۷٬۳۰۸٬۸۴۷٬۷۸۰٫۹۰ ریال** است در برابر **۳٬۶۵۷٬۳۰۸٬۸۴۷٬۸۴۰ ریال** که
خود MS Project برای پروژه می‌گوید — اختلاف ۵۹٫۱۰ ریال، که دقیقاً همان ته‌ماندهٔ کنارگذاشته‌شده
است.

## 0017 — تنها ستون وضعیتی که هیچ CHECKی نداشت

`progress_snapshot_refs.snapshot_status` از 0001 به بعد `text NOT NULL` خالی بود، در حالی که
هر ستون وضعیت دیگری در شِمای مالی واژگانش را با CHECK می‌بندد — `finance_mpp_source_versions.status`
دقیقاً `ready` و `failed` را می‌پذیرد و ستون‌های فاکتور، پیوست، استخراج، import و اجرای قیمت هم
همین‌طور. این یکی جا مانده بود.

قاعده‌ای که گرفت همان قاعدهٔ نسخهٔ منبع است، چون ارجاع snapshot در عمل ارجاع به تغذیهٔ یک نسخهٔ
منبع است و این دو با هم خوانده می‌شوند: `active_source_version` روی `status = 'ready'` فیلتر
می‌کند و ارجاعی که چیز دیگری باشد ارجاعی است که گزارش نمی‌تواند از آن استفاده کند.

**تأیید شده روی هر دو نسخه.** PG16 و PG18: اعمال، اجرای دوم بدون تغییر، `downgrade 0016` و
`upgrade head` دوباره — اثرانگشت شِما در هر نسخه پیش و پس یکسان
(PG16 `f652db5f2ec7e0a162b64582e9edafb2`، PG18 `40955a209760a7353d768dce9da2f0b7`).
تعداد قید دقیقاً یکی بالا رفت. هیچ ردیفی بازنویسی نشد.

## 0015 — آنچه فایل دربارهٔ هر تخصیص می‌گوید

`finance_mpp_rows` تا اینجا ارقام **تسک** را روی هر ردیف می‌نوشت: `finance_mpp_sync` یک
دیکشنری برای هر تسک می‌ساخت و روی تک‌تک تخصیص‌های آن کپی می‌کرد، پس تسکی با هفت تخصیص جمع
خودش را هفت بار ذخیره می‌کرد. فایل بیشتر از این می‌گوید — `assignment.getUnits()` و
`assignment.getCost()` برای هر ۷۲۷ تخصیص خوانده می‌شدند و بعد دور ریخته می‌شدند.

**دو نرمال‌سازی، هیچ‌کدام حدس.** MPXJ واحدها را با مقیاس صد برمی‌گرداند (۵۶۰۰۰ آنجا که فایل
۵۶۰ نشان می‌دهد) و عدد ذخیره‌شده همانی است که فایل نشان می‌دهد. فایل هم
`currencySymbol = تومان` می‌گوید و هم `currencyCode = IRR` — که با هم نمی‌خوانند — و ارقامش
با اعداد تومانِ همان دیالوگ یکی است؛ Finance همه‌جا ریال ذخیره می‌کند، پس مبلغ در ورود ×۱۰
می‌شود و آن‌وقت نام `_irr` دربارهٔ ستون راست است.

**آنچه این نیست.** `source_assignment_units` همان `quantity` نیست: `quantity` مقدار مالیِ
تأییدشده است و تا وقتی کسی تأیید نکند NULL می‌ماند. `unit_confidence` هم می‌گوید واحد چقدر
قابل اتکاست؛ واحدی که شناخته نشد NULL می‌ماند، نه اینکه ساخته شود.

**بازگشت:** `downgrade` هر پنج ستون و ایندکس را برمی‌دارد. داده‌ای که این ستون‌ها نگه
می‌دارند از فایل خوانده شده و با یک sync دوباره به دست می‌آید.


## 0013 — جای ثبت اینکه هر رکورد Finance از کدام ردیف MPP آمده

‏0011 و 0012 خواندن و نگه‌داشتن زمان‌بندی را ممکن کردند، ولی هیچ‌چیز آن ردیف‌ها را به
رکوردهای مالی (منبع و خط برآورد) تبدیل نمی‌کرد. برای این کار یک چیز کم بود: جایی برای نوشتن
اینکه هر رکورد Finance از **کدام ردیف فایل** آمده، تا خواندن دوبارهٔ همان فایل بفهمد چه چیزی
را قبلاً ساخته و دوباره نسازد.

**چرا ستون‌های موجود به کار نمی‌آمدند.** `finance_resources.external_resource_id` و
`estimate_lines.assignment_external_id` گزینه‌های بدیهی‌اند و هر دو تله‌اند، چون روی این
دیتابیس از قبل چیز دیگری در آن‌ها است: seed قدیمی **UID تسک‌های MSP** را نوشته و آن اعداد با
UID منبع و تخصیصِ فایل هم‌پوشانی دارند:

```
MPP resource 157 = «آبپاش»
external_resource_id "157" = MSP-T157 «ساخت و نصب وال پست دیوار»
```

۵ منبع از ۶۸ و ۵ تخصیص از ۷۲۷ همین‌طور برخورد می‌کنند. بازاستفاده از آن ستون‌ها یا روی
ایندکس یکتای جزئی شکست می‌خورد یا — بسیار بدتر — یک آبپاش را بی‌صدا به یک وال‌پست وصل
می‌کرد؛ همان نگاشت تصادفی که این کار برای پایان‌دادن به آن انجام شده. پس شناسه‌های فایل ستون
خودشان را گرفتند و ستون‌های قدیمی معنای قدیمی‌شان را نگه داشتند.

**آنچه ایندکس‌های یکتا تصمیم می‌گیرند**
- یک منبع مالی به ازای هر منبع MPP، در دامنهٔ پروژه — عمداً **نه** در دامنهٔ نسخهٔ منبع،
  چون «بتن ۴۰۰» در فایل این ماه و ماه بعد یک قلم مالی با یک تاریخچهٔ قیمت است، نه دو تا.
- یک خط برآورد به ازای هر تخصیص MPP — تخصیص دقیقاً یعنی «این منبع، روی این فعالیت»، که
  همان تعریف خط برآورد است. پس خواندن دوبارهٔ فایل بدون تغییر، هر خط را **match** می‌کند نه
  duplicate.

هر دو **جزئی** (partial) هستند: منبعی که با دست وارد شده هویت MPP ندارد و باید بتواند
هم‌زیستی کند. `NULL` یعنی «از فایل نیامده»، نه «ردیف فایلش نامعلوم است».

`source_task_uid` روی خط برآورد فقط برای **تأیید متقابل** است — تا re-sync ببیند یک تخصیص به
تسک دیگری منتقل شده، به‌جای اینکه بی‌صدا جذبش کند. هیچ کلیدی روی آن نیست.

هیچ ستونی در این Revision مقدار، قیمت، پیشرفت یا هزینه نگه نمی‌دارد. فقط **هویت**.

## 0012 — بقیهٔ آنچه Finance واقعاً از زمان‌بندی می‌خواند

‏0011 فقط اعدادی را نگه داشت که یک محاسبه مصرف می‌کند. صفحهٔ پیشرفت بیش از آن می‌خواند، و هر
فیلدی که می‌خواند از منبع Finance خالی می‌آمد در حالی که منبع Core پُرش می‌کرد — یعنی یک صفحه
روی یک snapshot کامل و روی دیگری خالی به‌نظر می‌رسید. این Revision دقیقاً فیلدهایی را اضافه
می‌کند که **مصرف‌کنندهٔ واقعی** دارند و نه بیشتر.

**افزوده‌شده و اینکه چه کسی خواسته:**
- `task_start` / `task_finish` — صفحهٔ پیشرفت آن‌ها را «شروع/پایان» نشان می‌دهد. **text**،
  دقیقاً مثل `msp_tasks` و دقیقاً همان‌طور که فایل می‌گوید: زمان‌بندی تاریخ دیواری بدون
  منطقهٔ زمانی می‌نویسد و تبدیل به timestamptz یعنی انتخاب منطقه‌ای که فایل هرگز نگفته.
- `resource_type` — نوع منبع در همان صفحه نمایش داده می‌شود.
- `resource_unit` — واحد خودِ منبع. این **واحد مقدار مصوب نیست**؛ `quantity_unit` سر جایش
  می‌ماند و این دو ادعای متفاوت دربارهٔ دو عدد متفاوت‌اند.
- `progress_variance` — از قبل در قرارداد metrics فید اعلام شده بود و فقط منبع Finance
  همیشه برایش null می‌داد.

**عمداً اضافه نشد:** فیلدهای Work و درصد تکمیل تخصیص — چون
`resolve_progress_quantity` کارِ گزارش‌شده را برای منبع نیروی انسانی/تجهیزات به‌عنوان
**مقدار اجراشده** می‌خواند؛ ذخیره‌کردنشان آن مسیر را برای منبع Finance باز می‌کرد و پول را
جابه‌جا می‌کرد، که تصمیمی مالی است نه کار این Revision. همچنین `outline_number` و
`outline_level`، چون والدِ WBS از خودِ رشتهٔ کد ساخته می‌شود و هیچ‌کس این دو را نمی‌خواند.

**تغییر نام، چون نام‌های قبلی تله بودند:** `cost`/`actual_cost`/`fixed_cost` ارقام **خودِ
زمان‌بندی**‌اند. هزینهٔ واقعی Finance فقط از فاکتورهای تأییدشده می‌آید، و ستونی به نام
`actual_cost` داخل یک جدول Finance دقیقاً همان اشتباهی را دعوت می‌کند که PRD هشدار داده.
به `source_cost` / `source_actual_cost` / `source_fixed_cost` تغییر نام دادند — پیشوند
می‌گوید عدد مال کیست. RENAME است نه ستون تازه، پس هر ۷۲۷ مقدار با معنای خودشان جابه‌جا شدند.

`quantity` دقت اعلام‌شده‌اش را گرفت: `numeric(18,4)`. امروز همهٔ مقادیر NULL‌اند، پس چیزی
گرد نشد.

**Downgrade:** نام‌ها برمی‌گردند و پنج ستون افزوده حذف می‌شوند؛ هیچ ردیفی از جدول دیگری
دست نمی‌خورد.

## 0011 — Finance-Owned MPP Source (`finance_mpp_source_versions` + `finance_mpp_rows`)

Finance فایل MPP را مستقیم می‌خواند، ولی تا این Revision چیزی از آن **ذخیره نمی‌کرد**؛
مقادیر فقط به‌اندازهٔ یک request در feed زندگی می‌کردند. برای بازتولید گزارش‌های گذشته و
برای استقلال واقعی از MSP، این دو جدول مالکیت Finance را بر دادهٔ موردنیازش برقرار می‌کنند.

- `finance_mpp_source_versions`: یک ردیف به ازای هر **محتوای متمایز فایل** (SHA-256). همان
  بایت‌ها = همان نسخه (sync خودکار idempotent)؛ بایت جدید = نسخهٔ جدید (تاریخچه حفظ می‌شود).
  **مسیر ذخیره نمی‌شود** — مسیر از `MPP_IMPORT_ROOT` می‌آید و جابه‌جایی به VPS نباید ردیف را
  بی‌اعتبار کند.
- `finance_mpp_rows`: ردیف‌های موردنیاز Finance، با **شناسه‌های خودِ MPP**
  (`source_task_uid` / `source_assignment_uid` / `source_resource_uid`). هیچ
  `msp_tasks.id`، `msp_snapshots.id` یا شناسهٔ Bridge در آن نیست.

**Quantity قابل NULL و امروز NULL است.** ستون وجود دارد تا معماری برای فایلی که Quantity
مصوب دارد آماده باشد؛ فایل فعلی چنین ستونی ندارد (اثبات: هر ۲۲ alias آن ضریب وزنی، حجم
برنامه‌ای یا شاخص پیشرفت است). پرکردن آن از Work/Duration/Cost/درصد، عددی می‌ساخت که هیچ‌کس
نمی‌توانست ساختگی‌بودنش را تشخیص دهد.

**حذف `msp_task_metrics`.** فقط برای اتصال نادرست Finance↔Core ساخته شده بود؛ Finance دیگر
به هیچ چیز join نمی‌کند و سمت MSP هیچ خواننده‌ای ندارد (نویسنده داشت، خواننده نه). Downgrade
همان جدول را دقیقاً بازمی‌سازد؛ ردیف‌ها با re-import برمی‌گردند.

## 0010 — Per-Task Schedule Metrics (`msp_task_metrics`)

یک زمان‌بندی عمرانی در این مجموعه، روی هر Task ستون‌های سفارشی نگه می‌دارد که پایهٔ هر
Rollup مالی‌اند: آحجام هرآیتم، ضرایب وزنی (ریالی/زمانی/مبنا)، معیارهای پیشرفت
(واقعی/فیزیکی/برنامه‌ای) و Cost خودِ Task. تا پیش از این Revision هیچ‌کدام خوانده نمی‌شدند.

**Entity واقعی:** هر ۲۲ فیلد سفارشی این فایل **Task-level** هستند (تأیید با probe؛ روی
Resource و Assignment هیچ فیلد سفارشی وجود ندارد). پس در سمت Core ذخیره می‌شوند، نه در
Finance.

**قواعد رعایت‌شده**
- `msp_tasks` **تغییر نکرد** — هیچ ستون جدیدی به آن اضافه نشد.
- کمیت منبع در `msp_resources.resource_quantity` و کمیت تخصیص در
  `msp_resource_assignments.*_quantity` می‌ماند؛ در این جدول تکرار نمی‌شود.
- Bridge (`finance_task_resource_map`) همچنان دقیقاً سه ستون است؛ هیچ Quantity/Cost/
  Progress/Weight واردش نشد.
- Finance این داده‌ها را **Duplicate نمی‌کند**؛ فقط از طریق Progress Feed می‌خواند.
- `raw_fields_json` روی `msp_tasks` کل ستون‌های alias‌دار (شامل ستون‌های هنوز نگاشت‌نشده)
  را نگه می‌دارد؛ فیلدهایی که واقعاً Query/Calculation می‌شوند typed هستند.

**خواندن با alias، نه با شمارهٔ Number.** برنامه‌ریز ستون را نام‌گذاری کرده
(«ضریب وزنی ریالی»)؛ اینکه در کدام `NumberN` نشسته بین فایل‌ها پایدار نیست. خواننده با
alias نگاشت می‌کند و ستون‌های این جدول به **معنا** نام‌گذاری شده‌اند.

**بدون CHECK روی مقدار.** این جدول آنچه فایل می‌گوید را ثبت می‌کند و «اختلاف پیشرفت»
می‌تواند منفی باشد؛ یک CHECK که آن را رد کند، فایل معتبر را به Import شکست‌خورده تبدیل
می‌کرد.

**بدون FK به Core.** همان قاعدهٔ 0007، و همان اصلی که 0009 پین کرد: تنها یک کلید مجاز به
Core می‌رود (`finance_task_resource_map.task_id`). این جدول لینک منطقی
`snapshot_id`/`task_uid` را دارد که Importer برقرارش می‌کند.

**Downgrade:** فقط `DROP TABLE msp_task_metrics` — هیچ ردیفی از جدول دیگری حذف نمی‌شود.

## 0008 — Price Intelligence Provider/Observation Layer

این Revision فقط ساختار افزایشی هسته قیمت آنلاین را ایجاد می‌کند. داده خام Provider ابتدا
در `price_observations` ثبت می‌شود و هیچ مسیر مستقیمی برای بازنویسی `price_versions` ندارد.
Observationها immutable هستند و تنها نتیجه Validation/Resolution تأییدشده می‌تواند از مسیر
سرویس موجود قیمت، یک PriceVersion جدید و append-only بسازد.

جداول افزوده‌شده:

- `price_providers`
- `provider_items`
- `provider_resource_mappings`
- `price_collection_runs`
- `price_observations`
- `price_collection_schedules`
- `price_resolution_policies`

تمام داده‌های عملیاتی Scope دوگانه سازمان/پروژه، FKهای `RESTRICT`، Decimal دقیق، وضعیت‌های
Text + CHECK و Indexهای Scope دارند. Up migration هیچ جدول یا رکورد قبلی را تغییر نمی‌دهد.
Downgrade جداول همین Revision را حذف می‌کند و بنابراین فقط با Backup و مجوز صریح قابل اجراست.

هر Revision داخل transaction خودش اجرا می‌شود (`env.py` آن را باز می‌کند) و اجرا روی اولین
خطا متوقف می‌شود. بدنه‌ها از نظر ساختاری rerunnable طراحی شده‌اند: `IF NOT EXISTS` روی جدول‌ها
و Indexها، `DROP TRIGGER IF EXISTS` پیش از هر `CREATE TRIGGER`، و برای 0005 یک بررسی صریح
`pg_constraint` که `ADD CONSTRAINT` نمی‌تواند بیان کند.

**نکته مهم برای دیتابیسی که Schema دارد ولی جدول `alembic_version` ندارد:** چون هر پنج
Revision rerunnable هستند، `alembic upgrade head` روی چنین دیتابیسی بدون خطا اجرا می‌شود و
در پایان `0005` را ثبت می‌کند. `alembic stamp` لازم نیست — و `stamp` روی دیتابیسی که وضعیت
واقعی‌اش تأیید نشده، خطرناک‌تر است، چون بدون اجرای چیزی ادعا می‌کند Migration انجام شده.

## 0009 — پیوند Task زمان‌بندی Core به Resource مالی

این Revision جدول `finance_task_resource_map` را می‌سازد: دقیقاً سه ستون
(`id uuid PK`، `task_id bigint`، `resource_id uuid`) با `UNIQUE (task_id, resource_id)`
و Index معکوس روی `resource_id`. دامنه سازمان/پروژه عمداً در این جدول تکرار نمی‌شود؛
هر دو سرِ پیوند آن را دارند و هر خواندنی از مسیر `finance_resources` عبور می‌کند.

**تصمیم ثبت‌شده — اولین FK به جدول Core:** `task_id` با
`REFERENCES msp_tasks (id) ON DELETE CASCADE` و `resource_id` با
`REFERENCES finance_resources (id) ON DELETE RESTRICT` تحمیل می‌شوند. این تصمیم صریح
مالک پروژه است و قاعده «صفر FK به Core» (مستند 0007) را فقط برای همین یک جفت برمی‌دارد؛
تست `test_core_alignment.py::test_exactly_the_sanctioned_key_reaches_into_core` همان
یک استثنا را پین می‌کند.

**پیش‌نیاز عملیاتی Production:** نقش Migration تولیدی طبق مستند 0007 امتیاز
`REFERENCES` روی جداول Core ندارد. پیش از اجرای 0009 در چنین محیطی الزامی است:

```sql
GRANT REFERENCES ON msp_tasks TO <migration role>;
```

بدون این GRANT، اجرای 0009 با خطای privilege متوقف می‌شود (و هیچ چیزی تغییر نمی‌کند؛
Revision داخل Transaction اجرا می‌شود).

**حفاظت Cross-Project:** یک Constraint Trigger
(`finance_task_resource_map_scope`) هنگام INSERT/UPDATE مسیر
`task → msp_snapshots.project_id` را با `finance_resources.project_id` مقایسه می‌کند و
در صورت اختلاف یا حل‌نشدن پروژه Task با SQLSTATE `23514`/`23503` رد می‌کند (fail-closed).
برابری سازمان — که سمت MSP ستونی برای آن ندارد — در لایه سرویس Import از روی Auth
Context تحمیل می‌شود.

**پیش‌بررسی وجود Core و قفل ضد-race:** ‏Revision ابتدا با `to_regclass('msp_tasks')`
fail-fast می‌کند (روی دیتابیس بدون Core، پیام دستورالعمل‌دار؛ آزموده: DB خام کاملاً
دست‌نخورده ماند) و سپس `LOCK TABLE finance_resources IN SHARE ROW EXCLUSIVE MODE`
می‌گیرد تا بین شمارش تکراری‌ها و ساخت Index یکتا هیچ نویسنده‌ای نلغزد.

**Index یکتای جزئی روی `finance_resources`:**
`ux_finance_resources_external_identity` روی
`(organization_id, project_id, external_resource_id)` فقط برای ردیف‌های زنده
(`external_resource_id IS NOT NULL AND deleted_at IS NULL`). پیش از ساخت، یک DO-block
داده تکراری را می‌شمارد و در صورت وجود با پیام شمارش‌دار متوقف می‌شود — این Migration
هرگز خودش ردیفی را merge یا حذف نمی‌کند.

**Downgrade:** فقط Trigger، Function، جدول پیوند و Index یکتا را حذف می‌کند؛ هیچ ردیفی
از `finance_resources` یا جداول Core لمس نمی‌شود. چون Downgrade جدولِ داده‌دار را حذف
می‌کند، اجرای آن در Production فقط با Backup و مجوز صریح مجاز است.

**نتیجه اجرا (محلی):** چرخه up/down/up روی دیتابیس خراشه سبز؛ ده رفتار runtime
(یکتایی جفت، دو شاخه رد Trigger، CASCADE/RESTRICT، رد NULL، Index جزئی با
soft-delete) با SQLSTATE مورد انتظار تأیید شد؛ `bambo_canonical_test` بدون خطا به 0009
ارتقا یافت (صفر گروه تکراری در پیش‌بررسی).

## نتیجه Validation

| Gate | نتیجه واقعی |
|---|---|
| تست ساختاری Migration | PASS — 15/15 |
| PostgreSQL 16 | BLOCKED — Docker daemon/سرور محلی موجود نیست |
| PostgreSQL 18 | BLOCKED — Docker daemon/سرور محلی موجود نیست |
| Rollback واقعی | BLOCKED |
| نبود `ON DELETE CASCADE` تاریخچه | PASS |
| `numeric(18,0)` پول و Decimal quantity | PASS |
| Scope indexها | PASS |
| Triggerهای immutable/append-only | PASS |

## 0005 — منبع نسخه پیشرفت

یک ستون `source_type text` به `progress_snapshot_refs` اضافه می‌کند تا مبدأ نسخه
پیشرفت به‌جای حدس‌زدن از پسوند نام فایل، صریح ثبت شود.

| مورد | وضعیت |
|---|---|
| `ADD COLUMN` بدون `DEFAULT` | PASS — تغییر فقط در Catalog، هیچ ردیفی بازنویسی نمی‌شود |
| اجرا روی PostgreSQL 16.4 واقعی | PASS — اجرا شد |
| اجرای دوباره (idempotent) | PASS — دو بار اجرا شد، نتیجه یکسان |
| Rollback واقعی | PASS — اجرا شد، ستون و CHECK حذف شد، سپس دوباره اعمال شد |
| Rollback دوباره (idempotent) | PASS |
| ردیف‌های موجود | PASS — هر ۳ ردیف `NULL` ماندند، هیچ Backfill انجام نشد |
| CHECK روی مقادیر مجاز | PASS — چهار مقدار مجاز و `NULL` پذیرفته؛ `msp`، `Microsoft Project` و `''` رد شد (همه در Transaction و Rollback) |
| سازگاری با Trigger تغییرناپذیری | PASS — `ALTER TABLE` Trigger را فعال نمی‌کند |

**نکته مهم برای Production:** Trigger `progress_snapshot_refs_immutable` هر `UPDATE`
را رد می‌کند (روی داده واقعی آزموده شد). یعنی `source_type` فقط در لحظه `INSERT`
قابل تعیین است و ردیف‌های موجود هرگز مقدار نمی‌گیرند مگر آنکه نسخه دوباره Import شود.
این عمدی است: تاریخچه پیشرفت append-only است و باید بماند.

**Backfill انجام نشد و نباید انجام شود.** مبدأ واقعی ردیف‌های موجود در هیچ‌جا ثبت
نشده است؛ `NULL` یعنی «ثبت نشده» که درست است، و `'other'` یعنی «ثبت شد که ابزاری
بیرون از فهرست بوده» که ادعایی بدون پشتوانه است.

## 0006 — مرجع Snapshot در Core

**مشکلی که حل می‌کند:** تا پیش از این، تنها چیزی که در `progress_snapshot_refs` می‌نوشت
Seed توسعه بود. روی یک دیتابیس واقعی — که Seed در آن ممنوع است — این جدول همیشه خالی
می‌ماند، هر گزارش زنده ۴۰۴ می‌گرفت و هیچ گزارشی هرگز صادر نمی‌شد.

**راه‌حل:** وقتی یک عملیات مالی باید به یک Snapshot مشخص Core گره بخورد، Finance از طریق
Adapter مرجع می‌سازد یا مرجع موجود را دوباره استفاده می‌کند. بدون هیچ عملیات دستی کاربر.

| موضوع | تصمیم |
|---|---|
| نوع شناسه Core | `bigint` — مطابق `msp_snapshots.id` و `msp_file_versions.id` |
| FK فیزیکی به Core | **ندارد.** Core با حذف پروژه، Snapshotها را CASCADE می‌کند؛ کلید RESTRICT حذف پروژه را در Core مسدود می‌کرد و CASCADE تاریخچه مالی را از بین می‌برد. اعتبارسنجی در Adapter انجام می‌شود |
| Idempotency | Index یکتای جزئی؛ یک Snapshot از Core هرگز دو مرجع Finance نمی‌سازد |
| ستون‌های قدیمی UUID | حذف **نشدند** و بازنویسی نشدند. `progress_snapshot_id` حالا شناسه عمومی خودِ Finance است؛ حذفش هر Route و هر گزارش صادرشده تغییرناپذیر را می‌شکست |
| Backfill | ندارد. `NULL` یعنی «به Snapshotی در Core وصل نبوده» که درباره هر ردیف قدیمی درست است |
| تریگر تغییرناپذیری | فعال نمی‌شود: `ADD COLUMN` بدون DEFAULT فقط تغییر Catalog است و `DROP NOT NULL` هم DDL است، نه UPDATE ردیف |

> **جدول نسخه Migration:** Alembic از `finance_alembic_version` استفاده می‌کند، نه
> `alembic_version` عمومی. Finance فقط مالک زنجیره Migration خودش است، نه مالک Migration
> کل دیتابیس مشترک BAMBO؛ اگر Core بعداً Alembic بگیرد، دو ماژول روی یک ردیف `version_num`
> برخورد نمی‌کنند.

## Expected Schema Diff

### جدول‌های جدید در Migration پایه

- `finance_project_settings`
- `finance_resources`
- `estimate_lines`
- `estimate_revisions`
- `price_versions`
- `unit_conversions`
- `progress_snapshot_refs`
- `progress_overrides`
- `invoices`
- `invoice_lines`
- `finance_attachments`
- `extraction_drafts`
- `report_snapshots`
- `finance_audit_events`
- `finance_import_batches`

تمام جدول‌ها هر دو کلید `organization_id` و `project_id` و index دامنه دارند.

### ستون‌های افزوده‌شده پس از Migration پایه

- `invoices.confirmation_idempotency_key`
- `report_snapshots.snapshot_payload`
- `report_snapshots.resource_version_ids`
- `progress_snapshot_refs.source_type`
- `progress_snapshot_refs.host_snapshot_id` — `bigint`, Nullable, بدون DEFAULT
- `progress_snapshot_refs.host_file_version_id` — `bigint`, Nullable, بدون DEFAULT
- `progress_snapshot_refs.source_file_version_id` — `NOT NULL` برداشته شد (ستون حذف نشد)

### Indexهای افزوده‌شده پس از Migration پایه

- `ux_invoices_confirmation_idempotency_scope`
- `ux_invoices_one_reversal_per_original`
- `ux_progress_snapshot_refs_host_snapshot` — یکتای **جزئی** روی
  `(organization_id, project_id, host_snapshot_id) WHERE host_snapshot_id IS NOT NULL`
- `ix_progress_snapshot_refs_host_file_version`

### Constraint و حفاظت تاریخچه

- FKهای تاریخچه با `ON DELETE NO ACTION`
- Price/Estimate revision/Conversion/Progress reference/Override/Report/Audit با trigger غیرقابل‌تغییر
- فاکتور Confirmed با trigger محافظ
- unique scoped برای idempotency تأیید و یک reversal برای هر original

تغییر destructive در Up migration: **NONE**. فایل `0004` برای رکوردهای Snapshot قبلی backfill کنترل‌شده انجام می‌دهد.

## Runtime و Configuration

- Python و dependencyهای pin‌شده در `requirements.txt`
- connection PostgreSQL از Composition Root میزبان
- Adapterهای Auth، Scope، Permission، File، Progress و AI از میزبان
- هیچ Secret، Mock Header یا Production URL در ماژول وجود ندارد

## Permission/Seed

Matrix کامل در `PERMISSION_MATRIX_FA.md` است. تصویب و Seed `finance_report.issue` و تصمیم fallback برای Confirm/Void/Progress/File توسط تیم BAMBO الزامی است.

## 0016 — مبنای برآورد: مقدار متریال و نرخ واحد

MS Project مقدار **فیزیکی** یک تخصیص متریال را در فیلد مستقل خودش نگه می‌دارد (`Material` در
MPXJ) و قیمت یک واحد از آن را روی خودِ منبع (`StandardRate`). هیچ‌کدام از این دو، `Units`
(همان مقدار ضرب‌در صد)، `Work` (زمان) یا `Cost` (جمع، نه نرخ) نیستند. روی فایل مرجع، این دو
دقیقاً در هم ضرب می‌شوند:

    تخصیص ۹۷۰۳ «تجهیز کارگاه مستمر» / منبع ۱۵۵ «تجهیز مستمر»
        Material ۱ واحد  ×  StandardRate ۱۲٬۵۶۵٬۱۱۵٬۳۹۱  =  Cost ۱۲٬۵۶۵٬۱۱۵٬۳۹۱

و این تساوی برای هر ۲۸۹ تخصیص متریال فایل برقرار است. همین تساوی، مدرکِ «نرخ بر واحد است»
شمرده می‌شود و در ستون `source_rate_basis` ردیف‌به‌ردیف ثبت می‌شود؛ ردیفی که ضربش جور در
نیاید، آنجا NULL می‌گیرد و مبنای برآورد نمی‌شود. ۴۳۸ تخصیص باقی متعلق به منابع WORK هستند:
فایل برایشان هیچ Material نمی‌گوید و نرخشان صفر است، پس هر سه ستون NULL می‌مانند — جوابِ
صادق، چون هزینه بدون مقدار، نرخ واحد نمی‌دهد.

**سه ستون افزوده به `finance_mpp_rows`:** `source_material_quantity` (مقدار فیزیکی به واحد
`resource_unit`)، `source_resource_rate_irr` (نرخ هر واحد به ریال، تبدیل یک‌بار روی همان
تصمیم تومان با تطابق hash فایل) و `source_rate_basis` (مدرک بالا).

**جدول `estimate_line_source_completions`:** ۷۱۵ خط برآوردی که پیش از این migration ساخته
شده بودند با مقدار و قیمت اولیهٔ NULL ساخته شدند، در حالی که فایل هر دو را داشت. تریگر
`estimate_original_fields_immutable` تغییر آن ستون‌ها را رد می‌کند و باید هم رد کند: برآورد
اولیه سند همان لحظه است. پس مقدار و نرخ **کنار** خط ثبت می‌شوند، نه داخلش — با نام نسخهٔ
منبع، sha256 آن، تخصیص، زمان ثبت و ثبت‌کننده. خواننده‌ای که «مقدار اولیهٔ مؤثر» می‌خواهد،
ستون خود خط را می‌گیرد و اگر NULL بود این را. هیچ رکوردی بازنویسی نمی‌شود، یکتایی روی خط
است و درج فقط جایی انجام می‌شود که ستون NULL باشد.

تکمیل، Revision نیست: Revision می‌گوید برآورد **تغییر کرد** و مقدار آخر را جابه‌جا می‌کند؛
تکمیل می‌گوید برآورد از اول همین بود و دیر نوشته شد. دو واقعیت متفاوت، دو جدول متفاوت.

اجرای محلی این تکمیل با `scripts/test_only/complete_mpp_estimate_basis.py` انجام می‌شود:
تراکنشی، idempotent (یکتا روی خط + `ON CONFLICT DO NOTHING`)، و اگر sha256 فایل با نسخهٔ
ثبت‌شده یکی نباشد هیچ‌چیز نمی‌نویسد.


## Backup و Recovery

Backup معتبر و Restore rehearsal پیش‌نیاز Migration است. دستورها و تفاوت Restore با Down migration در `RECOVERY_RUNBOOK_FA.md` ثبت شده‌اند.

## ریسک

ریسک فعلی: **MEDIUM / NOT CLEARED FOR PRODUCTION EXECUTION**، به‌دلیل اجرا نشدن چرخه Migration روی PG16/18، Restore rehearsal و تأیید نشدن Permission mapping میزبان. پس از موفقیت این Gateهای خارجی، ریسک فنی Migration قابل بازبینی مجدد است.

## Post-migration Verification

```powershell
python -m pytest backend/tests/test_migrations.py -q
python -m pytest backend/tests -q
python -m pip_audit -r backend/requirements.txt
```

در دیتابیس، وجود ۱۵ جدول، scope indexها، FKهای `NO ACTION`، triggerهای immutable و ستون/indexهای Migrationهای 0002 تا 0004 باید با catalog PostgreSQL تأیید شود.
