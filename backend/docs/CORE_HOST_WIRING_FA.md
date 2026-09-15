# قرارداد سیم‌کشی میزبان — مرز مسئولیت

## اصل

ماژول مالی یک **کتابخانه** است، نه یک سرویس. هیچ ریشه ترکیبی ندارد، هیچ متغیر محیطی
نمی‌خواند، و هیچ‌وقت نمی‌داند چه کسی Portهایش را پیاده کرده است.

میزبان BAMBO این ۱۴ کلید را روی `application.state` می‌گذارد و ماژول مالی کار می‌کند. اگر
یکی نباشد، مسیرهای وابسته‌اش شکست می‌خورند — و این درست است.

> **به‌روزرسانی ۲۰۲۶-۰۹-۱۳ · Alembic `0020`.** قرارداد چهارده‌کلیدی زیر تغییر نکرده. دو
> چیز به آن اضافه شده که میزبان باید بداند:
>
> 1. **`AuthProvider.current` هنوز باز است** و باید بماند. `app/` و `coreint/` هیچ هدر
>    درخواستی را **نمی‌خوانند** — دو آزمون در `tests/test_demo_isolation.py` این را نگه
>    می‌دارند، چون `X-Demo-User` که در `devhost` هست روی یک میزبان واقعی معنایش جعل هویت
>    هر کسی است که شناسه‌اش را حدس بزند.
> 2. **متغیرهای محیطی که پیکربندی واقعاً می‌خواند:** `FINANCE_DEV_DSN`،
>    `FINANCE_MIGRATION_DSN`، `FINANCE_CORE_DSN`، `FINANCE_CORE_PROGRESS`،
>    `MPP_IMPORT_ENABLED`، `MPP_IMPORT_ROOT`، `MPP_MAX_FILE_SIZE_MB`،
>    `MPP_IMPORT_INTERVAL_MINUTES`، `MPP_JAVA_HOME`، `EXTRACTION_PROVIDER`، و سه
>    `FINANCE_DEMO_*` که فقط میزبان توسعه می‌خواند. نمونهٔ کامل و فقط-placeholder در
>    `.env.example` ریشهٔ مخزن.
>
> فهرست کامل تحویل‌دادنی‌ها و معیارهای پذیرش در `INTEGRATION_KIT_FA.md`.

---

## خط تقسیم

| میزبان مسئول است | ماژول مالی مسئول است |
|---|---|
| **چه کسی** تماس گرفته (Session، احراز هویت) | آیا این شخص اجازه این کار را دارد |
| ساخت `AuthContext` | اعتبارسنجی شکل `AuthContext` |
| عضویت سازمان و پروژه | اعمال چهار دروازه به ترتیب |
| مجوزهای مؤثر | اینکه کدام مجوز برای کدام مسیر لازم است |
| خوراک پیشرفت با مقدار | تبدیل مقدار به پول، و صداقت وقتی مقدار نیست |
| فهرست فعالیت‌ها | تطبیق خط برآورد با فعالیت |
| ذخیره بایت فایل | فراداده، Hash، اعتبارسنجی نوع، تغییرناپذیری |
| اتصال دیتابیس و Pool | مرز تراکنش، SQL پارامتری |

> **ماژول مالی هرگز احراز هویت نمی‌کند.** `CoreAuthContextAssembler` یک درز دارد به نام
> `identity(request)` که میزبان پرش می‌کند. عمداً انتزاعی مانده: مالی قراردادی برای Session
> با میزبان ندارد و ساختن یکی، حدس‌زدن طراحی شخص دیگری است.

---

## ۱. هویت — `AuthContextProvider`

```python
async def current(request) -> AuthContext
```

میزبان باید این شش چیز را بدهد:

| فیلد | نوع | از کجا | اعتبارسنجی مالی |
|---|---|---|---|
| `userId` | UUID | Session میزبان | UUID الزامی |
| `organizationId` | UUID | Session میزبان | UUID الزامی |
| `projectId` | text | مسیر درخواست | `^[A-Za-z0-9_-]+$` |
| `organizationRole` | text | `user_roles` → `roles.code` | غیرخالی |
| `projectRole` | text | `project_memberships.role` | غیرخالی |
| `permissionCodes` | list | RBAC مؤثر | `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`، یکتا |
| `locale` · `timezone` | text | تنظیمات کاربر | `fa`/`en`/`ar` · `Asia/Tehran` |

**`organizationRole` مقدار `org_chief` را بدون ترجمه می‌خواهد.** این کد در جدول `roles`
هسته وجود دارد (تأییدشده با خواندن فقط‌خواندنی). سیاست ویرایش تنظیمات دقیقاً روی همین
رشته حساب می‌کند؛ لایه ترجمه یعنی دو واژگان که با هم از هم فاصله می‌گیرند.

> ⚠ **کد نامعتبر حذف می‌شود، نه اینکه درخواست را بشکند.** یک ردیف بدشکل در کاتالوگ مجوزها
> وگرنه هر درخواست را ۵۰۰ می‌کرد. حذف فقط می‌تواند «رد کند»، پس جهت خطایش امن است.

---

## ۲. دامنه — `ScopeAuthorizer`

```python
async def require_organization(context, organization_id) -> None
async def require_project(context, organization_id, project_id) -> None
```

هر دو در نبود عضویت باید **۴۰۳** بدهند.

**پیاده‌سازی مرجع:** `coreint/security.py` روی `organization_memberships` و
`project_memberships`.

> **`project_memberships` سازمان خودش را ثبت نمی‌کند.** بدون `JOIN projects`، عضویت در
> پروژه P درخواستی را که سازمان B را نام می‌برد برآورده می‌کند — نشتی بین‌سازمانی از راه
> ردیفی که خودش معتبر است. کوئری مرجع این JOIN را دارد و یک تست وجودش را قفل می‌کند.

**جفت جدول `organization_members` / `project_members` را نخوانید.** `user_id` در آن‌ها
اختیاری است، یعنی می‌توانند کسی را توصیف کنند که حساب کاربری ندارد. آن‌ها دفترچه تماس‌اند.

---

## ۳. مجوز — `PermissionAuthorizer`

```python
async def require(context, permission_code: str) -> None
```

**پیاده‌سازی مرجع** دیتابیس را دوباره می‌خواند و به `context.permission_codes` اعتماد
نمی‌کند. دو Port، دو دروازه مستقل — وگرنه دومی فقط تصمیم اولی را تکرار می‌کند و مجوزی که
در هسته سلب شده تا انقضای Session کار می‌کند.

```sql
user_roles → role_permissions → permissions      (اعطا)
user_permission_overrides                        (سلب یا اعطای فردی)
```

**دو قاعده که نباید عوض شوند:**

1. **سلب صریح بر اعطای نقش غلبه می‌کند.** Override تصمیمی درباره همین شخص است؛ نقش تصمیمی
   درباره یک دسته. تصمیم مشخص‌تر حرف آخر را می‌زند.
2. **نقش خارج از دامنه هیچ نمی‌دهد.** ردیف `user_roles` وقتی اعمال می‌شود که سازمانش دقیقاً
   بخواند یا `NULL` باشد؛ همین برای پروژه.

---

## ۴. پیشرفت — `ProgressSnapshotProvider`

```python
async def get_snapshot(organization_id, project_id, snapshot_id) -> feed | None
async def current_snapshot(organization_id, project_id, as_of) -> feed | None
```

> ### 🔴 این Port را هسته به‌تنهایی نمی‌تواند پر کند
>
> `msp_tasks` درصد دارد و **هیچ ستون منبع، واحد یا مقداری ندارد**. تفصیل در
> `PROGRESS_INTEGRATION_GAP_FA.md`.

**دو قاعده حیاتی برای پیاده‌سازی میزبان:**

**الف) با همان شناسه‌ای جواب بدهید که با آن پرسیده شده.** مالی Header را با شناسه‌ای که
فرستاده تطبیق می‌دهد، و وقتی ردیف ارجاع `host_snapshot_id` دارد با همان bigint می‌پرسد.
برگرداندن UUID مالی، یک درخواست معتبر را «Snapshot پیدا نشد» می‌کند.

> این اشتباه در چهار نقطه از کد مالی بود و هر چهار جا اصلاح شد — و یک‌بار هم در Fixture
> توسعه، که به هر دو شناسه جواب می‌داد ولی UUID را echo می‌کرد.

**ب) در نبود Snapshot، `None` برگردانید — نه Header خالی.** Header خالی ادعا می‌کند
«این همان Snapshot است» و بعد هیچ Snapshotی را توصیف نمی‌کند. مالی هر دو شکل را رد می‌کند،
ولی الگوی درست را باید Provider تعریف کند.

---

## ۵. فعالیت — `ProjectActivityProvider`

```python
async def list_activities(organization_id, project_id, query, status, page, page_size)
async def get_activity(organization_id, project_id, activity_external_id)
async def create_activity(...)   # اختیاری
```

`create_activity` **اختیاری** است. اگر نداشته باشید، `FinanceResourcesService` با
`hasattr` تشخیص می‌دهد و امتناع صریح می‌دهد. Adapter مرجع عمداً ندارد: تنها ردیف‌های
شبه‌فعالیت هسته در `msp_tasks` هستند که محتوای Parse‌شده یک فایل‌اند — درج در آن‌ها یعنی
گذاشتن چیزی در Snapshotی که فایل مبدأش آن را ندارد.

**کد فعالیت قابل تنظیم است:**

```python
CoreProgressSnapshotProvider(conn, activity_code_fields=("text1",))
CoreProjectActivityProvider(conn,  activity_code_fields=("text1",))
```

هر دو باید **یک ترتیب** بگیرند، وگرنه به یک خط برآورد کد فعالیتی پیشنهاد می‌شود که خوراک
پیشرفت هرگز نمی‌سازد. پیش‌فرض `("text1", "outline_number", "wbs")` است و یک **حدس
مستندشده** است، نه واقعیت Schema.

---

## ۶. ذخیره فایل و استخراج

`PRODUCTION_FILE_STORAGE_FA.md` — قرارداد کامل.
`LocalFileStorage` توسعه است و در Production قابل دسترسی نیست: `app/` هرگز `devhost` را
import نمی‌کند و یک تست این را تضمین می‌کند.

---

## چک‌لیست کامل سیم‌کشی

```python
# سه Adapter امنیتی — بدون این‌ها هیچ مسیری کار نمی‌کند
application.state.auth_context_provider   = ...
application.state.scope_authorizer        = ...
application.state.permission_authorizer   = ...

# یازده سرویس دامنه، هرکدام با Repository روی اتصال psycopg
application.state.finance_settings_service    = ...
application.state.finance_resources_service   = ...   # + activity_provider
application.state.finance_price_service       = ...
application.state.unit_conversion_service     = ...
application.state.progress_service            = ...   # + progress_provider
application.state.finance_import_service      = ...
application.state.invoice_service             = ...
application.state.finance_attachment_service  = ...   # + file_storage
application.state.finance_extraction_service  = ...   # + image, voice
application.state.finance_live_report_service = ...   # + progress_provider
application.state.finance_audit_service       = ...
```

**پیش‌نیاز:** `alembic upgrade head` صریحاً اجرا شده باشد.
**نقش‌ها:** Migration با Owner، اجرا با نقشی که DDL نمی‌تواند بزند.
