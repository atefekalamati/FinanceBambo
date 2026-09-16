# زنجیرهٔ قیمت روزانهٔ مصالح — ممیزی و تکمیل

تاریخ: ۱۴۰۵/۰۶/۲۵ (۲۰۲۶-۰۹-۱۶) · شاخه: `harden/material-price-db-ops-scripts`
پایگاه دادهٔ آزموده‌شده: `bambo_canonical_test` · Alembic: `0030` (بدون تغییر)

---

## ۱. پاسخ به پرسش کسب‌وکار

> وقتی Sheet قیمت روزانه به‌روز می‌شود، آیا BAMBO پایگاه داده را به‌روز می‌کند؟

**تا پیش از این تغییر: نه.**

`price_observations` دقیقاً **یک** نویسندهٔ تولیدی دارد
(`repositories/material_prices.py:260`) که فقط از طریق `MaterialPriceImportService`
در دسترس است، و آن سرویس تا امروز فقط از دو اسکریپت CLI صدا زده می‌شد:

* `scripts/import_material_prices.py`
* `scripts/ops/import_into_terrace.py`

**هیچ Scheduler، Worker، Cron یا Webhookی وجود ندارد.** ستون
`price_providers.default_interval_minutes` روی هر ۸ ردیف مقدار `1440` دارد و **هیچ کدی
آن را نمی‌خواند** — تنها مصرف‌کننده‌هایش دستورهای INSERT هستند. یعنی «روزانه» یک نیت
ذخیره‌شده بود، نه یک رفتار.

پس الگوی واقعی **D** بود: *اسکریپت دستی، Sheet را وارد پایگاه داده می‌کند.*

`POST /imports/prices/commit` این کار را **نمی‌کند** — آن Importer دیگری است که از فایل
Excel آپلودی به `price_versions` و `estimate_lines` می‌نویسد (قیمت رسمی Finance)، نه
مشاهدات بازار.

آخرین Import موفق: **۲۰۲۶-۰۹-۱۴** — دو روز پیش از این ممیزی.

### جریان داده، حالا

```
Google Sheet (یک سند، ۷ برگه)
   │  FINANCE_MATERIAL_PRICE_SHEET_URL  ← پیکربندی، نه پارامتر درخواست
   ▼
POST /material-prices/import-runs   ← تازه اضافه شد  (یا CLI، مثل قبل)
   ▼
MaterialPriceImportService.run(scope)
   ├─ کل Workbook خوانده می‌شود؛ اگر برگه‌ای غایب/خالی باشد هیچ‌چیز نوشته نمی‌شود
   ├─ price_collection_runs  ← یک Run؛ Index یکتای جزئی مانع دو Import هم‌زمان است
   ├─ اعتبارسنجی سطر به سطر
   ├─ provider_items          ← ساخت یا تطبیق
   └─ price_observations      ← فقط افزودنی (Trigger)، Fingerprint مانع تکرار
   ▼
GET /material-prices/current   ← تازه‌ترین مشاهدهٔ **معتبر**
   ▼
اقلام و برآورد / گزارش‌های مالی
```

---

## ۲. پیکربندی منابع

| Provider | دسته | نوع منبع | سند/برگه | فعال | مسیر Import | Parser | آخرین Run موفق |
|---|---|---|---|---|---|---|---|
| AhanOnline | steel | Google Sheet | `1RgjXoz…ctyas` # AhanOnline | بله | CLI + endpoint جدید | `material_price_sheet.py` | ۲۰۲۶-۰۹-۱۴ |
| Mashhad Foolad | steel | Google Sheet | همان سند # Mashhad Foolad | بله | همان | همان | ۲۰۲۶-۰۹-۱۴ |
| Sivanland | steel | Google Sheet | همان سند # Sivanland | بله | همان | همان | ۲۰۲۶-۰۹-۱۴ |
| Toranj Brick | brick | Google Sheet | همان سند # Toranj Brick | بله | همان | همان | ۲۰۲۶-۰۹-۱۴ |

(چهار Provider × دو پروژه = ۸ ردیف. شناسهٔ سند عمومی است و رمزی در آن نیست.)

هفت برگهٔ مجاز: `steel - I-beam`، `Angle iron-table`، `Channel_table`،
`Hollow structural section_table`، `Pipe-table`، `steel -Rebar`، `brick`.
برگه‌ای خارج از این فهرست **خوانده نمی‌شود** — برگهٔ تازه تصمیمی است که کسی باید ببیند.

---

## ۳. ماشه‌های Import

| ماشه | اجرا | مجوز | ورودی | خروجی | می‌نویسد؟ | Idempotent؟ |
|---|---|---|---|---|---|---|
| **`POST …/material-prices/import-runs`** (جدید) | HTTP | `finance.edit` | **هیچ** | شمارش‌ها + Run | بله | **بله** |
| `scripts/import_material_prices.py` | CLI | دسترسی به DSN | `--dsn --organization --project` | چاپ | بله | بله |
| `scripts/ops/import_into_terrace.py` | CLI | همان | همان | چاپ | بله | بله |
| `scripts/test_only/price_sheet_probe.py` | CLI | — | — | — | بله | — (فقط آزمون) |
| Scheduler / Webhook | **وجود ندارد** | — | — | — | — | — |

**Endpoint هیچ ورودی‌ای نمی‌گیرد.** Sheet از پیکربندی می‌آید: فراخوانی که بتواند Sheet را
نام ببرد می‌تواند این Host را به هر Sheetی بچرخاند، و فراخوانی که بتواند سطر بفرستد
می‌تواند قیمتی بنویسد که هیچ‌کس منتشر نکرده.

---

## ۴. نقصی که پیدا شد — و مهم بود

**یک سطر ردشده با تاریخ جدیدتر، قیمت معتبر را پنهان می‌کرد.**

`latest_observations` فقط بر اساس تاریخ مرتب می‌کرد. پس روزی که تأمین‌کننده در Sheet
«تماس بگیرید» می‌نوشت:

1. آن سطر با تاریخ کسب‌وکارِ **جدیدتر** وارد می‌شد،
2. `DISTINCT ON` را می‌برد،
3. و قیمت جاری محصول `null` می‌شد — `invalid_source`، بدون عدد، در هر برآوردی.

در همان جدول، قیمت کاملاً معتبرِ سه روز پیش نشسته بود و هیچ API آن را برنمی‌گرداند.

**اثبات شد** (پروژهٔ `selection_probe_204205`): قیمت معتبر ۹۵۵٬۰۰۰ در ۲۰۲۶-۰۹-۱۳ وجود
داشت و API `None` می‌داد.

### اصلاح

کلید مرتب‌سازی اول اضافه شد:

```sql
ORDER BY o.provider_item_id,
         (o.validation_status = 'valid'
          AND o.workflow_date_gregorian IS NOT NULL) DESC,   ← اصلاح
         o.workflow_date_gregorian DESC NULLS LAST,
         o.fetched_at DESC, o.id
```

سطری که باورپذیر نبوده نباید به همین دلیل چیزی شود که همه باور می‌کنند.

**فیلتر نیست، مرتب‌سازی است** — پس فهرستی که همهٔ مشاهداتش نامعتبرند همچنان دیده می‌شود
با قیمت null و دلایلش. «این محصول را داریم و نمی‌توانیم قیمتش بزنیم» پاسخی است که
خواننده لازم دارد؛ سکوت نیست.

و کنارگذاشتن **ساکت نیست**: سه فیلد تازه می‌گویند سطر جدیدتری رد شده:

```json
"rejectedAfterDate": "2026-09-16",
"rejectedAfterRawPrice": "تماس بگیرید",
"rejectedAfterReasons": ["price is not a number: 'تماس بگیرید'"]
```

---

## ۵. نتایج ۲۰ سناریوی زنده

پروژهٔ `ingestion_probe_20260916_204122` — **۲۰ قبول، ۰ رد**:

| # | سناریو | نتیجه |
|---|---|---|
| ۱ | سطر معتبر، تاریخ تازه | Run ساخته شد · ۷ قلم · ۷ مشاهده · `valid` · تاریخ از **Sheet** (۲۰۲۶-۰۹-۱۳) · قیمت ۹۵۵٬۰۰۰ · API برگرداند |
| ۲ | همان سطر دوباره | صفر تکرار · `alreadyPresent=7` |
| ۳ | تاریخ جدیدتر | مشاهدهٔ تازه · API قیمت ۹۸۰٬۰۰۰ داد · تاریخچه هر دو را دارد |
| ۴ | «تماس بگیرید»، «ناموجود»، «توافقی»، «-»، خالی | هر پنج رد شدند، هیچ‌کدام قیمت ندارد |
| ۵ | تاریخ ناخوانا `1405/13/40` | رد · `workflow_date_gregorian = NULL` (نه امروز) |
| ۶ | بدون productId | نه قلمی، نه مشاهده‌ای |
| ۹ | — | هیچ قلم دستی‌ای لازم نشد (`estimate_lines = 0`) |

**نکتهٔ مهم دربارهٔ Probe:** نخستین نسخه‌اش می‌خواست سطرهایش را پاک کند و
`price_observations_immutable` رد کرد. Trigger را خاموش نکردم (ممنوع است و معاملهٔ
بدی هم هست)؛ Probe هر بار پروژهٔ تاریخ‌دار خودش را می‌سازد و شواهدش باقی می‌ماند.
هیچ پروژهٔ ممیزی‌شده‌ای لمس نشد.

---

## ۶. آنچه بررسی شد و سالم بود

* **افزودنی بودن** — Trigger `price_observations_immutable` هر UPDATE/DELETE را رد می‌کند (عملاً اثبات شد).
* **Fingerprint** — `(productId، تاریخ ورک‌فلو، قیمت)` هش‌شده، با Index یکتای جزئی در دامنهٔ `(org, project, provider_item)` — تکرارِ مشروعِ چندپروژه‌ای نمی‌شکند.
* **حفاظت از Sheet نیمه‌کاره** — اگر برگه‌ای غایب یا خالی باشد، **هیچ‌چیز** نوشته نمی‌شود و قیمت‌های قبلی دست‌نخورده می‌مانند.
* **تاریخ** — نه `fetched_at` و نه امروز جایگزین تاریخ کسب‌وکار نمی‌شوند (دو تست اختصاصی).
* **Snapshotها** — روی هر مشاهدهٔ تازه نوشته می‌شوند.
* **هیچ دادهٔ Mock در Runtime نیست** — تمام برخوردهای `mock/fake/sample` در `app/` و `coreint/` توضیح‌اند نه کد؛ Seed فقط در `devhost/` و پشت `seeding_allowed()` + `FINANCE_MIGRATION_DSN`.

---

## ۷. آنچه هنوز باقی است

* **هنوز هیچ زمان‌بندی خودکاری وجود ندارد.** Endpoint ساخته شد، ولی کسی یا چیزی باید آن
  را صدا بزند — n8n، cron، یا یک دکمه. `default_interval_minutes = 1440` همچنان خوانده
  نمی‌شود و تا وقتی Scheduler نباشد یک عدد تزئینی است.
* Endpoint فقط وقتی سیم‌کشی می‌شود که `FINANCE_MATERIAL_PRICE_SHEET_URL` تنظیم باشد؛
  در غیر این صورت ۴۰۹ با کد `MATERIAL_PRICE_SHEET_NOT_CONFIGURED` می‌دهد و Host هنگام
  بالا آمدن این را چاپ می‌کند.
* پروژه‌های Probe (`ingestion_probe_*`، `selection_probe_*`) در پایگاه دادهٔ آزمون
  می‌مانند، چون جدول افزودنی است.
