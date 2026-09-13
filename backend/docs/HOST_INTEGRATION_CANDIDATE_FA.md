# کاندیدای یکپارچه‌سازی Backend Finance با میزبان BAMBO

تاریخ اعتبارسنجی محلی: ۲۰۲۶-۰۹-۱۳  
نسخه API: `1.0.0-rc2`  
نسخه Migration: `0020`

این کاندیدا نتیجه ادغام آخرین `origin/master` (`4917c024`) با کاندیدای مالی
`feature/fixed-cost-and-partial-sums` (`e2bf91cd`) در شاخه ایزوله
`integration/host-readiness-20260912` است. این شاخه Push یا Deploy نشده است.

## روش ترکیب با میزبان

Finance نباید Application، lifespan یا pool جداگانه‌ای در میزبان اصلی بسازد. میزبان هنگام
ساخت برنامه `mount_finance(host_app)` را صدا می‌زند و در lifespan موجود خودش، پس از ساخت
Adapterها و Serviceها، `configure_finance` را اجرا می‌کند:

```python
from app.finance.integration import (
    PsycopgFinanceReadinessProbe,
    configure_finance,
    mount_finance,
)
from app.finance.pool_connection import HostPoolConnection

mount_finance(host_app)

# داخل lifespan موجود میزبان
finance_db = HostPoolConnection(host_pool, timeout_seconds=5)
await configure_finance(
    host_app,
    components=finance_components,
    readiness_probe=PsycopgFinanceReadinessProbe(finance_db, "0020"),
    dedicated=False,
    operator_notice=operator_log,
)
```

انتشار Componentها اتمیک است: تا وقتی هر ۱۴ وابستگی اجباری و Probe دیتابیس موفق نشده‌اند،
هیچ مسیر Finance ترافیک نمی‌پذیرد و پاسخ غیرحساس `503 FINANCE_UNAVAILABLE` می‌دهد؛ مسیرهای
نامرتبط میزبان فعال می‌مانند. `/healthz/live` زنده‌بودن Process و `/healthz/finance`
آمادگی همین ماژول را جدا گزارش می‌کنند.

`app.main:app` ورودی اختصاصی سخت‌گیرانه است و بدون سیم‌کشی معتبر Startup را متوقف می‌کند.
این شیء جای Composition واقعی میزبان را نمی‌گیرد.

## وابستگی‌های اجباری

- امنیت: `auth_context_provider`، `scope_authorizer`، `permission_authorizer`
- دامنه: Settings، Resources، Prices، Unit Conversion، Progress، Import، Invoice،
  Attachment، Extraction، Live/Frozen Report و Audit
- دیتابیس: ledger دقیق `0020`، SELECT روی `finance_resources`، INSERT روی `invoices` و
  نداشتن حق `CREATE` برای نقش Runtime

قابلیت‌های اختیاری شامل Actor Directory، MPP sync/mapping و Background Executor هستند.
غیرفعال بودن Provider استخراج نباید Invoice دستی را از کار بیندازد؛ با این حال Endpoint
استخراج Async فقط وقتی `202` می‌دهد که میزبان Executor پایدار فراهم کند. اجرای موقت
`BackgroundTasks` فقط در `devhost` صریحاً مجاز است.

## مالکیت پیکربندی

| تنظیم | الزام | مالک | رفتار در نبود/خطا |
|---|---|---|---|
| Runtime DB DSN و pool min/max/acquire timeout | اجباری | میزبان | Finance آماده نمی‌شود |
| `FINANCE_MIGRATION_DSN` | فقط زمان انتشار | Release/DBA | Migration متوقف می‌شود |
| نقش Runtime بدون DDL | اجباری | DBA | Readiness رد می‌شود |
| Session/Cookie، scope و CSRF/origin protection | اجباری | میزبان | فعال‌سازی ممنوع |
| Durable File Storage | اجباری برای فایل | میزبان/Infra | Upload با 503 و بدون metadata نیمه‌کاره |
| Malware scanner | طبق تصمیم انتشار | میزبان/Security | اگر اجباری باشد قابلیت فایل Block است |
| Extraction provider | اختیاری | میزبان/AI | استخراج unavailable؛ Invoice دستی فعال |
| Durable background executor | برای Async extraction | میزبان | Endpoint Async با 503 رد می‌شود |
| MPP root/reader/job scheduler | فقط اگر MPP فعال است | میزبان/Planning | Sync غیرفعال یا unavailable |

متغیرهای `FINANCE_DEV_*`، `FINANCE_DEMO_*`، `FINANCE_ALLOW_SEED` و هویت هدرمحور مخصوص
توسعه‌اند و نباید در Composition تولید import یا فعال شوند.

## هویت و مجوز

قرارداد واقعی Cookie/Session و محافظت درخواست در این مخزن موجود نیست. میزبان باید seam
`identity(request)` در `CoreAuthContextAssembler` را از Session مورداعتماد خود پر کند؛
هدرهای Dev راه‌حل Production نیستند. شش مجوز لازم عبارت‌اند از:

- `finance.view`
- `finance.edit`
- `finance.manage_invoice`
- `finance_report.view`
- `finance_report.export`
- `finance_report.issue`

هر شش کد در دیتابیس ایزوله کاندیدا مشاهده شدند، اما وجودشان و Role grantهایشان در میزبان
هدف هنوز باید توسط تیم Core تأیید شود. هیچ Role تولیدی در این کار حدس یا اعطا نشده است.

## اتصال و تراکنش

`HostPoolConnection` فقط facade سازگار با Repository روی pool متعلق به میزبان است. هر
عملیات Lease جدا می‌گیرد و یک transaction صریح را با `ContextVar` به همان درخواست pin
می‌کند. Lease در موفقیت، exception، cancellation و حتی خطای ورود به cursor/transaction
آزاد می‌شود. ساخت/بستن pool، ظرفیت و timeoutهای سرور همچنان مسئولیت میزبان است.

## فایل و استخراج

نوشتن ناموفق Storage دیگر Upload موفق یا metadata دیتابیس ایجاد نمی‌کند. خطای خواندن
Storage به پاسخ کنترل‌شده 503 و نبود بایت به 404 scoped تبدیل می‌شود و مسیر/خطای داخلی
افشا نمی‌گردد. Adapter ذخیره پایدار و Scanner واقعی در کد میزبان حاضر نیستند و پیش از
فعال‌سازی Upload در Staging باید ارائه و آزموده شوند.

## MPP و Progress

Sync موجود از advisory transaction lock استفاده می‌کند و Scheduler دوره‌ای فقط در
`devhost` و پشت تنظیم صریح است. میزبان باید job mechanism خودش را متصل کند. ترتیب تجاری
نسخه‌های Schedule از checksum یا زمان Import استنباط نمی‌شود. اختلاف گزارش‌شده ۷۸۸/۷۸۹
بدون مدرک منبع باز می‌ماند. Finance داده Progress را فقط می‌خواند.

## Migration

Migration جدیدی برای این کار لازم نبود. اعتبارسنجی روی دیتابیس‌های یک‌بارمصرف:

- Upgrade از کپی وضعیت `0018`: `0018 → 0019 → 0020` موفق
  (`bambo_hostint_upgrade_20260913`).
- نصب تازه پس از Core prerequisite fixture: `base → 0020` موفق
  (`bambo_hostint_fresh_20260913`).
- ۲ Invoice تاریخی از نظر شماره، وضعیت، مبلغ و اثر مالی ثابت ماندند؛ `0020` فقط
  `invoice_seq` را طبق Migration موجود backfill کرد.
- اثرانگشت `report_snapshots`، `price_versions` و `finance_audit_events` ثابت ماند.
- invariant gate: ۲۱ Passed، صفر Failed/Skipped.

هیچ Dump جدیدی تولید نشد، چون تغییر Schema یا داده انجام نشده است.

## OpenAPI و مشاهده‌پذیری

OpenAPI موجود با exporter خود پروژه به‌روزرسانی شد: ۵۱ Path، نسخه `1.0.0-rc2`، توضیح
Session opaque میزبان و media type باینری واقعی برای Attachment/CSV/XLSX. Request ID معتبر
از میزبان حفظ و در غیر این صورت تولید می‌شود و در envelope و Header یکسان است.

## Rollback

Rollback این کاندیدای code-only با بازگرداندن Commit کاندیدا و restart میزبان انجام
می‌شود. Migration یا بازیابی دیتابیس لازم نیست. اگر در آینده میزبان `0020` را اعمال کرد،
Rollback دیتابیس یک تصمیم داده‌ای مستقل است و نباید با rollback برنامه خودکار شود.

## وضعیت فعال‌سازی

- نمایش محلی با دیتابیس واقعی: روی `127.0.0.1:43127` اجرا و Smoke شد؛ HTML دارای Host
  Context و فاقد marker مستقل Mock است و پاسخ API هدر `X-Finance-Data-Source: postgresql`
  دارد. دیتابیس `bambo_candidate_20260912` شامل ۱۹۰ Resource و ۸۳۸ EstimateLine فعال است.
  Assignment UID `9703` در API مقدار `1` و `125651153910` IRR برگرداند. Auth این اجرا
  توسعه‌ای است و شاهد اتصال Session واقعی نیست.
- Staging: تا اتصال Session/CSRF واقعی، Runtime role محدود، Storage/Scanner موردنیاز و
  acceptance میزبان Block است.
- Production: آماده اعلام نمی‌شود تا Gateهای واقعی Staging/Host عبور کنند.

نتیجه Gateهای محلی این کاندیدا:

- Backend: ۱۳۷۶ Passed، صفر Failed/Skipped؛ ۲۸۷۰ subtest Passed.
- Frontend: ۵۳۰ Passed، صفر Failed/Skipped.
- Integration Kit v1.1: ۲۹ Passed، صفر Failed/Error/Skipped.
- OpenAPI exporter: قرارداد جاری، ۵۱ Path.
- هشدار محیطی: JPype هنگام راه‌اندازی JVM روی Windows پیام native access-violation چاپ
  می‌کند، اما ۱۱ تست MPP و Suite کامل با exit code صفر پایان یافتند. این پیام باید پیش از
  اجرای Worker MPP در Staging روی Runtime هدف بررسی شود.
