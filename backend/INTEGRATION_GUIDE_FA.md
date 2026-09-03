# راهنمای Integration ماژول مالی

## Composition Root میزبان

میزبان BAMBO باید قبل از سرویس‌دهی، Portها و Serviceهای زیر را در `application.state` قرار دهد. Repositoryهای PostgreSQL موجود در `app/finance/repositories` یک connection سازگار با Psycopg می‌گیرند.

### Portهای میزبان

- `auth_context_provider`: تولید `AuthContext` معتبر از Session میزبان
- `scope_authorizer`: کنترل عضویت سازمان و پروژه
- `permission_authorizer`: کنترل Permission بدون fallback مخفی
- File Storage: پیاده‌سازی Port ذخیره فایل با کلید غیرعمومی
- Progress Snapshot Provider: خوراک فقط‌خواندنی مطابق Integration Kit
- Image/Voice Extraction Provider: Adapter مستقل از Provider

### Serviceهای route

- `finance_settings_service`
- `finance_resources_service`
- `finance_price_service`
- `unit_conversion_service`
- `progress_service`
- `finance_import_service`
- `invoice_service`
- `finance_attachment_service`
- `finance_extraction_service`
- `finance_live_report_service`
- `finance_audit_service`

## Permissionها

- خواندن داده مالی و Audit: `finance.view`
- تغییر داده‌های پایه: `finance.edit`
- مشاهده گزارش Snapshot: `finance_report.view`
- صدور Snapshot غیرقابل‌تغییر: `finance_report.issue`
- دریافت CSV/XLSX: `finance_report.export`

Permissionهای پیشنهادی جزئی‌تر Integration Kit فقط پس از تصویب mapping میزبان جایگزین Permissionهای موجود می‌شوند.

## قواعد اتصال

- `organizationId` فقط از AuthContext معتبر گرفته می‌شود و از body پذیرفته نمی‌شود.
- `projectId` مسیر باید با پروژه Context و عضویت کاربر تطبیق داده شود.
- تمام Repositoryها هر دو کلید scope را در Query اعمال می‌کنند.
- مبلغ IRR در API رشته Decimal و در PostgreSQL از نوع `numeric(18,0)` است.
- فایل و Progress از طریق Adapter مصرف می‌شوند؛ مسیر فایل Production و MPP مستقیماً خوانده نمی‌شود.
- Snapshot صادرشده، فاکتور Confirmed و تاریخچه‌های append-only نباید update یا delete شوند.

## Gate پیش از Production

1. Backup و برنامه Restore تأیید شود.
2. Up، اجرای مجدد Up و Down روی PostgreSQL 16 و 18 آزمایش شود.
3. Adapterهای واقعی میزبان جایگزین Fakeهای تست شوند.
4. تست tenant isolation، IDOR، Permission و Contract Kit اجرا شود.
5. هیچ Secret یا URL داخلی در تنظیمات/Repository ثبت نشود.
6. Migration فقط توسط تیم اصلی BAMBO اجرا شود.
