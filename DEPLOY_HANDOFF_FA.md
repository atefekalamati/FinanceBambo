# کیت تحویل ماژول مالی BAMBO — برای تیم دیپلوی و ادغام

این فایل تنها سندی است که تیم دیپلوی برای ادغام و راه‌اندازی این ماژول روی سایت اصلی لازم دارد.
هرچه در آن آمده، کاری است که **خارج از این مخزن** انجام می‌شود.

**نسخهٔ مرجع:** شاخهٔ `master` مخزن `FinanceBambo` · آخرین مهاجرت `0037`

---

## ۰. چک‌لیست تحویل

| # | کار | مسئول | بدون آن چه می‌شود |
|---|---|---|---|
| ۱ | ساخت نقش و دیتابیس PostgreSQL | دیپلوی | سرویس بالا نمی‌آید |
| ۲ | اجرای Alembic تا `0037` | دیپلوی | ۵۰۰ روی هر مسیر |
| ۳ | تعریف ۵ مجوز در Core | دیپلوی | ۴۰۳ روی همه‌چیز |
| ۴ | نسبت‌دادن مجوزها به نقش‌ها | دیپلوی | کاربر صفحهٔ خالی می‌بیند |
| ۵ | پر کردن متغیرهای محیطی | دیپلوی | رفتارهای خاموش (بخش ۴) |
| ۶ | Composition root (۱۴ مؤلفه) | دیپلوی | `503 FINANCE_UNAVAILABLE` |
| ۷ | سه endpoint هویت برای فرانت | دیپلوی | «پروژه‌ای انتخاب نشده» |
| ۸ | نصب بستهٔ فرانت و دو صفحهٔ mount | دیپلوی | صفحهٔ سفید |
| ۹ | صف پس‌زمینهٔ بادوام | دیپلوی | `503` روی پردازش فاکتور |
| ۱۰ | پیش‌نیازهای استخراج (اختیاری) | دیپلوی | پردازش تصویر/صدا خاموش |

---

## ۱. دیتابیس

### ۱-۱ نقش‌ها

دو نقش، و سرویس **هرگز** با نقش مالک اجرا نمی‌شود:

```sql
CREATE ROLE bambo_finance_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE <db> TO bambo_finance_app;
GRANT USAGE ON SCHEMA public TO bambo_finance_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bambo_finance_app;
```

نقش مالک (صاحب DDL) فقط برای اجرای مهاجرت استفاده می‌شود.

### ۱-۲ مهاجرت

- جدول نسخه: **`finance_alembic_version`** — نه `alembic_version`. اگر ماژول دیگری روی همین دیتابیس alembic دارد، تداخل ندارند.
- تعداد مهاجرت‌ها: ۳۷ · آخرین: `0037`
- مهاجرت با `FINANCE_MIGRATION_DSN` اجرا می‌شود، **جدا از راه‌اندازی برنامه**. برنامه در startup مهاجرت اجرا نمی‌کند.

```bash
cd backend
FINANCE_MIGRATION_DSN=<owner dsn> alembic upgrade head
```

دستورالعمل کامل با دروازهٔ تأیید و معیار بازگشت: `backend/docs/DEPLOYMENT_RUNBOOK_FA.md`

### ۱-۳ پیش از هر مهاجرت

`backend/docs/BACKUP_RESTORE_RUNBOOK_FA.md` — پشتیبان و برنامهٔ بازگشت باید **قبل** از `upgrade` تأیید شده باشد.

---

## ۲. مجوزها — باید در Core تعریف شوند

ماژول روی **کد مجوز** گیت می‌گذارد، نه روی کد نقش. این پنج کد باید در Core وجود داشته باشند:

| کد مجوز | عنوان پیشنهادی | چه چیزی را باز می‌کند | تعداد مسیر |
|---|---|---|---|
| `finance.view` | مشاهدهٔ داده‌های مالی | خواندن هر داده و Audit | ۵۰ |
| `finance.edit` | ویرایش داده‌های پایهٔ مالی | قیمت، منابع، تبدیل واحد، ایمپورت | ۲۶ |
| `finance.manage_invoice` | مدیریت فاکتورها | ثبت، آپلود، پردازش، تأیید فاکتور | ۱۲ |
| `finance_report.view` | مشاهدهٔ گزارش مالی | گزارش زنده و Snapshot | ۶ |
| `finance_report.issue` | صدور گزارش قطعی | ساخت Snapshot غیرقابل‌تغییر | ۱ |
| `finance_report.export` | خروجی گزارش | دریافت CSV و XLSX | ۲ |

دو مجوز دیگر **متعلق به ماژول MSP است، نه ما** — فقط مصرف می‌شوند:

| کد | کاربرد در ماژول مالی |
|---|---|
| `msp.upload` | آپلود فایل زمان‌بندی |
| `msp.view` | خواندن زمان‌بندی |

### ۲-۱ نسبت‌دادن به نقش‌ها

مدل دسترسی مصوب مالک محصول (۱۴۰۵/۰۶/۱۸ — بر PRD ارجح است):

| کد نقش | نام | امور مالی | گزارش مالی |
|---|---|---|---|
| `bambo_admin` | ادمین بامبو | کامل | کامل |
| `org_chief` | رییس سازمان | — | کامل، در تمام پروژه‌های سازمان خودش |
| `finance_expert` | کارشناس مالی | کامل | کامل |
| `project_manager` | مدیر پروژه | — | فقط پروژه‌های خودش |
| `quantity_survey_expert` | کارشناس متره و برآورد | فقط «اقلام و متره» | — |
| `project_control_expert` | کارشناس کنترل پروژه | — | — |
| `project_definition_expert` | کارشناس تعریف پروژه | — | — |
| `capture_expert` | کارشناس برداشت پروژه | — | — |
| `support` | پشتیبان | — | — |
| `site_supervisor` | سرپرست کارگاه | — | — |
| `technical_expert` | کارشناس فنی | — | — |
| `guest` | مهمان | — | — |

> **محدودیت شناخته‌شده:** `finance.edit` امروز یک کلید است که نُه در را باز می‌کند. ردیف
> `quantity_survey_expert` («فقط اقلام و متره») تا وقتی Core کدهای ریزتر تعریف نکند
> **قابل بیان نیست**. اگر این نقش را با `finance.edit` بسازید، دسترسی بیشتری از مدل بالا
> می‌گیرد. تصمیم با شماست: یا کد ریزتر تعریف کنید، یا این نقش فعلاً مجوز مالی نگیرد.

«Finance Viewer» **نقش نیست** — هرکسی که `finance_report.view` دارد.

---

## ۳. Composition Root — ۱۴ مؤلفهٔ اجباری

میزبان باید پیش از سرویس‌دهی این‌ها را روی `application.state` قرار دهد. مرجع اجرایی کامل:
`backend/devhost/app.py::wire()`.

**سه پورت میزبان:**

| نام | قرارداد |
|---|---|
| `auth_context_provider` | `AuthContext` معتبر از session میزبان |
| `scope_authorizer` | `require_organization` و `require_project` |
| `permission_authorizer` | `require(context, code)` — بدون fallback پنهان |

**یازده سرویس مالی:**

```
finance_settings_service      finance_resources_service     finance_price_service
unit_conversion_service       progress_service              finance_import_service
invoice_service               finance_attachment_service    finance_extraction_service
finance_live_report_service   finance_audit_service
```

**چهار مؤلفهٔ اختیاری:**

```
actor_directory  finance_mpp_sync_service  finance_mpp_mapping_service
finance_background_executor
```

اگر هرکدام از ۱۴ مؤلفهٔ اجباری نباشد، ماژول `503` با کد `FINANCE_UNAVAILABLE` می‌دهد و
`optionalCapabilities` را اعلام می‌کند. DSN، نام جدول، مسیر و متن exception از این مرز رد نمی‌شود.

### ۳-۱ صف پس‌زمینهٔ بادوام — **مانع واقعی production**

```python
# backend/devhost/app.py:308
# Explicitly development-only. Production composition never enables this
# flag and must provide a durable `finance_background_executor`.
application.state.allow_ephemeral_finance_tasks = True
```

- production **نباید** `allow_ephemeral_finance_tasks` را روشن کند.
- بدون `finance_background_executor` مسیر `POST /files/{id}/extractions/async` پاسخ
  `503 "durable extraction execution is not configured"` می‌دهد.
- **هیچ پیاده‌سازی‌ای از این executor در مخزن نیست.** فقط نامش در `OPTIONAL_COMPONENTS` ثبت شده.
- قرارداد: یک `submit(callable)` که کار را بادوام صف می‌کند.
- چرا لازم است: OCR بین ۲ تا ۶ ثانیه و رونویسی صدا تا ۴۰ ثانیه طول می‌کشد. پاسخ ۲۰۲ فوراً
  برمی‌گردد. اگر سرویس ری‌استارت شود و صف بادوام نباشد، کار گم می‌شود و کاربر فایلی می‌بیند
  که برای همیشه «در حال پردازش» است.

---

## ۴. متغیرهای محیطی

الگوی کامل با توضیح هر کلید: `.env.example` در ریشهٔ مخزن. `.env` هرگز کامیت نمی‌شود.

### ۴-۱ اجباری

| متغیر | مقدار |
|---|---|
| `FINANCE_DEV_DSN` | DSN نقش برنامه |
| `FINANCE_MIGRATION_DSN` | DSN نقش مالک — فقط برای مهاجرت |
| `APP_ENV` | `production` |

### ۴-۲ باید صریحاً خاموش بماند

| متغیر | مقدار در production | اگر اشتباه تنظیم شود |
|---|---|---|
| `FINANCE_ALLOW_SEED` | **تنظیم نشود** یا `false` | دادهٔ نمایشی وارد محیط واقعی می‌شود |
| `DEBUG` | `false` | |

> `--reseed` روی هیچ محیط مستقری اجرا نمی‌شود. staging هم seed نمی‌شود: فاکتور نمایشی
> آنجا از فاکتور واقعی قابل تشخیص نیست.

### ۴-۳ ایمپورت زمان‌بندی MPP

| متغیر | توضیح |
|---|---|
| `MPP_IMPORT_ENABLED` | `true` برای فعال‌سازی |
| `MPP_IMPORT_ROOT` | مسیر فایل‌سیستم تأییدشده. فایل به شکل `<MPP_IMPORT_ROOT>/<projectId>.mpp` خوانده می‌شود |
| `MPP_JAVA_HOME` | **JRE 17** — کتابخانهٔ MPXJ جاوا لازم دارد |
| `MPP_MAX_FILE_SIZE_MB` | پیش‌فرض ۱۰۰ |
| `MPP_IMPORT_INTERVAL_MINUTES` | خالی = بدون tick دوره‌ای |

- **Object storage پشتیبانی نمی‌شود.** فقط مسیر فایل‌سیستم یا mount سیستم‌عامل.
- بدون `MPP_JAVA_HOME` ایمپورت شکست می‌خورد. این تنها جای ماژول است که به جاوا نیاز دارد.

### ۴-۴ ذخیرهٔ پیوست‌ها

مسیر ذخیرهٔ فایل فاکتور از طریق پورت `FileStorage` تأمین می‌شود (در dev: آرگومان `--storage`،
پیش‌فرض `backend/devhost/.files`).

**الزام:** بیرون از هر دایرکتوری عمومی. فایل با کلید غیرقابل‌حدس ذخیره می‌شود و فقط از راه
API با مجوز `finance.view` سرو می‌شود.

### ۴-۵ ایمپورت خودکار قیمت روز (n8n)

```
FINANCE_MATERIAL_PRICE_IMPORT_SERVICE_KEY=<رشتهٔ تصادفی، حداقل ۳۲ کاراکتر>
```

- **تنها جایی است که ماژول اعتبارنامهٔ خودش را می‌پذیرد.** بقیهٔ مسیرها هویت را از میزبان می‌گیرند.
- خالی = خاموش. کلید کوتاه‌تر از ۳۲ کاراکتر = خاموش (fail closed).
- تولید: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- n8n فقط هدر می‌فرستد، بدون body:
  ```
  POST /api/projects/<projectId>/finance/material-prices/import-runs?force=true
  X-FINANCE-SERVICE-KEY: <کلید>
  ```
- n8n نمی‌تواند شیت، سازمان یا قیمتی را نام ببرد.

### ۴-۶ استخراج فاکتور — بخش ۷

---

## ۵. فرانت‌اند

### ۵-۱ ساخت بسته

```bash
cd frontend
npm run package            # خروجی: ../finance-package
```

- **بدون build step، بدون bundler، بدون CDN.** ES Module خام.
- بسته از گراف import ساخته می‌شود، نه از فهرست دستی.
- `src/adapters/mock` و `index.html` در بستهٔ production **نیستند** — میزبان بسته‌ای می‌گیرد که اصلاً دادهٔ نمایشی ندارد.

### ۵-۲ صفحات mount

بدنهٔ `frontend/host.html` را در دو صفحه کنار `msp.html` داشبورد کپی کنید:

```
/finance.html          →  امور مالی
/finance-report.html   →  گزارش مالی
```

تنها المنتی که ماژول نیاز دارد:

```html
<main id="finance-module-root" tabindex="-1"></main>
<script type="module" src="./src/app/bootstrap.js"></script>
```

`<html lang="fa" dir="rtl">` الزامی است.

**آنچه یک صفحهٔ میزبان را میزبان می‌کند:** نداشتن `data-finance-runtime` روی `<body>`.
حالت میزبان پیش‌فرض است.

### ۵-۳ سه endpoint هویت

اگر میزبان `window.__BAMBO_FINANCE_CONTEXT__` را تنظیم نکند، ماژول پروژه را از
`?project=<id>` یا `localStorage['bambo:project']` می‌خواند و این سه را صدا می‌زند:

| endpoint | فیلدهای لازم | اجباری |
|---|---|---|
| `GET /api/me` | `user.id`، `orgs[0].id`، `orgs[0].name` | بله |
| `GET /api/projects/{id}` | `id`، `name`، `code`، `organizationId`، `builtAreaSqm` | بله |
| `GET /api/rbac/my-permissions` | آرایهٔ کدهای مجوز | اختیاری |

- پاسخ `/api/projects/{id}` هم به شکل `{project: {...}}` و هم شیء ساده پذیرفته می‌شود.
- `builtAreaSqm` اختیاری است؛ نبودش یعنی شاخص‌های «هر مترمربع» نمایش داده نمی‌شوند.
- اگر هرکدام از دو مورد اجباری ناقص باشد، ماژول صفحه را نمی‌سازد و خطای فارسی نشان می‌دهد
  — به‌جای رندرکردن صفحه‌ای که دربارهٔ دسترسی کاربر دروغ بگوید.

### ۵-۴ CORS

API و فرانت باید **از یک origin** سرو شوند. کلاینت تماس cross-origin را رد می‌کند و هیچ
تنظیم CORS‌ای خوانده نمی‌شود.

---

## ۶. قواعدی که نباید شکسته شوند

- `organizationId` فقط از `AuthContext` می‌آید. از body پذیرفته **نمی‌شود**.
- `projectId` مسیر با پروژهٔ context و عضویت کاربر تطبیق داده می‌شود.
- مبلغ ریالی در API **رشتهٔ Decimal** است و در PostgreSQL `numeric(18,0)`. هیچ مبلغی به float تبدیل نمی‌شود.
- Snapshot صادرشده، فاکتور Confirmed و تاریخچه‌های append-only **نباید** update یا delete شوند.
- فایل و پیشرفت فقط از راه Adapter مصرف می‌شوند؛ مسیر فایل production مستقیم خوانده نمی‌شود.
- `estimate_original_fields_immutable` هر UPDATE روی `original_quantity` و
  `original_unit_price_irr` را رد می‌کند. این تریگر باید بماند.

---

## ۷. پردازش فاکتور با تصویر و صدا

**پیش‌فرض خاموش است و این عمدی است.** بدون تنظیم صریح، ماژول `UnavailableExtractor` نصب
می‌کند که صریحاً «در دسترس نیست» می‌گوید — چون استخراج‌کننده‌ای که بی‌سروصدا چیزی برنگرداند،
به بازبین اجازه می‌دهد فاکتور خالی را تأیید کند.

### حالت الف — خودمیزبان روی VPS

```
EXTRACTION_PROVIDER=self_hosted
```

| پیش‌نیاز | مقدار |
|---|---|
| Python | ۳٫۱۲ |
| RAM | حداقل ۴ گیگابایت، **۸ توصیه‌شده** |
| دیسک | ~۵ گیگابایت (بسته‌ها + وزن مدل‌ها) |
| **ffmpeg** | **الزامی — pip نصبش نمی‌کند** |

```bash
cd backend
pip install -r extraction/requirements.txt

# Debian / Ubuntu
apt-get install -y ffmpeg
```

**وزن مدل‌ها** باید دانلود شوند (PaddleOCR فارسی ~۲۰MB · Whisper small ~۵۰۰MB). اگر سرور
دسترسی اینترنت ندارد، `~/.cache/whisper/` را کپی کنید.

> ⚠ **پین‌های `extraction/requirements.txt` روی لینوکس تأیید نشده‌اند.** خودِ فایل این را
> می‌گوید: از مستندات پروژه‌ها انتخاب شده‌اند، نه از نصبی که اجرا شده باشد. نسخه‌ای که
> واقعاً اجرا شده نسل دیگری است (`paddlepaddle 3.0.0`، `paddleocr 3.7.0`، `torch 2.13.0`).
> **اولین نصب روی VPS:** بعد از `pip install`، این دو را اجرا کنید:
> ```
> python extraction/scripts/test_ocr.py
> python extraction/scripts/test_whisper.py
> ```
> اگر resolve شد، نسخه‌های واقعی را با تاریخ و پلتفرم در همان فایل ثبت کنید.

**کارایی مورد انتظار (CPU، ۴ هسته):** OCR یک فاکتور A4: ۲–۶ ثانیه · رونویسی ۳۰ ثانیه صدا: ۱۵–۴۰ ثانیه.

راهنمای کامل شامل حالت GPU: `backend/docs/EXTRACTION_SELF_HOSTED_SETUP_FA.md`

### حالت ب — API میزبان‌شده

```
FINANCE_AI_EXTRACTION_ENABLED=true
FINANCE_AI_PROVIDER=avalai
AVALAI_API_KEY=<کلید>
AVALAI_BASE_URL=https://api.avalai.ir/v1
FINANCE_STT_PROVIDER=avalai
```

بدون paddle، بدون torch، بدون ffmpeg، بدون ۵ گیگابایت.
**ولی تصویر و صدای فاکتور به سرور بیرونی می‌رود** — تصمیم حریم خصوصی است، نه فنی.

### امنیت فایل — از قبل پیاده شده

| | |
|---|---|
| تشخیص نوع | از **بایت‌های خود فایل**، نه از نوع اعلام‌شده |
| فایل اجرایی | `MZ`، `ELF`، `PK`، `#!` رد می‌شوند حتی با پسوند `.jpg` |
| سقف حجم | تصویر ۱۰MB · صدا ۲۵MB |
| فایل موقت ffmpeg | همیشه حذف می‌شود، حتی وقتی مدل خطا بدهد |

---

## ۸. موارد باز — تیم توسعه باید بداند

| # | مورد | اثر |
|---|---|---|
| ۱ | `finance_background_executor` پیاده‌سازی ندارد | پردازش ناهمگام فاکتور در production کار نمی‌کند (بخش ۳-۱) |
| ۲ | پین‌های استخراج روی لینوکس تأیید نشده | اولین نصب ممکن است resolve نشود (بخش ۷) |
| ۳ | `finance.edit` یک کلید برای نُه در | نقش «کارشناس متره و برآورد» قابل بیان نیست (بخش ۲-۱) |
| ۴ | تلفیق تصویر + صدا پیاده نشده | یک فاکتور با ویس، یک ردیف خوانده می‌شود |
| ۵ | ۴۲۶ ردیف تجهیزات مبنای مقدار ندارند | برآورد تجهیزات صفر گزارش می‌شود؛ منتظر استفاده از `planned_work` |

---

## ۹. Smoke test بعد از استقرار

```
GET  /healthz/finance                             → status: ready
                                                    (هر چیز جز این = بخش ۳ ناقص است)
GET  /api/projects/<id>/finance/resources         → ۲۰۰
GET  /api/projects/<id>/finance/reports/live?reportingDate=<امروز>
                                                  → ۲۰۰، calculationStatus اعلام شود
POST /api/projects/<id>/finance/files             → ۲۰۱ (با finance.manage_invoice)
POST /api/projects/<id>/finance/files/<fid>/extractions/async
                                                  → ۲۰۲، نه ۵۰۳
```

پاسخ `/healthz/finance` هیچ DSN، نام جدول، مسیر یا متن exception ندارد — فقط
`status`، `code`، `checkedAt` و `optionalCapabilities`.

بازکردن `/finance.html?project=<id>` با کاربری که `finance.view` دارد باید صفحه را کامل
رندر کند، نه «پروژه‌ای انتخاب نشده».

**معیار بازگشت:** هر کدام از این‌ها شکست بخورد → `backend/docs/DEPLOYMENT_RUNBOOK_FA.md` بخش ۱۰.

---

## ۱۰. محتویات بسته

```
bambo-finance-<commit>/
  DEPLOY_HANDOFF_FA.md     همین فایل — از اینجا شروع کنید
  VERSION.txt              commit، تاریخ، نسخهٔ مهاجرت، شمارش فایل‌ها
  .env.example             هر تنظیم با توضیح خودش
  backend/                 سرویس، مهاجرت‌ها، آداپتورها، قرارداد API
  frontend/                بستهٔ مرورگر — همان‌طور که هست سرو می‌شود، بدون build
  reference/               devhost — فقط‌خواندنی، نمونهٔ سیم‌کشی میزبان
```

### آنچه عمداً در بسته نیست

| | چرا |
|---|---|
| `.env` و هر اعتبارنامه‌ای | بسته از فهرست tracked ساخته می‌شود؛ `.env` اصلاً tracked نیست |
| dump دیتابیس، فایل `.mpp`، CSV | **هیچ دادهٔ محیط توسعه معتبر نیست.** میزبان از جداول خودش می‌خواند |
| `devhost/seed.py` و `seed.sql` | ۱۰۴ کیلوبایت فاکتور و قیمت و پیشرفت نمایشی |
| `backend/tests/` و `frontend/tests/` | میزبان CI خودش را روی composition خودش اجرا می‌کند |
| `frontend/index.html` و `src/adapters/mock/` | پیش‌نمایش مستقل و دادهٔ ساختگی پشت آن |
| `backend/scripts/{demo,test_only,dev}/` | ساخت و کاوش دیتابیس تست محلی |
| ۴ ماژول پارک‌شدهٔ فرانت | از هیچ صفحه‌ای قابل دسترس نیستند |
| ممیزی‌ها و گزارش‌های فاز | تاریخچهٔ تصمیم، نه مرجع استقرار |

بستهٔ فرانت از **گراف import** ساخته می‌شود، نه از فهرست دستی — ماژولی که ماه آینده
اضافه شود خودبه‌خود وارد می‌شود و ماژولی که از هیچ‌جا صدا زده نشود خودبه‌خود بیرون می‌ماند.

### بازسازی بسته

```bash
node scripts/build-delivery.mjs
```

اگر درخت کاری تغییر کامیت‌نشده داشته باشد **امتناع می‌کند** — بسته باید commit خودش را نام ببرد.

---

## ۱۱. مراجع داخل مخزن

| فایل | محتوا |
|---|---|
| `backend/INTEGRATION_GUIDE_FA.md` | قرارداد composition root |
| `backend/docs/DEPLOYMENT_RUNBOOK_FA.md` | ده مرحلهٔ استقرار، دروازهٔ مهاجرت، معیار بازگشت |
| `backend/docs/BACKUP_RESTORE_RUNBOOK_FA.md` | پشتیبان و بازیابی |
| `backend/docs/EXTRACTION_SELF_HOSTED_SETUP_FA.md` | نصب OCR و رونویسی، CPU و GPU |
| `backend/docs/CORE_HOST_WIRING_FA.md` | اتصال به جداول Core |
| `backend/docs/CORE_PERMISSION_REQUIREMENTS_FA.md` | نیازمندی‌های مجوز از Core |
| `backend/docs/DATABASE_SCHEMA_FA.md` | شمای کامل جداول |
| `.env.example` | هر متغیر محیطی با توضیح خودش |
