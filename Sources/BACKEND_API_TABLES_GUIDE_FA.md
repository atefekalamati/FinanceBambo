# راهنمای بک‌اند: هر بخش UI با کدام API و کدام جدول کار می‌کند

سند دریافتی از تیم بک‌اند. متن زیر تا انتهای بخش «جمع‌بندی بک‌اند» عیناً همان چیزی است
که فرستاده‌اند. بررسی و تطبیق با کد، جداگانه در انتهای فایل آمده است.

---

## ۱. نگاشت کلی UI ← API ← جدول

| بخش UI | API | جدول‌های اصلی | ستون‌های کلیدی |
|---|---|---|---|
| اقلام و برآورد MSP | `GET /estimate-lines` | `estimate_lines` | `id`, `resource_id`, `activity_external_id`, `assignment_external_id`, `original_quantity`, `original_unit_price_irr`, `source_assignment_uid`, `source_task_uid` |
| مشخصات قلم هزینه | `GET /resources` | `finance_resources` | `id`, `title`, `code`, `resource_type`, `base_unit`, `dimension`, `source_resource_uid` |
| عنوان فعالیت و WBS | `GET /activities` | host/Core activity provider | `activityExternalId`, `title`, `wbsCode`, `mppTaskCostIrr` |
| قیمت روز رسمی داخلی | `GET /prices/current` | `price_versions`, `finance_resources` | `resource_id`, `unit_price_irr`, `effective_from`, `scope_kind`, `version` |
| واحدهای مجاز | `GET /unit-registry` | جدول ندارد — از `UNIT_REGISTRY` در بک‌اند | — |
| قیمت‌های روز مصالح | `GET /material-prices/current` | `provider_items`, `price_observations`, `price_providers` | `external_name`, `external_id`, `category`, `metadata`, `normalized_price_irr`, `workflow_date_jalali`, `provider_name` |
| دسته‌های مصالح و ستون‌های اختصاصی | `GET /material-prices/categories` | `provider_items` | `category`, `active`، count‌ها؛ ستون‌ها از schema بک‌اند ساخته می‌شود |
| تاریخچهٔ قیمت یک محصول بازار | `GET /material-prices/{providerItemId}/history` | `price_observations` | `provider_item_id`, `raw_price`, `normalized_price_irr`, `workflow_date_*`, `validation_status` |
| اجرای import قیمت‌ها | `GET /material-prices/runs` | `price_collection_runs` | `status`, `started_at`, `finished_at`, `total_items`, `successful_items`, `worksheet_report` |
| ردیف‌های نامعتبر قیمت | `GET /material-prices/invalid-rows` | `price_observations` | `validation_status`, `validation_reasons`, `raw_data`, `source_row_number` |
| برچسب/نوع محصول بازار | `GET/POST /material-prices/{providerItemId}/labels` | `provider_item_labels` | `label`, `display_name`, `product_type`, `source_unit`, `source_basis`, `target_unit`, `finance_resource_id`, `mapping_approved` |
| تنظیم واحد دستهٔ مصالح | `GET/POST /material-prices/unit-settings` | `material_unit_settings` | `category`, `resource_id`, `display_unit`, `version`, `reason` |
| ضریب تبدیل اختصاصی کالا | `GET/POST /material-prices/{providerItemId}/factors` | `provider_item_unit_factors` | `provider_item_id`, `from_unit`, `to_unit`, `factor`, `factor_type`, `approved_by`, `approved_at` |
| وضعیت اتصال قیمت روز در جدول اقلام | `GET /item-price-mappings/status` | `finance_item_price_mappings`, `price_observations`, `provider_items`, `provider_item_unit_factors`, `estimate_lines` | `estimate_line_id`, `provider_item_id`, `selected_unit`, `conversion_status`, `conversion_factor_id`, `normalized_price_irr`, `quantity` |
| فیلترهای پنل اتصال | `GET /item-price-mappings/filters` | `provider_items`, `price_providers`, `provider_item_labels` | `category`, `provider_id`, `name`, `product_type` |
| کاندیدهای انتخاب محصول | `GET /item-price-mappings/candidates` | `provider_items`, `price_providers`, `price_observations`, `provider_item_labels` | `external_name`, `external_id`, `category`, `metadata`, `normalized_price_irr`, `product_type`, `display_name` |
| پیش‌نمایش تبدیل و هزینهٔ روز | `GET /estimate-lines/{lineId}/price-preview` | `estimate_lines`, `finance_item_price_mappings`, `price_observations`, `provider_item_unit_factors` | `selected_unit`, `source_unit`, `normalized_price_irr`, `factor`, `quantity` |
| ثبت اتصال قیمت روز به قلم MSP | `POST /estimate-lines/{lineId}/price-mapping` | `finance_item_price_mappings` | `estimate_line_id`, `provider_item_id`, `selected_unit`, `source_price_unit`, `conversion_status`, `effective_from`, `reason` |
| تاریخچهٔ اتصال قیمت روز | `GET /estimate-lines/{lineId}/price-mapping/history` | `finance_item_price_mappings` | `version`, `superseded_at`, `created_by`, `created_at`, `reason` |
| گزارش سطح ۱ و ۲ WBS | `GET /reports/live/by-wbs` | `estimate_lines`, `finance_resources`, `price_versions`, `invoice_lines`, `invoices`, `unit_conversions`, `progress_snapshot_refs` | `wbsCode`, `initialEstimateIrr`, `actualCostIrr`, `breakdown`, `missingEstimateLineCount` |
| گزارش زندهٔ مالی | `GET /reports/live` | همان جدول‌های گزارش | برآورد، هزینهٔ واقعی، پیشرفت، remaining/forecast |
| مغایرت‌ها | `GET /reports/live/variances` | همان جدول‌های گزارش | `varianceIrr`, `varianceQuantity`, `resourceType`, `impactSharePercent` |
| snapshot فایل MSP | `GET /progress-snapshots` | `progress_snapshot_refs` | `progress_snapshot_id`, `source_file_name_safe`, `reporting_date`, `snapshot_status`, `imported_at` |
| feed فایل MSP | `GET /progress-snapshots/{snapshotId}/feed` | `progress_snapshot_refs` + host progress provider | assignment/activity rows از فایل MPP |
| اصلاح دستی پیشرفت | `POST /estimate-lines/{lineId}/progress-override` | `progress_overrides`, `estimate_lines`, `progress_snapshot_refs` | `computed_value`, `override_value`, `reason`, `created_by` |

### جمع‌بندی ساده

- **MSP/MPP** از `estimate_lines`, `finance_resources`, `finance_mpp_rows`, `progress_snapshot_refs` می‌آید.
- **قیمت روز بازار مصالح** از `provider_items`, `price_observations`, `price_providers` می‌آید.
- **اتصال قیمت روز به قلم MSP** از `finance_item_price_mappings` می‌آید.
- **نوع محصول و برچسب دستی** از `provider_item_labels` می‌آید.
- **ضریب تبدیل اختصاصی** از `provider_item_unit_factors` می‌آید.
- **واحد انتخابی دستهٔ مصالح** از `material_unit_settings` می‌آید.
- **گزارش سطح ۱/۲** از ترکیب `estimate_lines`, `finance_resources`, `price_versions`, `invoice_lines`, `invoices`, `unit_conversions`, `progress_snapshot_refs` ساخته می‌شود.

> نتیجهٔ کلی بک‌اند: UI الان دیتای مالی را از API می‌خواند، نه mock و نه Google Sheet مستقیم.
> Google Sheet فقط سمت بک‌اند وارد دیتابیس می‌شود.

---

## ۲. صفحهٔ اقلام و برآورد — `#/finance/financial-items`

| بخش UI | API | جدول/ستون |
|---|---|---|
| لیست اقلام MSP/MPP | `GET /estimate-lines` | `estimate_lines.id`, `resource_id`, `activity_external_id`, `assignment_external_id`, `original_quantity`, `original_unit_price_irr`, `source_assignment_uid`, `source_task_uid` |
| نام/نوع/واحد قلم | `GET /resources` | `finance_resources.id`, `title`, `code`, `resource_type`, `base_unit`, `dimension` |
| عنوان فعالیت و WBS | `GET /activities` | از host/Core activity provider؛ در خود `estimate_lines` ستون عنوان/WBS اصلی نیست |
| قیمت روز رسمی داخلی | `GET /prices/current` | `price_versions.resource_id`, `unit_price_irr`, `effective_from`, `scope_kind` |
| واحدها | `GET /unit-registry` | از `UNIT_REGISTRY` در بک‌اند، جدول دیتابیس نیست |
| دکمهٔ اتصال قیمت روز | `GET /item-price-mappings/status` | `finance_item_price_mappings` + `price_observations` + `provider_items` |
| ثبت اتصال قیمت روز | `POST /estimate-lines/{lineId}/price-mapping` | `finance_item_price_mappings` |
| تاریخچهٔ اتصال | `GET /estimate-lines/{lineId}/price-mapping/history` | نسخه‌های قبلی `finance_item_price_mappings` |

> وضعیت اعلامی بک‌اند: تعریف API درست است. اتصال فعلی برای هر estimate line **یک mapping فعال**
> دارد؛ اگر بخواهی برای «کانال‌کنی» چند مصالح هم‌زمان اضافه شود و جمع قیمت روز محاسبه شود،
> مدل فعلی هنوز کافی نیست و باید sub-line/component اضافه شود.

---

## ۳. پنل اتصال قیمت روز (داخل همان صفحهٔ اقلام)

| فیلد/دکمه | API | جدول/ستون |
|---|---|---|
| دستهٔ مصالح | `GET /item-price-mappings/filters` | از `provider_items.category` |
| منبع/سایت | `GET /item-price-mappings/filters` | `price_providers.id`, `name` |
| نوع محصول | `GET /item-price-mappings/filters?category=...` | `provider_item_labels.product_type` |
| جستجوی محصول | `GET /item-price-mappings/candidates` | `provider_items.external_name`, `external_id` |
| جزئیات اختصاصی محصول | همان candidates | `provider_items.metadata` |
| قیمت روز محصول | همان candidates + latest observation | `price_observations.normalized_price_irr`, `raw_price`, `workflow_date_jalali` |
| انتخاب واحد رسمی | `GET /item-price-mappings/filters` | `UNIT_REGISTRY` |
| پیش‌نمایش تبدیل | `GET /estimate-lines/{lineId}/price-preview` | `price_observations` + `provider_item_unit_factors` + `estimate_lines` |
| ثبت اتصال | `POST /estimate-lines/{lineId}/price-mapping` | `finance_item_price_mappings` |

> نکتهٔ بک‌اند: فیلتر «نوع محصول» فقط از `provider_item_labels.product_type` می‌آید. اگر چیزی
> نشان نمی‌دهد یعنی برای آن دسته هنوز `label/product_type` ثبت نشده، نه اینکه API وجود ندارد.

---

## ۴. صفحهٔ قیمت روز مصالح — `#/finance/prices`

| بخش UI | API | جدول/ستون |
|---|---|---|
| تب دسته‌ها | `GET /material-prices/categories` | `provider_items.category`, `active` |
| ستون‌های اختصاصی هر دسته | همان categories | از schema بک‌اند، بر اساس category |
| ردیف‌های قیمت روز | `GET /material-prices/current` | `provider_items` + آخرین `price_observations` |
| نام محصول | — | `provider_items.external_name` |
| productId | — | `provider_items.external_id` |
| منبع | join به `price_providers.name` | `price_providers.name` |
| قیمت | — | `price_observations.normalized_price_irr` (تومان واردشده ×۱۰ به ریال) |
| تاریخ شیت | — | `price_observations.workflow_date_jalali/gregorian/raw` |
| ستون‌های اختصاصی (ضخامت/وزن/طول) | — | `provider_items.metadata` (کلیدهای worksheet-specific) |
| وضعیت حل قیمت | سرویس resolution | از وضعیت `unit`/`price`/`label`/`factor` ساخته می‌شود |

> وضعیت اعلامی بک‌اند: در آخرین master صفحهٔ قیمت روز دیگر جدول کاملاً عمومی نیست؛ ستون‌ها
> باید از `/material-prices/categories` بیاید. اگر هنوز UI قدیمی دیده می‌شود، احتمالاً devhost
> روی نسخهٔ قدیمی‌تر است یا branch/cache یکی نیست.

---

## ۵. گزارش سطح ۱ و ۲ — `#/finance/level-one`

| بخش UI | API | جدول/ستون |
|---|---|---|
| نمودار سطح ۱ | `GET /reports/live/by-wbs?level=1` | محاسبه از چند جدول |
| کلیک روی مرحله | `GET /reports/live/by-wbs?parentWbsCode=...` | فرزندهای WBS همان مرحله |
| برآورد اولیه | `estimate_lines.original_quantity × original_unit_price_irr` | `estimate_lines` |
| هزینهٔ واقعی | invoice lines با وضعیت confirmed/voided/corrected | `invoice_lines.final_line_amount_irr`, `invoices.financial_effect_sign` |
| تفکیک مصالح/نیروی انسانی/تجهیزات/عمومی | resource type | `finance_resources.resource_type` |
| قیمت جاری در گزارش | latest price version | `price_versions.unit_price_irr` |
| snapshot فایل MSP | `progress_snapshot_refs` | `progress_snapshot_id`, `source_file_name_safe`, `reporting_date` |

> نکتهٔ بک‌اند دربارهٔ سطح ۲: وقتی روی WBSای مثل `1.6` می‌زنی، API فقط فرزندهای آن را می‌خواهد.
> اگر ساختار MSP برای آن WBS فرزند نداشته باشد یا estimate lines به فرزندها وصل نشده باشند،
> سطح ۲ خالی/نامعلوم می‌شود. یعنی API تعریف شده ولی دادهٔ drilldown برای آن WBS کامل نیست،
> یا UI باید summary خود مرحله را هم نشان دهد.

---

## ۶. تبدیل واحد و ضرایب

| بخش | API | جدول/منبع |
|---|---|---|
| لیست واحدهای مجاز | `GET /unit-registry` | `UNIT_REGISTRY` |
| تبدیل‌های عمومی | domain service | `domain/unit_conversion.py` |
| تبدیل‌های دستی کالا | `GET/POST /material-prices/{providerItemId}/factors` | `provider_item_unit_factors` |
| تنظیم واحد دسته | `GET/POST /material-prices/unit-settings` | `material_unit_settings` |
| واحد MSP | `GET /resources` و estimate line context | `finance_resources.base_unit` |

> منطق اعلامی: واحد رسمی را کاربر انتخاب می‌کند. اگر واحد قیمت روز و واحد رسمی یکی باشند،
> تبدیل لازم نیست. اگر متفاوت باشند، یا تبدیل عمومی انجام می‌شود یا ضریب دستی لازم است.
> **مقدار نامعلوم صفر نمی‌شود.**

---

## ۷. جمع‌بندی بک‌اند

بلاکرهای اعلام‌شده:

1. اگر «نوع محصول» خالی است، باید برای محصولات `provider_item_labels.product_type` ثبت شود.
2. برای فعالیت‌هایی مثل «کانال‌کنی» که چند مصالح دارد، مدل فعلی single mapping است؛ برای جمع چند قلم باید جدول component اضافه شود.
3. برای سطح ۲ WBS، اگر فرزند ندارد، UI باید خود مرحله و ردیف‌های مستقیم همان WBS را نشان دهد، نه اینکه صفحه خالی شود.
4. برای اطمینان عددی، همین APIها روی `bambo_canonical_test` با Swagger اجرا شوند و خروجی با جدول‌ها مقایسه شود.

وضعیت اعلامی:

| بخش | وضعیت |
|---|---|
| خواندن MPP و برآوردها | تقریباً پایدار |
| گزارش مراحل/WBS | نقص اصلی تاریخ و نسخه رفع شده |
| قیمت روز مصالح | داده می‌آید، ولی ۸۴٪ به‌خاطر نبود تنظیمات قابل محاسبه نیست |
| بک‌اند تنظیم واحد/برچسب/ضریب | وجود دارد |
| UI تنظیم واحد/برچسب/ضریب | ساخته نشده یا به صفحه وصل نیست |
| تحویل Integration Kit | هنوز آماده نیست |

درصدهای پیشنهادی بک‌اند: آماده برای تست داخلی ۸۸٪ · آماده برای مهاجرت Production ۷۵٪ · آماده برای تحویل نهایی ۶۰٪.

سه رابط پیکربندی که بک‌اند می‌خواهد ساخته شود:

1. **تنظیم واحد دسته/منبع** — برای هر دسته و منبع مشخص شود قیمت مبدأ چیست
   (`rebar + AhanOnline = kg`، `angle + Mashhad Foolad = branch`، `brick + Toranj = each یا m2`).
2. **برچسب‌گذاری محصول** — تیرآهن، نبشی، آجر نما، لوله، اتصالات … تا در dropdown اتصال قیمت روز ظاهر شوند.
3. **ثبت ضریب تبدیل** — هر شاخه چند کیلو؟ هر شاخه چند متر؟ هر عدد آجر چند مترمربع؟ همراه با
   `approved_by`, `approved_at`, `reason`.

> جمع‌بندی بک‌اند: این تسک Frontend-led است، ولی Backend-supported.

---
---

# بررسی و تطبیق با کد — ۱۳۹۵/۰۶/۲۵ (2026-09-16)

این بخش را من نوشته‌ام، نه بک‌اند. هر ادعا با اندازه‌گیری روی کد و روی دیتابیس بررسی شده.

## الف) جایی که سند از کد عقب است

**مدل component از قبل ساخته شده.** بند ۲ بلاکرها می‌گوید «مدل فعلی single mapping است و
باید جدول component اضافه شود». هم بک‌اند و هم فرانت این را دارند:

| endpoint بک‌اند | فرانت صدایش می‌زند؟ |
|---|---|
| `GET /estimate-lines/{id}/price-mapping/components` | بله — `componentsFor` |
| `POST /estimate-lines/{id}/price-mapping/components` | بله — `addComponent` |
| `PATCH /estimate-lines/{id}/price-mapping/components/{componentId}` | بله — `updateComponent` |
| `POST …/components/{componentId}/deactivate` | بله — `deactivateComponent` |
| `GET …/price-mapping/components/history` | بله — `componentHistory` |
| `GET /estimate-lines/{id}/price-component-preview` | بله — `previewComponent` |
| `GET /estimate-lines/{id}/price-total-preview` | بله — `previewTotal` |

پنل `price-mapping-panel.js` دقیقاً همین هفت متد را استفاده می‌کند. پس «چند مصالح برای یک
فعالیت» بلاکر نیست؛ ساخته شده.

در عوض این سه endpoint که سند نام می‌برد، **فرانت هیچ‌وقت صدا نمی‌زند** و ظاهراً نسخهٔ قدیمیِ
همان کارند: `price-preview`, `POST price-mapping`, `price-mapping/history`.

## ب) جایی که سند درست است

سه رابط پیکربندی واقعاً وجود ندارند. متدهای adapter نوشته شده‌اند ولی **هیچ صفحه‌ای صدایشان
نمی‌زند** — با grep روی `src/features/` و `src/app/` تأیید شد:

```
setUnit            → هیچ‌جا
saveLabel          → هیچ‌جا
saveItemFactor     → هیچ‌جا
listUnitSettings   → هیچ‌جا
listLabels         → هیچ‌جا
listItemFactors    → هیچ‌جا
listUnresolved     → هیچ‌جا
listLabelHistory   → هیچ‌جا
```

یعنی لایهٔ API نوشته شده، رابط کاربری‌اش نه. این همان چیزی است که سند می‌گوید.

## ج) بلاکر دیتابیس — برطرف شد (۲۶ شهریور)

روی نسخهٔ قبلی دیتابیس (`…_20260913.dump`، ۳٫۵۲ مگابایت) چهار جدول این بخش وجود نداشت و
همهٔ endpointهای قیمت روز ۵۰۰ می‌دادند. نسخهٔ جایگزین‌شده (همان نام، ۴٫۲۳ مگابایت) هر پنج
جدول را دارد:

```
provider_items                        hast
price_observations                    hast
price_providers                       hast
price_collection_runs                 hast
provider_item_labels                  hast
provider_item_unit_factors            hast
material_unit_settings                hast
finance_item_price_mappings           hast
finance_item_price_mapping_components hast
```

**تصحیح:** جدول اجزا `finance_item_price_mapping_components` نام دارد. من اول به اشتباه
`item_price_components` گرفته بودمش — آن نام فایل ماژول دامنه است
(`backend/app/finance/domain/item_price_components.py`)، نه نام جدول. یک بار گزارش دادم که
این جدول در نسخهٔ جدید هم نیست، که غلط بود.

همهٔ جدول‌هایی که repositoryهای بک‌اند از آن‌ها می‌خوانند، در dump جدید موجودند.

## د) کاری که باید بشود

۱. نسخهٔ جدید restore شود و devhost روی آن بالا بیاید.
۲. بعد از آن، عدد «۸۴٪ قابل محاسبه نیست» روی همین داده اندازه‌گیری شود تا معلوم شود گلوگاه
   واحد است، برچسب است، یا ضریب — از روی شمارش `needs_*` در `/item-price-mappings/status`.
۳. سه رابط پیکربندی ساخته شود، با ترتیبی که آن اندازه‌گیری تعیین می‌کند نه حدس.
