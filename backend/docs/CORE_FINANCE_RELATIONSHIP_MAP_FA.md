# نقشه ارتباط هسته BAMBO و ماژول مالی

این سند نشان می‌دهد داده ماژول مالی چطور به داده هسته وصل می‌شود — و چرا این اتصال عمداً
**منطقی** است و نه **فیزیکی**.

---

## پنج اتصال اصلی

| هسته | ماژول مالی | نوع | یعنی چه |
|---|---|---|---|
| `organizations.id` | `organization_id` در **همه** جدول‌های مالی | uuid | سازمان مالک داده |
| `projects.id` | `project_id` در **همه** جدول‌های مالی | text | پروژه‌ای که داده به آن تعلق دارد |
| `msp_snapshots.id` | `progress_snapshot_refs.host_snapshot_id` | **bigint** | کدام Snapshot پیشرفت مبنای محاسبه بوده |
| `msp_file_versions.id` | `progress_snapshot_refs.host_file_version_id` | **bigint** | کدام فایل زمان‌بندی منبع آن Snapshot بوده |
| `users.id` | `created_by` · `submitted_by` · `confirmed_by` · `imported_by` · `actor_user_id` | uuid | چه کسی این کار را کرد |

### دو فضای نام شناسه که نباید قاطی شوند

```
هسته   →  bigint   9001, 9002, 9003        (msp_snapshots.id)
مالی   →  uuid     33333333-...-333331     (progress_snapshot_id)
```

این‌ها **دو نام برای یک چیزند**، نه دو چیز. ردیف `progress_snapshot_refs` هر دو را نگه
می‌دارد و همان جایی است که ترجمه اتفاق می‌افتد.

> **قاعده‌ای که چهار بار زیرش رفتیم:** وقتی ماژول مالی از میزبان می‌پرسد «اطلاعات این
> Snapshot را بده»، باید با **شناسه هسته** بپرسد، نه با UUID خودش. میزبان UUID مالی را
> هرگز نساخته و نمی‌شناسد.
>
> این اشتباه در چهار نقطه از کد وجود داشت و هر چهار جا اصلاح شد. در محیط توسعه دیده نمی‌شد،
> چون داده ساختگی به هر دو شناسه جواب می‌داد.

---

## چرا هیچ کلید خارجی فیزیکی از مالی به هسته نداریم

این یک سهل‌انگاری نیست؛ یک تصمیم است.

**مسئله:** هسته با حذف پروژه، رکوردهای وابسته را CASCADE حذف می‌کند:

```sql
msp_snapshots.project_id → projects(id) ON DELETE CASCADE
```

اگر از `progress_snapshot_refs` کلید خارجی به `msp_snapshots` می‌گذاشتیم، فقط دو حالت
ممکن بود — و **هر دو بد**:

| اگر می‌گذاشتیم | نتیجه |
|---|---|
| `ON DELETE CASCADE` | حذف یک پروژه در هسته، **تاریخچه مالی آن را نابود می‌کرد** — از جمله گزارش‌های رسمی صادرشده |
| `ON DELETE RESTRICT` | ماژول مالی **حذف پروژه را در هسته مسدود می‌کرد** — یعنی یک ماژول تابع، چرخه حیات هسته را گروگان می‌گرفت |

**راه‌حل:** ارجاع منطقی. عدد ذخیره می‌شود، اعتبارسنجی در Adapter انجام می‌شود، و اگر
Snapshot هسته حذف شود، ردیف مالی باقی می‌ماند و صادقانه می‌گوید به چیزی اشاره می‌کند که
دیگر نیست.

> **این ویژگی است، نه نقص.** یک گزارش مالی رسمی باید بعد از حذف پروژه هم بگوید بر چه مبنایی
> صادر شده. سند حسابداری با پاک‌شدن پروژه پاک نمی‌شود.

همین استدلال درباره `organizations`، `users`، `media_files` و `msp_file_versions` هم صدق
می‌کند.

---

## سه پرسش، سه منبع متفاوت

هسته سه پرسش را با سه مدل جدا جواب می‌دهد. قاطی‌کردنشان، اشتباه اصلی این حوزه است:

| پرسش | جدول مرجع |
|---|---|
| این شخص عضو این سازمان/پروژه هست؟ | `organization_memberships` · `project_memberships` |
| چه کارهایی می‌تواند بکند؟ | `user_roles` → `role_permissions` → `permissions` + `user_permission_overrides` |
| در این سازمان چه نامیده می‌شود؟ | `user_roles` → `roles.code` |

### دام: دو جدول شبیه که یکی نیستند

هسته یک جفت جدول دیگر هم دارد: `organization_members` و `project_members`. شبیه‌اند ولی
**منبع مجوز نیستند** — چون `user_id` در آن‌ها می‌تواند خالی باشد، یعنی می‌توانند شخصی را
توصیف کنند که اصلاً حساب کاربری ندارد.

آن‌ها یک **دفترچه تماس** هستند. هیچ‌کجای کد اتصال مالی خوانده نمی‌شوند، و یک تست این را
تضمین می‌کند.

---

## آنچه هسته می‌تواند و نمی‌تواند بگوید

این بخش را دست‌کم نگیرید؛ مهم‌ترین محدودیت فنی این یکپارچه‌سازی است.

| هسته چه دارد | آیا مالی می‌تواند استفاده کند |
|---|---|
| `msp_snapshots` — هویت، نوع، زنجیره نسخه | ✅ کامل |
| `msp_file_versions` — فایل منبع، نسخه، تاریخ | ✅ کامل |
| `msp_tasks` — نام، WBS، تاریخ، **درصد پیشرفت** | ✅ ولی فقط درصد |
| منبع (میلگرد، جرثقیل، اکیپ) | ❌ **وجود ندارد** |
| واحد (کیلوگرم، ساعت) | ❌ **وجود ندارد** |
| مقدار اجراشده | ❌ **وجود ندارد** |

> ### 🔴 نتیجه: مقدار اجراشده از هسته قابل استخراج نیست
>
> در هسته **هیچ جدول تخصیص منبع (assignment) وجود ندارد** و `msp_tasks` هیچ ستون منبع یا
> مقداری ندارد. یعنی امروز، از داده هسته به‌تنهایی، نمی‌شود گفت «۲۵۰۰ کیلوگرم میلگرد اجرا
> شده».
>
> Adapter پیشرفت این را **صادقانه گزارش می‌کند**: ردیف‌های سطح-فعالیت می‌فرستد با تمام
> فیلدهای مقدار خالی، و ماژول مالی آن خط را `unavailable` با هشدار `PROGRESS_MISSING` نشان
> می‌دهد — نه صفر.

سه راه‌حل بررسی و **رد** شد:

1. ساختن شناسه تخصیص ساختگی → ارتباطی جعل می‌کرد که هسته ادعایش را ندارد
2. ضرب درصد Task در مقدار برآورد → عددی می‌ساخت که **همیشه با برآورد می‌خواند** و هرگز مشکلی را لو نمی‌داد
3. استفاده از `percent_work_complete` به‌جای درصد مقدار → همان اشتباه «ساعت‌کار به‌جای مقدار» که قبلاً برطرف شده بود

**راه درست:** مقادیر سطح-تخصیص باید از ماژول پیشرفت میزبان بیاید. این یک بازدارنده Production
است و ثبت شده.

---

## راهنمای مشاهده کنار هم در DBeaver

### ۱. سازمان و پروژه

```sql
SELECT o.id, o.name, p.id AS project_id, p.name, p.code, p.built_area_sqm
FROM organizations o JOIN projects p ON p.organization_id = o.id;
```

سپس جدول `finance_project_settings` را باز کنید. `organization_id` و `project_id` دقیقاً
همان مقادیرند، و `gross_built_area` با `projects.built_area_sqm` می‌خواند.

### ۲. حلقه اصلی — Snapshot پیشرفت

این کوئری قلب یکپارچه‌سازی را در یک جدول نشان می‌دهد:

```sql
SELECT r.progress_snapshot_id  AS "شناسه مالی (UUID)",
       r.host_snapshot_id      AS "شناسه هسته (bigint)",
       s.id                    AS "msp_snapshots.id",
       s.snapshot_type,
       s.status_date_jalali    AS "تاریخ وضعیت شمسی",
       r.reporting_date        AS "تاریخ گزارش میلادی",
       v.id                    AS "msp_file_versions.id",
       v.original_filename
FROM progress_snapshot_refs r
LEFT JOIN msp_snapshots     s ON s.id = r.host_snapshot_id
LEFT JOIN msp_file_versions v ON v.id = r.host_file_version_id
ORDER BY r.reporting_date;
```

نتیجه روی دیتابیس دمو:

| شناسه هسته | msp_snapshots.id | نوع | شمسی | میلادی | فایل |
|---|---|---|---|---|---|
| 9001 | 9001 | ACTUAL | ۱۴۰۵-۰۵-۰۹ | 2026-07-31 | sample-progress-v1.mpp |
| 9002 | 9002 | ACTUAL | ۱۴۰۵-۰۵-۱۰ | 2026-08-01 | sample-resource-loaded-v2.mpp |
| 9003 | 9003 | ACTUAL | ۱۴۰۵-۰۵-۱۱ | 2026-08-02 | sample-progress-v3.mpp |

**نکته گفتنی:** تاریخ گزارش از `status_date_jalali` — تاریخ وضعیتی که خودِ برنامه‌ریز اعلام
کرده — تبدیل می‌شود، نه از تاریخ آپلود فایل. اگر فایل سه روز دیرتر آپلود شود، عدد مالی
همچنان به تاریخ درست منتسب است.

### ۳. تازگی از زنجیره، نه از نوع

```sql
SELECT s.id, s.snapshot_type, s.previous_snapshot_id,
       EXISTS (SELECT 1 FROM msp_snapshots l WHERE l.previous_snapshot_id = s.id)
           AS superseded
FROM msp_snapshots s ORDER BY s.id;
```

هر سه Snapshot نوع `ACTUAL` دارند، ولی ۹۰۰۱ و ۹۰۰۲ `superseded` هستند و ۹۰۰۳ نیست.

> `snapshot_type` می‌گوید Snapshot **چیست** (هدف / واقعی / زمان‌بندی مجدد). وضعیت مالی
> می‌گوید **هنوز جاری هست یا نه**. این دو یک پرسش نیستند و هرگز به هم نگاشت نمی‌شوند.

### ۴. مجوزها — و آن یکی که وجود ندارد

```sql
SELECT code FROM permissions WHERE code LIKE 'finance%' ORDER BY code;
```

چهار ردیف برمی‌گردد. `finance_report.issue` **نیست** — دقیقاً مثل هسته واقعی.

### ۵. مسیر کامل مجوز مؤثر

```sql
SELECT u.display_name, r.code AS role, p.code AS permission, ur.organization_id, ur.project_id
FROM user_roles ur
JOIN users u ON u.id = ur.user_id
JOIN roles r ON r.id = ur.role_id
JOIN role_permissions rp ON rp.role_id = r.id
JOIN permissions p ON p.id = rp.permission_id
ORDER BY u.display_name, p.code;
```

و سلب فردی که بر نقش غلبه می‌کند:

```sql
SELECT u.display_name, p.code, o.allowed
FROM user_permission_overrides o
JOIN users u ON u.id = o.user_id
JOIN permissions p ON p.id = o.permission_id;
```

---

## چه چیزهایی عمداً پیاده نشده‌اند

| مورد | چرا |
|---|---|
| کلید خارجی فیزیکی مالی → هسته | بالا توضیح داده شد |
| نوشتن در `projects.estimated_cost` | تصمیم محصولی گرفته نشده؛ یک‌طرفه و فقط هنگام صدور گزارش رسمی پیشنهاد شده است |
| ساختن جدول تخصیص در هسته | هسته مالک ساختار خودش است |
| ساختن `finance_report.issue` توسط ما | RBAC مال هسته است؛ ماژول مالی مجوز نمی‌سازد |
| جایگزینی `finance_attachments` با `media_files` | ۱۶ ستون در برابر ۸؛ Hash، وضعیت پردازش و حذف منطقی از دست می‌رفت |
