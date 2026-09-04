# اجرای کنترل‌شدهٔ منابع و تخصیص‌های MSP روی دیتابیس مرکزی

**هدف:** یک MPP، یک snapshot، از ابتدا تا گزارش مالی. نه بارگذاری انبوه.

**دیتابیس:** فقط `bambo_canonical_local` روی `192.168.100.200:5432`.

**فازهای B و D را فقط اپراتور انسانی اجرا می‌کند.** خودکار نشوند.

---

## فاز A — PRECHECK

```bash
psql -f backend/docs/sql/msp_resource_assignment_precheck.sql
```

فقط‌خواندنی. بخش تفسیر انتهای خودِ فایل را بخوانید.

| | |
|---|---|
| **PASS** | جدول‌های Core موجود · هر دو جدول هدف غایب · بدون تصادم نام · `CREATE` روی `public` |
| **STOP** | هر یک از جدول‌های هدف از قبل هست · نامی گرفته است · `CREATE` ندارید |

**اگر جدولی از قبل وجود دارد، آن را نه adopt کنید نه drop.** نسخه‌ای از این schema قبلاً
اعمال شده و اینکه کدام نسخه بوده اهمیت دارد.

---

## فاز B — APPLY · فقط دستی

```bash
psql -v ON_ERROR_STOP=1 -f backend/docs/sql/msp_resource_assignment_apply.sql
```

دو جدول می‌سازد. هیچ ردیفی نمی‌نویسد، هیچ جدول Core موجودی را تغییر نمی‌دهد، backfill
ندارد. اگر جدول‌ها از قبل باشند، با پیام صریح می‌ایستد.

> این SQL روی PostgreSQL 18 محلی اجرا و آزموده شده: ساخت موفق، اجرای دوباره با خطای
> واضح رد شد، و rollback جدول‌های Core را دست‌نخورده گذاشت.

---

## فاز C — POSTCHECK ساختاری

```bash
psql -f backend/docs/sql/msp_resource_assignment_postcheck.sql
```

**PASS:** هر دو جدول موجود · هر ستون مقدار/هزینه/نرخ از نوع `numeric` · سه کلید یکتا
موجود · بخش ۶ هیچ ردیفی برنگرداند · هر دو جدول خالی · شمار قیدهای `msp_tasks` نسبت به
PRECHECK تغییر نکرده.

هر چیز دیگری **FAIL**. دستی تعمیر نکنید؛ rollback و دوباره apply.

---

## فاز D — بارگذاری کنترل‌شده · فقط دستی

**دقیقاً یک MPP تأییدشده.** نه هر ۱۳ snapshot تاریخی.

بارگذاری با همان جریان موجود Core انجام می‌شود. ماژول مالی در این فاز هیچ نقشی ندارد و
هیچ فایلی را تجزیه نمی‌کند.

اگر parser هنوز نگهداشت منابع/تخصیص‌ها را ندارد، این فاز مسدود است — [مشخصات
پیاده‌سازی](MSP_PARSER_RESOURCE_ASSIGNMENT_IMPLEMENTATION_SPEC.md) را به تیم Core بدهید.

---

## فاز E — اعتبارسنجی داده

```bash
psql -f backend/docs/sql/msp_resource_assignment_data_validation.sql
```

**PASS:** بدون کلید تکراری · بدون شناسهٔ null · صفر تخصیصِ بدون فعالیت متناظر · صفر مقدارِ
بدون واحد · **`MISMATCHED = 0`** در بخش ۸.

بخش ۸ مهم‌ترین است: مقدار Resource Sheet هر منبع باید با جمع مقادیر تخصیص‌هایش برابر
باشد. جایی که نیست، بارگذاری ردیفی را گم یا تکرار کرده.

**انتظار درست، نه شکست:** `with_actual_quantity = 0` تا وقتی برنامه‌ریز پیشرفت مصالح وارد
نکرده، و `unclassified > 0` برای منابع WORK.

---

## فاز F — provider مالی

میزبان را با هر دو DSN روی `bambo_canonical_local` اجرا کنید و بررسی کنید که feed این‌ها
را می‌دهد:

```
assignmentExternalId · resourceExternalId · resourceName · resourceType · unit
plannedQuantity · actualQuantity · remainingQuantity
task.wbsCode · task.activityCode
```

آداپتور خودش تشخیص می‌دهد: هر دو جدول موجود → feed واقعی · هیچ‌کدام → بازگشت به سطح
فعالیت · **فقط یکی → `CoreSchemaMismatch` و توقف صریح**.

---

## فاز G — گزارش مالی

```
GET /reports/live            بدون ۵۰۰
GET /overview                بدون ۵۰۰
GET /reports/live/by-wbs     سطح ۱ و سپس parentWbsCode
```

بررسی کنید:

- هیچ مقداری ساخته نشده باشد — خط بدون مقدار باید `unavailable` بماند، نه صفر
- خط‌های MATERIAL به فعالیت و WBS درست وصل شده باشند
- منابع WORK طبقه‌بندی‌نشده دیده شوند، نه اینکه در labor یا equipment ناپدید شوند
- در `by-wbs`: جمع گره‌های ریشه + `unattributedActualIrr` + `unmappedWbsActualIrr` دقیقاً
  برابر `totals.actualCostIrr` باشد

---

## فاز H — GO / NO-GO

**GO** فقط اگر همهٔ فازهای A تا G سبز باشند.

**NO-GO:** بایستید. **بارگذاری انبوه نکنید.** اگر schema باید برگردد:

```bash
psql -f backend/docs/sql/msp_resource_assignment_rollback.sql
```

اگر جدول‌ها ردیف دارند، با شمارش ردیف‌ها امتناع می‌کند. برای حذف واقعاً مخرب:

```bash
psql -v allow_data_loss=yes -f backend/docs/sql/msp_resource_assignment_rollback.sql
```

دو عمل آگاهانه، نه یکی. هیچ جدول Core دیگری لمس نمی‌شود.

---

## چیزی که این runbook حل نمی‌کند

**پایداری UID بین نسخه‌ها اثبات نشده.** فقط یک نسخه از پروژهٔ پل وجود دارد. روی یک
زمان‌بندی دیگر ثابت شد که `Task UID` بین دو ذخیره پایدار می‌ماند و `GUID` کاملاً بازتولید
می‌شود — به همین دلیل هیچ‌جا GUID کلید نیست و هیچ قید یکتای بین‌snapshotی ساخته نشده.

نتیجهٔ عملی: اگر UIDها روزی جابه‌جا شوند، ردیف‌ها «بدون تطابق» می‌شوند — دیدنی — نه
داده‌ای که بی‌صدا اشتباه به هم وصل شده باشد. برای بستن کامل این مسئله، دو نسخهٔ پیاپی از
یک پروژه با یک ویرایش واقعی بینشان لازم است.
