# پیاده‌سازی نگهداشت منابع و تخصیص‌ها در Parser — مشخصات دقیق

**برای تیم Core/Planning.** ماژول مالی فایل MPP را تجزیه نمی‌کند و نخواهد کرد. این سند
دقیقاً می‌گوید parser موجود چه چیزی را باید بخواند و کجا بنویسد.

> **وضعیت parser:** روی این ماشین پیدا نشد. کل `E:\bamboo` و آرشیو استقرار
> `bambo-platform` جست‌وجو شد — صفر تطابق برای `msp_tasks`، `mpxj`، `MPPReader` یا
> `Aspose.Tasks`. پس هیچ patch کدی نوشته نشد و **هیچ parser دومی ساخته نشد**. این سند
> جای آن patch را می‌گیرد.

---

## آنچه اثبات شده

همه از خواندن فایل واقعی با MPXJ، نه از مستندات:

```
فایل      زمان بندی پل.mpp  ·  پروژه تقاطع غير همسطح شاهنامه
منابع     ۸۱   (MATERIAL=۶۲ · WORK=۱۹ · COST=۰)
تخصیص‌ها  ۷۲۷  (۷۱۵ متصل به منبع · ۱۲ بدون منبع)
مقدار     ۲۸۹ تخصیص مقدار فیزیکی دارند
alias     هیچ فیلد سفارشی نام‌گذاری‌شده‌ای در کل فایل نیست
```

**ستون «Quantity» که در Resource Sheet دیده می‌شود، فیلد سفارشی نیست.** برای منبع نوع
`MATERIAL`، خودِ MS Project مصرف را در `Work` نگه می‌دارد و MPXJ همان را با نام `Material`
هم عرضه می‌کند — همیشه دقیقاً برابر. `NumberN`ها همه صفرند.

---

## نگاشت منابع

```java
for (Resource r : project.getResources()) {
    if (r.getName() == null) continue;          // ردیف صفر MSP، منبع واقعی نیست

    row.snapshot_id            = snapshotId;
    row.resource_uid           = r.getUniqueID();          // هویت. NOT NULL
    row.resource_guid          = str(r.getGUID());         // فقط تشخیصی — پایین را بخوانید
    row.resource_name          = r.getName();
    row.native_type            = r.getType().name();       // WORK | MATERIAL | COST

    row.resource_quantity      = r.getMaterial();          // ستون Quantity
    row.resource_quantity_unit = unitOf(r);
    row.quantity_unit_source   = unitSourceOf(r);

    row.initials               = r.getInitials();
    row.material_label         = r.getMaterialLabel();
    row.resource_group         = r.getGroup();
    row.code                   = r.getCode();
    row.max_units              = r.getMaxUnits();

    row.standard_rate          = rateAmount(r.getStandardRate());
    row.overtime_rate          = rateAmount(r.getOvertimeRate());
    row.cost_per_use           = r.getCostPerUse();

    row.work                   = hours(r.getWork());
    row.actual_work            = hours(r.getActualWork());
    row.remaining_work         = hours(r.getRemainingWork());

    row.source_cost            = r.getCost();
    row.source_actual_cost     = r.getActualCost();
    row.source_remaining_cost  = r.getRemainingCost();

    row.raw_fields_json        = populatedFields(r);
    row.bambo_resource_type    = classify(r);              // پایین
}
```

### واحد — و چرا دو ستون دارد

```java
String unitOf(Resource r) {
    if (notBlank(r.getMaterialLabel())) return r.getMaterialLabel();
    if (r.getType() == ResourceType.MATERIAL && notBlank(r.getInitials()))
        return r.getInitials();
    return null;                                  // هرگز حدس نزنید
}

String unitSourceOf(Resource r) {
    if (notBlank(r.getMaterialLabel())) return "material_label";
    if (r.getType() == ResourceType.MATERIAL && notBlank(r.getInitials()))
        return "initials";
    return null;
}
```

`Material Label` جای رسمی واحد در MS Project است. در این فایل **هر ۸۱ منبع خالی‌اش
گذاشته‌اند** و واحد را در `Initials` نوشته‌اند: آرماتور → کیلوگرم، بتن → مترمکعب،
قالب‌بندی → مترمربع.

**این قرارداد یک برنامه‌ریز است، نه استاندارد.** `quantity_unit_source` ذخیره می‌شود تا
فایل بعدی که `Material Label` را درست پر کند، بی‌صدا تفسیر نشود.

توجه: برای منبع `WORK`، `Initials` حرف اول نام است (رفتار پیش‌فرض MSP)، نه واحد. به همین
دلیل `unitOf` آن را فقط برای `MATERIAL` می‌پذیرد.

### طبقه‌بندی

```java
String classify(Resource r) {
    switch (r.getType()) {
        case MATERIAL: return "material";
        case COST:     return "general_cost";
        case WORK:     return null;         // ← عمدی
    }
}
```

MSP تفکیک labor از equipment ندارد. در این فایل هر ۱۸ منبع WORK: `Code = null`،
`Group = "1"`. **هرگز از نام منبع استنتاج نکنید** — «جرثقیل ۳۰ تن» با heuristic نامی به
نیروی انسانی تبدیل می‌شود و هیچ خطایی نمی‌دهد.

اگر بعداً قرارداد صریحی روی `Code` یا `Group` توافق شد، همین‌جا اضافه شود.

---

## نگاشت تخصیص‌ها

```java
for (ResourceAssignment a : project.getResourceAssignments()) {
    row.snapshot_id       = snapshotId;
    row.assignment_uid    = a.getUniqueID();       // NOT NULL
    row.task_uid          = a.getTaskUniqueID();   // NOT NULL
    row.resource_uid      = a.getResourceUniqueID();  // NULL مجاز — ۱۲ از ۷۲۷

    row.units             = a.getUnits();

    row.planned_work      = hours(a.getWork());
    row.actual_work       = hours(a.getActualWork());
    row.remaining_work    = hours(a.getRemainingWork());

    row.planned_quantity   = a.getPlannedMaterial()   != null
                           ? a.getPlannedMaterial()   : a.getMaterial();
    row.actual_quantity    = a.getActualMaterial();
    row.remaining_quantity = a.getRemainingMaterial();
    row.quantity_unit      = resourceUnitFor(a.getResourceUniqueID());

    row.assignment_work_complete_percent = a.getPercentageWorkComplete();

    row.source_cost           = a.getCost();
    row.source_actual_cost    = a.getActualCost();
    row.source_remaining_cost = a.getRemainingCost();

    row.raw_fields_json = populatedFields(a);
}
```

### چهار قاعده که نباید شکسته شوند

**۱. مقدار فیزیکی هرگز ساخته نمی‌شود.** نه از `Work`، نه از `Duration`، نه از
`PercentComplete`، نه از `Units`، نه از `MaxUnits`. `Work` ساعت است؛ `Units` درصد ظرفیت
است. اگر MPXJ مقدار نداد، ستون `NULL` می‌ماند.

**۲. `NULL` با `0` یکی نیست.** در این فایل `ActualMaterial` روی هر ۷۲۷ تخصیص صفر است، یعنی
برنامه‌ریز پیشرفت مصالح وارد نکرده. آن باید `NULL` نوشته شود، نه `0` — مالی «صفر
اندازه‌گیری‌شده» را از «اندازه‌گیری غایب» جدا می‌کند و این تفکیک اینجا از بین می‌رود.

**۳. مقدار بدون واحد پذیرفته نمی‌شود.** دیتابیس با یک `CHECK` جلویش را می‌گیرد. اگر منبع
واحد ندارد، مقدار را هم ننویسید — عددی که کسی نمی‌تواند بخواند بدتر از نبودنش است.

**۴. تخصیص بدون منبع حذف نمی‌شود.** `resource_uid = NULL` بنویسید. ۱۲ ردیف در این فایل.

---

## هویت — و چرا GUID نه

دو نسخهٔ ذخیره‌شده از یک زمان‌بندی واقعی مقایسه شد:

```
نام فعالیت‌ها   ۹۱۸/۹۱۸ یکسان
کد WBS         ۱۲۴۸/۱۲۴۸ یکسان
Task UID       ۱۲۴۸/۱۲۴۸ یکسان      ← پایدار
Task GUID      ۰/۱۲۴۸ یکسان         ← کاملاً بازتولید شده
```

**صرفِ ذخیرهٔ فایل تحت نام تازه، همهٔ GUIDها را باطل می‌کند** — بدون هیچ تغییر محتوایی.

پس: `resource_uid` و `assignment_uid` هویت‌اند. `resource_guid` فقط برای تشخیص ذخیره
می‌شود و **در هیچ کلید، قید یا join استفاده نمی‌شود**.

هیچ قید یکتای بین‌snapshotی ساخته نشده. اگر UIDها روزی بین نسخه‌ها جابه‌جا شوند، نتیجه
ردیف‌های «بدون تطابق» است — دیدنی — نه داده‌ای که بی‌صدا به هم وصل شده باشد.

---

## تراکنش

```
BEGIN
  1. msp_snapshots        (جریان موجود)
  2. msp_tasks            (جریان موجود)
  3. msp_resources        ← تازه، پیش از تخصیص‌ها (کلید خارجی به آن اشاره دارد)
  4. msp_resource_assignments
COMMIT
```

**هر چهار مرحله در یک تراکنش.** اگر مرحلهٔ ۳ یا ۴ شکست بخورد، snapshot نباید منتشر شده
باشد: یک snapshot با فعالیت‌ها ولی بدون مقدار، از هیچ snapshot بدتر است — کامل به نظر
می‌رسد و مالی روی آن گزارش می‌سازد.

**شکست:** کل تراکنش برگردد. هیچ نگهداشت جزئی.
**تلاش دوباره:** کل import از نو. بدون upsert جزئی — `UNIQUE (snapshot_id, resource_uid)`
تلاش دوم روی همان snapshot را رد می‌کند، که درست است: هر بارگذاری snapshot تازه‌ای است.

---

## آنچه مالی با این داده می‌کند — و نمی‌کند

```
planned_quantity  → مقدار برآورد، فقط با پذیرش صریح
                    original_quantity پس از آن تغییرناپذیر است؛ تغییر بعدی = بازنگری
actual_quantity   → پیشرفت واقعی، وقتی وجود داشته باشد
standard_rate     → مرجع. قیمت معتبر مالی price_versions است
source_actual_cost→ مقایسه. هزینهٔ واقعی معتبر، فاکتور تأییدشده است
resource_quantity → نمایش و ممیزی. مالی آن را بین فعالیت‌ها توزیع نمی‌کند
```

آخری مهم است: مقدار سطح منبع **جمعِ** مقادیر تخصیص است (روی ۱۰ منبع آزموده شد، تطابق
کامل). اگر روزی فقط مقدار سطح منبع موجود باشد، مالی `plannedQuantity` را `NULL` می‌گذارد و
سهم محاسبه نمی‌کند.
