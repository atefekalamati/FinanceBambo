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
13. `0013_finance_mpp_source_identity` (head)

```powershell
alembic current      # این دیتابیس کجاست
alembic upgrade head
alembic current      # باید 0013 باشد
```





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
