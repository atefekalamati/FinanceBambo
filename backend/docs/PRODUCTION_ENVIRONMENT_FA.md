# متغیرهای محیطی — طبقه‌بندی برای Production

## یافته‌ای که ترتیب این سند را تعیین می‌کند

**تقریباً هیچ‌کدام از متغیرهای این مخزن در Production خوانده نمی‌شوند.**

هر هشت متغیر بک‌اند در `devhost/environment.py` خوانده می‌شوند — ماژولی که میزبان
Production هرگز import نمی‌کند. یک تست این را تضمین می‌کند: `backend/app/` اجازه ندارد
`devhost`، `scripts` یا هر چیز mock/seed را import کند.

> در Production، **میزبان BAMBO** پیکربندی را از سیستم خودش می‌خواند و ماژول مالی را با
> نوشتن روی `application.state` سیم‌کشی می‌کند. ماژول مالی متغیر محیطی نمی‌خواند.

تنها استثنا `FINANCE_MIGRATION_DSN` است، که Alembic می‌خواند — و Alembic بخشی از **انتشار**
است، نه بخشی از **اجرا**.

---

## جدول کامل

| متغیر | طبقه | Secret؟ | اگر نباشد چه می‌شود |
|---|---|---|---|
| `FINANCE_MIGRATION_DSN` | **REQUIRED_PRODUCTION** (فقط هنگام انتشار) | ✅ بله | Alembic با `MissingConfiguration` متوقف می‌شود — عمداً کشنده |
| `FINANCE_DEV_DSN` | DEVELOPMENT_ONLY | ✅ بله | میزبان توسعه بالا نمی‌آید و مسیر `.env.example` را نشان می‌دهد |
| `FINANCE_CORE_DSN` | DEVELOPMENT_ONLY | ✅ بله | Adapterهای هسته سیم‌کشی نمی‌شوند؛ میزبان توسعه به داده ثابت برمی‌گردد |
| `FINANCE_CORE_PROGRESS` | DEVELOPMENT_ONLY | ❌ | پیشرفت از خوراک میزبان خوانده می‌شود (پیش‌فرض) |
| `FINANCE_DEMO_DSN` | DEMO_ONLY | ✅ بله | اسکریپت دمو از پیش‌فرض loopback بدون رمز استفاده می‌کند |
| `FINANCE_DEMO_PORT` | DEMO_ONLY | ❌ | پورت ۸۰۱۰ |
| `APP_ENV` | DEVELOPMENT_ONLY | ❌ | برای **توصیف** «development»؛ برای **مجوز**، نبودنش یعنی رد |
| `FINANCE_ALLOW_SEED` | DEVELOPMENT_ONLY | ❌ | داده نمایشی بارگذاری نمی‌شود |
| `BAMBO_AUDIT_URL` · `CHROME_PATH` | DEVELOPMENT_ONLY (اسکریپت ساخت فرانت‌اند) | ❌ | اسکریپت ممیزی چیدمان اجرا نمی‌شود |

**فرانت‌اند در زمان اجرا هیچ متغیر محیطی نمی‌خواند.** آدرس API نسبی است و نسبت به Origin
صفحه حل می‌شود؛ Cross-origin رد می‌شود.

---

## `FINANCE_MIGRATION_DSN` — تنها متغیر Production

```
postgresql://<owner_role>:<password>@<host>:5432/<database>
```

| | |
|---|---|
| چه کسی می‌خواندش | فقط `alembic/env.py` |
| کِی | هنگام `alembic upgrade head` در انتشار |
| نقش دیتابیس | نقشی که **می‌تواند DDL بزند** |
| اگر نباشد | `MissingConfiguration` — Alembic اجرا نمی‌شود |

**چرا DSN اجرا را نمی‌خواند:** نقش اجرا عمداً حق `CREATE` ندارد. اگر Alembic از DSN اجرا
استفاده می‌کرد، این جداسازی بی‌صدا از بین می‌رفت. `alembic/env.py` این را صریح نوشته و یک
تست آن را قفل می‌کند.

> **راه‌اندازی برنامه هرگز Migration اجرا نمی‌کند.** اجرای یک پروسه، رضایت به تغییر Schema
> نیست. اگر Schema نباشد، `SchemaNotMigrated` می‌گوید چه دستوری را باید زد.

---

## دو محافظ که با هم کار می‌کنند

داده نمایشی فقط وقتی بارگذاری می‌شود که **هر دو** شرط برقرار باشند:

```
APP_ENV ∈ {development, dev, test}     ← و باید صریحاً تنظیم شده باشد
FINANCE_ALLOW_SEED ∈ {1, true, yes, on}
```

`staging` عمداً در فهرست نیست: محیطی مستقر است و فاکتور نمایشی در آن، از فاکتور واقعی
قابل تشخیص نیست.

> **هیچ پیش‌فرضی نباید درج داده نمایشی را مجاز کند.** به همین دلیل `seeding_allowed()`
> مقدار خام تنظیم را می‌خواند، نه `app_env()` را که وقتی چیزی تنظیم نشده «development»
> برمی‌گرداند. یک محیط پیکربندی‌نشده نباید تصادفاً شرط اول را برآورده کند.

---

## پیکربندی مرده که پاک شد

`FRONTEND_ORIGIN` در `.env.example` بود و **هیچ کدی آن را نمی‌خواند** — نه CORS داریم و نه
لازم داریم، چون API و فایل‌های ایستا از یک Origin سرو می‌شوند و کلاینت Cross-origin را رد
می‌کند. مقدارش اصلاح و به‌عنوان مستند علامت‌گذاری شد.

**فایل `.env` واقعی شما دست نخورده است.** هیچ اعتباری در این مخزن نوشته نشده.

---

## چک‌لیست Production

```
✅ FINANCE_MIGRATION_DSN  → فقط در محیط انتشار، با نقش Owner
❌ FINANCE_DEV_DSN        → در Production تنظیم نشود
❌ FINANCE_CORE_DSN       → در Production تنظیم نشود
❌ FINANCE_ALLOW_SEED     → در Production تنظیم نشود
❌ APP_ENV=development    → در Production تنظیم نشود
```

سه ردیف پایین اگر تنظیم شوند بی‌اثرند، چون میزبان Production `devhost` را import نمی‌کند.
ولی نبودشان لایه دومی است که به «کسی اشتباه نکند» تکیه ندارد.
