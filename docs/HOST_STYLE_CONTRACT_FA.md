# قرارداد Style ماژول مالی با BAMBO

منبع این قرارداد Tokenها و CSS اصلی BAMBO است که در تاریخ ۱۴۰۵/۰۵/۱۵ برای پروژه ارائه شد.

## اصل ادغام

ماژول مالی Header، Sidebar یا Dashboard داخلی نمی‌سازد. در حالت Host، BAMBO مقدار `data-theme`، فونت و Tokenهای سراسری را فراهم می‌کند و ماژول فقط محتوای داخل mount را رندر می‌کند. Header کوچک موجود در `index.html` صرفاً پیش‌نمایش مستقل است و با `data-finance-runtime="host"` مخفی می‌شود.

## Tokenهای مصرفی

- هندسه: `--header-height`, `--toolbar-min-height`, radiusها و spaceها.
- رنگ و Theme: `--color-surface-*`, `--color-text-*`, `--color-border*`, `--brand-*`.
- Card: `--dash-card-grad`, `--dash-shadow`, `--dash-inner`؛ فقط ظاهر Card استفاده می‌شود و کلاس‌های Dashboard میزبان کپی نمی‌شوند.
- افکت: Glass background، blur، glow و shadowهای میزبان.
- Motion: durationها و easingهای اصلی، همراه با رعایت `prefers-reduced-motion`.

## Fallback مستقل

`src/shared/styles/tokens.css` مقادیر Dark/Light میزبان را برای اجرای مستقل روی پورت توسعه نگه می‌دارد. هنگام ادغام، Tokenهای میزبان با همان نام‌ها بدون Mapping اضافی قابل استفاده‌اند.

## قواعد ممنوع

- اعمال `body.dash-page`, `has-sidebar` یا offsetهای Sidebar در ماژول.
- قفل‌کردن `body` با `overflow: hidden`؛ Scroll متعلق به Container میزبان است.
- بازسازی Chrome میزبان یا استفاده از z-index خارج قرارداد.
- تغییر Token سراسری میزبان از داخل Featureهای مالی.
