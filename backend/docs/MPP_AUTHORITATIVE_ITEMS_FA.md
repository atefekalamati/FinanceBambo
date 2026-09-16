# مدل MPP-محور برای «اقلام و برآوردها»

تاریخ: ۱۴۰۵/۰۶/۲۵ (۲۰۲۶-۰۹-۱۶) · شاخه: `harden/material-price-db-ops-scripts`
پایگاه دادهٔ آزموده‌شده: `bambo_canonical_test` · Alembic: `0029` → `0030`

---

## ۱. تصمیم

فایل Microsoft Project مرجعِ **چه چیزی وجود دارد** است: منابع، نام‌ها، هویت‌ها، تخصیص‌ها،
فعالیت‌ها، مقادیر و هزینه‌های اصلی. Finance آن را طبقه‌بندی، نگاشت، تبدیل و محاسبه می‌کند
و **قلم مستقلی کنار آن نمی‌سازد**.

```
منبع MPP (یک source_resource_uid)
  └── تخصیص (یک source_assignment_uid، در یک فعالیت)
        └── برآورد اینجا محاسبه می‌شود — و فقط اینجا
```

جمعِ منبع = جمع تخصیص‌هایش. جمعِ پروژه = جمع همان تخصیص‌ها، **نه** جمع جمع‌های منبع.

---

## ۲. سطح نوشتن API

| Method | Endpoint | کار | Permission | قلم پروژه می‌سازد؟ |
|---|---|---|---|---|
| POST | `/resources` | — | `finance.edit` | **مسدود شد** → ۴۰۹ `MPP_RESOURCE_REQUIRED` |
| POST | `/estimate-lines` | سطر برآورد | `finance.edit` | **مشروط**: فقط روی منبعی که `source_resource_uid` دارد |
| PATCH | `/resources/{id}` | طبقه‌بندی منبع موجود | `finance.edit` | نه — ویرایش، نه ساخت |
| POST | `/estimate-lines/{id}/revisions` | بازنگری مقدار | `finance.edit` | نه |
| POST | `/estimate-lines/{id}/price-mapping` | نگاشت به قیمت روز | `finance.edit` | نه |
| POST | `/estimate-lines/{id}/price-mapping/components` | جزء نگاشت | `finance.edit` | نه |
| POST | `/material-prices/unit-settings` | واحد نمایش دسته | `finance.edit` | نه — کاتالوگ بازار |
| POST | `/material-prices/{id}/labels` | برچسب فهرست بازار | `finance.edit` | نه — کاتالوگ بازار |
| POST | `/material-prices/{id}/factors` | ضریب اندازه‌گیری‌شده | `finance.edit` | نه — کاتالوگ بازار |
| POST | `/invoices`، `/invoices/{id}/lines` | فاکتور | `finance.manage_invoice` | نه |
| POST | `/activities` | فعالیت (به host واگذار) | `finance.edit` | نه — فعالیت قلم مالی نیست |
| GET | `/items-and-estimates` | **جدید** — سلسله‌مراتب منبع ← تخصیص | `finance.view` | نه — فقط خواندن |

**چرا `POST /resources` کاملاً مسدود شد و `POST /estimate-lines` مشروط:** ردیفی که
`create_resource` می‌نوشت **هرگز** ستونی برای `source_resource_uid` نداشت، پس هر منبعی که
می‌ساخت بی‌منشأ بود. اما `create_estimate_line` می‌تواند روی منبعی بنشیند که Importer
ساخته — و آن سطر کاملاً مشروع است. دروازه، `source_resource_uid` خودِ منبع است نه ادعای
درخواست: فراخوان نمی‌تواند منشأیی را اعلام کند که ندارد.

**مسیر Import دست‌نخورده است.** `coreint/finance_mpp_mapping.py` منابع و سطرها را با UID
از طریق دستور خودش می‌نویسد و هرگز این Service را صدا نمی‌زند.

---

## ۳. معنای عدد «Units»

| نوع منبع در فایل | واحد تبدیل‌شده | معنا | قابل قیمت‌گذاری؟ |
|---|---|---|---|
| `MATERIAL` | دارد (`m3`، `m2`، …) | `physical_quantity` | بله |
| `MATERIAL` | ندارد (`not_a_unit`) | `unknown` | **نه** — `unknown_assignment_semantics` |
| `WORK` | — | `allocation_percentage` | **نه** — `allocation_percentage_not_quantity` |

MPXJ تخصیص ۱۰۰٪ را `1.0` گزارش می‌کند. ضرب ۱.۰ در «قیمت هر مترمکعب» عددی تولید می‌کند
که خطای کوچکی نیست و دیده هم نمی‌شود: شبیه یک بیل مکانیکی ارزان است.

`Quantity ≠ Daily Quantity ≠ احجام` — هیچ‌کدام fallback دیگری نیست و این ماژول هیچ‌یک از
آن ستون‌ها را نمی‌خواند.

---

## ۴. «کانال کنی» (task uid 1219) — دادهٔ واقعی

| Resource UID | Assignment UID | نام | نوع فایل | Units خام | معنا | مقدار فیزیکی | درصد | هزینهٔ اصلی (ریال) | وضعیت |
|---|---|---|---|---|---|---|---|---|---|
| 152 | 9447 | کانال کنی | MATERIAL | 7516.4 | `physical_quantity` | 7516.4 m3 | — | 15,234,765,668 | `missing_price` |
| 134 | 9459 | بسترکوبی | MATERIAL | 3956.0 | `physical_quantity` | 3956.0 m2 | — | 197,800,000 | `missing_price` |
| 158 | 9816 | بیل مکانیکی | WORK | 1.0 | `allocation_percentage` | **null** | ۱۰۰٪ | 0 | `allocation_percentage_not_quantity` |
| 171 | 9817 | کامیون | WORK | 1.0 | `allocation_percentage` | **null** | ۱۰۰٪ | 0 | `allocation_percentage_not_quantity` |

هر چهار تخصیص به همان task باقی ماندند و هیچ قلم اضافه‌ای ساخته نشد.

---

## ۵. وضعیت واقعی پروژه terrace

نسخهٔ زنده: `b889bc98` (`test_progress.mpp`، ۲۰۲۶-۰۹-۱۴، ۷۸۹ سطر)

* ۸۰ گروه منبع · ۷۲۷ تخصیص
* **۰ قابل محاسبه، ۷۲۷ کنار گذاشته‌شده** → جمع پروژه `null`
* دلایل: `allocation_percentage_not_quantity` ۴۲۶ · `missing_price` ۲۸۳ ·
  `unknown_assignment_semantics` ۱۸

**چرا هیچ‌چیز قیمت نخورد و چرا این درست است:** تنها نگاشت زندهٔ دارای
`source_assignment_uid` روی تخصیص ۹۷۰۲ «تجهیز اولیه» است — منبعی `MATERIAL` که واحدش
تبدیل نشده. ۱.۰ «تجهیز اولیه» مقداری نیست که بتوان در قیمت میلگرد ضرب کرد، و سیستم با
`unknown_assignment_semantics` آن را رد می‌کند. خودِ آن نگاشت هم جای بازبینی دارد.

مسیر محاسبه با Fixture کنترل‌شده اثبات شده است (۳۴ تست)، نه با دادهٔ واقعی — چون دادهٔ
واقعی هنوز هیچ تخصیص قابل قیمت‌گذاری ندارد.

---

## ۶. ردیف‌های بی‌منشأ

۱۲۰ سطر از ۸۳۵ نه `source_assignment_uid` دارند و نه `source_task_uid`، و هر ۱۲۰ روی
منابعی نشسته‌اند که `source_resource_uid` ندارند. سهمشان از برآورد اولیه:

```
MPP-derived      ۷۱۵ سطر     ۳٬۶۰۵٬۸۲۳٬۹۶۷٬۷۷۶ ریال
بی‌منشأ          ۱۲۰ سطر         ۱٬۶۱۵٬۰۰۰٬۰۰۰ ریال   ← از این پس شمرده نمی‌شود
```

۰٫۰۴۵٪ از عدد گزارش‌شده. کوچک، ولی عددی که هیچ فایلی نمی‌تواند توضیحش دهد.

**هیچ‌کدام حذف یا غیرفعال نشد.** با `legacy_status='legacy_unlinked'` علامت خوردند، در
`legacyLines` فهرست می‌شوند و از هر جمعی کنار گذاشته شده‌اند. دوتای‌شان
(`00dcc20e…` «برآورد مصالح مورد نياز» و `065b648f…` «بتن ريزي سقف») توسط سطر فاکتور
ارجاع داده می‌شوند و زنده و کامل باقی ماندند.

هیچ هویتی ساخته نشد و هیچ ردیفی با نام تطبیق داده نشد.

---

## ۷. فرمول‌ها

```
convertedUnitPrice        = قیمت روز، تبدیل‌شده به واحد تخصیص
                            (فقط وقتی conversion_status ∈ {automatic, factor})
assignmentCurrentEstimate = assignmentQuantity × convertedUnitPrice
resourceCurrentEstimate   = Σ assignmentCurrentEstimate همان منبع
projectCurrentEstimate    = Σ assignmentCurrentEstimate همهٔ تخصیص‌های واجد شرایط
```

هر ورودیِ غایب ⇒ `null` و نه صفر. مقدار **صفر** باقی می‌ماند و `calculated` است: «صفر
عدد» با «نمی‌دانیم» یکی نیست.

`totalAssignmentQuantity` فقط وقتی داده می‌شود که همهٔ تخصیص‌ها مقدار فیزیکی در **یک**
واحد باشند. چهار مترمکعب به‌علاوهٔ چهار مترمربع، هشتِ هیچ‌چیز است.

---

## ۸. مهاجرت ۰۰۳۰

سه CHECK روی `estimate_lines` و یک ستون `legacy_status`. سومی
(`estimate_lines_state_their_provenance`) ردیف بی‌منشأ بعدی را در خود پایگاه داده متوقف
می‌کند — با یک INSERT آزمایشی ثابت شد. چرخهٔ upgrade → downgrade → upgrade اجرا شد،
۸۳۵ سطر در هر سه مرحله، یک head.

---

## ۹. آنچه هنوز باقی است

* **۷۲۷ از ۷۲۷ تخصیص قابل محاسبه نیست.** ۴۲۶ تای آن ذاتی است (تخصیص درصدی مبنای مالی
  تأییدشده ندارد) و ۲۸۳ تا منتظر نگاشت قیمت روز است. این یک نقص نیست؛ کاری است که هنوز
  انجام نشده.
* **۴ نگاشت از ۵ نگاشت موجود `source_assignment_uid` ندارند** و فقط با `estimate_line_id`
  شناخته می‌شوند، پس در این نما دیده نمی‌شوند. نگاشت‌های تاریخی‌اند و دست نخوردند.
* ۱۸ تخصیص `MATERIAL` با واحد تبدیل‌نشده، منتظر تصمیم انسانی دربارهٔ واحدشان.
