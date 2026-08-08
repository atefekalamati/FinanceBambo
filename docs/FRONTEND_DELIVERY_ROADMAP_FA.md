# مسیر تحویل Frontend مالی BAMBO

وضعیت روزانه، درصد وزنی، اولویت بعدی و تخمین پایان در `docs/PROJECT_PROGRESS_FA.md` نگه‌داری می‌شود. این فایل مسیر سطح‌بالا را تعریف می‌کند و فایل وضعیت، مرجع اجرای روزانه است.

این مسیر فقط مسئولیت Frontend را پوشش می‌دهد. Backend، Migration، محاسبات مرجع، Auth و Scope سمت سرور خارج از مسئولیت این مخزن هستند.

## Gate 1 — Foundation و Shell (شروع شده)

خروجی: HTML/ES Modules بدون Build، RTL shell، Design Tokens، Router، Host Context Adapter، Same-Origin API client، permission visibility، stateهای عمومی، صفحه یکپارچه امور مالی، print base و unit test بدون dependency. مطابق UI میزبان، ماژول Dashboard یا Sidebar داخلی ندارد.

معیار پایان: اجرای محلی، دسترسی صفحه‌کلید، responsive پایه، عدم استفاده از Mock Auth و عدم فرض Endpoint تولید.

## Gate 2 — تنظیمات و اقلام مالی

ترتیب: Settings زیربنا → Financial Items → Estimate Lines → Revision → Import Preview/Commit.

وضعیت: Settings، Financial Items، Revision و Estimate Import Preview/Commit تکمیل شده‌اند.

وابستگی Backend آینده: schema دقیق list/detail، pagination/filter، optimistic version و error details. تا آن زمان Feature APIها پشت Adapter و fixtureهای منطبق با Contract توسعه می‌یابند.

## Gate 3 — قیمت و تبدیل واحد

ترتیب: Price list/current/history → base/override form → price import preview → unit conversions. سه بخش نخست تکمیل شده‌اند و اولویت فعال Unit Conversion است. Frontend فقط Decimal string را validate/ارسال می‌کند و محاسبه مرجع ندارد؛ پول و unit price طبق نسخه ۱.۱ حتماً رشته عدد صحیح ریال‌اند.

## Gate 4 — Progress Snapshot

فهرست Snapshot، feed فقط‌خواندنی، نمایش sourceMethod/quality/warning و modal Override با reason. Finance هیچ MPP را Parse نمی‌کند.

## Gate 5 — فاکتور دستی

فهرست و جزئیات → فرم سه‌مرحله‌ای چندردیفی → preview → duplicate warning → confirm → void/corrective. Idempotency key و expected version در مرز API مدیریت می‌شوند.

## Gate 6 — فایل و AI Review

Upload عکس/ویس → processing states → field confidence/edit → retry/reject/confirm. Draft قبل از Confirm همیشه اثر مالی صفر دارد و Provider از Browser فراخوانی نمی‌شود.

## Gate 7 — خلاصه مالی و Reports

پس از پایدارشدن داده‌های مراحل قبل: ۸ KPI، warningها، نمودار داخلی SVG/Canvas، جدول جایگزین، live report، issue snapshot، print A4 و CSV.

## Gate 8 — Audit و سخت‌سازی

Audit list/detail، تمام stateهای 403/404/409/422/503، RTL/mobile/keyboard/print QA، race/stale/idempotency UX و contract test.

## Gate 9 — تطبیق با Backend روی GitHub

1. دریافت OpenAPI و نمونه Payload واقعی Backend.
2. ساخت ماتریس اختلاف بین Adapter فعلی و Backend.
3. تطبیق mapperها و Feature APIها، بدون نشت شکل Backend به UI.
4. تست Scope/permission/error/decimal/version/idempotency مقابل محیط مشترک.
5. حذف fixtureهای موقت از runtime و نگه‌داشتن آن‌ها فقط در tests.
6. Integration QA و Acceptance Testهای PRD.

## ترتیب پیشنهادی Iterationها

| Iteration | خروجی Frontend |
|---|---|
| ۱ | Foundation، Shell و صفحه یکپارچه امور مالی |
| ۲ | Settings، Items، Estimate Lines و Import Preview |
| ۳ | Prices، Conversions و Progress Feed |
| ۴ | Invoice دستی end-to-end |
| ۵ | File/AI Review |
| ۶ | Dashboard واقعی، Reports، Print و CSV |
| ۷ | Audit، accessibility، responsive و error hardening |
| ۸ | Backend integration و acceptance fixes |

هر Iteration تنها زمانی بسته می‌شود که loading/empty/error/denied/content، validation، keyboard و mobile آن Feature تکمیل شده باشد.
