# فاز ۳-الف — ممیزی اتصال Finance به Core

**تاریخ:** ۱۴۰۵/۰۶/۰۴ · **شاخه:** `backend-finance` · **Baseline:** `e81b085`
**این ممیزی فقط خواندنی است.** هیچ دیتابیسی تغییر نکرد و به دیتابیس اصلی BAMBO وصل نشدیم.

شواهد از خودِ کد مخزن گرفته شده، نه از حدس. هرجا ادعایی هست، مسیر فایل کنارش آمده.

---

## خلاصه یک‌خطی

Finance از نظر معماری **آماده اتصال** است: هیچ Mockی در مسیر Production قابل دسترسی نیست،
هر ۵۷ مسیر API از دروازه چهارگانه رد می‌شوند، و هیچ تغییر شکسته‌ای در Contract لازم نیست.
آنچه مانده **نوشتن چهار Adapter و سیم‌کشی ۱۴ وابستگی** است، به‌علاوه یک تصمیم RBAC که فقط
تیم BAMBO می‌تواند بگیرد.

---

## ۱. احراز هویت

### آنچه Finance از میزبان می‌خواهد

```python
AuthContextProvider.current(request) -> AuthContext
```

`AuthContext` (در `security/context.py`) این میدان‌ها را **الزامی** می‌کند:

| میدان | نوع | محدودیت |
|---|---|---|
| `user_id` | UUID | الزامی — با `users.id` در Core هم‌نوع است ✅ |
| `organization_id` | UUID | الزامی — با `organizations.id` هم‌نوع است ✅ |
| `project_id` | Text | **الگوی `^[A-Za-z0-9_-]+$`** |
| `organization_role` | Text | حداقل یک کاراکتر |
| `project_role` | Text | حداقل یک کاراکتر |
| `permission_codes` | Tuple | یکتا، و الگوی `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` — **دقیقاً یک نقطه** |
| `locale` | fa / en / ar | مقدار نامعتبر به `fa` برمی‌گردد |
| `timezone` | **فقط `Asia/Tehran`** | هیچ مقدار دیگری پذیرفته نمی‌شود |

### دو ریسک واقعی که باید پیش از اتصال بررسی شوند

> **ریسک A-01 — الگوی `project_id`.** در Core، `projects.id` از نوع `text` است و **هیچ CHECK
> ندارد**. اگر شناسه پروژه‌ای در Production نقطه، فاصله، یا کاراکتر غیر-ASCII داشته باشد،
> اعتبارسنجی `AuthContext` رد می‌شود و **کل درخواست شکست می‌خورد** — نه فقط یک میدان.
> این با یک کوئری فقط‌خواندنی روی `projects.id` قابل بررسی است و باید پیش از اتصال انجام شود.

> **ریسک A-02 — `timezone` تک‌مقداری است.** `Literal["Asia/Tehran"]`. اگر میزبان منطقه زمانی
> کاربر را بفرستد و کاربری روی منطقه دیگری باشد، Context ساخته نمی‌شود. Adapter باید این
> مقدار را ثابت بفرستد یا این محدودیت با تصمیم صریح باز شود.

### آیا مسیری می‌تواند از احراز هویت فرار کند؟

**خیر.** از ۵۷ مسیر، ۵۲ مسیر مستقیماً `_resource_scope(...)` را صدا می‌زنند و سه مسیر باقی‌مانده
(`preview_estimate`، `commit_estimate`، `commit_prices`) به `_preview_import` / `_commit_import`
واگذار می‌کنند که خودشان دروازه را اجرا می‌کنند. هیچ Handlerی بدون دروازه پیدا نشد.

### چه چیزی لازم است

فقط **سیم‌کشی میزبان** — یک Adapter که Session واقعی BAMBO را به `AuthContext` تبدیل کند.
`StaticAuthContextProvider` در `devhost/ports.py` فقط برای توسعه است و کتابخانه Finance هرگز
آن را import نمی‌کند.

---

## ۲. دامنه سازمان و پروژه

`authorize_finance_request` در `security/guards.py` چهار دروازه را **به همین ترتیب** اجرا می‌کند:

1. `auth_provider.current(request)` → کاربر احراز هویت‌شده
2. `scope_authorizer.require_organization(context, organization_id)`
3. `scope_authorizer.require_project(context, organization_id, project_id)`
4. `permission_authorizer.require(context, permission_code)`

### نکته امنیتی مهم

```python
organization_id = str(context.organization_id)   # از Context میزبان، نه از Client
```

**شناسه سازمان اصلاً از Client گرفته نمی‌شود** — نه در مسیر، نه در Body. فقط از Context میزبان
می‌آید. `project_id` از مسیر می‌آید ولی بلافاصله به `require_project` سپرده می‌شود تا میزبان
اجازه‌اش را تأیید کند.

**هیچ مسیری شناسه سازمان یا پروژه ارسالی Client را بدون تأیید میزبان باور نمی‌کند.**

لایه دوم: `require_scoped_record` هر رکورد را با هر دو کلید مقایسه می‌کند و در صورت عدم تطابق
۴۰۴ می‌دهد — نه ۴۰۳ — تا وجود رکورد در سازمان دیگر لو نرود.

### چه چیزی لازم است

Adapterی که `ScopeAuthorizer` را با عضویت واقعی Core پیاده کند. جدول‌های مرتبط در Core:
`organization_members` / `organization_memberships` و `project_members` / `project_memberships`.

> **ریسک S-01 — کدام جفت جدول معتبر است؟** در Core هر دو نسل جدول عضویت وجود دارند و از روی
> Metadata نمی‌شود فهمید کدام زنده است. تأیید تیم BAMBO لازم است، وگرنه اعتبارسنجی دامنه روی
> جدول اشتباه انجام می‌شود.

---

## ۳. مجوزها (RBAC)

### کدهایی که کد فعلی واقعاً می‌خواهد

| کد | تعداد استفاده | وضعیت |
|---|---:|---|
| `finance.view` | ۲۲ | **الف — موجود** |
| `finance.edit` | ۲۱ | **الف — موجود** |
| `finance_report.view` | ۵ | **الف — موجود** |
| `finance_report.export` | ۲ | **الف — موجود** |
| `finance_report.issue` | ۱ | **ب — پیشنهادی، نیازمند تصویب و Seed در Core** |

به‌علاوه یک مجوز **محاسبه‌شده** در `services/settings.py`:

```python
def settings_edit_permission(context):
    return "finance.view" if context.organization_role == "org_chief" else "finance.edit"
```

### دو مسئله

> **ریسک P-01 — `finance_report.issue` تأیید نشده است.** مسیر `POST /report-snapshots` این کد را
> می‌خواهد، ولی Integration Kit آن را زیر «PROPOSED — not production facts» فهرست کرده. اگر در
> Core وجود نداشته باشد، **صدور گزارش برای هر کاربری شکست می‌خورد** — و این خرابی در بدترین
> زمان ممکن، یعنی بعد از استقرار، کشف می‌شود.
>
> با یک کوئری فقط‌خواندنی حل می‌شود:
> `SELECT code FROM permissions WHERE code LIKE 'finance%'`
> ارزان‌ترین بررسی این ممیزی است.

> **ریسک P-02 — وابستگی به رشته `org_chief`.** سیاست بالا به مقدار دقیق `organization_role`
> وابسته است. اگر Core این نقش را با نام دیگری برگرداند، مدیر سازمان بی‌صدا اجازه ویرایش
> تنظیمات را از دست می‌دهد (یا برعکس). مقدارهای واقعی `organization_role` باید تأیید شوند.

**هیچ کد دیگری استفاده نشده است** (رده ج: ده مجوز ریزدانه پیشنهادی Kit در کد فعلی مصرف‌کننده
ندارند). **هیچ RBAC موازی در Finance ساخته نشده** و هیچ Migrationی مجوز Seed نمی‌کند.

---

## ۴. پیشرفت / MSP

### آنچه Adapter تولیدی باید برگرداند

هر دو متد باید همین ساختار را بدهند:

```
{ "snapshot": { ...header... }, "assignments": [ ...rows... ] }
```

**کلیدهای Header** (از `domain/progress.py`):

| کلید | منبع در Core | توضیح |
|---|---|---|
| `organizationId` | Context میزبان | باید دقیقاً با دامنه درخواست بخواند |
| `projectId` | `msp_snapshots.project_id` | همان |
| `progressSnapshotId` | — | شناسه‌ای که Adapter با آن سؤال شده را echo می‌کند |
| `hostSnapshotId` | **`msp_snapshots.id`** (bigint) | شناسه واقعی Core |
| `hostFileVersionId` | **`msp_file_versions.id`** (bigint) | |
| `sourceFileNameSafe` | `msp_file_versions.original_filename` | پاک‌سازی‌شده |
| `reportingDate` | `msp_snapshots.status_date_jalali` یا معادل میلادی | `date` یا رشته ISO |
| `status` | — | **DTO فقط `ready` یا `superseded` می‌پذیرد** |
| `importedBy` | `msp_snapshots.created_by` | UUID |
| `importedAt` | `msp_snapshots.created_at` | Timestamptz |
| `sourceType` | — | `microsoft_project` / `primavera` / `manual` / `other` یا `NULL` |

> **ریسک M-01 — `status`.** در Core ستون `snapshot_type` مقادیر `TARGET` / `ACTUAL` /
> `RESCHEDULED` دارد که هیچ‌کدام `ready` یا `superseded` نیستند. Adapter باید نگاشت صریح انجام
> دهد؛ هر مقدار دیگری پاسخ API را با خطای اعتبارسنجی می‌شکند.

**دو متد و تفاوتشان:**

- `current_snapshot(organization_id, project_id, as_of)` — «Snapshot جاری این پروژه کدام است؟»
  اختیاری است؛ میزبانی که آن را ندارد رفتار قبلی را حفظ می‌کند.
- `get_snapshot(organization_id, project_id, snapshot_id)` — **با شناسه میزبان (bigint به‌صورت
  رشته) صدا زده می‌شود**، نه با UUID فایننس. این نکته حیاتی است: میزبان UUID فایننس را
  نمی‌شناسد.

**کلیدهای هر ردیف Assignment:** `assignmentExternalId`، `task.activityCode`،
`task.taskProgressPercent`، `plannedQuantity`، `actualQuantity`، `actualWork`،
`assignmentWorkCompletePercent`، `manualOverride`.

### وقتی داده سطح Assignment وجود ندارد

در Core **هیچ جدول نرمال‌شده Assignment مشاهده نشده است.** Adapter باید ردیف‌ها را در سطح
Task تولید کند و `assignmentExternalId` را `None` بگذارد. **هیچ Assignmentی ساخته نمی‌شود.**

رفتار Finance در این حالت — بررسی و تأیید شد:

1. تطبیق از راه `activityCode` انجام می‌شود (`ProgressPairing`).
2. اگر خطی تطبیق نشود، وضعیتش `unmapped_activity` می‌شود و مقدار اجرا صفر، **ولی با هشدار**.
3. اگر تخصیص چیزی گزارش نکند، وضعیت `unavailable` می‌شود.
4. اگر فقط `actualWork` باشد، `measurement_type = work_effort`، کیفیت ۰.۵، و هشدار
   `PROGRESS_WORK_NOT_QUANTITY`.
5. **`missing` هرگز به `zero` تبدیل نمی‌شود** — «صفرِ اندازه‌گیری‌شده» فقط وقتی است که منبع
   واقعاً صفر گزارش کرده باشد.

**هیچ مقدار فیزیکی از Work یا Duration استنتاج نمی‌شود.**

---

## ۵. ذخیره فایل

```python
FileStorage.put(metadata, content: bytes) -> stored_name
FileStorage.get(organization_id, project_id, file_id) -> bytes
```

**Finance بایت‌ها را خودش نگه نمی‌دارد.** در `finance_attachments` فقط Metadata ذخیره می‌شود:
`sha256` (با CHECK طول ۶۴ و **یکتای Scope-دار** — همین Unique است که فایل تکراری را می‌گیرد)،
`mime_type`، `size_bytes`، `processing_status`، `storage_key`، `invoice_id`، و حذف منطقی.

اعتبارسنجی محتوا سمت Finance انجام می‌شود (`detect_file` امضای بایتی PNG/JPEG/WebP و
MP3/M4A/WAV/OGG را می‌خواند) — یعنی Adapter لازم نیست نوع فایل را تشخیص دهد.

**Adapter تولیدی باید:** بایت‌ها را بگیرد و یک نام ذخیره برگرداند، و با
`(organization_id, project_id, file_id)` همان بایت‌ها را پس بدهد. `LocalFileStorage` روی دیسک
می‌نویسد و **فقط برای توسعه** است.

**نسبت با `media_files` در Core:** جدول Core فقط ۸ ستون دارد و فاقد Hash، یکتایی تکراری،
وضعیت پردازش، ارتباط با فاکتور، حذف منطقی و دامنه سازمان است. **جایگزین `finance_attachments`
نمی‌شود.** افزودن `host_media_file_id` اختیاری به فاز بعد موکول شده و **FK فیزیکی نباید اضافه
شود** — `media_files` با حذف پروژه CASCADE می‌شود.

---

## ۶. استخراج تصویر و صوت

```python
InvoiceImageExtractor.extract(file, hints) -> draft
InvoiceVoiceExtractor.extract(file, hints) -> draft
```

**هر دو در Production موجود نیستند.** `UnavailableExtractor` در `devhost` عمداً خطا می‌دهد:
`AIExtractionFailed` → **HTTP 503 با کد `AI_EXTRACTION_FAILED`**.

| بخش | بدون OCR/Voice |
|---|---|
| بارگذاری فایل (`POST /files`) | ✅ کار می‌کند |
| دانلود فایل | ✅ |
| ثبت دستی فاکتور | ✅ |
| تأیید/ابطال/اصلاح فاکتور | ✅ |
| برآورد، قیمت، تبدیل واحد، ورود اکسل | ✅ |
| گزارش‌ها و پیشرفت | ✅ |
| `POST /files/{id}/extractions` | ❌ **503** |
| `POST /extractions/{id}/retry` | ❌ **503** |

**۵۵ از ۵۷ مسیر بدون هیچ Provider هوش مصنوعی کار می‌کنند.** این دو مسیر باید ۵۰۳ بدهند، نه
اینکه داده جعلی بسازند — که همان کاری است که الان می‌کنند.

---

## ۷. خلاصه مالی پروژه در Core

جست‌وجوی کامل در `backend/app/`:

```
built_area_sqm | estimated_cost | actual_cost_to_date
cost_source | cost_unit | cost_updated_at | cost_updated_by
→ هیچ ارجاعی یافت نشد
```

**Finance این ستون‌ها را نه می‌خواند، نه می‌نویسد، و هیچ کد Syncی وجود ندارد.** این دقیقاً وضع
مطلوب است: محاسبات Finance به هیچ خلاصه غیرنرمال وابسته نیستند.

**فاز ۳-الف هیچ Write-back اضافه نمی‌کند.** قرارداد پیشنهادی برای آینده در سند برنامه آمده است.

---

## ۸. وابستگی‌های Mock در مسیر Production

| بررسی | نتیجه |
|---|---|
| آیا `backend/app/` چیزی از `devhost` import می‌کند؟ | **خیر — هیچ‌چیز** |
| آیا شناسه ثابت (`sample_site_01`, `11111111-…`, `aaaaaaaa-…`) در `app/` هست؟ | **خیر** |
| آیا `SeededProgressSnapshotProvider` / `SeededActivityProvider` در `app/` هست؟ | **خیر** |
| آیا `StaticAuthContextProvider` / `SingleTenantScopeAuthorizer` در `app/` هست؟ | **خیر** |
| آیا `LocalFileStorage` / `UnavailableExtractor` در `app/` هست؟ | **خیر** |

**طبقه‌بندی: هر مورد `DEV_ONLY` است. هیچ وابستگی Mock از مسیر Production قابل دسترسی نیست.**

**هیچ Blockerی در این حوزه وجود ندارد.** مهار ساختاری است نه قراردادی: کتابخانه Finance
`devhost` را import نمی‌کند، پس حتی اگر کسی بخواهد هم نمی‌تواند تصادفی به آن برسد.

---

## ۹. ترکیب برنامه — آنچه میزبان باید تزریق کند

میزبان باید ۱۴ کلید را روی `application.state` بگذارد:

**سه Adapter امنیتی:**

| کلید | Protocol |
|---|---|
| `auth_context_provider` | `AuthContextProvider` |
| `scope_authorizer` | `ScopeAuthorizer` |
| `permission_authorizer` | `PermissionAuthorizer` |

**یازده سرویس دامنه** (هرکدام یک Repository روی اتصال psycopg می‌گیرند):

`finance_settings_service` · `finance_resources_service` · `finance_price_service` ·
`unit_conversion_service` · `progress_service` · `finance_import_service` ·
`invoice_service` · `finance_attachment_service` · `finance_extraction_service` ·
`finance_live_report_service` · `finance_audit_service`

سرویس‌هایی که Adapter اضافی می‌خواهند:

- `progress_service` و `finance_live_report_service` → `ProgressSnapshotProvider`
- `finance_resources_service` → `ProjectActivityProvider`
- `finance_attachment_service` و `finance_extraction_service` → `FileStorage`
- `finance_extraction_service` → `InvoiceImageExtractor` + `InvoiceVoiceExtractor`

**`backend/app` هیچ Composition Root ندارد** — و این طراحی است، نه نقص. ماژول مالی یک
کتابخانه است. `devhost/app.py` فقط نمونه توسعه است.

---

## ۱۰. تأثیر بر Contract API

| نوع تغییر | لازم است؟ |
|---|---|
| تغییر شکننده | **خیر** |
| تغییر Contract درخواست | **خیر** |
| افزودن اختیاری به پاسخ | **قبلاً در فاز ۲-الف انجام شده** |
| تغییر هیچ | ✅ اتصال فقط Adapter است |

آنچه در فاز ۲-الف اضافه شد و اتصال Core را ممکن می‌کند:

- `progressSnapshotId` اکنون Nullable است (خواندن مرجع نمی‌سازد)
- `hostSnapshotId` و `hostFileVersionId` اختیاری اضافه شده‌اند
- `sourceFileVersionId` اختیاری شده

**اتصال Core هیچ تغییر API جدیدی لازم ندارد.**

---

## جمع‌بندی ریسک‌ها

| شناسه | موضوع | شدت | چطور حل می‌شود |
|---|---|---|---|
| **P-01** | `finance_report.issue` تأیید نشده | **بالا** | یک کوئری فقط‌خواندنی روی `permissions` |
| **A-01** | الگوی `project_id` ممکن است با شناسه‌های واقعی نخواند | **بالا** | یک کوئری فقط‌خواندنی روی `projects.id` |
| **M-01** | نگاشت `snapshot_type` به `status` | متوسط | تصمیم Adapter |
| **S-01** | کدام جفت جدول عضویت معتبر است | متوسط | تأیید تیم BAMBO |
| **P-02** | وابستگی به رشته `org_chief` | متوسط | تأیید مقادیر واقعی نقش |
| **A-02** | `timezone` تک‌مقداری | پایین | Adapter مقدار ثابت بفرستد |

سه مورد اول با **دو کوئری فقط‌خواندنی** روی دیتابیس اصلی حل می‌شوند — که طبق قواعد این پروژه
اقدام RED محسوب می‌شود و تأیید صریح می‌خواهد، هرچند چیزی نمی‌نویسد.
