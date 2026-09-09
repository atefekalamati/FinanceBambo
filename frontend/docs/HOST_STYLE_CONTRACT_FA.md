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

## Tooltip

تولتیپ متعلق به میزبان است، نه ماژول. میزبان `scripts/app/tooltips.js` را دارد که هر
`title` بومی را به حباب تم‌دار `styles/components/tooltip.css` تبدیل می‌کند: روی hover و
focus متن را می‌خواند، `title` را موقتاً برمی‌دارد تا حباب خاکستری خود مرورگر ظاهر نشود،
و هنگام خروج برش می‌گرداند.

**قاعدهٔ ماژول: هر توضیحی که باید روی hover دیده شود، یک `title` بومی است و بس.** ماژول
هیچ حبابی نمی‌کشد — نه با `::after`، نه با عنصر شناور، نه با z-index بالا.

- در حالت Host: حباب میزبان خودکار روی همان `title`ها می‌نشیند؛ صفر خط کد اتصال.
- در پیش‌نمایش مستقل: تولتیپ بومی مرورگر دیده می‌شود. این پذیرفته‌شده است — کپی‌کردن
  موتور میزبان به داخل ماژول یعنی ساختن سیستم موازی و دو ظاهر متفاوت.
- عنصری که `title` می‌گیرد و با صفحه‌کلید معنا دارد، باید `tabIndex` و در صورت لزوم
  `aria-label` هم داشته باشد؛ موتور میزبان روی `focusin` هم باز می‌شود.

**تنها استثنا:** پنل تولتیپ نمودار روند ماهانه (`.combo-chart__tooltip`). آن یک پنل
چندسطری با ردیف‌های داده است، نه یک جملهٔ کوتاه، و `title` نمی‌تواند نگهش دارد.

## قواعد ممنوع

- اعمال `body.dash-page`, `has-sidebar` یا offsetهای Sidebar در ماژول.
- قفل‌کردن `body` با `overflow: hidden`؛ Scroll متعلق به Container میزبان است.
- بازسازی Chrome میزبان یا استفاده از z-index خارج قرارداد.
- تغییر Token سراسری میزبان از داخل Featureهای مالی.
- ساختن تولتیپ اختصاصی با `::after` یا عنصر شناور (به بخش Tooltip بالا نگاه کنید).
