# یکپارچه‌سازی MPP ↔ Finance — مستند عملیاتی و معماری

آخرین به‌روزرسانی: ۲۰۲۶-۰۹-۰۴ — پس از E2E واقعی روی `bambo_canonical_test`
(نسخه‌های ۴۱..۴۴) و دو دور بازبینی خصمانهٔ چندعاملی (۲۴ عامل؛ ۱۲ یافتهٔ تأییدشده، همه
برطرف). Migration مرجع: `0009_finance_task_resource_map`.

---

## ۱. معماری و مرز مالکیت

```
فایل .mpp (MPP_IMPORT_ROOT)
   │  coreint/mpp_files.py      ← تنها درِ ورود مسیر (containment/size/magic/sha256)
   ▼
coreint/mpp_reader.py           ← MppReaderPort + MpxjMppReader (MPXJ روی JVM)
   │  ParsedMppProject           (داده خام: هیچ شناسه دیتابیسی هنوز وجود ندارد)
   ▼
coreint/mpp_import.py           ← MppImportService: یک Transaction اتمیک
   │   msp_file_versions → msp_snapshots → msp_tasks → msp_resources
   │   → msp_resource_assignments → finance_task_resource_map
   ▼
app/finance (فقط خواندن)        ← GET /finance/task-resource-mappings
```

- **فقط Core فایل MPP را می‌خواند.** `app/finance` نه MPXJ را import می‌کند نه JPype را؛
  تست `test_schedule_contract.py::MppBoundaryTests` این را با AST تحمیل می‌کند.
- Endpointهای Import روی devhost (نقش Core-host) قرار دارند؛ Finance فقط
  نگاشت را از مسیر scoped می‌خواند.
- هیچ ستون مالی به `msp_tasks` اضافه نشده است.

## ۲. پیکربندی (Environment)

| متغیر | پیش‌فرض | معنا |
|---|---|---|
| `MPP_IMPORT_ENABLED` | خاموش | روشن‌کردن حلقه دوره‌ای import |
| `MPP_IMPORT_ROOT` | — (بدون آن سرویس ۵۰۳ می‌دهد) | تنها پوشه مجاز فایل‌ها، مثل `E:/bamboo/mpp-files` |
| `MPP_MAX_FILE_SIZE_MB` | 100 | سقف اندازه فایل |
| `MPP_IMPORT_INTERVAL_MINUTES` | 60 | فاصله اجرای دوره‌ای |
| `MPP_JAVA_HOME` | `JAVA_HOME` محیط | JRE کامل (jlink مینیمال شکست می‌خورد — jdk.charsets/MacRoman) |

مفسر کانونیکال: `backend/ai-extraction-env` (mpxj + jpype1 + psycopg + fastapi).
JRE آزموده: Temurin 17 در `E:/bamboo/jre/jdk-17.0.20.1+1-jre`.

## ۳. امنیت مسیر (دو قاعده، تمام)

**قاعدهٔ ۱ — قید پروژه (سرویس):** برای پروژهٔ `P` فقط نام `P.mpp` پذیرفته می‌شود؛ هر نام
دیگر — چه موجود چه ناموجود — **پیش از هر تماس با فایل‌سیستم** با `MPP_PATH_NOT_ALLOWED`
رد می‌شود. ریشهٔ Import بین همهٔ پروژه‌ها مشترک است؛ بدون این قید، دارندهٔ `msp.upload`
روی یک پروژه می‌توانست زمان‌بندی staged پروژهٔ دیگر را داخل snapshot خودش بخواند
(یافتهٔ تأییدشدهٔ بازبینی خصمانه، برطرف‌شده). رد پیش از resolve یعنی endpoint هیچ
oracle وجود/عدم فایل هم نیست.

**قاعدهٔ ۲ — مهار مسیر (دروازهٔ فایل):** فایل فقط وقتی خوانده می‌شود که **مسیر
resolve-شدهٔ نهایی داخل ریشهٔ resolve-شده** باشد: `..`، symlink و junction با همین یک
چک رد می‌شوند؛ نام anchored (مطلق، rooted، درایو-نسبی مثل `C:x`) حتی وقتی داخل ریشه
می‌افتد رد می‌شود تا رشتهٔ مطلق هرگز وارد ردیف/پاسخ/لاگ نشود (`MPP_PATH_NOT_ALLOWED`).
سپس: پسوند فقط `.mpp`، فایل خالی رد، سقف اندازه، و جادوی OLE2
(`d0 cf 11 e0 a1 b1 1a e1`) پیش از هر Parser. sha256 در همان یک عبور محاسبه می‌شود و
کلید idempotency کل Import است. **هیچ پیام خطا/لاگ/پاسخی مسیر مطلق سرور را حمل نمی‌کند**
— فقط نام نسبی.

## ۴. طبقه‌بندی خطا (کدهای پایدار)

| کد | HTTP | کی |
|---|---|---|
| `MPP_FILE_NOT_FOUND` | 404 | نام نسبی وجود ندارد |
| `MPP_PATH_NOT_ALLOWED` | 422 | خروج از ریشه / ریشه ناموجود |
| `MPP_FILE_TOO_LARGE` | 413 | بزرگ‌تر از سقف (پیام سقف را می‌گوید) |
| `MPP_FILE_EMPTY` | 422 | صفر بایت |
| `MPP_FORMAT_UNSUPPORTED` | 422 | پسوند غلط یا غیر-OLE2 |
| `MPXJ_NOT_AVAILABLE` | 503 | mpxj/jpype نصب نیست |
| `JAVA_RUNTIME_NOT_AVAILABLE` | 503 | JAVA_HOME/JRE کامل نیست |
| `MPP_FILE_CORRUPTED` / `MPP_PARSE_FAILED` | 422 | MPXJ نتوانست/فایل ناسازگار درونی |
| `MPP_IMPORT_ALREADY_RUNNING` | 409 | قفل advisory پروژه گرفته است |
| `MPP_DUPLICATE_FILE` | 409 | sha با آخرین نسخه یکسان است |
| `MPP_IMPORT_REFUSED` | 403 | پروژه ناموجود / سازمان ناهم‌خوان |

## ۵. قواعد استخراج داده (تخطی‌ناپذیر)

- **Work ≠ Quantity.** ‏Work زمان است (ساعت، با تبدیل واحد Duration)؛ Quantity فیزیکی است
  (فیلدهای Material). کلیدهای جدا، هرگز جایگزین هم نمی‌شوند.
- **مقدار نامعلوم NULL می‌ماند** — هرگز صفر فرض نمی‌شود.
- **هویت = UID** (اولویت مستند GUID>UID>ID ثبت می‌شود، اما روی زمان‌بندی مرجع GUID بین
  ذخیره‌ها بازتولید شد و UID پایدار ماند 1248/1248؛ نام هرگز هویت نیست).
- اعداد به‌صورت رشتهٔ Decimal سفر می‌کنند، نه float (`66150.0` امانت‌دارانه از دابل ژاوا).
- واحد Quantity فقط وقتی ادعا می‌شود که Quantity وجود دارد؛ منبع واحد
  (`material_label` یا `initials`) جدا ثبت می‌شود.
- Assignmentهای بدون Resource **نگه داشته می‌شوند** (resource_uid=NULL) و شمارش‌شان هشدار است.
- **اعتبارسنجی پیش از دیتابیس:** ‏task_uid و resource_uid هر Assignment باید در خود فایل
  موجود باشند؛ کمیت بدون واحد (وقتی فایل هیچ‌جا واحدی نگفته) با کد `MPP_PARSE_FAILED`
  رد می‌شود، نه با خطای خام CHECK. واحد Assignment در نبود واحدِ سطح-کمیت، از
  `material_label`/`initials` خود Resource برداشته می‌شود (باز هم از فایل، نه اختراع).
- `detected_role` **عددی** تصمیم می‌گیرد (Decimal، نه املای رشته) و
  `physical_percent_complete` را هم می‌بیند — فایل actuals با ردیابی فیزیکی دیگر TARGET
  برچسب نمی‌خورد.
- `parser_engine` از نسخهٔ واقعی mpxj نصب‌شده و JVM در حال اجرا ساخته می‌شود
  (provenance ثبت می‌شود، تایپ نمی‌شود).

## ۶. جدول `finance_task_resource_map` (Migration 0009)

دقیقاً سه ستون: `id uuid PK`، `task_id bigint NOT NULL`، `resource_id uuid NOT NULL`؛
`UNIQUE (task_id, resource_id)`؛ Index معکوس روی `resource_id`.

- `task_id` → **`msp_tasks.id`** (هویت ردیف دیتابیس؛ هرگز Task ID نمایشی فایل)
  با `ON DELETE CASCADE`.
- `resource_id` → `finance_resources.id` با `ON DELETE RESTRICT`.
- دامنه tenant عمداً تکرار نشده: هر خواندن از JOIN با `finance_resources` scoped می‌شود.
- **Constraint Trigger** `finance_task_resource_map_scope`: برابری پروژهٔ Task
  (از مسیر snapshot) با پروژهٔ Resource؛ حل‌نشدن پروژه = رد (fail-closed، ‏SQLSTATE
  23503/23514). برابری سازمان — که سمت MSP ستونش را ندارد — در لایه سرویس
  (`validate_mapping_scope` + چک org در `run_import`) تحمیل می‌شود.
- **Index یکتای جزئی** `ux_finance_resources_external_identity` روی
  `(org, project, external_resource_id) WHERE external_resource_id IS NOT NULL AND
  deleted_at IS NULL` — با پیش‌بررسی شمارش‌دار که روی دادهٔ کثیف **متوقف می‌شود** و هرگز
  خودش merge/حذف نمی‌کند.
- **پیش‌نیاز وجودی:** ‏0009 ابتدا با `to_regclass` بودن `msp_tasks` را چک می‌کند و روی
  دیتابیس بدون Core با پیام دستورالعمل‌دار متوقف می‌شود (اثبات‌شده: DB خام کاملاً
  دست‌نخورده ماند). یک `LOCK TABLE finance_resources IN SHARE ROW EXCLUSIVE MODE` هم
  فاصلهٔ بین شمارش تکراری‌ها و ساخت Index یکتا را در برابر نویسنده‌های هم‌زمان می‌بندد.
- **پیش‌نیاز Production:** ‏`GRANT REFERENCES ON msp_tasks TO <migration role>;`
  (مستند 0007: نقش Migration تولیدی این امتیاز را ندارد). تست
  `test_core_alignment.py::test_exactly_the_sanctioned_key_reaches_into_core` این استثنا
  را به همان یک جفت پین می‌کند.

## ۷. تراکنش اتمیک Import

ترتیب داخل **یک** `connection.transaction()`:
قید پروژه → resolve فایل و parse **قبل** از تراکنش (فایل خراب نباید قفل/ردیف بسازد) →
**re-hash پس از parse** (اگر فایل وسط کار عوض شده باشد رد می‌شود — sha ثبت‌شده باید
همان بایت‌های snapshot باشد) →
تأیید project/org (پاسخ سرور، نه ادعای کالر) →
`pg_try_advisory_xact_lock(hashtextextended('mpp_import:'||project_id, 0))` (کلید ۶۴بیتی) →
چک sha آخرین نسخه (تکراری=۴۰۹) →
`msp_file_versions` (نسخه بعدی؛ `detected_role`= ‏ACTUAL اگر درصدی>۰ وگرنه TARGET) →
`msp_snapshots` (`status_date_jalali` عمداً NULL — حدس تقویم غلط سمی است؛ fallback مستند
`created_at`) → tasks (خلاصه‌ها نگه داشته می‌شوند) → resources → assignments → نگاشت.
هر خطا = ROLLBACK کامل؛ قفل transaction-scoped است و با crash آزاد می‌شود.

## ۸. نگاشت به Finance

مسیر دقیق: `assignment.resource_uid → finance_resources.external_resource_id`
(داخل org+project، فقط ردیف‌های زنده) و `task_uid → ردیف task همین snapshot`.
- تطبیق‌نشده = گزارش، نه اختراع:
  `{resourceExternalId, resourceName, status:"unmapped", reason:"FINANCE_RESOURCE_NOT_FOUND"}`
  و وضعیت `completed_with_warnings`. هیچ `finance_resources`ای ساخته نمی‌شود.
- `ON CONFLICT (task_id, resource_id) DO NOTHING` **فقط** برای جفت تکراری؛ خطای FK/تریگر
  conflict نیست و کل Import را می‌شکند.
- دو Assignment روی یک جفت → یک ردیف نگاشت.

### اولویت جفت‌سازی EstimateLine (مستند، بدون تغییر رفتار موجود)
1. `estimate_lines.resource_id → finance_resources.external_resource_id` (مسیر موجود feed)
2. از این پس `finance_task_resource_map` منبع صریح Task↔Resource است؛
3. تطبیق نام هرگز مجاز نیست.

### برخورد شناسهٔ خارجی تکراری در CRUD منابع
از 0009 به بعد، ساخت/ویرایش `finance_resources` با external id تکراری (بین ردیف‌های
زنده) به‌جای 500 خام، ‏`409 DUPLICATE_EXTERNAL_RESOURCE_ID` برمی‌گرداند — نگاشت از روی
نام Index تشخیص داده می‌شود تا برخورد PK معنای خودش را نگه دارد (زنده روی سرور
تأیید شد).

### هشدار دادهٔ موجود (یافتهٔ E2E — اصلاح خودکار نشده)
`finance_resources` پروژه terrace از seeder قدیمی **UID تسک‌های B10** را در
`external_resource_id` دارد (کدهای `MSP-T…`). Import فایل آزمایشی ۲۴ تطبیق «عددیِ
تصادفی» ساخت (نام‌ها کاملاً متفاوت). سیستم طبق سفارش هیچ چک معنایی/نامی ندارد؛
پاک‌سازی این external idها تصمیم دادهٔ اپراتور است، نه کد.

## ۹. Import دوره‌ای

هیچ scheduler قبلی در repo وجود نداشت (ممیزی کامل)؛ حلقهٔ `asyncio.create_task` در
lifespan devhost تنها scheduler است (خاموشی هم await می‌شود تا Import در جریان، تراکنشش
را جمع کند). قرارداد: فایل `<project_id>.mpp` داخل ریشه = «MPP فعال». sha بدون تغییر
**پیش از** `run_import` تشخیص داده می‌شود → `{status:"unchanged"}`، هیچ نوشتنی و هیچ
ردی در رجیستری (GET latest همیشه آخرین Import واقعی را نشان می‌دهد)؛ فایل جدید →
Import کامل؛ خطای یک پروژه — حتی crash غیرمنتظره (`MPP_IMPORT_CRASHED`) — بقیه را
متوقف نمی‌کند؛ هیچ snapshot/گزارش قدیمی هرگز بازنویسی نمی‌شود
(digestهای قبل/بعد در E2E یکسان بودند).

## ۱۰. APIها

| Endpoint | مجوز | نکته |
|---|---|---|
| `POST /api/projects/{id}/mpp-imports` | `msp.upload` | body اختیاری؛ تنها مقدار مجاز `fileName` همان `{id}.mpp` است؛ **org از Auth Context** |
| `GET /api/projects/{id}/mpp-imports/latest` | `msp.view` | از رجیستری درون-پردازشی (سقف ۲۰۰ رکورد، حذف قدیمی‌ترین) |
| `GET /api/projects/{id}/mpp-imports/{importId}` | `msp.view` | ۴۰۴ برای id ناشناس/پروژه غلط |
| `GET /api/projects/{id}/finance/task-resource-mappings` | `finance.view` | فقط snapshot جاری پروژه؛ صفحه‌بندی clamp-شده، `totalItems` |

## ۱۱. کوئری‌های کنترلی (DBeaver)

```sql
-- نگاشت با جزئیات دو سر
SELECT m.id, t.snapshot_id, t.uid AS task_uid, t.name, fr.code, fr.title,
       fr.external_resource_id
FROM finance_task_resource_map m
JOIN msp_tasks t        ON t.id = m.task_id
JOIN finance_resources fr ON fr.id = m.resource_id
ORDER BY t.snapshot_id, t.uid;

-- کشف نگاشت نامعتبر (باید همیشه صفر باشد)
SELECT COUNT(*) FILTER (WHERE s.project_id IS DISTINCT FROM fr.project_id) AS cross_project,
       COUNT(*) FILTER (WHERE s.id IS NULL)                                AS dangling_task
FROM finance_task_resource_map m
JOIN msp_tasks t          ON t.id = m.task_id
LEFT JOIN msp_snapshots s ON s.id = t.snapshot_id
JOIN finance_resources fr ON fr.id = m.resource_id;

-- تکرار external id بین ردیف‌های زنده (باید صفر بماند؛ Index یکتا هم هست)
SELECT organization_id, project_id, external_resource_id, COUNT(*)
FROM finance_resources
WHERE external_resource_id IS NOT NULL AND deleted_at IS NULL
GROUP BY 1,2,3 HAVING COUNT(*) > 1;
```

نتیجهٔ اجرای واقعی (۲۰۲۶-۰۹-۰۳): ‏cross_project=0، ‏dangling_task=0، ‏dups=0.

## ۱۲. اجرا و تست

```powershell
# migration (اپراتور، هرگز خودکار در startup)
$env:FINANCE_MIGRATION_DSN = "<dsn نقش مالک>"
python -m alembic upgrade head        # → 0009

# devhost با import فعال
$env:MPP_IMPORT_ROOT = "E:/bamboo/mpp-files"
$env:MPP_JAVA_HOME  = "E:/bamboo/jre/jdk-17.0.20.1+1-jre"
backend/ai-extraction-env/Scripts/python.exe -m devhost --port 8010

# کل تست‌ها (مفسر کانونیکال؛ تست فایل واقعی JVM می‌خواهد)
$env:MPP_JAVA_HOME = "E:/bamboo/jre/jdk-17.0.20.1+1-jre"
ai-extraction-env/Scripts/python.exe -m pytest tests -q
# Contract Kit — از ریشه Kit استخراج‌شده
python tests/run_contract_tests.py
```

تست‌های اختصاصی: `test_mpp_files.py` (۱۷ حمله/سانحه مسیر، بدون skip — روی ویندوز
junction جایگزین symlink)، `test_mpp_import_service.py` (۲۷ تست با بدل‌ها: اتمیک بودن،
قفل، تکرار، unmapped، retry)، `test_mpp_reader_real_file.py` (فایل واقعی: 328/81/727،
آرماتور uid94، ‏۱۲ assignment بدون resource)، `test_migrations.py` (زنجیره تا 0009 +
قرارداد 0009).
