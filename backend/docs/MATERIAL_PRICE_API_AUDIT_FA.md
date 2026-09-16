# ممیزی APIهای قیمت مصالح — پس از ۰۰۲۷ / ۰۰۲۸ / ۰۰۲۹

تاریخ: ۱۴۰۵/۰۶/۲۵ (۲۰۲۶-۰۹-۱۶) · شاخه: `harden/material-price-db-ops-scripts`
پایگاه دادهٔ آزموده‌شده: `bambo_canonical_test` · Alembic head: `0029`

---

## ۱. فهرست Endpointها

| Method | Endpoint | Permission | Service | Repository query | جدول‌های اصلی | صفحه‌بندی | وضعیت |
|---|---|---|---|---|---|---|---|
| GET | `/material-prices/categories` | `finance.view` | `categories` | `categories` | `provider_items` | ندارد | سالم |
| GET | `/material-prices/current` | `finance.view` | `current` | `latest_observations` + `unit_settings` + `labels` + `item_unit_factors` | `price_observations`, `provider_items`, `price_providers` | دارد (در حافظه) | **اصلاح شد** |
| GET | `/material-prices/{id}/history` | `finance.view` | `history` | `observation_history` | `price_observations` ⟕ `provider_items` ⟕ `price_providers` | دارد (SQL) | **اصلاح شد** |
| GET | `/material-prices/runs` | `finance.view` | `runs` | `runs_page` | `price_collection_runs` | دارد (SQL) | سالم |
| GET | `/material-prices/invalid-rows` | `finance.view` | `invalid_rows` | `invalid_observations_page` | `price_observations` ⟕ `provider_items` ⟕ `price_providers` | دارد (SQL) | **اصلاح شد** |
| GET | `/material-prices/unresolved` | `finance.view` | `unresolved` | `unresolved_items` | `provider_items` ⟕ `provider_item_labels` | دارد (SQL) | سالم |
| GET | `/material-prices/unit-settings` | `finance.view` | `unit_settings` | `unit_settings` | `material_unit_settings` | ندارد | سالم |
| POST | `/material-prices/unit-settings` | `finance.edit` | `set_unit` | `append_unit_setting` | `material_unit_settings` | — | سالم (append-only) |
| GET | `/material-prices/labels` | `finance.view` | `labels` | `labels` | `provider_item_labels` ⨝ `finance_resources` | ندارد | سالم |
| GET | `/material-prices/{id}/labels` | `finance.view` | `label_history` | `label_history` | `provider_item_labels` | ندارد | سالم |
| POST | `/material-prices/{id}/labels` | `finance.edit` | `save_label` | `append_label` | `provider_item_labels` | — | سالم (append-only) |
| GET | `/material-prices/{id}/factors` | `finance.view` | — (repository مستقیم) | `item_unit_factors` | `provider_item_unit_factors` | ندارد | سالم |
| POST | `/material-prices/{id}/factors` | `finance.edit` | `save_item_factor` | `append_item_factor` | `provider_item_unit_factors` | — | سالم (append-only) |

**چرا `current` در حافظه صفحه‌بندی می‌شود:** وضعیت هر ردیف به تنظیمات واحد و ضریب‌های
در دسترسِ همان ردیف وابسته است، پس یک صفحهٔ SQL صفحه‌ای از ردیف‌هایی می‌شد که وضعیتشان
هنوز معلوم نیست. جمعیت، فهرست‌های یک پروژه است — صدها، نه میلیون‌ها.

---

## ۲. نقص‌هایی که پیدا و اصلاح شد

### ۲.۱ ۲۹ فیلد اعلام‌شده که هرگز پر نمی‌شدند

`MaterialPriceResponse` این‌ها را اعلام می‌کرد، OpenAPI منتشرشان می‌کرد، پایگاه داده
داشتشان — و `_shape` در میانه رهایشان می‌کرد. نتیجه: **همیشه null**.

* هر ۲۳ ستون مشخصاتِ تایپ‌شده که ۰۰۲۷ اضافه کرد (`weightValue`، `weightBasis`،
  `manufacturer`، `lengthM`، …) به‌علاوهٔ `specSource` و `specConflicts`
* هر سه Snapshot: `productIdSnapshot`، `productNameSnapshot`، `providerNameSnapshot`
* `labelledByName` — که **Frontend می‌خواندش** و روی هر ردیف خالی رندر می‌شد

`productIdSnapshot` جداگانه خراب بود: Router آن را از کلیدی می‌ساخت
(`product_external_id`) که Service اصلاً در ردیف نمی‌گذاشت.

روی دادهٔ واقعی پس از اصلاح (۴۰۰ ردیف terrace): `weightValue` روی ۵۸، `specSource` روی
۹۴، `productCode` روی ۱۵، `manufacturer` روی ۶ ردیف مقدار دارد.

### ۲.۲ تاریخِ ناخوانا به‌عنوان «معتبر» پذیرفته می‌شد

سلولی که چیزی گفته بود ولی تاریخ نبود — «۱۴۰۵/۱۳/۴۰»، «فردا»، «۱۴۰۵-۰۷-۳۱» (مهر ۳۰ روز
دارد)، «۱۴۰۵-۱۲-۳۰» (۱۴۰۵ کبیسه نیست) — **پذیرفته** می‌شد و با
`validation_status = 'valid'` و `workflow_date_gregorian = NULL` ذخیره می‌شد.

از ۰۰۲۷ به بعد قید `price_observations_valid_row_has_business_date` دقیقاً همین ردیف را
رد می‌کند. یعنی **یک سلول خرابِ یک شیت دوهزارتایی کل Import را ساقط می‌کرد**، نه یک ردیف
را. حالا ردیف رد می‌شود، متن خام به‌عنوان شاهد می‌ماند، دلیل نامش را می‌برد و روی
`/invalid-rows` پیدا می‌شود. آنچه هرگز نباید بشود — و نشده — جایگزینی با `fetched_at` یا
«امروز» است.

### ۲.۳ نگهبانی که نقصی را که برای آن نوشته شده بود رد می‌کرد

`test_every_actor_column_the_api_exposes_is_covered` یک فهرست دست‌نویس را pin می‌کرد، پس
فقط وقتی می‌شکست که کسی **همان فهرست** را ویرایش کند — و نقصی که برای گرفتنش نوشته شده
بود این است که کسی فیلد نام اضافه کند و فهرست را ویرایش **نکند**. حالا جفت‌ها از روی
Schemaها استخراج می‌شوند و آنچه pin شده «طبقه‌بندی» است نه «فهرست». با برداشتن موقت
جفتِ `labelled_by` ثابت شد که تست حالا می‌شکند.

### ۲.۴ اعلام دوگانهٔ سه فیلد تاریخ

`workflow_date_jalali` و `workflow_date_gregorian` دو بار در `MaterialPriceResponse`
اعلام شده بودند؛ کپی اول مستندات را داشت و کپی دوم — بی‌صدا — تعریف را. Python دومی را
نگه می‌دارد، پس هر توضیحی که بالای کپی اول نوشته شده بود به اعلامی چسبیده بود که دیگر
وجود نداشت. یکی شد. تعداد فیلدهای منتشرشده تغییر نکرد (۷۵ = ۷۵).

### ۲.۵ سه نسخه از یک فهرست ستون

`SPEC_COLUMNS` در سه فایل تکرار شده بود، زیر توضیحی که می‌گفت «یک بار نام‌گذاری شده تا
ستون تازه نیمه‌سیم‌کشی نشود». حالا واقعاً یک بار در `domain/material_specs.py` است و
Repository، Importer و اسکریپت Backfill همان را import می‌کنند.

---

## ۳. فیلدهای تازه

| فیلد | Endpoint | معنا |
|---|---|---|
| `conversionEligible` | `current` | `null` = چیزی برای تبدیل نیست · `true` = رجیستری پل می‌زند یا کسی این محصول را اندازه گرفته · `false` = تبدیل باید به وزنی تکیه کند که **پایه‌اش را کسی اعلام نکرده** |
| `productExternalId` | `history` | شناسه، همان‌طور که وارد شد |
| `productNameSnapshot` | `history` | نام محصول در **روز مشاهده** |
| `providerNameSnapshot` | `history` | نام تأمین‌کننده در روز مشاهده |
| `currentProductName` | `history` | نام **امروزِ** همان فهرست — فیلد جدا، هرگز ادغام‌نشده |
| `currentProviderName` | `history` | نام امروز تأمین‌کننده |
| `rowFingerprint` | `history` | `(productId، تاریخ ورک‌فلو، قیمت)` هش‌شده |
| `collectionRunId` | `history` | کدام Import این ردیف را خواند |
| `providerItemId` | `history` | کدام فهرست |

**چرا دو نامِ جدا:** تاریخچه‌ای که نام امروز را کنار قیمت پارسال نشان دهد، ادعا می‌کند
محصول آن روز همین نام را داشت. شاید نداشت. خواننده باید بتواند تغییر نام را **ببیند**.

`conversionEligible` مشتق است و هیچ‌جا ذخیره نمی‌شود: حکمی دربارهٔ آنچه امروز مجاز است،
نه واقعیتی دربارهٔ مشاهده. لحظه‌ای که کسی اندازه‌ای ثبت کند تغییر می‌کند.

**چرا `weightBasis = 'unknown'` مانع می‌شود:** هیچ شیتی نمی‌گوید وزن **به‌ازای چه** است.
پس ۲۷ می‌تواند ۲۷ به‌ازای شاخه، متر یا عدد باشد — و این‌ها بیش از یک مرتبهٔ بزرگی فرق
دارند. در پایگاه دادهٔ آزموده‌شده، هر ۴۱۵ فهرستی که وزن دارند `unknown` هستند.

---

## ۴. تأیید روی API زندهٔ متصل به `bambo_canonical_test`

۳۵ سناریو، **۳۵ قبول، ۰ رد**. از جمله:

* `current` روی ۱۷۳۵ ردیف فعال، `categories` روی ۸ دسته
* دو صفحهٔ متوالی هیچ ردیف مشترکی ندارند (۱۰۰ شناسه، ۱۰۰ یکتا)
* هیچ Snapshot‌ای از نام فعلی پر نشده (۰ ردیف مشکوک)
* هیچ مشخصهٔ غایبی به `0`، `""`، `"-"` یا `"unknown"` تبدیل نشده
* هیچ ردیف ردشده‌ای قیمت جاری ندارد
* بدون `finance.view` → ۴۰۳ · پروژهٔ دیگر → ۴۰۳ · `pageSize=9999` → ۴۲۲
* `contracts/openapi.json` با آنچه اپلیکیشن سرو می‌کند یکی است (۷۵ property)

Invariantهای مالی: **۲۲ از ۲۲ قبول، ۰ رد**.
تست‌ها: **۱۸۳۰ قبول، ۰ رد** (روی مفسر canonical با JRE، پس تست‌های MPXJ واقعاً اجرا شدند).

---

## ۵. یافتهٔ خارج از دامنه — اصلاح نشد

`DailyEstimateResponse` (مسیر «برآورد روزانه»، نه قیمت مصالح) **۹ فیلد اعلام‌شده دارد که
هیچ‌چیز پرشان نمی‌کند**: `quantitySource`، `dailyQuantitySource`،
`dailyQuantitySourceField`، `dailyQuantityAsOf`، `resourceId`، `resourceName`،
`resourceUnitSource`، `resourceUnitConfidence`، `conversionIssueId`.

همان جنس نقص بند ۲.۱ است. اصلاح نشد چون:

* این Endpoint از ۰۰۲۷ متأثر نیست و در دامنهٔ این مأموریت نبود
* برای شش‌تای اول داده **وجود دارد** و فقط منتقل نمی‌شود (اصلاح ساده است)
* اما برای `resourceUnitSource` و `resourceUnitConfidence` **هیچ داده‌ای در هیچ لایه‌ای
  وجود ندارد** — مفهومش ساخته نشده. پر کردنشان یعنی ساختن عدد، و حذفشان یعنی تغییر
  قرارداد منتشرشده. هیچ‌کدام تصمیمی نیست که وسط یک ممیزی دیگر گرفته شود.
* `conversionIssueId` روی پاسخ **بیرونی** (`ConvertedPricePreviewResponse`) پر می‌شود؛
  اعلام دومش روی `DailyEstimateResponse` تکراری و همیشه null است.

هیچ فایل Frontend هیچ‌کدام از این نه فیلد را نمی‌خواند.

---

## ۶. مسدودکنندهٔ پابرجا

۱۱ از ۱۳ متد Adapter قیمت مصالح هیچ فراخوانی از UI ندارند. ۱٬۴۲۴ فهرست از ۱٬۷۳۵ روی
`/unresolved` هستند — یعنی کسی هنوز نگفته هرکدام چه چیزی است. این یک نقص Backend نیست و
با این تغییرها حل نمی‌شود.
