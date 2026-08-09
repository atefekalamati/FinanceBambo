# معماری پایه Frontend ماژول مالی BAMBO

ساختار پروژه Feature-based است. تعداد دامنه‌های مستقل مالی زیاد است و ساختار سراسریِ `services/components/validation` در حجم بالا وابستگی‌های نامشخص ایجاد می‌کند.

```text
finance-frontend/
├── AGENTS.md
├── README.md
├── docs/
├── public/assets/              # فقط Asset محلی تأییدشده
├── src/
│   ├── app/                    # bootstrap، router و shell
│   ├── adapters/
│   │   ├── host/               # Context و mount contract میزبان
│   │   └── mock/               # اتصال توسعه‌ای؛ نه auth تولید
│   ├── core/
│   │   ├── api/                # Same-origin client و error envelope
│   │   ├── auth/               # مصرف AuthContext و permission
│   │   ├── config/
│   │   ├── routing/
│   │   └── state/              # Context مشترک محدود
│   ├── features/
│   │   ├── finance-home/        # صفحه یکپارچه امور مالی؛ بدون Dashboard داخلی
│   │   ├── settings/
│   │   ├── financial-items/
│   │   ├── estimate-lines/
│   │   ├── prices/
│   │   ├── unit-conversions/
│   │   ├── progress-snapshots/
│   │   ├── invoices/
│   │   ├── ai-review/
│   │   ├── reports/
│   │   └── audit/
│   └── shared/
│       ├── components/
│       ├── formatters/
│       ├── styles/
│       ├── validation/
│       └── utils/
└── tests/{contract,unit,ui}/
```

هر Feature فقط در صورت نیاز زیرشاخه‌های `api/`, `components/`, `pages/`, `state/`, `validation/` و `tests/` خود را می‌سازد.

## جهت وابستگی

```text
Host BAMBO → adapters/host → core → feature pages → shared UI
Mock Host   → adapters/mock ────┘
```

- `shared` از Featureها import نمی‌کند.
- Featureها از فایل داخلی یکدیگر import نمی‌کنند.
- API mapping و Validation دامنه کنار همان Feature باقی می‌ماند.
- State سراسری فقط Context کاربر/سازمان/پروژه، permissionها و route را نگه می‌دارد؛ داده صفحه و draft فرم محلی Feature است.
- وضعیت درخواست‌ها به‌صورت `idle/loading/success/empty/error/denied` قابل آزمون است.

## قرارداد CSS و Responsive

- Responsive هر Feature هم‌زمان با خود Feature تکمیل می‌شود و در فایل CSS همان Feature قرار می‌گیرد.
- Ruleهای مشترک Layout فقط در `src/shared/styles/layout.css` و قواعد چاپ در فایل‌های Print نگه‌داری می‌شوند.
- هر Declaration در خط جدا، بین Ruleها یک خط خالی و بخش‌های فایل با Comment مشخص از هم جدا می‌شوند.
- نوشتن CSS فشرده و تک‌خطی در این مخزن مجاز نیست.

## مواردی که هنوز نباید کدنویسی شوند

- مسیر و شکل نهایی Adapterهای تولید BAMBO: در منابع تعریف نشده است.
- نگاشت نهایی permissionهای ریز: نیازمند تأیید BAMBO است.
- Provider واقعی OCR/Voice: باید از دو گزینه انتخاب شود و در Kit تعریف نشده است.
- Malware scanning، CSRF/Origin policy، worker پردازش طولانی و Endpointهای نهایی تولید: نهایی نشده‌اند.
