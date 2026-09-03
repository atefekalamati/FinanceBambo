# Permission Matrix ماژول مالی BAMBO

مرجع: `04_AUTH_AND_PERMISSION_CONTRACT.md` از Integration Kit نسخه ۱.۱ و نقش‌های PRD نسخه ۱.۱.

## قواعد قطعی

- Naming میزبان دقیقاً `<module>.<action>` و دارای یک نقطه است.
- Permissionهای موجود و تأییدشده: `finance.view`، `finance.edit`، `finance_report.view` و `finance_report.export`.
- `finance_report.issue` و Permissionهای جزئی `finance.*` پیشنهادی‌اند و تا زمان تأیید/Seed تیم BAMBO واقعیت Production محسوب نمی‌شوند.
- Authentication، عضویت سازمان، عضویت پروژه و Permission چهار Gate مستقل‌اند.

## Mapping فعلی Endpointها

| Endpoint/Action | Permission فعلی Backend | وضعیت قرارداد |
|---|---|---|
| GET settings/summary/resources/estimate-lines/prices/conversions/progress/invoices/audit | `finance.view` | خواندن عملیاتی امور مالی؛ موجود و معتبر |
| GET reports/live | `finance_report.view` | مشاهده خروجی محاسبه‌شده گزارش مالی؛ موجود و معتبر |
| PATCH settings برای `org_chief` | `finance.view` | رفتار نقش از PRD؛ تأیید mapping میزبان لازم |
| PATCH settings برای سایر نقش‌های مجاز | `finance.edit` | موجود؛ target پیشنهادی `finance.manage_settings` |
| POST/PATCH resources و estimate revisions | `finance.edit` | fallback موجود؛ targetهای جزئی پیشنهادی‌اند |
| POST prices/conversions و Import | `finance.edit` | fallback موجود؛ target پیشنهادی `finance.manage_prices` |
| POST/PATCH invoice draft | `finance.edit` | fallback موجود؛ targetهای پیشنهادی `finance.create_invoice`/`finance.manage_invoice` |
| POST invoice confirm | `finance.edit` | تصمیم fallback در Kit نهایی نشده؛ Approval لازم |
| POST invoice void/corrective | `finance.edit` | تصمیم fallback در Kit نهایی نشده؛ Approval لازم |
| POST progress override | `finance.edit` | `finance.override_progress` پیشنهادی؛ Approval لازم |
| POST file و retry/confirm extraction | `finance.edit` | fallback موجود؛ mapping جزئی نیازمند Review |
| GET attachment metadata | `finance.view` | `finance.view_attachments` پیشنهادی؛ Approval لازم |
| POST report snapshot | `finance_report.issue` | پیشنهادی؛ Seed/Approval میزبان الزامی |
| GET report snapshot | `finance_report.view` | موجود و معتبر |
| GET CSV/XLSX | `finance_report.export` | موجود و معتبر |

## جداسازی قطعی Capabilityها

- `finance_report.view` با `finance.view` برابر نیست و دسترسی گزارش‌محور نباید فاکتور، قیمت، متره، فایل، Extraction یا Audit عملیاتی را در دسترس قرار دهد.
- `finance.view` با `finance_report.export` برابر نیست و مشاهده امور مالی مجوز Export گزارش ایجاد نمی‌کند.
- `GET /summary` یک Projection زمینه‌ای امور مالی شامل زیربنا، ارز و Revision تنظیمات است و با `finance.view` باقی می‌ماند.
- `GET /reports/live` فقط خروجی محاسبه‌شده گزارش را برمی‌گرداند و با `finance_report.view` محافظت می‌شود.

## نتیجه Review

- Naming Rule: **PASS**
- Permission چندنقطه‌ای: **وجود ندارد**
- Permission خارج از قرارداد: **وجود ندارد**
- Mapping قابل اجرای Production بدون تصمیم میزبان: **NO**
- Seed/Approval موردنیاز: `finance_report.issue` و تصمیم نهایی Confirm، Void/Corrective، Progress Override و Attachment access

Backend از `PermissionAuthorizer` میزبان استفاده می‌کند و هیچ Seed خودکاری انجام نمی‌دهد. تیم اصلی BAMBO باید mapping نهایی را تصویب، RBAC را Seed و تست 403/404 را در میزبان واقعی تکرار کند.
