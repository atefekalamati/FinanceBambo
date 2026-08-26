# راهنمای دموی فردا — گام به گام

این سند دقیقاً می‌گوید چه چیزی را کجا کلیک کنید. برای اجرا هیچ دانش قبلی لازم نیست.

---

## آماده‌سازی و اجرا — یک دستور

```
cd backend
python -m scripts.demo.prepare --recreate --serve
```

همین. این دستور دیتابیس را از صفر می‌سازد، Migration را اجرا می‌کند، داده نمایشی را
می‌ریزد و برنامه را بالا می‌آورد. مرورگر: **`http://127.0.0.1:8010`**

اگر فقط می‌خواهید دیتابیس ساخته شود بدون اجرای برنامه، `--serve` را بردارید.

خروجی باید شامل این خط‌ها باشد:

```
finance_alembic_version                      0006
public tables                                30
demo database ready.
```

**اگر پیامی با `STOP:` دیدید، هیچ کاری انجام نشده** — این محافظِ هدف است که فقط اجازه
می‌دهد روی دیتابیس دموی محلی نوشته شود.

### اجرای دستی (اگر لازم شد)

```
set FINANCE_DEV_DSN=postgresql://postgres@127.0.0.1:5432/bambo_finance_integration_demo
set FINANCE_CORE_DSN=postgresql://postgres@127.0.0.1:5432/bambo_finance_integration_demo
python -m devhost
```

`--serve` دقیقاً همین کار را می‌کند. در هر دو حالت دو خط زیر در کنسول ظاهر می‌شود:

```
development seed DISABLED (APP_ENV=development)
core integration ENABLED: membership, roles and permissions come from Core
```

خط دوم یعنی **مجوزها از جدول‌های هسته خوانده می‌شوند**، نه از داده ثابت.

مرورگر: **`http://127.0.0.1:8010`**

> اگر `FINANCE_CORE_DSN` را تنظیم نکنید، برنامه مثل قبل با داده ثابت کار می‌کند و همه
> مجوزها را می‌دهد. برای دمو حتماً تنظیمش کنید.

---

## دو برنامه، دو پورت — قاطی نشوند

| برنامه | پورت | ربطی به هم دارند؟ |
|---|---|---|
| **Pilot** | `http://127.0.0.1:8000` | ❌ |
| **مالی (این دمو)** | **`http://127.0.0.1:8010`** | ❌ |

**این دو کاملاً مستقل‌اند:** دیتابیس مشترک ندارند، کد مشترک ندارند، و تنظیمات مشترک ندارند.
تنها اشتراکشان این بود که هر دو پورت ۸۰۰۰ را می‌خواستند — و همین حل شد.

میزبان مالی اگر با `--port 8000` صدا زده شود **با پیام روشن امتناع می‌کند** و آن پورت را
نمی‌گیرد. اگر پورت ۸۰۱۰ هم مشغول باشد، متوقف می‌شود و **هیچ پروسه‌ای را نمی‌کُشد** — چون
هرچه آنجا گوش می‌دهد مال ما نیست.

> اگر Pilot روی ۸۰۰۰ در حال اجراست، بگذارید بماند. دمو به آن کاری ندارد.

اگر لازم شد پورت دیگری بگیرید:

```
python -m scripts.demo.prepare --recreate --serve --port 8011
```

یا با متغیر محیطی `FINANCE_DEMO_PORT`.

---

## اتصال DBeaver

| فیلد | مقدار |
|---|---|
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `bambo_finance_integration_demo` |
| Username | `postgres` |
| Password | خالی (PostgreSQL محلی اتصال loopback را trust می‌کند) |

مسیر جدول‌ها در درخت سمت چپ:

```
bambo_finance_integration_demo › Schemas › public › Tables
```

---

# سناریوی نمایش — ۱۳ گام

## گام ۱ — نسخه ساختار دیتابیس

جدول **`finance_alembic_version`** را باز کنید.

یک ردیف، یک ستون: `version_num = 0006`

**چه بگویید:** «ساختار جدول‌های مالی فقط از راه Alembic ساخته می‌شود. این عدد یعنی هر شش
مرحله اعمال شده. نام جدول عمداً `finance_alembic_version` است، نه `alembic_version`، چون
دیتابیس BAMBO مشترک است و ماژول مالی نباید نام عمومی را برای خودش بردارد.»

## گام ۲ — جدول‌های Mirror هسته

این ۱۴ جدول را در فهرست نشان دهید:

```
organizations · users · projects
organization_memberships · project_memberships
roles · permissions · role_permissions · user_roles · user_permission_overrides
msp_file_versions · msp_snapshots · msp_tasks · media_files
```

روی هرکدام کلیک راست → **Properties**. در قسمت **Comment** این متن دیده می‌شود:

> `DEMO_LOCAL_ONLY - local mirror of the BAMBO Core table of the same name...`

**چه بگویید:** «ساختار این جدول‌ها از روی ساختار واقعی هسته تولید شده — همان نام ستون‌ها،
همان نوع‌ها، همان قیدها. ولی **هیچ ردیفی از Production کپی نشده**؛ همه داده‌ها ساختگی‌اند و
خودِ دیتابیس این را در توضیح جدول می‌گوید.»

## گام ۳ — جدول‌های مالی

۱۵ جدول:

```
finance_project_settings · finance_resources
estimate_lines · estimate_revisions
price_versions · unit_conversions
progress_snapshot_refs · progress_overrides
invoices · invoice_lines
report_snapshots · finance_attachments · extraction_drafts
finance_audit_events · finance_import_batches
```

## گام ۴ — یک پروژه، دیده‌شده از دو طرف

```sql
SELECT p.id, p.name, p.code, p.built_area_sqm, o.name AS organization
FROM projects p JOIN organizations o ON o.id = p.organization_id
WHERE p.id = 'sample_site_01';

SELECT organization_id, project_id, gross_built_area, revision
FROM finance_project_settings ORDER BY revision DESC LIMIT 1;
```

**چه بگویید:** «`organization_id` و `project_id` در هر دو یکی است. اتصال منطقی است — کلید
خارجی فیزیکی نداریم، و گام ۱۲ می‌گوید چرا.»

## گام ۵ — حلقه اصلی: Snapshot هسته ↔ ارجاع مالی

**این مهم‌ترین کوئری دمو است.**

```sql
SELECT r.host_snapshot_id      AS "شناسه هسته",
       s.id                    AS "msp_snapshots.id",
       s.snapshot_type         AS "نوع",
       s.status_date_jalali    AS "تاریخ وضعیت شمسی",
       r.reporting_date        AS "تاریخ گزارش",
       v.original_filename     AS "فایل زمان‌بندی"
FROM progress_snapshot_refs r
LEFT JOIN msp_snapshots     s ON s.id = r.host_snapshot_id
LEFT JOIN msp_file_versions v ON v.id = r.host_file_version_id
ORDER BY r.reporting_date;
```

سه ردیف: `9001` · `9002` · `9003` — و در هر ردیف، ستون هسته و ستون مالی **عدد یکسان** دارند.

**چه بگویید:** «هسته با عدد صحیح شناسایی می‌کند، ماژول مالی با UUID. تا پیش از نسخه 0006،
ماژول مالی نمی‌توانست بگوید گزارشش بر اساس کدام فایل زمان‌بندی ساخته شده. الان می‌تواند.»

**اضافه کنید:** «تاریخ گزارش از تاریخ وضعیتی که برنامه‌ریز اعلام کرده تبدیل می‌شود، نه از
تاریخ آپلود فایل.»

## گام ۶ — تازگی از زنجیره می‌آید، نه از نوع

```sql
SELECT s.id, s.snapshot_type, s.previous_snapshot_id,
       EXISTS (SELECT 1 FROM msp_snapshots l WHERE l.previous_snapshot_id = s.id) AS superseded
FROM msp_snapshots s ORDER BY s.id;
```

هر سه `ACTUAL` هستند، ولی فقط ۹۰۰۳ جاری است.

**چه بگویید:** «نوع Snapshot می‌گوید *چیست*؛ زنجیره می‌گوید *هنوز معتبر هست یا نه*. این دو
را به هم نگاشت نکردیم چون یک پرسش نیستند.»

## گام ۷ — منابع، قیمت‌ها، برآورد، فاکتور

```sql
SELECT code, title, resource_type, base_unit FROM finance_resources ORDER BY code;

SELECT p.version, f.code, p.scope_kind, p.unit_price_irr, p.effective_from
FROM price_versions p JOIN finance_resources f ON f.id = p.resource_id ORDER BY p.version;

SELECT f.code, l.activity_external_id, l.assignment_external_id, l.original_quantity
FROM estimate_lines l JOIN finance_resources f ON f.id = l.resource_id ORDER BY f.code;

SELECT status, count(*), sum(final_amount_irr) FROM invoices GROUP BY status ORDER BY status;
```

۵۳ فاکتور در پنج وضعیت. همین اعداد در مرورگر هم دیده می‌شوند.

**یک نکته خوب برای گفتن:** «خط دوم میلگرد (ACT-201) تخصیص ندارد. این خطا نیست — خوراک
پیشرفت برای آن فعالیت ردیف میلگرد ندارد، و سیستم به‌جای اینکه صفر بگذارد، هشدار می‌دهد که
این خط به پیشرفتی وصل نیست.»

## گام ۸ — ویرایش در مرورگر

در مرورگر: صفحه **تنظیمات** → زیربنای کل را عوض کنید (مثلاً `4250` → `4400`) → دلیل بنویسید
→ ذخیره.

## گام ۹ — همان لحظه در DBeaver

```sql
SELECT revision, gross_built_area, effective_from, reason, created_at
FROM finance_project_settings ORDER BY revision DESC;
```

Refresh کنید (**F5**). یک ردیف **جدید** با شماره نسخه بالاتر ظاهر می‌شود.

**چه بگویید:** «ردیف قبلی تغییر نکرد. سیستم فقط اضافه می‌کند. تاریخچه کامل باقی می‌ماند.»

## گام ۱۰ — ویرایش مستقیم در دیتابیس

در DBeaver این را اجرا کنید:

```sql
INSERT INTO finance_project_settings
    (id, organization_id, project_id, revision, gross_built_area,
     effective_from, reason, created_by, created_at)
SELECT gen_random_uuid(), organization_id, project_id, revision + 1, 4600.0000,
       '2026-06-05', 'ویرایش مستقیم در دیتابیس (نمایشی)', created_by, now()
FROM finance_project_settings
ORDER BY revision DESC LIMIT 1;
```

## گام ۱۱ — همان لحظه در مرورگر

صفحه را Refresh کنید. عدد `4600` ظاهر می‌شود.

**چه بگویید:** «مرورگر با API واقعی حرف می‌زند و API با همین دیتابیس. هیچ داده ساختگی در
مسیر نیست.»

> در Network مرورگر، هر پاسخ API این Header را دارد:
> `X-Finance-Data-Source: postgresql`

## گام ۱۲ — تاریخچه تغییرناپذیر است

این را اجرا کنید — **باید شکست بخورد**:

```sql
UPDATE invoices SET status = 'draft' WHERE status = 'confirmed';
```

خطای دیتابیس برمی‌گردد.

```sql
SELECT tgname FROM pg_trigger
WHERE tgrelid = 'invoices'::regclass AND NOT tgisinternal;
```

**چه بگویید:** «۱۰ تریگر روی جدول‌های تاریخی هر `UPDATE` و `DELETE` را رد می‌کنند. این در
خودِ دیتابیس است، نه در کد برنامه — یعنی حتی با دسترسی مستقیم به دیتابیس هم نمی‌شود دورش
زد. برای همین در گام ۱۰ یک ردیف **جدید** اضافه کردیم و ردیف قبلی را عوض نکردیم.»

## گام ۱۳ — مجوزی که در هسته وجود ندارد

```sql
SELECT code FROM permissions WHERE code LIKE 'finance%' ORDER BY code;
```

چهار ردیف:

```
finance.edit · finance.view · finance_report.export · finance_report.view
```

`finance_report.issue` **نیست**.

سپس در مرورگر، صفحه **گزارش‌ها** را باز کنید: دکمه **«ثبت گزارش دوره‌ای»** اصلاً وجود ندارد.

**چه بگویید — و این نکته پایانی خوبی است:**

> «در دیتابیس واقعی BAMBO هم دقیقاً همین چهار مجوز هست و `finance_report.issue` نیست. ما
> این را با یک بررسی فقط‌خواندنی روی سرور اصلی تأیید کردیم.
>
> ماژول مالی این را با نگاشت به یک مجوز دیگر دور نزد. اگر `finance_report.issue` را به
> `finance_report.export` وصل می‌کردیم، هرکسی که فقط حق خروجی‌گرفتن دارد می‌توانست گزارش
> رسمی صادر کند. صدور گزارش یعنی تثبیت یک عدد رسمی — این با خروجی‌گرفتن یکی نیست.
>
> پس سیستم **بسته می‌ماند** تا تیم هسته آن مجوز را بسازد. رابط کاربری هم دکمه را نشان
> نمی‌دهد، چون همان مجوزهایی را می‌خواند که سرور روی آن تصمیم می‌گیرد.»

---

## نمایش‌های اختیاری — اگر وقت بود

### الف) سلب فردی بر نقش غلبه می‌کند

```sql
SELECT u.display_name, p.code, o.allowed
FROM user_permission_overrides o
JOIN users u ON u.id = o.user_id
JOIN permissions p ON p.id = o.permission_id;
```

کاربر «کاربر با محدودیت نمونه» نقشی دارد که `finance.edit` می‌دهد، ولی یک سلب فردی آن را
پس می‌گیرد. **سلب برنده است.**

### ب) نقش در یک سازمان، در سازمان دیگر بی‌اثر است

`other_site_99` یک پروژه در سازمان دیگر است و کاربرش نقش `org_chief` دارد — ولی روی
`sample_site_01` هیچ دسترسی‌ای ندارد.

---

## هشدارها

| نکن | چرا |
|---|---|
| در جدول‌های تاریخچه مستقیم `UPDATE` نزن | دیتابیس رد می‌کند؛ برای تغییر، ردیف جدید اضافه کن |
| به `192.168.100.200` وصل نشو | دیتابیس اصلی است و در این دمو نقشی ندارد |
| `alembic downgrade` نزن | لازم نیست؛ اگر خواستی از صفر بسازی، `prepare.py --recreate` |
| `FINANCE_CORE_DSN` را جا نینداز | بدون آن، دمو با داده ثابت اجرا می‌شود و گام ۱۳ کار نمی‌کند |

## اگر چیزی خراب شد

```
cd backend
python -m scripts.demo.prepare --recreate --serve
```

دیتابیس دمو یک‌بارمصرف است. ساخت دوباره‌اش ۲ ثانیه طول می‌کشد و هیچ داده واقعی از بین
نمی‌رود.
