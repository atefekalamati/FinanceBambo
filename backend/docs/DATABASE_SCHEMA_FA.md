# شمای دیتابیس BAMBO Finance

مرجع ساختار دیتابیس: هر جدول برای چیست، هر ستون چه نگه می‌دارد، و کدام endpoint به آن می‌رسد.

| | |
|---|---|
| دیتابیس | `bambo_canonical_test` |
| نسخهٔ مهاجرت | `0036` |
| تعداد جدول | 84 |
| تعداد ستون | 1086 |
| تعداد endpoint | 102 |
| جدول‌هایی که API مالی به آن‌ها می‌رسد | 30 از 84 |
| پیشوند مسیرها | `/api/projects/{projectId}/finance` |

این سند ساخته می‌شود، دستی نوشته نمی‌شود: `python -m scripts.generate_schema_doc`.

ساختار، نوع، کلید خارجی، مقدار پیش‌فرض و واژگان CHECK مستقیماً از دیتابیس زنده خوانده شده‌اند. کاربردِ هر جدول و معنای هر ستون دستی نوشته شده است. ستونی که هیچ‌کدام پوشش نداده‌اند با **توضیح ثبت‌نشده** علامت خورده و در انتهای سند شمرده شده — حدس زده نشده.

---

## فهرست دامنه‌ها

| دامنه | جدول | سطر | کاربرد |
|---|---:|---:|---|
| [برنامهٔ زمان‌بندی و فایل MPP](#برنامهٔ-زمان‌بندی-و-فایل-mpp) | 15 | 27,585 | برنامهٔ MS Project و خوانشِ مالیِ آن. مرجعِ «چه کاری قرار است انجام شود». |
| [قیمت بازار و گوگل‌شیت](#قیمت-بازار-و-گوگل‌شیت) | 11 | 24,801 | قیمت‌هایی که از گوگل‌شیت وارد می‌شوند، و هویت کالایی که قیمت به آن می‌چسبد. |
| [برآورد، منابع مالی و تبدیل واحد](#برآورد،-منابع-مالی-و-تبدیل-واحد) | 10 | 1,470 | از برنامه تا عدد ریالی: سطر برآورد، منبع مالی، قیمت و ضریب تبدیل واحد. |
| [فاکتور و استخراج هوش مصنوعی](#فاکتور-و-استخراج-هوش-مصنوعی) | 6 | 90 | سند واقعی خرج: پیوست، استخراج، پیش‌نویس و فاکتور تأییدشده. |
| [پیشرفت، گزارش و حسابرسی](#پیشرفت،-گزارش-و-حسابرسی) | 7 | 226 | آنچه واقعاً اجرا شده، و ردِ هر تغییر. |
| [سازمان، کاربر و دسترسی](#سازمان،-کاربر-و-دسترسی) | 15 | 449 | هویت و مجوز. بخش مالی این‌ها را می‌خواند و نمی‌نویسد. |
| [ماژول‌های دیگر BAMBO](#ماژول‌های-دیگر-bambo) | 20 | 77 | در همین دیتابیس‌اند، ولی API مالی به آن‌ها دست نمی‌زند. |

---

## برنامهٔ زمان‌بندی و فایل MPP

برنامهٔ MS Project و خوانشِ مالیِ آن. مرجعِ «چه کاری قرار است انجام شود».

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`msp_tasks`](#msp-tasks) | 17,864 | 30 | فعالیت‌های فایل MS Project؛ هر سطر یک تسک با تاریخ، مدت و جایگاه WBS. | — |
| [`msp_resource_assignments`](#msp-resource-assignments) | 5,195 | 19 | تخصیص منبع به تسک. مقدار و هزینه در سطح همین تخصیص معنا دارد، نه تسک. | — |
| [`finance_mpp_rows`](#finance-mpp-rows) | 2,366 | 38 | خوانشِ مالیِ فایل MPP: هر سطر یک تخصیص با مقدار، واحد و هزینه. منبعی که «موارد و برآوردها» از آن تغذیه می‌شود. | 25 endpoint |
| [`msp_resources`](#msp-resources) | 1,965 | 26 | منابع فایل MPP: نیروی انسانی، ماشین‌آلات و مصالح، با نرخ و واحد. | — |
| [`finance_task_resource_map`](#finance-task-resource-map) | 120 | 3 | پل بین تسک MPP و منبع مالی. | 10 endpoint |
| [`msp_reporting_periods`](#msp-reporting-periods) | 29 | 14 | دوره‌های گزارش‌دهی که پیشرفت در آن‌ها ثبت می‌شود. | — |
| [`msp_snapshots`](#msp-snapshots) | 18 | 17 | هر بار خواندن یک فایل MPP یک snapshot می‌سازد؛ مرجع نسخه‌ای برنامه. | — |
| [`msp_file_versions`](#msp-file-versions) | 18 | 20 | فایل‌های MPP بارگذاری‌شده و نسخه‌بندی آن‌ها. | — |
| [`finance_mpp_source_versions`](#finance-mpp-source-versions) | 3 | 15 | نسخهٔ فایل MPP که سمت مالی به آن قفل شده؛ در هر لحظه فقط یکی «زنده» است. | 1 endpoint |
| [`msp_voice_report_audio`](#msp-voice-report-audio) | 2 | 12 | فایل صوتی خام هر گزارش صوتی. | — |
| [`msp_baseline_revisions`](#msp-baseline-revisions) | 1 | 11 | بازنگری‌های خط مبنا (baseline) برنامه. | — |
| [`msp_reporting_calendars`](#msp-reporting-calendars) | 1 | 8 | تقویم گزارش‌دهی پروژه. | — |
| [`msp_edit_sessions`](#msp-edit-sessions) | 1 | 39 | جلسهٔ ویرایش برنامه؛ تغییرات پیش از اعمال اینجا جمع می‌شود. | — |
| [`msp_voice_reports`](#msp-voice-reports) | 1 | 17 | گزارش پیشرفت صوتی ثبت‌شده در کارگاه. | — |
| [`finance_mpp_currency_decisions`](#finance-mpp-currency-decisions) | 1 | 12 | تصمیم «تومان یا ریال» برای هر فایل MPP، همراه با شواهدی که تصمیم بر آن استوار است. | — |

### `msp_tasks`

فعالیت‌های فایل MS Project؛ هر سطر یک تسک با تاریخ، مدت و جایگاه WBS.

`17,864` سطر · `30` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `snapshot_id` | `bigint` | بله | FK | ارجاع به `msp_snapshots.id` |
| `uid` | `integer` | — |  | شناسهٔ تسک در فایل MPP (UID) |
| `guid` | `text` | — |  | شناسهٔ سراسری تسک در فایل MPP |
| `task_id` | `integer` | — |  | شناسهٔ task |
| `name` | `text` | بله |  | نام<br>پیش‌فرض: `''` |
| `wbs` | `text` | — |  | کد WBS تسک |
| `outline_number` | `text` | — |  | شمارهٔ سلسله‌مراتبی تسک در درخت برنامه |
| `outline_level` | `integer` | — |  | عمق تسک در درخت برنامه؛ ۱ یعنی سطح اول |
| `start` | `text` | — |  | تاریخ شروع برنامه‌ریزی‌شده |
| `finish` | `text` | — |  | تاریخ پایان برنامه‌ریزی‌شده |
| `duration` | `text` | — |  | مدت تسک |
| `percent_complete` | `numeric(7,4)` | — |  | درصد تکمیل تسک |
| `percent_work_complete` | `numeric(7,4)` | — |  | درصد تکمیل بر مبنای کار (نفر-ساعت) |
| `physical_percent_complete` | `numeric(7,4)` | — |  | درصد تکمیل فیزیکی، جدا از درصد کار |
| `baseline_start` | `text` | — |  | شروع خط مبنا |
| `baseline_finish` | `text` | — |  | پایان خط مبنا |
| `baseline_duration` | `text` | — |  | مدت خط مبنا |
| `baseline_cost` | `numeric(18,4)` | — |  | هزینهٔ خط مبنا |
| `number1` | `numeric(18,6)` | — |  | فیلد عددی سفارشی MS Project (Number1). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی‌خواند — **معنای آن احراز نشده** |
| `number3` | `numeric(18,6)` | — |  | فیلد عددی سفارشی MS Project (Number3). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی‌خواند — **معنای آن احراز نشده** |
| `number4` | `numeric(18,6)` | — |  | فیلد عددی سفارشی MS Project (Number4). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی‌خواند — **معنای آن احراز نشده** |
| `number13` | `numeric(18,6)` | — |  | فیلد عددی سفارشی MS Project (Number13). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی‌خواند — **معنای آن احراز نشده** |
| `number14` | `numeric(18,6)` | — |  | فیلد عددی سفارشی MS Project (Number14). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی‌خواند — **معنای آن احراز نشده** |
| `number18` | `numeric(18,6)` | — |  | فیلد عددی سفارشی MS Project (Number18). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی‌خواند — **معنای آن احراز نشده** |
| `text1` | `text` | — |  | فیلد متنی سفارشی MS Project (Text1) |
| `start1` | `text` | — |  | فیلد تاریخ سفارشی MS Project (Start1) |
| `finish1` | `text` | — |  | فیلد تاریخ سفارشی MS Project (Finish1) |
| `raw_fields_json` | `jsonb` | — |  | دادهٔ raw fields به صورت JSON |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `msp_resource_assignments`

تخصیص منبع به تسک. مقدار و هزینه در سطح همین تخصیص معنا دارد، نه تسک.

> MSP resource assignments, one row per task-resource assignment per snapshot. Finance reads it; the parser writes it.

`5,195` سطر · `19` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `snapshot_id` | `bigint` | بله | FK | Logically references msp_snapshots.id. No foreign key: the migration role has no REFERENCES privilege on Core. |
| `assignment_uid` | `integer` | بله |  | شناسهٔ assignment در فایل مبدأ |
| `task_uid` | `integer` | بله |  | Logically references msp_tasks.uid within the same snapshot. No foreign key: no REFERENCES privilege on Core, and msp_tasks carries no UNIQUE (snapshot_id, uid) to point at. |
| `resource_uid` | `integer` | — | FK | NULL where MSP left the assignment unlinked -- 12 of 727 in the reference file. Kept, so the row stays countable. |
| `units` | `numeric(18,6)` | — |  | ضریب تخصیص منبع به تسک؛ در فایل ×۱۰۰ ذخیره می‌شود |
| `planned_work` | `numeric(18,6)` | — |  | کار برنامه‌ریزی‌شدهٔ این تخصیص |
| `actual_work` | `numeric(18,6)` | — |  | کار انجام‌شدهٔ این تخصیص |
| `remaining_work` | `numeric(18,6)` | — |  | کار باقی‌ماندهٔ این تخصیص |
| `planned_quantity` | `numeric(18,6)` | — |  | Physical quantity from MPXJ Assignment.Material. The task-granular figure a WBS rollup may use.<br>*حداقل 0* |
| `actual_quantity` | `numeric(18,6)` | — |  | From MPXJ Assignment.ActualMaterial. NULL means not reported -- never zero by assumption.<br>*حداقل 0* |
| `remaining_quantity` | `numeric(18,6)` | — |  | مقدار باقی‌ماندهٔ این تخصیص<br>*حداقل 0* |
| `quantity_unit` | `text` | — |  | واحدِ quantity |
| `assignment_work_complete_percent` | `numeric(7,4)` | — |  | درصد assignment work complete |
| `source_cost` | `numeric(18,4)` | — |  | هزینهٔ این تخصیص طبق فایل |
| `source_actual_cost` | `numeric(18,4)` | — |  | Reference only. The authoritative actual cost is a confirmed Finance invoice. |
| `source_remaining_cost` | `numeric(18,4)` | — |  | هزینهٔ باقی‌ماندهٔ این تخصیص طبق فایل |
| `raw_fields_json` | `jsonb` | — |  | دادهٔ raw fields به صورت JSON |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `finance_mpp_rows`

خوانشِ مالیِ فایل MPP: هر سطر یک تخصیص با مقدار، واحد و هزینه. منبعی که «موارد و برآوردها» از آن تغذیه می‌شود.

> The schedule rows Finance needs, keyed by the MPP's own identifiers. Finance-owned: readable with no msp_* table present.

`2,366` سطر · `38` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `source_version_id` | `uuid` | بله | FK | ارجاع به `finance_mpp_source_versions.id` |
| `source_task_uid` | `integer` | بله |  | شناسهٔ تسک در فایل MPP |
| `source_assignment_uid` | `integer` | — |  | شناسهٔ تخصیص در فایل MPP |
| `source_resource_uid` | `integer` | — |  | شناسهٔ منبع در فایل MPP |
| `task_name` | `text` | — |  | نام تسک، کپی‌شده از فایل برای خواندن بدون join |
| `task_wbs` | `text` | — |  | کد WBS تسک |
| `resource_name` | `text` | — |  | نام منبع |
| `quantity` | `numeric(18,4)` | — |  | NULL unless the file states an approved Finance quantity. Never inferred from work, duration, cost or percent complete. |
| `quantity_unit` | `text` | — |  | واحد مقدار این سطر |
| `weight_rial` | `numeric` | — |  | وزن سطر بر مبنای ریال، برای تجمیع پیشرفت |
| `weight_time` | `numeric` | — |  | وزن سطر بر مبنای زمان |
| `weight_base` | `numeric` | — |  | مبنایی که وزن بر آن حساب شده |
| `actual_progress` | `numeric` | — |  | پیشرفت واقعی گزارش‌شده |
| `actual_progress_percent` | `numeric` | — |  | درصد actual progress |
| `physical_progress` | `numeric` | — |  | پیشرفت فیزیکی |
| `planned_progress` | `numeric` | — |  | پیشرفت برنامه‌ای در همان تاریخ |
| `source_cost` | `numeric` | — |  | The SCHEDULE's cost for this task. Not a Finance figure: Finance actual cost comes from confirmed invoices. |
| `source_actual_cost` | `numeric` | — |  | هزینهٔ واقعی طبق فایل |
| `source_fixed_cost` | `numeric` | — |  | هزینهٔ ثابت تسک؛ تنها جای پولی که مدت‌ها خوانده نمی‌شد |
| `task_start` | `text` | — |  | Schedule start as the file states it. Text, because the file names no timezone. |
| `task_finish` | `text` | — |  | تاریخ پایان تسک |
| `resource_type` | `text` | — |  | نوع منبع (نیرو، مصالح، تجهیزات) |
| `resource_unit` | `text` | — |  | The resource's own unit of measure. NOT the unit of an approved quantity -- that is quantity_unit. |
| `progress_variance` | `numeric` | — |  | اختلاف پیشرفت واقعی با برنامه‌ای |
| `source_assignment_units` | `numeric` | — |  | The units the file states for THIS assignment, on the file's own scale. Not a financial quantity: `quantity` is that, and it stays NULL until a person approves one. |
| `source_assignment_cost_irr` | `numeric` | — |  | The cost the file states for THIS assignment, in rials (the file's toman amount x10). Not a price and not an actual cost: a price is per unit and entered by a person, and an actual cost comes from a confirmed invoice. |
| `normalized_unit` | `text` | — |  | The unit-registry code `resource_unit` was recognised as, or NULL when nothing recognised it. NULL is an answer here, not a gap to fill. |
| `unit_source` | `text` | — |  | اینکه واحد از کجا تعیین شده |
| `unit_confidence` | `text` | — |  | How the unit was arrived at: `exact` when the file named a registry unit, `alias` when a known spelling of one, `low` when nothing recognised it. |
| `source_material_quantity` | `numeric` | — |  | The physical quantity the file states for this assignment (MPXJ Material), in `resource_unit`. NOT `source_assignment_units`, which is this number scaled by a hundred, and NOT `quantity`, which is the approved financial quantity. |
| `source_resource_rate_irr` | `numeric` | — |  | The resource's standard rate in rials per unit of `resource_unit` (the file's toman rate x10). NULL when the file states none; a real zero stays zero. |
| `source_rate_basis` | `text` | — |  | `material_unit` when the resource is MATERIAL and quantity x rate reproduces the assignment's own cost -- the proof that the rate is per material unit. NULL when nothing proves it, and then the rate is not an estimate basis. |
| `source_fixed_cost_irr` | `numeric` | — |  | The task's own Fixed Cost in rials -- the file's `source_fixed_cost` through the same currency decision the assignment cost passes through. Repeated on every row of the task, exactly as `source_cost` is, so it must be de-duplicated by task uid before it is summed. NULL when the file states none. |
| `source_daily_quantity` | `numeric(24,8)` | — |  | The quantity the schedule states for TODAY, from its own dedicated column. NULL means the file states none -- never zero-by-default. A zero read from an MS Project Number column is indistinguishable from an empty one, so the importer records only a non-zero value here; a zero entered by a person is a different fact and is kept. |
| `source_daily_quantity_field` | `text` | — |  | The planner's own ALIAS for the column the value came from, never the NumberN index: the same meaning lands on a different index in the next file, so the alias is the contract and is recorded with the value. |

**API:** `GET /activities` · `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /estimate-lines` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /items-and-estimates` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /resources`

### `msp_resources`

منابع فایل MPP: نیروی انسانی، ماشین‌آلات و مصالح، با نرخ و واحد.

> MSP Resource Sheet, one row per resource per snapshot. Finance reads it; the parser writes it.

`1,965` سطر · `26` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `snapshot_id` | `bigint` | بله |  | Logically references msp_snapshots.id. No foreign key: the migration role has no REFERENCES privilege on Core. Orphans are counted by docs/sql/msp_resource_assignment_data_validation.sql. |
| `resource_uid` | `integer` | بله |  | Native MSP Resource UID. The identity. GUID is regenerated on save and must not be used as one. |
| `resource_guid` | `text` | — |  | شناسهٔ سراسری منبع در فایل MPP |
| `resource_name` | `text` | — |  | نام منبع، همان‌طور که در فایل نوشته شده |
| `native_type` | `text` | بله |  | نوع منبع در خودِ MS Project (کار / مصالح / هزینه)<br>*مقادیر مجاز: WORK / MATERIAL / COST* |
| `bambo_resource_type` | `text` | — |  | BAMBO-wide classification. NULL when MSP gives no basis to classify, which is every WORK resource so far.<br>*مقادیر مجاز: material / labor / equipment / general_cost* |
| `resource_quantity` | `numeric(18,6)` | — |  | Physical quantity from MPXJ Resource.Material -- the Resource Sheet Quantity column. Not Work, not Max Units.<br>*حداقل 0* |
| `resource_quantity_unit` | `text` | — |  | Unit of resource_quantity. quantity_unit_source records which MSP field it was read from. |
| `quantity_unit_source` | `text` | — |  | اینکه واحد مقدار از کجا آمده<br>*مقادیر مجاز: material_label / initials / custom_field / other* |
| `initials` | `text` | — |  | حروف اختصاری منبع در MS Project |
| `material_label` | `text` | — |  | برچسب واحد مصالح در MS Project |
| `resource_group` | `text` | — |  | گروه منبع |
| `code` | `text` | — |  | کد |
| `max_units` | `numeric(18,6)` | — |  | حداکثر ظرفیت منبع |
| `standard_rate` | `numeric(18,4)` | — |  | Reference only. The authoritative price history is price_versions. |
| `overtime_rate` | `numeric(18,4)` | — |  | نرخ اضافه‌کاری |
| `cost_per_use` | `numeric(18,4)` | — |  | هزینهٔ ثابت هر بار استفاده |
| `work` | `numeric(18,6)` | — |  | کار برنامه‌ریزی‌شدهٔ منبع |
| `actual_work` | `numeric(18,6)` | — |  | کار انجام‌شدهٔ منبع |
| `remaining_work` | `numeric(18,6)` | — |  | کار باقی‌ماندهٔ منبع |
| `source_cost` | `numeric(18,4)` | — |  | هزینهٔ منبع طبق فایل |
| `source_actual_cost` | `numeric(18,4)` | — |  | هزینهٔ واقعی منبع طبق فایل |
| `source_remaining_cost` | `numeric(18,4)` | — |  | هزینهٔ باقی‌ماندهٔ منبع طبق فایل |
| `raw_fields_json` | `jsonb` | — |  | دادهٔ raw fields به صورت JSON |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `finance_task_resource_map`

پل بین تسک MPP و منبع مالی.

> One row per (Core schedule task, Finance resource) pair. Exactly three columns by design: tenant scope lives on the two endpoints and every read joins through finance_resources.

`120` سطر · `3` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `task_id` | `bigint` | بله | FK | msp_tasks.id -- the database row identity. NEVER the MPP file's display Task ID, which renumbers on every insertion. |
| `resource_id` | `uuid` | بله | FK | ارجاع به `finance_resources.id` |

**API:** `GET /activities` · `GET /estimate-lines` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /resources`

### `msp_reporting_periods`

دوره‌های گزارش‌دهی که پیشرفت در آن‌ها ثبت می‌شود.

`29` سطر · `14` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `msp_snapshots.project_id` |
| `sequence_number` | `integer` | بله |  | شمارهٔ sequence<br>*حداقل 0* |
| `period_start_jalali` | `text` | بله |  | تاریخ period start، شمسی |
| `period_end_jalali` | `text` | بله |  | تاریخ period end، شمسی |
| `target_snapshot_id` | `bigint` | — | FK | ارجاع به `msp_snapshots.id` |
| `actual_snapshot_id` | `bigint` | — | FK | ارجاع به `msp_snapshots.id` |
| `baseline_revision_id` | `bigint` | — | FK | ارجاع به `msp_baseline_revisions.id` |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: PLANNED / AWAITING_ACTUAL / REPORTED / SKIPPED*<br>پیش‌فرض: `'PLANNED'` |
| `is_manual` | `boolean` | بله |  | اینکه دوره دستی ساخته شده یا از تقویم<br>پیش‌فرض: `false` |
| `notes` | `text` | — |  | یادداشت آزاد |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `msp_snapshots`

هر بار خواندن یک فایل MPP یک snapshot می‌سازد؛ مرجع نسخه‌ای برنامه.

`18` سطر · `17` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `msp_file_versions.project_id` |
| `file_version_id` | `bigint` | بله | FK | ارجاع به `msp_file_versions.id` |
| `snapshot_type` | `text` | بله |  | نوع snapshot<br>*مقادیر مجاز: TARGET / ACTUAL / RESCHEDULED* |
| `target_snapshot_id` | `bigint` | — | FK | ارجاع به `msp_snapshots.id` |
| `previous_snapshot_id` | `bigint` | — | FK | ارجاع به `msp_snapshots.id` |
| `source_filename` | `text` | — |  | نام فایلی که snapshot از آن ساخته شده |
| `source_version_number` | `integer` | — |  | شمارهٔ source version |
| `display_label` | `text` | — |  | برچسب display |
| `task_count` | `integer` | بله |  | تعداد task<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `parser_engine` | `text` | — |  | موتورِ parser |
| `parser_warnings` | `jsonb` | — |  | هشدارهای parser |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |
| `status_date_jalali` | `text` | — |  | تاریخ status date، شمسی |
| `reporting_period_id` | `bigint` | — |  | شناسهٔ reporting period |

### `msp_file_versions`

فایل‌های MPP بارگذاری‌شده و نسخه‌بندی آن‌ها.

`18` سطر · `20` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `version_number` | `integer` | بله |  | شمارهٔ version<br>*حداقل 0* |
| `original_filename` | `text` | بله |  | نام اصلی فایل بارگذاری‌شده |
| `stored_rel_path` | `text` | بله |  | مسیر نسبی فایل stored |
| `file_type` | `text` | بله |  | نوع file<br>پیش‌فرض: `'MPP'` |
| `detected_role` | `text` | بله |  | نقشِ detected<br>*مقادیر مجاز: MAIN / TARGET / ACTUAL / UNKNOWN*<br>پیش‌فرض: `'UNKNOWN'` |
| `size_bytes` | `bigint` | بله |  | حجم size به بایت<br>*حداقل 0* |
| `sha256` | `text` | بله |  | اثرانگشت فایل؛ همان فایل دوبار وارد نمی‌شود |
| `uploaded_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `uploaded_at` | `timestamp with time zone` | بله |  | زمانِ uploaded<br>پیش‌فرض: `now()` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |
| `source_deleted_at` | `timestamp with time zone` | — |  | زمانِ source deleted |
| `source_deleted_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `upload_role` | `text` | — |  | نقشِ upload<br>*مقادیر مجاز: PLAN / ACTUAL* |
| `plan_intent` | `text` | — |  | قصدِ بارگذاری این نسخه<br>*مقادیر مجاز: INITIAL_BASELINE / FORECAST_REVISION / APPROVED_REVISED_BASELINE* |
| `intended_period_id` | `bigint` | — |  | شناسهٔ intended period |
| `archived_at` | `timestamp with time zone` | — |  | زمانِ archived |
| `archived_by` | `uuid` | — | FK | ارجاع به `users.id` |

### `finance_mpp_source_versions`

نسخهٔ فایل MPP که سمت مالی به آن قفل شده؛ در هر لحظه فقط یکی «زنده» است.

> One row per distinct MPP file CONTENT that Finance has read. Finance-owned; needs no MSP table to be interpreted.

`3` سطر · `15` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `source_file_name_safe` | `text` | بله |  | نام source file، پاک‌سازی‌شده برای ذخیره روی دیسک<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `source_sha256` | `text` | بله |  | اثر انگشت SHA-256 فایل مبدأ؛ همان فایل دوبار وارد نمی‌شود |
| `source_size_bytes` | `bigint` | — |  | حجم source به بایت<br>*حداقل 0* |
| `reader_engine` | `text` | — |  | موتورِ reader |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: ready / failed* |
| `row_count` | `integer` | بله |  | تعداد row<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `imported_by` | `uuid` | — |  | کاربرِ imported |
| `imported_at` | `timestamp with time zone` | بله |  | زمانِ imported<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `reporting_date` | `date` | — |  | Status Date stated by the source schedule; NULL when the file states none. |
| `superseded_at` | `timestamp with time zone` | — |  | When this version stopped being one anybody may read. NULL means live. The rows and the hash are untouched: a superseded version is still the evidence of what was imported that day, and a report issued against it must stay explainable. |
| `superseded_by` | `uuid` | — | FK | ارجاع به `finance_mpp_source_versions.id` |
| `superseded_reason` | `text` | — |  | Why, in a sentence. A version marked superseded with no reason is a state somebody set rather than a decision somebody made. |

**API:** `GET /items-and-estimates`

### `msp_voice_report_audio`

فایل صوتی خام هر گزارش صوتی.

`2` سطر · `12` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `voice_report_id` | `bigint` | بله | FK | ارجاع به `msp_voice_reports.id` |
| `audio_rel_path` | `text` | بله |  | مسیر نسبی فایل audio |
| `audio_mime` | `text` | بله |  | نوع MIME فایل audio |
| `audio_size_bytes` | `bigint` | بله |  | حجم audio به بایت<br>*حداقل 0* |
| `audio_sha256` | `text` | بله |  | اثرانگشت SHA-256 audio |
| `audio_duration_ms` | `bigint` | — |  | مدت audio به میلی‌ثانیه<br>*حداقل 0* |
| `audio_source` | `text` | بله |  | منبعِ audio<br>*مقادیر مجاز: MANUAL_UPLOAD / LOCAL_TTS*<br>پیش‌فرض: `'MANUAL_UPLOAD'` |
| `label` | `text` | — |  | برچسب نمایشی |
| `uploaded_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `uploaded_at` | `timestamp with time zone` | بله |  | زمانِ uploaded<br>پیش‌فرض: `now()` |
| `tag` | `text` | — |  | برچسب فایل صوتی<br>*مقادیر مجاز: SHORT / FULL* |

### `msp_baseline_revisions`

بازنگری‌های خط مبنا (baseline) برنامه.

`1` سطر · `11` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `revision_number` | `integer` | بله |  | شمارهٔ revision<br>*حداقل 0* |
| `snapshot_id` | `bigint` | بله | FK | ارجاع به `msp_snapshots.id` |
| `effective_from_jalali` | `text` | بله |  | تاریخ effective from، شمسی |
| `label` | `text` | — |  | برچسب نمایشی |
| `approved_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `approved_at` | `timestamp with time zone` | — |  | زمانِ approved |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `msp_reporting_calendars`

تقویم گزارش‌دهی پروژه.

`1` سطر · `8` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `anchor_date_jalali` | `text` | بله |  | تاریخ anchor date، شمسی |
| `cadence_kind` | `text` | بله |  | نوع cadence<br>*مقادیر مجاز: DAYS / JALALI_MONTHS* |
| `cadence_interval` | `integer` | بله |  | طول هر دورهٔ گزارش‌دهی<br>*حداقل 0* |
| `horizon_date_jalali` | `text` | — |  | تاریخ horizon date، شمسی |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `msp_edit_sessions`

جلسهٔ ویرایش برنامه؛ تغییرات پیش از اعمال اینجا جمع می‌شود.

`1` سطر · `39` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `launch_token_hash` | `text` | بله |  | درهم‌سازی launch token (خود مقدار ذخیره نمی‌شود) |
| `bridge_token_hash` | `text` | — |  | درهم‌سازی bridge token (خود مقدار ذخیره نمی‌شود) |
| `user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `source_file_version_id` | `bigint` | بله | FK | ارجاع به `msp_file_versions.id` |
| `result_file_version_id` | `bigint` | — | FK | ارجاع به `msp_file_versions.id` |
| `requested_role` | `text` | — |  | نقشِ requested<br>*مقادیر مجاز: TARGET / ACTUAL* |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: created / claimed / downloaded / completed / expired / cancelled / failed*<br>پیش‌فرض: `'created'` |
| `source_sha256` | `text` | — |  | اثر انگشت SHA-256 فایل مبدأ؛ همان فایل دوبار وارد نمی‌شود |
| `result_sha256` | `text` | — |  | اثرانگشت SHA-256 result |
| `launch_expires_at` | `timestamp with time zone` | بله |  | زمانِ launch expires |
| `expires_at` | `timestamp with time zone` | بله |  | زمانِ expires |
| `claimed_at` | `timestamp with time zone` | — |  | زمانِ claimed |
| `downloaded_at` | `timestamp with time zone` | — |  | زمانِ downloaded |
| `completed_at` | `timestamp with time zone` | — |  | زمانِ completed |
| `cancelled_at` | `timestamp with time zone` | — |  | زمانِ cancelled |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |
| `failed_at` | `timestamp with time zone` | — |  | زمانِ failed |
| `fail_reason_code` | `text` | — |  | کد دلیل fail |
| `fail_detail` | `text` | — |  | جزئیات fail |
| `bridge_stage` | `text` | — |  | مرحلهٔ bridge |
| `bridge_stage_at` | `timestamp with time zone` | — |  | زمانِ bridge stage |
| `bridge_stage_detail` | `text` | — |  | جزئیات bridge stage |
| `pending_rel_path` | `text` | — |  | مسیر نسبی فایل pending |
| `pending_sha256` | `text` | — |  | اثرانگشت SHA-256 pending |
| `pending_size_bytes` | `bigint` | — |  | حجم pending به بایت |
| `pending_role` | `text` | — |  | نقشِ pending |
| `pending_at` | `timestamp with time zone` | — |  | زمانِ pending |
| `change_verdict` | `text` | — |  | حکمِ change |
| `change_summary` | `jsonb` | — |  | خلاصهٔ change |
| `review_state` | `text` | — |  | وضعیت review |
| `decided_at` | `timestamp with time zone` | — |  | زمانِ decided |
| `decided_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `last_heartbeat_at` | `timestamp with time zone` | — |  | زمانِ last heartbeat |
| `heartbeat_count` | `integer` | بله |  | تعداد heartbeat<br>پیش‌فرض: `0` |
| `stale_closed_at` | `timestamp with time zone` | — |  | زمانِ stale closed |
| `stale_closed_by` | `uuid` | — | FK | ارجاع به `users.id` |

### `msp_voice_reports`

گزارش پیشرفت صوتی ثبت‌شده در کارگاه.

`1` سطر · `17` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `reporting_period_id` | `bigint` | — | FK | ارجاع به `msp_reporting_periods.id` |
| `report_date_jalali` | `text` | — |  | تاریخ report date، شمسی |
| `summary_text` | `text` | بله |  | متن خلاصهٔ گزارش صوتی |
| `text_generator` | `text` | بله |  | متن خلاصه را چه چیزی تولید کرده<br>پیش‌فرض: `'DETERMINISTIC_TEXT_V1'` |
| `audio_rel_path` | `text` | — |  | مسیر نسبی فایل audio |
| `audio_mime` | `text` | — |  | نوع MIME فایل audio |
| `audio_size_bytes` | `bigint` | — |  | حجم audio به بایت<br>*حداقل 0* |
| `audio_sha256` | `text` | — |  | اثرانگشت SHA-256 audio |
| `audio_duration_ms` | `bigint` | — |  | مدت audio به میلی‌ثانیه<br>*حداقل 0* |
| `audio_source` | `text` | — |  | منبعِ audio<br>*مقادیر مجاز: MANUAL_UPLOAD / LOCAL_TTS* |
| `uploaded_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `uploaded_at` | `timestamp with time zone` | — |  | زمانِ uploaded |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `finance_mpp_currency_decisions`

تصمیم «تومان یا ریال» برای هر فایل MPP، همراه با شواهدی که تصمیم بر آن استوار است.

`1` سطر · `12` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `source_sha256` | `text` | بله |  | اثر انگشت SHA-256 فایل مبدأ؛ همان فایل دوبار وارد نمی‌شود |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `file_currency_symbol` | `text` | — |  | نماد پولی که خود فایل نشان می‌دهد (مثلاً «تومان») |
| `file_currency_code` | `text` | — |  | کد پولی که فایل اعلام می‌کند (مثلاً IRR) — می‌تواند با نماد نخواند |
| `amounts_are` | `text` | بله |  | تصمیم نهایی: اعداد فایل تومان‌اند یا ریال<br>*مقادیر مجاز: toman / rial / unknown* |
| `evidence` | `text` | بله |  | شواهدی که تصمیم بر آن استوار است<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `compared_with_sha256` | `text` | — |  | فایلی که برای این مقایسه مبنا بوده |
| `decided_by` | `uuid` | بله |  | کاربرِ decided |
| `decided_at` | `timestamp with time zone` | بله |  | زمانِ decided<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

---

## قیمت بازار و گوگل‌شیت

قیمت‌هایی که از گوگل‌شیت وارد می‌شوند، و هویت کالایی که قیمت به آن می‌چسبد.

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`price_observations`](#price-observations) | 14,260 | 39 | قیمت‌های واردشده از گوگل‌شیت. هر ردیفِ شیت یک مشاهده؛ جدول اصلی قیمت بازار. | 31 endpoint |
| [`provider_items`](#provider-items) | 10,421 | 35 | فهرست کالاهای هر تأمین‌کننده؛ هویتی که قیمت به آن می‌چسبد. | 31 endpoint |
| [`price_collection_runs`](#price-collection-runs) | 73 | 15 | هر بار اجرای ایمپورت قیمت، با آمار و وضعیت پایانی. | 17 endpoint |
| [`price_providers`](#price-providers) | 43 | 12 | تأمین‌کننده یا منبع قیمت. | 30 endpoint |
| [`provider_item_labels`](#provider-item-labels) | 3 | 23 | نام‌ها و مشخصات جایگزین یک کالا، به‌صورت تاریخچه‌دار. | 30 endpoint |
| [`provider_item_unit_factors`](#provider-item-unit-factors) | 1 | 17 | ضریب تبدیل واحد مخصوص یک کالای مشخص؛ دقیق‌ترین لایهٔ تبدیل. | 30 endpoint |
| [`price_collection_schedules`](#price-collection-schedules) | 0 | 10 | زمان‌بندی اجرای خودکار ایمپورت قیمت. | — |
| [`material_unit_settings`](#material-unit-settings) | 0 | 17 | واحد نمایشی انتخاب‌شده برای هر دستهٔ مصالح. | 17 endpoint |
| [`finance_price_categories`](#finance-price-categories) | 0 | 8 | دسته‌بندی‌های قیمت که در سطح سازمان یا پروژه تعریف شده‌اند. | 17 endpoint |
| [`price_resolution_policies`](#price-resolution-policies) | 0 | 11 | سیاست انتخاب قیمت وقتی چند مشاهده برای یک کالا وجود دارد. | — |
| [`provider_resource_mappings`](#provider-resource-mappings) | 0 | 10 | نگاشت کالای تأمین‌کننده به منبع مالی. | — |

### `price_observations`

قیمت‌های واردشده از گوگل‌شیت. هر ردیفِ شیت یک مشاهده؛ جدول اصلی قیمت بازار.

`14,260` سطر · `39` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `price_collection_runs.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `price_collection_runs.project_id` |
| `provider_id` | `uuid` | بله | FK | ارجاع به `price_providers.id` |
| `provider_item_id` | `uuid` | بله | FK | ارجاع به `provider_items.id` |
| `mapping_id` | `uuid` | — | FK | ارجاع به `provider_resource_mappings.id` |
| `resource_id` | `uuid` | — | FK | ارجاع به `finance_resources.id` |
| `collection_run_id` | `uuid` | — | FK | اجرای ایمپورتی که این ردیف را آورد |
| `raw_price` | `text` | بله |  | عدد قیمت، دقیقاً همان‌طور که در سلول شیت نوشته شده (متن)<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `normalized_price_irr` | `numeric(18,0)` | — |  | همان قیمت به ریال — برای محاسبه این را بخوانید، نه raw_price را |
| `source_currency` | `text` | بله |  | واحد پول مبدأ؛ شیت به تومان است<br>*مقادیر مجاز: IRR / TOMAN* |
| `source_unit` | `text` | — |  | واحد مبدأ، همان‌طور که در شیت آمده (مثلاً «کیلو») |
| `normalized_unit` | `text` | — |  | واحدِ normalized |
| `source_url` | `text` | — |  | نشانی source<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `observed_at` | `timestamp with time zone` | بله |  | زمان اعتبار قیمت |
| `fetched_at` | `timestamp with time zone` | بله |  | زمان واکشی از گوگل |
| `availability` | `text` | بله |  | موجود بودن کالا<br>*مقادیر مجاز: available / unavailable / unknown* |
| `validation_status` | `text` | بله |  | معتبر بودن ردیف<br>*مقادیر مجاز: pending / valid / needs_review / rejected* |
| `confidence_score` | `numeric(5,4)` | — |  | میزان اطمینان به درستی این مشاهده<br>*محدودهٔ مجاز: 0 تا 1* |
| `validation_reasons` | `jsonb` | بله |  | دلیل رد شدن ردیف<br>پیش‌فرض: `'[]'` |
| `raw_data` | `jsonb` | بله |  | کل ردیف خام شیت (JSON) برای ردیابی |
| `price_version_id` | `uuid` | — | FK | ارجاع به `price_versions.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `source_document_id` | `text` | — |  | شناسهٔ سند گوگل‌شیت |
| `source_worksheet` | `text` | — |  | نام تب شیت |
| `source_row_number` | `integer` | — |  | شمارهٔ ردیف در همان تب<br>*حداقل 0* |
| `workflow_date_raw` | `text` | — |  | تاریخ ردیف، خام |
| `workflow_date_jalali` | `text` | — |  | تاریخ ردیف، شمسی |
| `workflow_date_gregorian` | `date` | — |  | The day the price applied, canonically. NOT the day it was fetched: fetched_at is when BAMBO received the row and may be months later. A row that states no business date is rejected at import rather than given one. |
| `observed_at_source` | `text` | بله |  | زمانی که خود سند برای قیمت اعلام کرده<br>*مقادیر مجاز: provider / workflow_date / fetch_time / unknown*<br>پیش‌فرض: `'unknown'` |
| `secondary_price_irr` | `numeric(18,0)` | — |  | قیمت دوم ردیف (مثلاً نقدی در برابر مدت‌دار) به ریال<br>*حداقل 0* |
| `secondary_price_basis` | `text` | — |  | مبنای قیمت دوم |
| `row_fingerprint` | `text` | — |  | اثرانگشت ردیف؛ پایهٔ ON CONFLICT DO NOTHING که ایمپورت مجدد را بی‌خطر می‌کند |
| `product_external_id` | `text` | — |  | شناسهٔ کالا نزد تأمین‌کننده، در لحظهٔ ثبت |
| `product_name_snapshot` | `text` | — |  | What the product was CALLED when this price was read. Not a replacement for provider_item_id, which still says which listing it is today: a supplier renaming a product must not silently rewrite last month's evidence. NULL on rows imported before this revision -- see the NOT VALID constraint below. |
| `provider_name_snapshot` | `text` | — |  | نام تأمین‌کننده در لحظهٔ ثبت |
| `origin` | `text` | بله |  | مشاهده از کجا آمده — در دادهٔ فعلی: sheet یا manual<br>*مقادیر مجاز: sheet / manual*<br>پیش‌فرض: `'sheet'` |
| `entered_by` | `uuid` | — |  | کاربرِ entered |
| `reason` | `text` | — |  | دلیل ثبت‌شده برای این تغییر |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /items-and-estimates` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `provider_items`

فهرست کالاهای هر تأمین‌کننده؛ هویتی که قیمت به آن می‌چسبد.

`10,421` سطر · `35` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `price_providers.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `price_providers.project_id` |
| `provider_id` | `uuid` | بله | FK | ارجاع به `price_providers.id` |
| `external_id` | `text` | بله |  | شناسهٔ کالا نزد تأمین‌کننده<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `external_name` | `text` | بله |  | نام کالا، همان‌طور که تأمین‌کننده نوشته<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `category` | `text` | بله |  | دستهٔ مصالح (میلگرد، آجر، لوله، …)<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `url` | `text` | — |  | نشانی آگهی یا صفحهٔ کالا نزد تأمین‌کننده<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `source_unit` | `text` | — |  | واحد کالا، همان‌طور که در منبع نوشته شده |
| `metadata` | `jsonb` | بله |  | Uncommon, provider-specific or newly discovered attributes, and the original value of anything a typed column now mirrors. Not deleted and not demoted: it is the layer a sheet's next new column lands in before anybody declares what it means.<br>پیش‌فرض: `'{}'` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `true` |
| `inactive_reason` | `text` | — |  | دلیل غیرفعال شدن کالا |
| `source_worksheet` | `text` | — |  | تبِ شیتی که کالا از آن آمده |
| `product_code` | `text` | — |  | کد کالا |
| `manufacturer` | `text` | — |  | سازنده |
| `grade` | `text` | — |  | گرید یا رده (مثلاً A3 برای میلگرد) |
| `product_type` | `text` | — |  | نوع محصول |
| `dimensions_text` | `text` | — |  | Verbatim, e.g. «7×33×2.5». Never split into width, height and thickness: nobody has declared the order, and width-first versus thickness-first is the difference between a 7mm brick and a 2.5mm one. |
| `length_value` | `numeric(24,8)` | — |  | طول کالا |
| `length_m` | `numeric(24,8)` | — |  | A length normalised to metres at import. Since 0033 this is the ONLY place a length unit is recorded: length_unit said 'm' on every row that had one, and this column already carried the same number with its unit settled. |
| `width_value` | `numeric(24,8)` | — |  | عرض کالا |
| `height_value` | `numeric(24,8)` | — |  | ارتفاع کالا |
| `thickness_value` | `numeric(24,8)` | — |  | ضخامت کالا |
| `diameter_value` | `numeric(24,8)` | — |  | قطر کالا |
| `weight_basis` | `text` | — |  | What the weight is PER: branch, meter, piece, package, bag, total, or unknown. No sheet read so far states one, so 'unknown' is the honest value -- and an unknown basis must never be used in a conversion.<br>*مقادیر مجاز: branch / meter / piece / package / bag / total / unknown* |
| `branch_count` | `numeric(24,8)` | — |  | تعداد branch |
| `pieces_per_package` | `numeric(24,8)` | — |  | تعداد در هر بسته |
| `coverage_m2` | `numeric(24,8)` | — |  | سطح پوشش هر واحد، متر مربع |
| `volume_m3` | `numeric(24,8)` | — |  | حجم هر واحد، متر مکعب |
| `spec_source` | `text` | — |  | مشخصات فنی از کجا استخراج شده<br>*مقادیر مجاز: dedicated_column / approved_label / legacy_metadata / unresolved* |
| `spec_conflicts` | `jsonb` | — |  | تعارض بین مشخصات استخراج‌شده از منابع مختلف |
| `origin` | `text` | بله |  | sheet: the importer created this listing from the configured workbook. manual: a person entered it. The importer never writes a manual row -- its upsert is scoped to origin = 'sheet' -- so a re-import cannot overwrite or deactivate a price somebody recorded by hand.<br>*مقادیر مجاز: sheet / manual*<br>پیش‌فرض: `'sheet'` |
| `weight_kg` | `numeric(18,6)` | — |  | A product weight in kilograms, always. It replaced a weight_value/weight_unit pair in 0034; g was divided by 1000 and kg carried across unchanged. NULL where the source stated a bare number with no unit -- 84 Angle and Channel listings -- because a weight whose unit nobody wrote down cannot be converted, and the original pair is kept in metadata._legacyWeight for every row that had one. This is a PHYSICAL attribute and has nothing to do with source_unit, which is what a price is per. |
| `weight_value` | `numeric(18,6)` | — |  | Numeric weight as stated by the source sheet. Its unit may be unknown; weight_kg is independently derived only with unit evidence. Historical values were restored from metadata._legacyWeight, which remains intact. |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /items-and-estimates` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `price_collection_runs`

هر بار اجرای ایمپورت قیمت، با آمار و وضعیت پایانی.

`73` سطر · `15` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `price_providers.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `price_providers.project_id` |
| `provider_id` | `uuid` | بله | FK | ارجاع به `price_providers.id` |
| `started_at` | `timestamp with time zone` | بله |  | زمانِ started |
| `finished_at` | `timestamp with time zone` | — |  | زمانِ finished |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: running / succeeded / partially_succeeded / failed* |
| `total_items` | `integer` | بله |  | تعداد کل ردیف‌های خوانده‌شده در این اجرا<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `successful_items` | `integer` | بله |  | تعداد ردیف‌های پذیرفته‌شده<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `failed_items` | `integer` | بله |  | تعداد ردیف‌های ردشده<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `error_message` | `text` | — |  | خطای پایانی اجرا، اگر شکست خورده |
| `source_document_id` | `text` | — |  | شناسهٔ source document |
| `worksheet_report` | `jsonb` | بله |  | گزارش تب‌به‌تب همین اجرا<br>پیش‌فرض: `'{}'` |
| `rejected_items` | `integer` | بله |  | ردیف‌های ردشده به همراه دلیل<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `published_at` | `timestamp with time zone` | — |  | زمانِ published |

**API:** `GET /item-price-mappings/filters` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `price_providers`

تأمین‌کننده یا منبع قیمت.

`43` سطر · `12` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `name` | `text` | بله |  | نام<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `domain` | `text` | بله |  | دامنهٔ اینترنتی تأمین‌کننده<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `description` | `text` | — |  | شرح |
| `provider_type` | `text` | بله |  | نوع تأمین‌کننده<br>*مقادیر مجاز: website / spreadsheet / manual* |
| `crawl_method` | `text` | بله |  | روش گردآوری قیمت (شیت، خزش، دستی)<br>*مقادیر مجاز: json / html / browser / google_sheet / disabled / manual_entry* |
| `active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `false` |
| `default_interval_minutes` | `integer` | بله |  | فاصلهٔ پیش‌فرض اجرای خودکار، به دقیقه<br>*حداقل 0* |
| `last_success_at` | `timestamp with time zone` | — |  | زمانِ last success |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `provider_item_labels`

نام‌ها و مشخصات جایگزین یک کالا، به‌صورت تاریخچه‌دار.

`3` سطر · `23` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `finance_resources.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `finance_resources.project_id` |
| `provider_item_id` | `uuid` | بله | FK | ارجاع به `provider_items.id` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `label` | `text` | — |  | برچسب نمایشی<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `display_name` | `text` | — |  | نامی که به کاربر نشان داده می‌شود<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `category` | `text` | — |  | دسته‌بندی<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `product_type` | `text` | — |  | نوع محصول<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `source_unit` | `text` | — |  | واحد مبدأ<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `source_basis` | `text` | — |  | مبنای واحد مبدأ<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `target_unit` | `text` | — |  | واحد مقصد<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `finance_resource_id` | `uuid` | — | FK | ارجاع به `finance_resources.id` |
| `mapping_approved` | `boolean` | بله |  | اینکه این نگاشت تأیید انسانی گرفته یا نه<br>پیش‌فرض: `false` |
| `mapping_approved_by` | `uuid` | — |  | کاربرِ mapping approved |
| `mapping_approved_at` | `timestamp with time zone` | — |  | زمانِ mapping approved |
| `active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `true` |
| `notes` | `text` | — |  | یادداشت آزاد |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `superseded_at` | `timestamp with time zone` | — |  | زمان جایگزین‌شدن با نسخهٔ جدیدتر؛ خالی یعنی نسخهٔ جاری |
| `superseded_by` | `uuid` | — |  | سطری که جای این را گرفت |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `provider_item_unit_factors`

ضریب تبدیل واحد مخصوص یک کالای مشخص؛ دقیق‌ترین لایهٔ تبدیل.

`1` سطر · `17` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `provider_items.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `provider_items.project_id` |
| `provider_item_id` | `uuid` | بله | FK | ارجاع به `provider_items.id` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `from_unit` | `text` | بله |  | واحد مبدأ<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `to_unit` | `text` | بله |  | واحد مقصد<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `factor` | `numeric(24,8)` | بله |  | ضریب تبدیل — در این جدول نام ستون factor است، برخلاف finance_unit_conversion_rules<br>*حداقل 0* |
| `origin` | `text` | بله |  | ضریب از کجا آمده (اندازه‌گیری، اعلام فروشنده، …)<br>*مقادیر مجاز: sheet_attribute / manual* |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `superseded_at` | `timestamp with time zone` | — |  | زمان جایگزین‌شدن با نسخهٔ جدیدتر؛ خالی یعنی نسخهٔ جاری |
| `superseded_by` | `uuid` | — |  | سطری که جای این را گرفت |
| `factor_type` | `text` | — |  | نوع ضریب<br>*مقادیر مجاز: weight_per_piece / weight_per_branch / length_per_branch / mass_per_bag / area_per_piece / volume_per_piece / other* |
| `approved_by` | `uuid` | — |  | کاربرِ approved |
| `approved_at` | `timestamp with time zone` | — |  | زمانِ approved |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `price_collection_schedules`

زمان‌بندی اجرای خودکار ایمپورت قیمت.

`0` سطر · `10` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `price_providers.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `price_providers.project_id` |
| `provider_id` | `uuid` | بله | FK | ارجاع به `price_providers.id` |
| `category` | `text` | بله |  | دسته‌بندی<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `interval_minutes` | `integer` | بله |  | فاصلهٔ اجرا، به دقیقه<br>*حداقل 0* |
| `enabled` | `boolean` | بله |  | فعال بودن زمان‌بندی<br>پیش‌فرض: `false` |
| `next_run_at` | `timestamp with time zone` | — |  | زمانِ next run |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

### `material_unit_settings`

واحد نمایشی انتخاب‌شده برای هر دستهٔ مصالح.

`0` سطر · `17` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `provider_items.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `provider_items.project_id` |
| `category` | `text` | بله |  | دسته‌بندی<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `resource_id` | `uuid` | — | FK | ارجاع به `finance_resources.id` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `display_unit` | `text` | بله |  | واحدی که به کاربر نشان داده می‌شود<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `provider_item_id` | `uuid` | — | FK | ارجاع به `provider_items.id` |
| `source_unit` | `text` | — |  | واحد اصلی داده |
| `source_basis` | `text` | — |  | مبنای واحد اصلی |
| `conversion_mode` | `text` | — |  | روش رسیدن از واحد اصلی به واحد نمایشی<br>*مقادیر مجاز: dimension / product_factor / none* |
| `effective_from` | `date` | — |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `superseded_at` | `timestamp with time zone` | — |  | زمان جایگزین‌شدن با نسخهٔ جدیدتر؛ خالی یعنی نسخهٔ جاری |
| `superseded_by` | `uuid` | — |  | سطری که جای این را گرفت |

**API:** `GET /item-price-mappings/filters` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `finance_price_categories`

دسته‌بندی‌های قیمت که در سطح سازمان یا پروژه تعریف شده‌اند.

> Categories a person declared, with the level they belong to. It does NOT replace provider_items.category -- the chips are still counted from that column and a manual listing is born with its category there. This table holds the two things that column cannot: which level a category belongs to, and a category that exists before any product has been recorded in it.

`0` سطر · `8` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | — |  | پروژه‌ای که سطر به آن تعلق دارد |
| `scope_level` | `text` | بله |  | سطح تعریف دسته (سازمان یا پروژه)<br>*مقادیر مجاز: project / organization / global* |
| `category` | `text` | بله |  | دسته‌بندی |
| `label` | `text` | — |  | برچسب نمایشی |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /item-price-mappings/filters` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels`

### `price_resolution_policies`

سیاست انتخاب قیمت وقتی چند مشاهده برای یک کالا وجود دارد.

`0` سطر · `11` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `price_providers.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `price_providers.project_id` |
| `resource_id` | `uuid` | بله | FK | ارجاع به `finance_resources.id` |
| `strategy` | `text` | بله |  | راهبرد انتخاب قیمت میان چند مشاهده<br>*مقادیر مجاز: median / preferred_provider / weighted_provider / manual_approval* |
| `preferred_provider_id` | `uuid` | — | FK | ارجاع به `price_providers.id` |
| `provider_weights` | `jsonb` | بله |  | وزن هر تأمین‌کننده در انتخاب قیمت<br>پیش‌فرض: `'{}'` |
| `anomaly_threshold_percent` | `numeric(9,4)` | بله |  | درصد anomaly threshold<br>*حداقل 0* |
| `max_age_minutes` | `integer` | بله |  | حداکثر کهنگی قابل‌قبول قیمت، به دقیقه<br>*حداقل 0* |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

### `provider_resource_mappings`

نگاشت کالای تأمین‌کننده به منبع مالی.

`0` سطر · `10` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `finance_resources.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `finance_resources.project_id` |
| `provider_item_id` | `uuid` | بله | FK | ارجاع به `provider_items.id` |
| `finance_resource_id` | `uuid` | بله | FK | ارجاع به `finance_resources.id` |
| `confidence_score` | `numeric(5,4)` | بله |  | میزان اطمینان به درستی نگاشت<br>*محدودهٔ مجاز: 0 تا 1* |
| `approved` | `boolean` | بله |  | اینکه نگاشت تأیید انسانی گرفته یا نه<br>پیش‌فرض: `false` |
| `approved_by` | `uuid` | — |  | کاربرِ approved |
| `approved_at` | `timestamp with time zone` | — |  | زمانِ approved |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

---

## برآورد، منابع مالی و تبدیل واحد

از برنامه تا عدد ریالی: سطر برآورد، منبع مالی، قیمت و ضریب تبدیل واحد.

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`estimate_lines`](#estimate-lines) | 835 | 16 | سطرهای برآورد پروژه: چه کاری، چه مقدار، با چه واحدی. | 54 endpoint |
| [`estimate_line_source_completions`](#estimate-line-source-completions) | 289 | 16 | درصد تکمیل هر سطر برآورد، به تفکیک منبعِ مبدأ. | 14 endpoint |
| [`finance_resources`](#finance-resources) | 189 | 14 | منابع مالی پروژه (مصالح، نیرو، تجهیزات) با واحد پایه. | 69 endpoint |
| [`price_versions`](#price-versions) | 125 | 11 | قیمت‌های دستیِ نسخه‌دار برای منابع مالی — جدا از قیمت‌های گوگل‌شیت. | 24 endpoint |
| [`finance_item_price_mapping_components`](#finance-item-price-mapping-components) | 16 | 30 | اجزای قیمت یک سطر، وقتی از چند مصالح ساخته می‌شود. | 9 endpoint |
| [`finance_unit_conversion_issues`](#finance-unit-conversion-issues) | 6 | 20 | تبدیل‌هایی که قانون ندارند؛ ثبتِ پرسشِ بی‌پاسخ به‌جای حدس‌زدن. | 22 endpoint |
| [`finance_item_price_mappings`](#finance-item-price-mappings) | 6 | 21 | کدام آگهی بازار، کدام سطر برآورد را قیمت می‌دهد. | 6 endpoint |
| [`finance_unit_conversion_rules`](#finance-unit-conversion-rules) | 3 | 28 | قانون تبدیل واحد با دامنه و اولویت؛ مثلاً «کیلوگرم به شاخه» برای یک پروژه. | 22 endpoint |
| [`unit_conversions`](#unit-conversions) | 1 | 13 | تبدیل واحد عمومی پروژه. | 30 endpoint |
| [`estimate_revisions`](#estimate-revisions) | 0 | 10 | بازنگری دستی یک سطر برآورد؛ مقدار دستی بر مقدار محاسبه‌شده اولویت دارد. | 20 endpoint |

### `estimate_lines`

سطرهای برآورد پروژه: چه کاری، چه مقدار، با چه واحدی.

`835` سطر · `16` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `finance_resources.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `finance_resources.project_id` |
| `resource_id` | `uuid` | بله | FK | ارجاع به `finance_resources.id` |
| `activity_external_id` | `text` | — |  | شناسهٔ activity external |
| `assignment_external_id` | `text` | — |  | شناسهٔ assignment external |
| `original_quantity` | `numeric(18,4)` | — |  | مقدار original |
| `original_unit_price_irr` | `numeric(18,0)` | — |  | مبلغ original unit price به ریال |
| `source` | `text` | بله |  | سطر از کجا آمده — در دادهٔ فعلی: progress_feed یا manual_entry<br>*مقادیر مجاز: progress_feed / excel_import / manual_entry* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `deleted_at` | `timestamp with time zone` | — |  | زمان حذف نرم؛ خالی یعنی سطر فعال است |
| `deleted_by` | `uuid` | — |  | کاربرِ deleted |
| `source_assignment_uid` | `integer` | — |  | The MPP Assignment UID this line came from, or NULL when the line was not read from a file. NOT assignment_external_id: that column holds a legacy value. |
| `source_task_uid` | `integer` | — |  | شناسهٔ source task در فایل مبدأ |
| `legacy_status` | `text` | — |  | NULL when the row is MPP-derived. 'legacy_unlinked' when it names no MPP assignment or task and is therefore kept out of MPP-derived totals. 'approved_exception' when somebody decided such a row counts anyway. It describes the ABSENCE of schedule provenance and may never sit on a row that has some.<br>*مقادیر مجاز: legacy_unlinked / approved_exception* |

**API:** `GET /activities` · `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /estimate-lines/{lineId}/progress-overrides` · `GET /estimate-lines` · `GET /extractions/{draftId}` · `GET /extractions` · `GET /invoices/{invoiceId}` · `GET /invoices` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /items-and-estimates` · `GET /overview` · `GET /progress-snapshots/{snapshotId}/feed` · `GET /progress-snapshots/{snapshotId}` · `GET /progress-snapshots` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `PATCH /invoices/{invoiceId}` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /estimate-lines/{lineId}/progress-override` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions` · `POST /invoices/{invoiceId}/confirm` · `POST /invoices/{invoiceId}/corrective` · `POST /invoices/{invoiceId}/void` · `POST /invoices` · `POST /report-snapshots` · `POST /resources`

### `estimate_line_source_completions`

درصد تکمیل هر سطر برآورد، به تفکیک منبعِ مبدأ.

> The original quantity and rate a mapped estimate line was created without, recorded from the exact source version it was mapped from. One row per line, ever: the effective original is the line's own column when it has one and this otherwise.

`289` سطر · `16` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `estimate_line_id` | `uuid` | بله | FK | ارجاع به `estimate_lines.id` |
| `source_version_id` | `uuid` | بله | FK | ارجاع به `finance_mpp_source_versions.id` |
| `source_sha256` | `text` | بله |  | اثر انگشت SHA-256 فایل مبدأ؛ همان فایل دوبار وارد نمی‌شود |
| `source_task_uid` | `integer` | — |  | شناسهٔ source task در فایل مبدأ |
| `source_assignment_uid` | `integer` | بله |  | شناسهٔ source assignment در فایل مبدأ |
| `source_resource_uid` | `integer` | — |  | شناسهٔ source resource در فایل مبدأ |
| `quantity` | `numeric` | — |  | مقدار |
| `quantity_unit` | `text` | — |  | واحدِ quantity |
| `unit_price_irr` | `numeric` | — |  | مبلغ unit price به ریال |
| `currency` | `text` | بله |  | واحد پول<br>پیش‌فرض: `'IRR'` |
| `basis` | `text` | بله |  | مبنایی که درصد تکمیل بر آن حساب شده |
| `completed_by` | `uuid` | بله |  | کاربرِ completed |
| `completed_at` | `timestamp with time zone` | بله |  | زمانِ completed<br>پیش‌فرض: `now()` |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping`

### `finance_resources`

منابع مالی پروژه (مصالح، نیرو، تجهیزات) با واحد پایه.

`189` سطر · `14` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `resource_type` | `text` | بله |  | نوع resource<br>*مقادیر مجاز: material / labor / equipment / general_cost* |
| `code` | `text` | بله |  | کد |
| `title` | `text` | بله |  | عنوان |
| `base_unit` | `text` | — |  | واحدِ base |
| `dimension` | `text` | — |  | بُعد فیزیکی واحد منبع (جرم، طول، زمان، …) |
| `external_resource_id` | `text` | — |  | شناسهٔ external resource |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `deleted_at` | `timestamp with time zone` | — |  | زمان حذف نرم؛ خالی یعنی سطر فعال است |
| `deleted_by` | `uuid` | — |  | کاربرِ deleted |
| `source_resource_uid` | `integer` | — |  | The MPP Resource UID this item came from, or NULL when it did not come from a file. NOT external_resource_id: that column holds a legacy value with a different meaning. |

**API:** `GET /activities` · `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /estimate-lines` · `GET /extractions/{draftId}` · `GET /extractions` · `GET /invoices/{invoiceId}` · `GET /invoices` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `GET /items-and-estimates` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `GET /overview` · `GET /price-history` · `GET /prices/current` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}/prices` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `PATCH /invoices/{invoiceId}` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions` · `POST /invoices/{invoiceId}/confirm` · `POST /invoices/{invoiceId}/corrective` · `POST /invoices/{invoiceId}/void` · `POST /invoices` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels` · `POST /report-snapshots` · `POST /resources/{resourceId}/prices` · `POST /resources`

### `price_versions`

قیمت‌های دستیِ نسخه‌دار برای منابع مالی — جدا از قیمت‌های گوگل‌شیت.

`125` سطر · `11` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `finance_resources.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `finance_resources.project_id` |
| `resource_id` | `uuid` | بله | FK | ارجاع به `finance_resources.id` |
| `scope_kind` | `text` | بله |  | نوع scope<br>*مقادیر مجاز: organization / project* |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `unit_price_irr` | `numeric(18,0)` | بله |  | مبلغ unit price به ریال<br>*حداقل 0* |
| `effective_from` | `date` | بله |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `reason` | `text` | — |  | Why this rate was set, when somebody chose to say. Optional: created_by and created_at are recorded on every version and are the evidence that a revision happened. An empty string is still refused -- absent and blank are different statements and only one of them is honest.<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /activities` · `GET /estimate-lines` · `GET /overview` · `GET /price-history` · `GET /prices/current` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}/prices` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /report-snapshots` · `POST /resources/{resourceId}/prices` · `POST /resources`

### `finance_item_price_mapping_components`

اجزای قیمت یک سطر، وقتی از چند مصالح ساخته می‌شود.

`16` سطر · `30` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `component_id` | `uuid` | بله |  | شناسهٔ component |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `estimate_line_id` | `uuid` | بله |  | شناسهٔ estimate line |
| `finance_resource_id` | `uuid` | — |  | شناسهٔ finance resource |
| `provider_item_id` | `uuid` | بله |  | شناسهٔ provider item |
| `category` | `text` | — |  | دسته‌بندی |
| `provider_id` | `uuid` | — |  | شناسهٔ provider |
| `product_type` | `text` | — |  | نوع محصول این جزء |
| `selected_unit` | `text` | بله |  | واحد انتخاب‌شده برای این جزء |
| `source_price_unit` | `text` | — |  | واحد قیمت در منبع |
| `source_price_basis` | `text` | — |  | مبنای قیمت در منبع |
| `usage_mode` | `text` | — |  | نحوهٔ مصرف این جزء در سطر برآورد<br>*مقادیر مجاز: per_msp_unit / total_quantity* |
| `usage_quantity_decimal` | `numeric(24,8)` | — |  | مقدار مصرف این جزء |
| `usage_unit` | `text` | — |  | واحد مصرف این جزء |
| `conversion_status` | `text` | بله |  | وضعیت تبدیل واحد این جزء<br>*مقادیر مجاز: automatic / factor / incompatible / unknown* |
| `conversion_factor_id` | `uuid` | — | FK | ارجاع به `provider_item_unit_factors.id` |
| `converted_daily_unit_price_irr` | `numeric(24,4)` | — |  | مبلغ converted daily unit price به ریال |
| `component_quantity_decimal` | `numeric(24,8)` | — |  | مقدار جزء پس از تبدیل واحد |
| `component_daily_cost_irr` | `numeric(24,4)` | — |  | مبلغ component daily cost به ریال |
| `status` | `text` | — |  | وضعیت سطر |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `true` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `effective_from` | `date` | بله |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `superseded_at` | `timestamp with time zone` | — |  | زمان جایگزین‌شدن با نسخهٔ جدیدتر؛ خالی یعنی نسخهٔ جاری |
| `superseded_by` | `uuid` | — |  | سطری که جای این را گرفت |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components`

### `finance_unit_conversion_issues`

تبدیل‌هایی که قانون ندارند؛ ثبتِ پرسشِ بی‌پاسخ به‌جای حدس‌زدن.

> Unit mismatches that blocked a daily estimate, as records rather than as messages. Append-and-update, never delete: a resolved issue is the evidence that somebody answered the question, and deleting it loses why the figure changed.

`6` سطر · `20` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `estimate_line_id` | `uuid` | — |  | شناسهٔ estimate line |
| `finance_resource_id` | `uuid` | — |  | شناسهٔ finance resource |
| `provider_item_id` | `uuid` | — |  | شناسهٔ provider item |
| `source_task_uid` | `integer` | — |  | شناسهٔ source task در فایل مبدأ |
| `source_assignment_uid` | `integer` | — |  | شناسهٔ source assignment در فایل مبدأ |
| `source_resource_uid` | `integer` | — |  | شناسهٔ source resource در فایل مبدأ |
| `resource_unit` | `text` | — |  | واحدِ resource |
| `daily_price_unit` | `text` | — |  | واحدِ daily price |
| `error_code` | `text` | بله |  | کد error |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: open / resolved / obsolete*<br>پیش‌فرض: `'open'` |
| `first_detected_at` | `timestamp with time zone` | بله |  | زمانِ first detected<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `last_detected_at` | `timestamp with time zone` | بله |  | زمانِ last detected<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `occurrence_count` | `integer` | بله |  | تعداد occurrence<br>*حداقل 0*<br>پیش‌فرض: `1` |
| `resolved_at` | `timestamp with time zone` | — |  | زمانِ resolved |
| `resolved_by` | `uuid` | — |  | کاربرِ resolved |
| `resolution_rule_id` | `uuid` | — | FK | ارجاع به `finance_unit_conversion_rules.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /finance-settings/unit-conversion-issues` · `GET /finance-settings/unit-conversions/{ruleId}/history` · `GET /finance-settings/unit-conversions/{ruleId}/preview` · `GET /finance-settings/unit-conversions/{ruleId}` · `GET /finance-settings/unit-conversions` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /finance-settings/unit-conversions/{ruleId}/approve` · `POST /finance-settings/unit-conversions/{ruleId}/supersede` · `POST /finance-settings/unit-conversions`

### `finance_item_price_mappings`

کدام آگهی بازار، کدام سطر برآورد را قیمت می‌دهد.

`6` سطر · `21` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `estimate_line_id` | `uuid` | — |  | شناسهٔ estimate line |
| `finance_resource_id` | `uuid` | — |  | شناسهٔ finance resource |
| `source_assignment_uid` | `integer` | — |  | شناسهٔ source assignment در فایل مبدأ |
| `source_task_uid` | `integer` | — |  | شناسهٔ source task در فایل مبدأ |
| `source_resource_uid` | `integer` | — |  | شناسهٔ source resource در فایل مبدأ |
| `provider_item_id` | `uuid` | بله |  | شناسهٔ provider item |
| `selected_unit` | `text` | بله |  | واحدی که برای قیمت‌گذاری انتخاب شده |
| `source_price_unit` | `text` | — |  | واحد قیمت در منبع |
| `source_price_basis` | `text` | — |  | مبنای قیمت در منبع |
| `conversion_status` | `text` | بله |  | وضعیت تبدیل واحد این نگاشت<br>*مقادیر مجاز: automatic / factor / incompatible / unknown* |
| `conversion_factor_id` | `uuid` | — | FK | ارجاع به `provider_item_unit_factors.id` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `effective_from` | `date` | بله |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `superseded_at` | `timestamp with time zone` | — |  | زمان جایگزین‌شدن با نسخهٔ جدیدتر؛ خالی یعنی نسخهٔ جاری |
| `superseded_by` | `uuid` | — |  | سطری که جای این را گرفت |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |

**API:** `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /item-price-mappings/candidates` · `GET /items-and-estimates` · `POST /estimate-lines/{lineId}/price-mapping`

### `finance_unit_conversion_rules`

قانون تبدیل واحد با دامنه و اولویت؛ مثلاً «کیلوگرم به شاخه» برای یک پروژه.

> Scoped, approved, versioned statements of the form `1 from_unit = factor to_unit`. The price conversion is DERIVED from this in the domain, never stored, so no call site can get the direction backwards. Formula-ready and formula-executing are different things: conversion_method admits formula and nothing evaluates one.

`3` سطر · `28` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | — |  | پروژه‌ای که سطر به آن تعلق دارد |
| `provider_item_id` | `uuid` | — |  | شناسهٔ provider item |
| `provider_id` | `uuid` | — |  | شناسهٔ provider |
| `category` | `text` | — |  | دسته‌بندی |
| `scope_type` | `text` | بله |  | How broadly this rule may be believed. `global` is not a synonym for safe: kg to ton is a fact about units and is safe everywhere; branch to kg is a fact about one product and must be scoped to it.<br>*مقادیر مجاز: global / organization / project / provider / category / provider_item* |
| `from_unit` | `text` | بله |  | واحد مبدأ |
| `to_unit` | `text` | بله |  | واحد مقصد |
| `conversion_method` | `text` | بله |  | روش تبدیل: ضریب ثابت یا فرمول<br>*مقادیر مجاز: factor / formula*<br>پیش‌فرض: `'factor'` |
| `factor_value` | `numeric(32,12)` | — |  | ضریب تبدیل — نام ستون factor_value است نه factor؛ خواندن با کلید اشتباه قانون را بی‌اثر می‌کند<br>*حداقل 0* |
| `formula_definition` | `jsonb` | — |  | تعریف فرمول تبدیل، وقتی ضریب ثابت کافی نیست |
| `formula_schema_version` | `text` | — |  | نسخهٔ ساختار فرمول |
| `direction_definition` | `text` | بله |  | اینکه قانون یک‌طرفه است یا دوطرفه<br>پیش‌فرض: `'one_from_unit_equals_factor_to_unit'` |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: draft / approved / rejected / superseded*<br>پیش‌فرض: `'draft'` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `effective_from` | `date` | بله |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `effective_to` | `date` | — |  | تاریخی که اعتبار این مقدار تا آن است |
| `supersedes_rule_id` | `uuid` | — | FK | ارجاع به `finance_unit_conversion_rules.id` |
| `evidence_source` | `text` | — |  | مستندی که ضریب بر آن استوار است |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `approved_by` | `uuid` | — |  | کاربرِ approved |
| `approved_at` | `timestamp with time zone` | — |  | زمانِ approved |
| `product_dependent_acknowledged` | `boolean` | بله |  | True when this rule crosses dimensions at a scope wider than one listing and a person stated, in the request that created it, that they know the crossing depends on the product. False is the ordinary case and the only value a same-dimension or listing-scoped rule ever carries.<br>پیش‌فرض: `false` |
| `product_dependent_acknowledged_by` | `uuid` | — |  | Who made the claim. The point of the acknowledgement is that it has a name on it: a flag nobody is attached to is indistinguishable from a default. |
| `product_dependent_acknowledged_at` | `timestamp with time zone` | — |  | زمانِ product dependent acknowledged |

**API:** `GET /estimate-lines/{lineId}/price-component-preview` · `GET /estimate-lines/{lineId}/price-mapping/components/history` · `GET /estimate-lines/{lineId}/price-mapping/components` · `GET /estimate-lines/{lineId}/price-mapping/history` · `GET /estimate-lines/{lineId}/price-mapping` · `GET /estimate-lines/{lineId}/price-preview` · `GET /estimate-lines/{lineId}/price-total-preview` · `GET /finance-settings/unit-conversion-issues` · `GET /finance-settings/unit-conversions/{ruleId}/history` · `GET /finance-settings/unit-conversions/{ruleId}/preview` · `GET /finance-settings/unit-conversions/{ruleId}` · `GET /finance-settings/unit-conversions` · `GET /item-price-mappings/candidates` · `GET /item-price-mappings/filters` · `GET /item-price-mappings/status` · `PATCH /estimate-lines/{lineId}/price-mapping/components/{componentId}` · `POST /estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` · `POST /estimate-lines/{lineId}/price-mapping/components` · `POST /estimate-lines/{lineId}/price-mapping` · `POST /finance-settings/unit-conversions/{ruleId}/approve` · `POST /finance-settings/unit-conversions/{ruleId}/supersede` · `POST /finance-settings/unit-conversions`

### `unit_conversions`

تبدیل واحد عمومی پروژه.

`1` سطر · `13` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `scope_kind` | `text` | بله |  | دامنهٔ اعتبار تبدیل<br>*مقادیر مجاز: organization / project* |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `source_unit` | `text` | بله |  | واحد مبدأ |
| `target_unit` | `text` | بله |  | واحد مقصد |
| `dimension` | `text` | بله |  | بُعد فیزیکی (جرم، طول، زمان، …)؛ عبور از بُعد بدون قانون مجاز نیست |
| `factor` | `numeric(24,8)` | بله |  | ضریب تبدیل<br>*حداقل 0* |
| `effective_from` | `date` | بله |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /item-price-mappings/filters` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `GET /overview` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /unit-conversions` · `PATCH /unit-conversions/{conversionId}` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels` · `POST /report-snapshots` · `POST /unit-conversions`

### `estimate_revisions`

بازنگری دستی یک سطر برآورد؛ مقدار دستی بر مقدار محاسبه‌شده اولویت دارد.

`0` سطر · `10` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `estimate_lines.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `estimate_lines.project_id` |
| `estimate_line_id` | `uuid` | بله | FK | ارجاع به `estimate_lines.id` |
| `revision` | `integer` | بله |  | شمارهٔ بازنگری<br>*حداقل 0* |
| `previous_quantity` | `numeric(18,4)` | — |  | مقدار previous |
| `new_quantity` | `numeric(18,4)` | — |  | مقدار new |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /activities` · `GET /estimate-lines` · `GET /overview` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /report-snapshots` · `POST /resources`

---

## فاکتور و استخراج هوش مصنوعی

سند واقعی خرج: پیوست، استخراج، پیش‌نویس و فاکتور تأییدشده.

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`extraction_drafts`](#extraction-drafts) | 56 | 15 | پیش‌نویس استخراج هوش مصنوعی از پیوست؛ تا تأیید نشود هیچ اثر مالی ندارد. | 7 endpoint |
| [`finance_attachments`](#finance-attachments) | 16 | 16 | فایل‌های پیوست مالی (تصویر فاکتور، صوت، سند). | 11 endpoint |
| [`finance_import_batches`](#finance-import-batches) | 13 | 12 | دسته‌های واردات داده به بخش مالی. | — |
| [`invoices`](#invoices) | 2 | 26 | فاکتورها. | 34 endpoint |
| [`invoice_lines`](#invoice-lines) | 2 | 18 | سطرهای هر فاکتور. | 35 endpoint |
| [`finance_invoice_counters`](#finance-invoice-counters) | 1 | 3 | شمارندهٔ شمارهٔ فاکتور برای هر پروژه. | — |

### `extraction_drafts`

پیش‌نویس استخراج هوش مصنوعی از پیوست؛ تا تأیید نشود هیچ اثر مالی ندارد.

`56` سطر · `15` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `finance_attachments.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `finance_attachments.project_id` |
| `attachment_id` | `uuid` | بله | FK | پیوستی که از آن استخراج شده |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0* |
| `review_status` | `text` | بله |  | وضعیت بازبینی انسانی<br>*مقادیر مجاز: awaitingReview / accepted / rejected* |
| `provider_adapter` | `text` | بله |  | کدام مسیر استخراج این سطر را ساخته (تصویر یا صوت) |
| `extracted_fields` | `jsonb` | بله |  | فیلدهای استخراج‌شده (JSONB: آرایه‌ای از key / extractedValue / confidence / editedByUser / confirmedValue) — افزودن فیلد تازه مهاجرت نمی‌خواهد |
| `confirmed_fields` | `jsonb` | — |  | مقادیری که انسان تأیید کرده |
| `financial_effect_irr` | `numeric(18,0)` | بله |  | اثر مالی پیش‌نویس؛ CHECK آن را صفر نگه می‌دارد تا پیش‌نویس هرگز پول جابه‌جا نکند<br>*همیشه برابر 0*<br>پیش‌فرض: `0` |
| `submitted_by` | `uuid` | بله |  | کاربرِ submitted |
| `confirmed_by` | `uuid` | — |  | کاربرِ confirmed |
| `confirmed_at` | `timestamp with time zone` | — |  | زمانِ confirmed |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /extractions/{draftId}` · `GET /extractions` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions`

### `finance_attachments`

فایل‌های پیوست مالی (تصویر فاکتور، صوت، سند).

`16` سطر · `16` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `invoices.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `invoices.project_id` |
| `invoice_id` | `uuid` | — | FK | ارجاع به `invoices.id` |
| `logical_type` | `text` | بله |  | نقش منطقی فایل (فاکتور، صوت، سند)<br>*مقادیر مجاز: invoice_image / invoice_voice* |
| `original_name_safe` | `text` | بله |  | نام اصلی فایل، پاک‌سازی‌شده |
| `stored_name` | `text` | بله |  | نامی که فایل با آن ذخیره شده |
| `mime_type` | `text` | بله |  | نوع MIME فایل |
| `size_bytes` | `bigint` | بله |  | حجم size به بایت<br>*حداقل 0* |
| `sha256` | `text` | بله |  | اثرانگشت فایل؛ فایل تکراری دوبار ذخیره نمی‌شود |
| `storage_key` | `text` | بله |  | کلید فایل در فضای ذخیره‌سازی |
| `processing_status` | `text` | بله |  | وضعیت پردازش فایل<br>*مقادیر مجاز: uploaded / processing / ready / failed* |
| `uploaded_by` | `uuid` | بله |  | کاربرِ uploaded |
| `uploaded_at` | `timestamp with time zone` | بله |  | زمانِ uploaded<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `deleted_at` | `timestamp with time zone` | — |  | زمان حذف نرم؛ خالی یعنی سطر فعال است |
| `deleted_by` | `uuid` | — |  | کاربرِ deleted |

**API:** `GET /extractions/{draftId}` · `GET /extractions` · `GET /files/{fileId}/content` · `GET /files/{fileId}` · `GET /files` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions` · `POST /files`

### `finance_import_batches`

دسته‌های واردات داده به بخش مالی.

`13` سطر · `12` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `import_kind` | `text` | بله |  | نوع واردات<br>*مقادیر مجاز: estimate / prices* |
| `currency_unit` | `text` | — |  | واحد پول فایل واردشده<br>*مقادیر مجاز: IRR / TOMAN* |
| `file_sha256` | `text` | بله |  | اثرانگشت SHA-256 file |
| `normalized_rows` | `jsonb` | بله |  | ردیف‌های استانداردشدهٔ فایل |
| `validation_errors` | `jsonb` | بله |  | خطاهای اعتبارسنجی فایل |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: previewed / committed* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `committed_at` | `timestamp with time zone` | — |  | زمانِ committed |

### `invoices`

فاکتورها.

`2` سطر · `26` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `invoices.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `invoices.project_id` |
| `invoice_number` | `text` | — |  | شمارهٔ فاکتور |
| `invoice_date` | `date` | بله |  | تاریخ فاکتور |
| `vendor_name` | `text` | بله |  | نام فروشنده |
| `description` | `text` | — |  | شرح |
| `source` | `text` | بله |  | فاکتور از کجا آمده (دستی، استخراج، واردات)<br>*مقادیر مجاز: manual / image / voice / corrective / reversal* |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: draft / awaitingConfirmation / confirmed / voided / corrected* |
| `discount_irr` | `numeric(18,0)` | بله |  | مبلغ discount به ریال<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `tax_irr` | `numeric(18,0)` | بله |  | مبلغ tax به ریال<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `shipping_irr` | `numeric(18,0)` | بله |  | مبلغ shipping به ریال<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `other_costs_irr` | `numeric(18,0)` | بله |  | مبلغ other costs به ریال<br>*حداقل 0*<br>پیش‌فرض: `0` |
| `final_amount_irr` | `numeric(18,0)` | — |  | مبلغ final amount به ریال |
| `financial_effect_sign` | `smallint` | بله |  | جهت اثر مالی: فاکتور عادی مثبت، اصلاحیه منفی<br>پیش‌فرض: `1` |
| `idempotency_key` | `text` | — |  | کلید یکتاسازی؛ ارسال دوبارهٔ یک درخواست، فاکتور دوم نمی‌سازد |
| `source_file_sha256` | `text` | — |  | اثرانگشت فایل مبدأ فاکتور |
| `original_invoice_id` | `uuid` | — | FK | ارجاع به `invoices.id` |
| `version` | `integer` | بله |  | شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود<br>*حداقل 0*<br>پیش‌فرض: `1` |
| `submitted_by` | `uuid` | بله |  | کاربرِ submitted |
| `confirmed_by` | `uuid` | — |  | کاربرِ confirmed |
| `confirmed_at` | `timestamp with time zone` | — |  | زمانِ confirmed |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `confirmation_idempotency_key` | `text` | — |  | همان کلید، برای مرحلهٔ تأیید |
| `invoice_seq` | `integer` | بله |  | The invoice's number within its project: 1 for the first invoice of a project and one more for each after it, allocated by finance_invoice_counters. Every invoice has one, including a reversal -- a void is its own document and carries its own number. |

**API:** `GET /activities` · `GET /estimate-lines` · `GET /extractions/{draftId}` · `GET /extractions` · `GET /invoices/{invoiceId}` · `GET /invoices` · `GET /overview` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /invoices/{invoiceId}` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions` · `POST /invoices/{invoiceId}/confirm` · `POST /invoices/{invoiceId}/corrective` · `POST /invoices/{invoiceId}/void` · `POST /invoices` · `POST /report-snapshots` · `POST /resources`

### `invoice_lines`

سطرهای هر فاکتور.

`2` سطر · `18` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `estimate_lines.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `estimate_lines.project_id` |
| `invoice_id` | `uuid` | بله | FK | ارجاع به `invoices.id` |
| `estimate_line_id` | `uuid` | — | FK | ارجاع به `estimate_lines.id` |
| `resource_id` | `uuid` | بله | FK | ارجاع به `finance_resources.id` |
| `quantity` | `numeric(18,4)` | — |  | مقدار |
| `unit` | `text` | — |  | واحد |
| `unit_price_snapshot_irr` | `numeric(18,0)` | — |  | مبلغ unit price snapshot به ریال |
| `raw_amount_irr` | `numeric(18,0)` | بله |  | مبلغ raw amount به ریال |
| `allocated_discount_irr` | `numeric(18,0)` | بله |  | مبلغ allocated discount به ریال<br>پیش‌فرض: `0` |
| `allocated_tax_irr` | `numeric(18,0)` | بله |  | مبلغ allocated tax به ریال<br>پیش‌فرض: `0` |
| `allocated_shipping_irr` | `numeric(18,0)` | بله |  | مبلغ allocated shipping به ریال<br>پیش‌فرض: `0` |
| `allocated_other_costs_irr` | `numeric(18,0)` | بله |  | مبلغ allocated other costs به ریال<br>پیش‌فرض: `0` |
| `final_line_amount_irr` | `numeric(18,0)` | بله |  | مبلغ final line amount به ریال |
| `price_version_id` | `uuid` | — | FK | ارجاع به `price_versions.id` |
| `description` | `text` | — |  | شرح |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /activities` · `GET /estimate-lines` · `GET /extractions/{draftId}` · `GET /extractions` · `GET /invoices/{invoiceId}` · `GET /invoices` · `GET /items-and-estimates` · `GET /overview` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}` · `GET /resources` · `GET /task-resource-mappings` · `PATCH /invoices/{invoiceId}` · `PATCH /resources/{resourceId}` · `POST /activities` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions` · `POST /invoices/{invoiceId}/confirm` · `POST /invoices/{invoiceId}/corrective` · `POST /invoices/{invoiceId}/void` · `POST /invoices` · `POST /report-snapshots` · `POST /resources`

### `finance_invoice_counters`

شمارندهٔ شمارهٔ فاکتور برای هر پروژه.

> One row per project holding the next invoice number to hand out. Allocation is an INSERT ... ON CONFLICT DO UPDATE ... RETURNING inside the transaction that writes the invoice, so a rolled back invoice releases its number and leaves no gap.

`1` سطر · `3` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `next_number` | `integer` | بله |  | شمارهٔ next<br>*حداقل 1* |

---

## پیشرفت، گزارش و حسابرسی

آنچه واقعاً اجرا شده، و ردِ هر تغییر.

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`audit_logs`](#audit-logs) | 149 | 8 | لاگ حسابرسی عمومی سامانه. | — |
| [`finance_audit_events`](#finance-audit-events) | 55 | 11 | رویدادهای حسابرسی بخش مالی؛ فقط‌افزودنی. | 72 endpoint |
| [`report_snapshots`](#report-snapshots) | 16 | 15 | گزارش‌های ذخیره‌شده؛ عددِ لحظهٔ گرفتن گزارش را نگه می‌دارد. | 10 endpoint |
| [`progress_snapshot_refs`](#progress-snapshot-refs) | 4 | 14 | ارجاع به snapshot پیشرفتی که گزارش بر آن بنا شده. | 15 endpoint |
| [`finance_project_settings`](#finance-project-settings) | 1 | 10 | تنظیمات مالی پروژه، به‌صورت تاریخچهٔ فقط‌افزودنی. | 14 endpoint |
| [`finance_alembic_version`](#finance-alembic-version) | 1 | 1 | شمارهٔ مهاجرت جاری دیتابیس مالی. | — |
| [`progress_overrides`](#progress-overrides) | 0 | 10 | اصلاح دستی پیشرفت یک تخصیص. | 15 endpoint |

### `audit_logs`

لاگ حسابرسی عمومی سامانه.

`149` سطر · `8` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | — |  | پروژه‌ای که سطر به آن تعلق دارد |
| `user_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `action` | `text` | بله |  | کاری که ثبت شده |
| `target_type` | `text` | — |  | نوع target |
| `target_id` | `text` | — |  | شناسهٔ target |
| `meta` | `jsonb` | — |  | دادهٔ جانبی رویداد |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `finance_audit_events`

رویدادهای حسابرسی بخش مالی؛ فقط‌افزودنی.

`55` سطر · `11` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `actor_user_id` | `uuid` | بله |  | شناسهٔ actor user |
| `action` | `text` | بله |  | کاری که انجام شده |
| `entity_type` | `text` | بله |  | نوع موجودیتی که تغییر کرده |
| `entity_id` | `uuid` | بله |  | شناسهٔ entity |
| `reason` | `text` | — |  | دلیل ثبت‌شده برای این تغییر |
| `before_values` | `jsonb` | — |  | مقادیر پیش از تغییر |
| `after_values` | `jsonb` | — |  | مقادیر پس از تغییر |
| `occurred_at` | `timestamp with time zone` | بله |  | زمانِ occurred<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /activities` · `GET /audit-events` · `GET /estimate-lines/{lineId}/progress-overrides` · `GET /estimate-lines` · `GET /extractions/{draftId}` · `GET /extractions` · `GET /files/{fileId}/content` · `GET /files/{fileId}` · `GET /files` · `GET /invoices/{invoiceId}` · `GET /invoices` · `GET /item-price-mappings/filters` · `GET /material-prices/categories` · `GET /material-prices/current` · `GET /material-prices/invalid-rows` · `GET /material-prices/labels` · `GET /material-prices/runs` · `GET /material-prices/unit-settings` · `GET /material-prices/unresolved` · `GET /material-prices/{providerItemId}/factors` · `GET /material-prices/{providerItemId}/history` · `GET /material-prices/{providerItemId}/labels` · `GET /material-prices/{providerItemId}/latest` · `GET /overview` · `GET /price-history` · `GET /prices/current` · `GET /progress-snapshots/{snapshotId}/feed` · `GET /progress-snapshots/{snapshotId}` · `GET /progress-snapshots` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /resources/{resourceId}/prices` · `GET /resources/{resourceId}` · `GET /resources` · `GET /settings/revisions` · `GET /settings` · `GET /summary` · `GET /task-resource-mappings` · `GET /unit-conversions` · `PATCH /invoices/{invoiceId}` · `PATCH /resources/{resourceId}` · `PATCH /settings` · `PATCH /unit-conversions/{conversionId}` · `POST /activities` · `POST /estimate-lines/{lineId}/progress-override` · `POST /estimate-lines/{lineId}/revisions` · `POST /estimate-lines` · `POST /extractions/{draftId}/confirm` · `POST /extractions/{draftId}/reject` · `POST /extractions/{draftId}/retry` · `POST /files/{fileId}/extractions/async` · `POST /files/{fileId}/extractions` · `POST /files` · `POST /invoices/{invoiceId}/confirm` · `POST /invoices/{invoiceId}/corrective` · `POST /invoices/{invoiceId}/void` · `POST /invoices` · `POST /material-prices/categories` · `POST /material-prices/manual` · `POST /material-prices/unit-settings` · `POST /material-prices/{providerItemId}/factors` · `POST /material-prices/{providerItemId}/labels` · `POST /report-snapshots` · `POST /resources/{resourceId}/prices` · `POST /resources` · `POST /unit-conversions`

### `report_snapshots`

گزارش‌های ذخیره‌شده؛ عددِ لحظهٔ گرفتن گزارش را نگه می‌دارد.

`16` سطر · `15` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `finance_project_settings.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `finance_project_settings.project_id` |
| `reporting_date` | `date` | بله |  | تاریخی که گزارش برای آن گرفته شده |
| `progress_snapshot_ref_id` | `uuid` | بله | FK | ارجاع به `progress_snapshot_refs.id` |
| `finance_settings_id` | `uuid` | بله | FK | ارجاع به `finance_project_settings.id` |
| `estimate_revision_ids` | `jsonb` | بله |  | کدام بازنگری‌های برآورد در این گزارش لحاظ شده‌اند |
| `price_version_ids` | `jsonb` | بله |  | کدام نسخه‌های قیمت لحاظ شده‌اند |
| `unit_conversion_ids` | `jsonb` | بله |  | کدام تبدیل‌های واحد لحاظ شده‌اند |
| `invoice_ids` | `jsonb` | بله |  | کدام فاکتورها لحاظ شده‌اند |
| `calculated_metrics` | `jsonb` | بله |  | سنجه‌های محاسبه‌شدهٔ گزارش |
| `issued_by` | `uuid` | بله |  | کاربرِ issued |
| `issued_at` | `timestamp with time zone` | بله |  | زمانِ issued<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `snapshot_payload` | `jsonb` | بله |  | کل خروجی گزارش در لحظهٔ گرفتن |
| `resource_version_ids` | `jsonb` | بله |  | کدام نسخه‌های منابع لحاظ شده‌اند |

**API:** `GET /overview` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `POST /report-snapshots`

### `progress_snapshot_refs`

ارجاع به snapshot پیشرفتی که گزارش بر آن بنا شده.

`4` سطر · `14` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `progress_snapshot_id` | `uuid` | بله |  | شناسهٔ progress snapshot |
| `source_file_version_id` | `uuid` | — |  | شناسهٔ source file version |
| `source_file_name_safe` | `text` | بله |  | نام فایل مبدأ، پاک‌سازی‌شده |
| `reporting_date` | `date` | بله |  | تاریخ گزارشِ این snapshot |
| `snapshot_status` | `text` | بله |  | وضعیت snapshot<br>*مقادیر مجاز: ready / superseded* |
| `imported_by` | `uuid` | بله |  | کاربرِ imported |
| `imported_at` | `timestamp with time zone` | بله |  | زمانِ imported |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |
| `source_type` | `text` | — |  | نوع منبع snapshot<br>*مقادیر مجاز: microsoft_project / primavera / manual / other* |
| `host_snapshot_id` | `bigint` | — |  | شناسهٔ host snapshot<br>*حداقل 0* |
| `host_file_version_id` | `bigint` | — |  | شناسهٔ host file version<br>*حداقل 0* |

**API:** `GET /estimate-lines/{lineId}/progress-overrides` · `GET /overview` · `GET /progress-snapshots/{snapshotId}/feed` · `GET /progress-snapshots/{snapshotId}` · `GET /progress-snapshots` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `POST /estimate-lines/{lineId}/progress-override` · `POST /report-snapshots`

### `finance_project_settings`

تنظیمات مالی پروژه، به‌صورت تاریخچهٔ فقط‌افزودنی.

`1` سطر · `10` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله |  | سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها |
| `project_id` | `text` | بله |  | پروژه‌ای که سطر به آن تعلق دارد |
| `revision` | `integer` | بله |  | شمارهٔ بازنگری تنظیمات؛ جدول فقط‌افزودنی است<br>*حداقل 0* |
| `gross_built_area` | `numeric(18,4)` | بله |  | زیربنای ناخالص پروژه، مبنای سنجه‌های «به ازای متر مربع»<br>*حداقل 0* |
| `currency` | `text` | بله |  | واحد پول<br>پیش‌فرض: `'IRR'` |
| `effective_from` | `date` | بله |  | تاریخی که این مقدار از آن به بعد معتبر است |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /overview` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `GET /settings/revisions` · `GET /settings` · `GET /summary` · `PATCH /settings` · `POST /report-snapshots`

### `finance_alembic_version`

شمارهٔ مهاجرت جاری دیتابیس مالی.

`1` سطر · `1` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `version_num` | `character varying(32)` | بله |  | شمارهٔ مهاجرت جاری؛ تنها ستون و تنها سطر این جدول |

### `progress_overrides`

اصلاح دستی پیشرفت یک تخصیص.

`0` سطر · `10` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | بله | FK | ارجاع به `estimate_lines.organization_id` |
| `project_id` | `text` | بله | FK | ارجاع به `estimate_lines.project_id` |
| `estimate_line_id` | `uuid` | بله | FK | ارجاع به `estimate_lines.id` |
| `progress_snapshot_ref_id` | `uuid` | بله | FK | ارجاع به `progress_snapshot_refs.id` |
| `computed_value` | `numeric(18,4)` | بله |  | مقدار computed |
| `override_value` | `numeric(18,4)` | بله |  | مقدار override |
| `reason` | `text` | بله |  | دلیل ثبت‌شده برای این تغییر<br>*نمی‌تواند خالی یا فقط فاصله باشد* |
| `created_by` | `uuid` | بله |  | کاربری که سطر را ساخته |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `CURRENT_TIMESTAMP` |

**API:** `GET /estimate-lines/{lineId}/progress-overrides` · `GET /overview` · `GET /progress-snapshots/{snapshotId}/feed` · `GET /progress-snapshots/{snapshotId}` · `GET /progress-snapshots` · `GET /report-snapshots/{reportId}/csv` · `GET /report-snapshots/{reportId}/xlsx` · `GET /report-snapshots/{reportId}` · `GET /report-snapshots` · `GET /reports/live/by-wbs` · `GET /reports/live/variances` · `GET /reports/live` · `GET /reports/monthly` · `POST /estimate-lines/{lineId}/progress-override` · `POST /report-snapshots`

---

## سازمان، کاربر و دسترسی

هویت و مجوز. بخش مالی این‌ها را می‌خواند و نمی‌نویسد.

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`role_permissions`](#role-permissions) | 331 | 2 | کدام نقش کدام مجوز را دارد. | — |
| [`permissions`](#permissions) | 88 | 6 | مجوزهای قابل‌اعطا. | — |
| [`roles`](#roles) | 12 | 7 | نقش‌ها. | — |
| [`otp_codes`](#otp-codes) | 4 | 6 | کدهای یک‌بارمصرف ورود. | — |
| [`users`](#users) | 2 | 9 | کاربران. | — |
| [`user_roles`](#user-roles) | 2 | 6 | کدام کاربر کدام نقش را دارد. | — |
| [`organization_memberships`](#organization-memberships) | 2 | 6 | عضویت کاربر در سازمان. | — |
| [`sessions`](#sessions) | 2 | 4 | نشست‌های ورود. | — |
| [`organizations`](#organizations) | 1 | 20 | سازمان‌ها. | — |
| [`projects`](#projects) | 1 | 20 | پروژه‌ها. | — |
| [`organization_members`](#organization-members) | 1 | 11 | عضویت کاربر در سازمان (جدول قدیمی‌تر، ستون‌های بیشتر). | — |
| [`project_members`](#project-members) | 1 | 5 | عضویت کاربر در پروژه (جدول قدیمی‌تر). | — |
| [`project_memberships`](#project-memberships) | 1 | 6 | عضویت کاربر در پروژه. | — |
| [`project_sequences`](#project-sequences) | 1 | 2 | شمارنده برای تولید کدهای ترتیبی پروژه. | — |
| [`user_permission_overrides`](#user-permission-overrides) | 0 | 3 | استثناء مجوز در سطح یک کاربر. | — |

### `role_permissions`

کدام نقش کدام مجوز را دارد.

`331` سطر · `2` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `role_id` | `uuid` | بله | FK | ارجاع به `roles.id` |
| `permission_id` | `uuid` | بله | FK | ارجاع به `permissions.id` |

### `permissions`

مجوزهای قابل‌اعطا.

`88` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `module_key` | `text` | بله |  | ماژولی که مجوز به آن تعلق دارد |
| `action_key` | `text` | بله |  | کاری که مجوز اجازه می‌دهد |
| `code` | `text` | بله |  | کد |
| `label` | `text` | بله |  | برچسب نمایشی |
| `group_name` | `text` | بله |  | نام group |

### `roles`

نقش‌ها.

`12` سطر · `7` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `name` | `text` | بله |  | نام |
| `code` | `text` | بله |  | کد |
| `category` | `text` | بله |  | دسته‌بندی<br>*مقادیر مجاز: internal / customer*<br>پیش‌فرض: `'customer'` |
| `is_system` | `boolean` | بله |  | نقش سیستمی است و قابل حذف نیست<br>پیش‌فرض: `false` |
| `is_active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `true` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `otp_codes`

کدهای یک‌بارمصرف ورود.

`4` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `phone` | `text` | بله |  | شماره‌ای که کد برای آن فرستاده شده |
| `code` | `text` | بله |  | کد |
| `expires_at` | `timestamp with time zone` | بله |  | زمانِ expires |
| `consumed` | `boolean` | بله |  | کد مصرف شده است<br>پیش‌فرض: `false` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `users`

کاربران.

`2` سطر · `9` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `email` | `text` | — |  | رایانامهٔ کاربر |
| `phone` | `text` | — |  | شمارهٔ تلفن کاربر |
| `password_hash` | `text` | — |  | درهم‌سازی گذرواژه؛ خودِ گذرواژه ذخیره نمی‌شود |
| `display_name` | `text` | بله |  | نام نمایشی کاربر<br>پیش‌فرض: `''` |
| `avatar_path` | `text` | — |  | مسیر تصویر کاربر |
| `is_active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `true` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `user_roles`

کدام کاربر کدام نقش را دارد.

`2` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `role_id` | `uuid` | بله | FK | ارجاع به `roles.id` |
| `organization_id` | `uuid` | — | FK | ارجاع به `organizations.id` |
| `project_id` | `text` | — | FK | ارجاع به `projects.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `organization_memberships`

عضویت کاربر در سازمان.

`2` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `organization_id` | `uuid` | بله | FK | ارجاع به `organizations.id` |
| `user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `role` | `text` | بله |  | نقش کاربر در سازمان<br>*مقادیر مجاز: org_admin / editor / viewer / finance_viewer / owner_client* |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `sessions`

نشست‌های ورود.

`2` سطر · `4` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `token` | `text` | بله |  | توکن نشست |
| `user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `expires_at` | `timestamp with time zone` | بله |  | زمانِ expires |

### `organizations`

سازمان‌ها.

`1` سطر · `20` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `name` | `text` | بله |  | نام |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |
| `code` | `text` | — |  | کد |
| `org_type` | `text` | — |  | نوع سازمان |
| `status` | `text` | بله |  | وضعیت سطر<br>پیش‌فرض: `'active'` |
| `member_limit` | `integer` | بله |  | سقف تعداد اعضا<br>پیش‌فرض: `10` |
| `country` | `text` | — |  | کشور<br>پیش‌فرض: `'ایران'` |
| `province` | `text` | — |  | استان |
| `city` | `text` | — |  | شهر |
| `street_address` | `text` | — |  | نشانی street |
| `postal_code` | `text` | — |  | کد postal |
| `maps_embed` | `text` | — |  | کد جاسازی نقشه |
| `contact_info` | `text` | — |  | اطلاعات تماس |
| `logo_path` | `text` | — |  | مسیر لوگو |
| `landline_phone` | `text` | — |  | شمارهٔ تلفن landline |
| `mobile_phone` | `text` | — |  | شمارهٔ تلفن mobile |
| `org_email` | `text` | — |  | رایانامهٔ org |
| `website` | `text` | — |  | وب‌سایت سازمان |

### `projects`

پروژه‌ها.

`1` سطر · `20` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `text` | بله | PK | کلید اصلی سطر |
| `organization_id` | `uuid` | — | FK | ارجاع به `organizations.id` |
| `name` | `text` | بله |  | نام |
| `code` | `text` | — |  | کد |
| `address` | `text` | — |  | نشانی پروژه |
| `cover_image_path` | `text` | — |  | مسیر تصویر شاخص پروژه |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: active / closed / archived*<br>پیش‌فرض: `'active'` |
| `start_date` | `date` | — |  | تاریخ شروع پروژه |
| `planned_end_date` | `date` | — |  | تاریخ پایان برنامه‌ریزی‌شده |
| `description` | `text` | — |  | شرح |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |
| `built_area_sqm` | `numeric` | — |  | زیربنا، متر مربع<br>*حداقل 0* |
| `estimated_cost` | `numeric(20,2)` | — |  | هزینهٔ برآوردی پروژه<br>*حداقل 0* |
| `actual_cost_to_date` | `numeric(20,2)` | — |  | هزینهٔ واقعی تا امروز<br>*حداقل 0* |
| `cost_source` | `text` | — |  | منبع عدد هزینه<br>*مقادیر مجاز: MANUAL / FINANCE_MODULE* |
| `cost_unit` | `text` | — |  | واحد پول هزینه |
| `cost_updated_at` | `timestamp with time zone` | — |  | زمانِ cost updated |
| `cost_updated_by` | `uuid` | — | FK | ارجاع به `users.id` |

### `organization_members`

عضویت کاربر در سازمان (جدول قدیمی‌تر، ستون‌های بیشتر).

`1` سطر · `11` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `organization_id` | `uuid` | بله | FK | ارجاع به `organizations.id` |
| `name` | `text` | بله |  | نام |
| `phone` | `text` | — |  | شمارهٔ تلفن عضو |
| `role_title` | `text` | — |  | عنوان سِمت عضو در سازمان |
| `is_active` | `boolean` | بله |  | فعال بودن سطر<br>پیش‌فرض: `true` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `role_id` | `uuid` | — | FK | ارجاع به `roles.id` |
| `is_org_president` | `boolean` | بله |  | عضو، رئیس سازمان است<br>پیش‌فرض: `false` |
| `email` | `text` | — |  | رایانامهٔ عضو |
| `user_id` | `uuid` | — | FK | ارجاع به `users.id` |

### `project_members`

عضویت کاربر در پروژه (جدول قدیمی‌تر).

`1` سطر · `5` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `organization_member_id` | `uuid` | بله | FK | ارجاع به `organization_members.id` |
| `project_role` | `text` | — |  | نقشِ project |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `project_memberships`

عضویت کاربر در پروژه.

`1` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `role` | `text` | بله |  | نقش کاربر در پروژه<br>*مقادیر مجاز: viewer / editor / project_admin* |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `project_sequences`

شمارنده برای تولید کدهای ترتیبی پروژه.

`1` سطر · `2` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `last_seq` | `integer` | بله |  | آخرین عدد مصرف‌شدهٔ دنباله<br>پیش‌فرض: `0` |

### `user_permission_overrides`

استثناء مجوز در سطح یک کاربر.

`0` سطر · `3` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `permission_id` | `uuid` | بله | FK | ارجاع به `permissions.id` |
| `allowed` | `boolean` | بله |  | مجوز برای این کاربر صریحاً داده یا گرفته شده |

---

## ماژول‌های دیگر BAMBO

در همین دیتابیس‌اند، ولی API مالی به آن‌ها دست نمی‌زند.

| جدول | سطر | ستون | کاربرد | API |
|---|---:|---:|---|---|
| [`tags`](#tags) | 26 | 6 | برچسب‌های عمومی سامانه. | — |
| [`field_note_tags`](#field-note-tags) | 12 | 4 | برچسب‌های یادداشت کارگاهی. | — |
| [`notifications`](#notifications) | 10 | 9 | اعلان‌ها. | — |
| [`media_files`](#media-files) | 9 | 8 | فایل‌های رسانه‌ای. | — |
| [`note_activities`](#note-activities) | 7 | 15 | رویدادهای یادداشت عمومی. | — |
| [`field_note_statuses`](#field-note-statuses) | 6 | 6 | وضعیت‌های ممکن یادداشت کارگاهی. | — |
| [`note_tags`](#note-tags) | 3 | 3 | برچسب‌های یادداشت عمومی. | — |
| [`floors`](#floors) | 2 | 9 | طبقات ساختمان. | — |
| [`sheets`](#sheets) | 2 | 8 | شیت‌ها و نقشه‌ها. | — |
| [`field_notes`](#field-notes) | 0 | 20 | یادداشت‌های کارگاهی. | — |
| [`field_note_tag_links`](#field-note-tag-links) | 0 | 2 | اتصال یادداشت به برچسب. | — |
| [`field_note_comments`](#field-note-comments) | 0 | 6 | نظرات روی یادداشت کارگاهی. | — |
| [`field_note_attachments`](#field-note-attachments) | 0 | 7 | پیوست‌های یادداشت کارگاهی. | — |
| [`field_note_activities`](#field-note-activities) | 0 | 7 | رویدادهای یک یادداشت کارگاهی. | — |
| [`messages`](#messages) | 0 | 5 | پیام‌ها. | — |
| [`message_threads`](#message-threads) | 0 | 6 | رشته‌های گفت‌وگو. | — |
| [`panoramas`](#panoramas) | 0 | 9 | تصاویر پانوراما. | — |
| [`capture_sessions`](#capture-sessions) | 0 | 13 | جلسات برداشت میدانی (عکس و پانوراما). | — |
| [`capture_path_points`](#capture-path-points) | 0 | 7 | نقاط مسیر یک جلسهٔ برداشت. | — |
| [`zones`](#zones) | 0 | 7 | زون‌های هر طبقه. | — |

### `tags`

برچسب‌های عمومی سامانه.

`26` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `label` | `text` | بله |  | برچسب نمایشی |
| `is_default` | `boolean` | بله |  | برچسب پیش‌فرض است<br>پیش‌فرض: `false` |
| `owner_user_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `project_id` | `text` | — | FK | ارجاع به `projects.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `field_note_tags`

برچسب‌های یادداشت کارگاهی.

`12` سطر · `4` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `text` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | — | FK | ارجاع به `projects.id` |
| `label_fa` | `text` | بله |  | برچسب فارسی |
| `order` | `integer` | بله |  | ترتیب نمایش<br>پیش‌فرض: `0` |

### `notifications`

اعلان‌ها.

`10` سطر · `9` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `recipient_user_id` | `uuid` | بله | FK | ارجاع به `users.id` |
| `actor_user_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `type` | `text` | بله |  | نوع اعلان |
| `note_id` | `text` | — |  | شناسهٔ note |
| `project_id` | `text` | — |  | پروژه‌ای که سطر به آن تعلق دارد |
| `message` | `text` | بله |  | متن اعلان |
| `is_read` | `boolean` | بله |  | اعلان خوانده شده است<br>پیش‌فرض: `false` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `media_files`

فایل‌های رسانه‌ای.

`9` سطر · `8` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `kind` | `text` | بله |  | نوع رسانه |
| `file_path` | `text` | بله |  | مسیر فایل file |
| `mime` | `text` | — |  | نوع MIME فایل |
| `bytes` | `bigint` | — |  | حجم فایل به بایت |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `note_activities`

رویدادهای یادداشت عمومی.

`7` سطر · `15` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `note_id` | `text` | بله |  | شناسهٔ note |
| `project_id` | `text` | — |  | پروژه‌ای که سطر به آن تعلق دارد |
| `author_user_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `author_name` | `text` | بله |  | نام author<br>پیش‌فرض: `''` |
| `body` | `text` | — |  | متن رویداد |
| `image_path` | `text` | — |  | مسیر فایل image |
| `status_from` | `text` | — |  | وضعیت پیشین |
| `status_to` | `text` | — |  | وضعیت جدید |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `file_path` | `text` | — |  | مسیر فایل file |
| `file_name` | `text` | — |  | نام file |
| `file_size` | `bigint` | — |  | حجم فایل پیوست |
| `mime` | `text` | — |  | نوع MIME فایل پیوست |
| `source` | `text` | — |  | منبع رویداد |

### `field_note_statuses`

وضعیت‌های ممکن یادداشت کارگاهی.

`6` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `text` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | — | FK | ارجاع به `projects.id` |
| `label_fa` | `text` | بله |  | برچسب فارسی وضعیت |
| `color` | `text` | — |  | رنگ نمایش وضعیت |
| `order` | `integer` | بله |  | ترتیب نمایش<br>پیش‌فرض: `0` |
| `is_closed_state` | `boolean` | بله |  | این وضعیت، وضعیتِ بسته‌شده است<br>پیش‌فرض: `false` |

### `note_tags`

برچسب‌های یادداشت عمومی.

`3` سطر · `3` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `note_id` | `text` | بله |  | شناسهٔ note |
| `tag_id` | `uuid` | بله | FK | ارجاع به `tags.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `floors`

طبقات ساختمان.

`2` سطر · `9` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `text` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `building_id` | `text` | — |  | شناسهٔ building |
| `label` | `text` | بله |  | برچسب نمایشی<br>پیش‌فرض: `''` |
| `order` | `integer` | بله |  | ترتیب طبقه<br>پیش‌فرض: `0` |
| `plan_interior_rect` | `jsonb` | — |  | مستطیل داخلی پلان (هندسه) |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |
| `exterior_boundary` | `jsonb` | — |  | مرز بیرونی طبقه (هندسه) |

### `sheets`

شیت‌ها و نقشه‌ها.

`2` سطر · `8` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `floor_id` | `text` | بله | FK | ارجاع به `floors.id` |
| `is_primary` | `boolean` | بله |  | شیت اصلی است<br>پیش‌فرض: `true` |
| `kind` | `text` | بله |  | نوع شیت یا نقشه<br>پیش‌فرض: `'image'` |
| `image_path` | `text` | — |  | مسیر فایل image |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `field_notes`

یادداشت‌های کارگاهی.

`0` سطر · `20` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `text` | بله | PK | کلید اصلی سطر |
| `display_id` | `text` | — |  | شناسهٔ display |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `floor_id` | `text` | — | FK | ارجاع به `floors.id` |
| `sheet_id` | `uuid` | — | FK | ارجاع به `sheets.id` |
| `capture_session_id` | `uuid` | — | FK | ارجاع به `capture_sessions.id` |
| `panorama_id` | `uuid` | — | FK | ارجاع به `panoramas.id` |
| `x` | `real` | — |  | مختصات X یادداشت روی پلان |
| `y` | `real` | — |  | مختصات Y یادداشت روی پلان |
| `title` | `text` | — |  | عنوان |
| `description` | `text` | — |  | شرح |
| `status_id` | `text` | — | FK | ارجاع به `field_note_statuses.id` |
| `assignee_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `due_date` | `date` | — |  | تاریخ due |
| `screenshot_path` | `text` | — |  | مسیر فایل screenshot |
| `context` | `jsonb` | — |  | زمینهٔ یادداشت |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `is_closed` | `boolean` | بله |  | یادداشت بسته شده است<br>پیش‌فرض: `false` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `field_note_tag_links`

اتصال یادداشت به برچسب.

`0` سطر · `2` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `field_note_id` | `text` | بله | FK | ارجاع به `field_notes.id` |
| `tag_id` | `text` | بله | FK | ارجاع به `field_note_tags.id` |

### `field_note_comments`

نظرات روی یادداشت کارگاهی.

`0` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `field_note_id` | `text` | بله | FK | ارجاع به `field_notes.id` |
| `author_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `body` | `text` | بله |  | متن نظر |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `field_note_attachments`

پیوست‌های یادداشت کارگاهی.

`0` سطر · `7` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `field_note_id` | `text` | بله | FK | ارجاع به `field_notes.id` |
| `file_path` | `text` | بله |  | مسیر فایل file |
| `mime` | `text` | — |  | نوع MIME پیوست |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `field_note_activities`

رویدادهای یک یادداشت کارگاهی.

`0` سطر · `7` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `field_note_id` | `text` | بله | FK | ارجاع به `field_notes.id` |
| `user_id` | `uuid` | — | FK | ارجاع به `users.id` |
| `action` | `text` | بله |  | کاری که روی یادداشت انجام شده |
| `meta` | `jsonb` | — |  | دادهٔ جانبی رویداد |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `messages`

پیام‌ها.

`0` سطر · `5` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `thread_id` | `uuid` | بله | FK | ارجاع به `message_threads.id` |
| `sender_name` | `text` | بله |  | نام sender<br>پیش‌فرض: `''` |
| `body` | `text` | بله |  | متن پیام |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `message_threads`

رشته‌های گفت‌وگو.

`0` سطر · `6` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `organization_id` | `uuid` | بله | FK | ارجاع به `organizations.id` |
| `title` | `text` | بله |  | عنوان |
| `scope` | `text` | بله |  | دامنهٔ گفت‌وگو<br>*مقادیر مجاز: organization / project*<br>پیش‌فرض: `'organization'` |
| `project_id` | `text` | — | FK | ارجاع به `projects.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `panoramas`

تصاویر پانوراما.

`0` سطر · `9` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `capture_session_id` | `uuid` | بله | FK | ارجاع به `capture_sessions.id` |
| `frame_index` | `integer` | — |  | نمایهٔ frame |
| `file_path` | `text` | — |  | مسیر فایل file |
| `sheet_x` | `real` | — |  | مختصات X روی شیت |
| `sheet_y` | `real` | — |  | مختصات Y روی شیت |
| `yaw` | `real` | — |  | زاویهٔ چرخش افقی دوربین |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |

### `capture_sessions`

جلسات برداشت میدانی (عکس و پانوراما).

`0` سطر · `13` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `floor_id` | `text` | بله | FK | ارجاع به `floors.id` |
| `visit_date` | `text` | بله |  | تاریخ visit |
| `status` | `text` | بله |  | وضعیت سطر<br>*مقادیر مجاز: uploaded / processing / ready / failed*<br>پیش‌فرض: `'ready'` |
| `capture_fps` | `integer` | — |  | فریم بر ثانیهٔ capture |
| `display_fps` | `integer` | — |  | فریم بر ثانیهٔ display |
| `panorama_stride` | `integer` | — |  | گامِ panorama |
| `trajectory_path` | `text` | — |  | مسیر فایل trajectory |
| `source_map_path` | `text` | — |  | مسیر فایل source map |
| `created_by` | `uuid` | — | FK | ارجاع به `users.id` |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

### `capture_path_points`

نقاط مسیر یک جلسهٔ برداشت.

`0` سطر · `7` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `bigint` | بله | PK | کلید اصلی سطر |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `capture_session_id` | `uuid` | بله | FK | ارجاع به `capture_sessions.id` |
| `frame_index` | `integer` | — |  | نمایهٔ frame |
| `x` | `real` | — |  | مختصات X نقطه |
| `y` | `real` | — |  | مختصات Y نقطه |
| `yaw` | `real` | — |  | زاویهٔ چرخش افقی در این نقطه |

### `zones`

زون‌های هر طبقه.

`0` سطر · `7` ستون

| ستون | نوع | الزامی | کلید | معنا |
|---|---|:--:|:--:|---|
| `id` | `uuid` | بله | PK | کلید اصلی سطر<br>پیش‌فرض: `gen_random_uuid()` |
| `project_id` | `text` | بله | FK | ارجاع به `projects.id` |
| `floor_id` | `text` | — | FK | ارجاع به `floors.id` |
| `name` | `text` | — |  | نام |
| `rect` | `jsonb` | — |  | مستطیل زون روی پلان |
| `created_at` | `timestamp with time zone` | بله |  | زمان ساخت سطر<br>پیش‌فرض: `now()` |
| `updated_at` | `timestamp with time zone` | بله |  | زمان آخرین تغییر سطر<br>پیش‌فرض: `now()` |

---

## فهرست کامل API

102 مسیر، همه زیر `/api/projects/{projectId}/finance`.

ستون «جدول‌ها» از روی repositoryای ساخته شده که به هر service تزریق می‌شود، پس در سطح **service** دقیق است: جدول‌هایی که آن service می‌تواند بخواند یا بنویسد. تضمین نمی‌کند که این endpoint خاص به تک‌تک آن‌ها دست می‌زند — مثلاً یک `GET` جدولی را فقط می‌خواند، هرچند هم‌سرویسِ آن `POST` همان جدول را می‌نویسد.

| متد | مسیر | service | جدول‌ها |
|---|---|---|---|
| `GET` | `/settings` | finance_settings | `finance_audit_events`, `finance_project_settings` |
| `PATCH` | `/settings` | finance_settings | `finance_audit_events`, `finance_project_settings` |
| `GET` | `/settings/revisions` | finance_settings | `finance_audit_events`, `finance_project_settings` |
| `GET` | `/summary` | finance_settings | `finance_audit_events`, `finance_project_settings` |
| `GET` | `/resources` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `POST` | `/resources` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `GET` | `/task-resource-mappings` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `GET` | `/resources/{resourceId}` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `PATCH` | `/resources/{resourceId}` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `GET` | `/unit-registry` | — | — |
| `GET` | `/activities` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `POST` | `/activities` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `GET` | `/items-and-estimates` | items_and_estimates | `estimate_lines`, `finance_item_price_mappings`, `finance_mpp_rows`, `finance_mpp_source_versions`, `finance_resources`, `invoice_lines`, `price_observations`, `provider_items` |
| `GET` | `/estimate-lines` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `POST` | `/estimate-lines` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `POST` | `/estimate-lines/{lineId}/revisions` | finance_resources | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_mpp_rows`, `finance_resources`, `finance_task_resource_map`, `invoice_lines`, `invoices`, `price_versions` |
| `GET` | `/resources/{resourceId}/prices` | finance_price | `finance_audit_events`, `finance_resources`, `price_versions` |
| `POST` | `/resources/{resourceId}/prices` | finance_price | `finance_audit_events`, `finance_resources`, `price_versions` |
| `GET` | `/price-history` | finance_price | `finance_audit_events`, `finance_resources`, `price_versions` |
| `GET` | `/prices/current` | finance_price | `finance_audit_events`, `finance_resources`, `price_versions` |
| `GET` | `/unit-conversions` | unit_conversion | `finance_audit_events`, `unit_conversions` |
| `POST` | `/unit-conversions` | unit_conversion | `finance_audit_events`, `unit_conversions` |
| `PATCH` | `/unit-conversions/{conversionId}` | unit_conversion | `finance_audit_events`, `unit_conversions` |
| `GET` | `/progress-snapshots` | progress | `estimate_lines`, `finance_audit_events`, `progress_overrides`, `progress_snapshot_refs` |
| `GET` | `/progress-snapshots/{snapshotId}` | progress | `estimate_lines`, `finance_audit_events`, `progress_overrides`, `progress_snapshot_refs` |
| `GET` | `/progress-snapshots/{snapshotId}/feed` | progress | `estimate_lines`, `finance_audit_events`, `progress_overrides`, `progress_snapshot_refs` |
| `GET` | `/estimate-lines/{lineId}/progress-overrides` | progress | `estimate_lines`, `finance_audit_events`, `progress_overrides`, `progress_snapshot_refs` |
| `POST` | `/estimate-lines/{lineId}/progress-override` | progress | `estimate_lines`, `finance_audit_events`, `progress_overrides`, `progress_snapshot_refs` |
| `POST` | `/imports/estimate/preview` | — | — |
| `POST` | `/imports/prices/preview` | — | — |
| `POST` | `/imports/estimate/preview-link` | — | — |
| `POST` | `/imports/prices/preview-link` | — | — |
| `POST` | `/imports/estimate/commit` | — | — |
| `POST` | `/imports/prices/commit` | — | — |
| `GET` | `/invoices` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/invoices` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `GET` | `/invoices/{invoiceId}` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `PATCH` | `/invoices/{invoiceId}` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/invoices/{invoiceId}/confirm` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/invoices/{invoiceId}/void` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/invoices/{invoiceId}/corrective` | invoice | `estimate_lines`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/files` | finance_attachment | `finance_attachments`, `finance_audit_events` |
| `GET` | `/files` | finance_attachment | `finance_attachments`, `finance_audit_events` |
| `GET` | `/files/{fileId}` | finance_attachment | `finance_attachments`, `finance_audit_events` |
| `GET` | `/files/{fileId}/content` | finance_attachment | `finance_attachments`, `finance_audit_events` |
| `POST` | `/files/{fileId}/extractions` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/files/{fileId}/extractions/async` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `GET` | `/extractions` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `GET` | `/extractions/{draftId}` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/extractions/{draftId}/reject` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/extractions/{draftId}/retry` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `POST` | `/extractions/{draftId}/confirm` | finance_extraction | `estimate_lines`, `extraction_drafts`, `finance_attachments`, `finance_audit_events`, `finance_resources`, `invoice_lines`, `invoices` |
| `GET` | `/reports/live` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/overview` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/reports/live/by-wbs` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/reports/live/variances` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/reports/monthly` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `POST` | `/report-snapshots` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/report-snapshots` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/report-snapshots/{reportId}` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/report-snapshots/{reportId}/csv` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/report-snapshots/{reportId}/xlsx` | finance_live_report | `estimate_lines`, `estimate_revisions`, `finance_audit_events`, `finance_project_settings`, `finance_resources`, `invoice_lines`, `invoices`, `price_versions`, `progress_overrides`, `progress_snapshot_refs`, `report_snapshots`, `unit_conversions` |
| `GET` | `/audit-events` | finance_audit | `finance_audit_events` |
| `GET` | `/material-prices/categories` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `POST` | `/material-prices/categories` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `POST` | `/material-prices/manual` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/current` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/{providerItemId}/history` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/{providerItemId}/latest` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `POST` | `/material-prices/import-runs` | — | — |
| `GET` | `/material-prices/runs` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/invalid-rows` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/unit-settings` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `POST` | `/material-prices/unit-settings` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/labels` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/{providerItemId}/labels` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `POST` | `/material-prices/{providerItemId}/labels` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/{providerItemId}/factors` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `POST` | `/material-prices/{providerItemId}/factors` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/material-prices/unresolved` | material_price | `finance_audit_events`, `finance_price_categories`, `finance_resources`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/item-price-mappings/candidates` | item_price_mapping | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mappings`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/item-price-mappings/filters` | item_price_component, material_price | `estimate_line_source_completions`, `estimate_lines`, `finance_audit_events`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_price_categories`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `material_unit_settings`, `price_collection_runs`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items`, `unit_conversions` |
| `GET` | `/estimate-lines/{lineId}/price-mapping` | item_price_mapping | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mappings`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/estimate-lines/{lineId}/price-mapping/history` | item_price_mapping | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mappings`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/estimate-lines/{lineId}/price-preview` | item_price_mapping | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mappings`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `POST` | `/estimate-lines/{lineId}/price-mapping` | item_price_mapping | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mappings`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/item-price-mappings/status` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/estimate-lines/{lineId}/price-mapping/components` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/estimate-lines/{lineId}/price-mapping/components/history` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/estimate-lines/{lineId}/price-component-preview` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/estimate-lines/{lineId}/price-total-preview` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `POST` | `/estimate-lines/{lineId}/price-mapping/components` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `PATCH` | `/estimate-lines/{lineId}/price-mapping/components/{componentId}` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `POST` | `/estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate` | item_price_component | `estimate_line_source_completions`, `estimate_lines`, `finance_item_price_mapping_components`, `finance_mpp_rows`, `finance_resources`, `finance_unit_conversion_issues`, `finance_unit_conversion_rules`, `price_observations`, `price_providers`, `provider_item_labels`, `provider_item_unit_factors`, `provider_items` |
| `GET` | `/finance-settings/unit-conversions` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `POST` | `/finance-settings/unit-conversions` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `GET` | `/finance-settings/unit-conversions/{ruleId}` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `GET` | `/finance-settings/unit-conversions/{ruleId}/history` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `GET` | `/finance-settings/unit-conversions/{ruleId}/preview` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `POST` | `/finance-settings/unit-conversions/{ruleId}/approve` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `POST` | `/finance-settings/unit-conversions/{ruleId}/supersede` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |
| `GET` | `/finance-settings/unit-conversion-issues` | unit_conversion_rule | `finance_unit_conversion_issues`, `finance_unit_conversion_rules` |

---

## پوشش توضیحات

| منبع توضیح | ستون |
|---|---:|
| قاعدهٔ عمومی نام ستون | 322 |
| نوشتهٔ دستی، مخصوص همان جدول | 312 |
| از روی پسوند نام ستون | 230 |
| از روی کلید خارجی | 175 |
| COMMENT خودِ دیتابیس | 47 |
| **جمع** | **1086** |

