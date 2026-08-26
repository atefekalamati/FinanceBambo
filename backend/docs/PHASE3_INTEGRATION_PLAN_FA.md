# فاز ۳ — برنامه اتصال Finance به Core

**همراه سند:** `PHASE3_CORE_INTEGRATION_AUDIT_FA.md`
**وضعیت:** پیشنهاد. هیچ‌چیز از این سند پیاده نشده است.

---

## اصل حاکم

> اتصال به Core باید **فقط Adapter** باشد. هیچ تغییری در دامنه، محاسبات، Contract یا Schema
> لازم نیست — و اگر لازم شد، نشانه‌ی این است که مرزی جای اشتباهی کشیده شده.

فاز ۲ این را ممکن کرد: `progressSnapshotId` اختیاری شد، شناسه‌های Core جای خودشان را گرفتند،
و خواندن دیگر نمی‌نویسد. فاز ۳ فقط باید Adapterها را بنویسد.

---

## ترتیب پیشنهادی فاز ۳-ب

ترتیب بر اساس **وابستگی** چیده شده، نه اندازه. هر گام بدون گام بعدی هم ارزش دارد.

### گام ۰ — دو کوئری فقط‌خواندنی (RED، نیازمند تأیید صریح)

پیش از نوشتن هر خط Adapter:

```sql
SELECT code FROM permissions WHERE code LIKE 'finance%' ORDER BY code;
SELECT id FROM projects LIMIT 50;   -- فقط برای بررسی الگوی شناسه
```

**چرا اول:** پاسخ اولی تعیین می‌کند آیا صدور گزارش در Production کار می‌کند یا نه (ریسک P-01)،
و پاسخ دومی تعیین می‌کند آیا `AuthContext` اصلاً ساخته می‌شود (ریسک A-01). هر دو ارزان‌اند و
هر دو اگر دیر کشف شوند گران می‌شوند.

هیچ‌چیز نوشته نمی‌شود، ولی چون به دیتابیس اصلی وصل می‌شود، طبق قواعد این پروژه اقدام RED است
و تأیید جداگانه می‌خواهد.

### گام ۱ — Adapter احراز هویت و دامنه

سه کلاس، هیچ‌کدام در مخزن Finance:

```
AuthContextProvider    → Session واقعی BAMBO ← AuthContext
ScopeAuthorizer        → عضویت سازمان و پروژه
PermissionAuthorizer   → RBAC واقعی Core
```

**چرا اول:** بدون این سه، هیچ مسیری قابل آزمودن نیست. و ساده‌ترین‌اند — نگاشت داده، بدون منطق.

نکاتی که ممیزی پیدا کرد و باید رعایت شوند:

- `timezone` باید دقیقاً `Asia/Tehran` باشد
- `permission_codes` باید دقیقاً یک نقطه داشته باشند
- `organization_role` باید مقداری بدهد که سیاست `org_chief` رویش حساب می‌کند
- `project_id` باید با `^[A-Za-z0-9_-]+$` بخواند

### گام ۲ — Adapter پیشرفت (MSP)

```
current_snapshot(organization_id, project_id, as_of)
get_snapshot(organization_id, project_id, snapshot_id)   ← با شناسه bigint میزبان
```

از `msp_snapshots` + `msp_file_versions` + `msp_tasks` می‌خواند. **فقط خواندنی.**

سه تصمیم که باید در همین گام گرفته شوند:

1. **نگاشت `snapshot_type` → `status`** — Core مقادیر `TARGET`/`ACTUAL`/`RESCHEDULED` دارد و DTO
   فقط `ready`/`superseded` می‌پذیرد.
2. **کدام Snapshot «جاری» است** — `current_snapshot` باید تعریف کند: آخرین `ACTUAL`؟ آخرین به
   ترتیب `created_at`؟ این یک تصمیم محصولی است.
3. **ردیف‌های Assignment در سطح Task** — `assignmentExternalId = None` و تطبیق از راه
   `activityCode`. **هیچ Assignmentی ساخته نمی‌شود.**

> بدون این Adapter، Finance کار می‌کند ولی گزارش‌ها بدون پیشرفت‌اند: هر خط `unmapped_activity`
> می‌شود، با هشدار. **این وضعیتی صادقانه است، نه خرابی** — و دقیقاً چیزی است که در فاز ۲
> تضمین شد.

### گام ۳ — Adapter ذخیره فایل

```
put(metadata, content) -> stored_name
get(organization_id, project_id, file_id) -> bytes
```

باید Storage واقعی میزبان را بپوشاند. تشخیص نوع فایل لازم نیست — Finance خودش امضای بایتی را
می‌خواند.

**بدون این، بارگذاری فایل کار نمی‌کند** ولی بقیه ماژول کار می‌کند.

### گام ۴ — Adapter فعالیت پروژه

```
list_activities / get_activity / create_activity
```

برای اتصال خطوط برآورد به فعالیت‌های WBS. اگر Core منبع فعالیت دارد، از آن؛ وگرنه از
`msp_tasks`.

### گام ۵ — استخراج تصویر و صوت (اختیاری)

`InvoiceImageExtractor` و `InvoiceVoiceExtractor`. **۵۵ از ۵۷ مسیر بدون این‌ها کار می‌کنند.**
تا وقتی Provider واقعی نیست، `UnavailableExtractor` رفتار درست را دارد: ۵۰۳ صریح، نه داده ساختگی.

**بدون عجله.** این گام می‌تواند بعد از استقرار اولیه بیاید.

### گام ۶ — Host Fixture برای تست یکپارچه (اختیاری)

فقط اگر بخواهیم Adapterها را روی Schema واقعی Core بیازماییم. باید:

- در `devhost/` بماند و کتابخانه Finance آن را import نکند
- هرگز در Migrationهای Production نیاید
- از روی Export واقعی Core ساخته شود، نه دست‌ساز
- فقط حداقل جدول‌های لازم را بسازد

---

## چک‌لیست سیم‌کشی Production

میزبان BAMBO باید این ۱۴ کلید را روی `application.state` بگذارد:

```python
# سه Adapter امنیتی — بدون این‌ها هیچ مسیری کار نمی‌کند
application.state.auth_context_provider   = <BambooAuthContextProvider>
application.state.scope_authorizer        = <BambooScopeAuthorizer>
application.state.permission_authorizer   = <BambooPermissionAuthorizer>

# یازده سرویس دامنه، هرکدام با Repository روی اتصال psycopg
application.state.finance_settings_service    = FinanceSettingsService(...)
application.state.finance_resources_service   = FinanceResourcesService(..., activity_provider)
application.state.finance_price_service       = FinancePriceService(...)
application.state.unit_conversion_service     = UnitConversionService(...)
application.state.progress_service            = ProgressService(..., progress_provider)
application.state.finance_import_service      = FinanceImportService(...)
application.state.invoice_service             = FinanceInvoiceService(...)
application.state.finance_attachment_service  = FinanceAttachmentService(..., file_storage)
application.state.finance_extraction_service  = FinanceExtractionService(..., image, voice)
application.state.finance_live_report_service = FinanceLiveReportService(..., progress_provider)
application.state.finance_audit_service       = FinanceAuditService(...)
```

**پیش‌نیاز Schema:** `alembic upgrade head` باید **صریحاً** اجرا شده باشد. راه‌اندازی برنامه
Migration اجرا نمی‌کند؛ اگر Schema نباشد، پیام روشن می‌دهد.

**نقش دیتابیس:** Migration با نقش Owner، Runtime با نقشی که DDL نمی‌تواند بزند.

---

## قرارداد پیشنهادی همگام‌سازی خلاصه مالی (پیاده نشده)

Core این ستون‌ها را دارد و Finance امروز **هیچ‌کدام را نمی‌خواند و نمی‌نویسد**:

`estimated_cost` · `actual_cost_to_date` · `cost_source` · `cost_unit` ·
`cost_updated_at` · `cost_updated_by`

اگر روزی تصمیم گرفته شود Finance مرجع این اعداد باشد:

| پرسش | پیشنهاد | چرا |
|---|---|---|
| چه رویدادی Sync را راه می‌اندازد؟ | **صدور گزارش رسمی** | همان لحظه‌ای است که Finance عددی را رسمی اعلام می‌کند و ورودی‌هایش را Pin می‌کند |
| `estimated_cost` یعنی چه؟ | باید صریح انتخاب شود | Finance سه کاندید دارد: برآورد اولیه، برآورد بازنگری‌شده، پیش‌بینی نهایی. انتخاب اشتباه هر مصرف‌کننده Core را گمراه می‌کند |
| `actual_cost_to_date` یعنی چه؟ | `actualCostIrr` | روشن‌ترین مورد: جمع خطوط فاکتور تأییدشده با علامت مالی |
| `cost_source` کی `FINANCE_MODULE` می‌شود؟ | اولین انتشار موفق | |
| شکست چه می‌شود؟ | `cost_updated_at` قدیمی بماند | نوشتن ناقص بدتر از ننوشتن است؛ و Finance نباید تراکنش خودش را به نوشتن در Core گره بزند |
| آیا Core می‌تواند ورودی Finance شود؟ | **هرگز** | `numeric(20,2)` در Core مقادیری می‌پذیرد که Finance به‌عنوان ریال کسری رد می‌کند |

**یک‌طرفه، همیشه.** و هیچ محاسبه‌ای در Finance نباید به این ستون‌ها وابسته شود.

**این نوشتن اقدام RED است** و تأیید جداگانه می‌خواهد.

---

## آنچه عمداً پیشنهاد نمی‌شود

| مورد | چرا |
|---|---|
| FK فیزیکی از Finance به Core | Core با حذف پروژه CASCADE می‌کند؛ `RESTRICT` حذف را در Core مسدود می‌کند و `CASCADE` تاریخچه مالی را نابود. اعتبارسنجی در Adapter می‌ماند |
| Seed کردن مجوزها از Migration | ممنوع. RBAC مال Core است |
| ساختن جدول Assignment در Core | Core مالک Schema خودش است |
| جایگزینی `finance_attachments` با `media_files` | ۸ ستون در برابر ۱۶؛ Hash، یکتایی تکراری، وضعیت پردازش و حذف منطقی از دست می‌رود |
| ادغام `finance_audit_events` در `audit_logs` | ممیزی Core تریگر تغییرناپذیری ندارد — ادغام یک ویژگی امنیتی را تنزل می‌دهد |
| Revision 0007 | تا وقتی تصمیمی که به Schema نیاز دارد گرفته نشده، لازم نیست |

---

## معیار پایان فاز ۳

1. سه Adapter امنیتی نوشته و آزموده شده‌اند
2. Adapter پیشرفت از Core واقعی می‌خواند و نگاشت `status` تأیید شده است
3. Adapter ذخیره فایل کار می‌کند
4. `finance_report.issue` در Core تأیید یا نگاشت شده است
5. تست‌های یکپارچه با Adapterهای واقعی روی دیتابیس Disposable سبزند
6. هیچ Mockی در مسیر Production نیست — که **امروز هم همین‌طور است**
7. هیچ تغییر API شکننده‌ای رخ نداده
