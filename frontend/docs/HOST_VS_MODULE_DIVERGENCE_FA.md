# جاهایی که سایت اصلی و ماژول مالی دو راه متفاوت رفته‌اند

تاریخ بررسی: ۱۸ شهریور ۱۴۰۵ — 2026-09-09

**روش:** یازده اسکریپت عمومی داشبورد از `dash.bambo.one` دانلود و خوانده شد
(`api.js`، `ProjectScopeSelector.js`، `rbac.js`، `sidebar.js`، `layout.js`،
`dashboard.js`، `msp.js`، `msp/schedule-tab.js`، `msp/reports-tab.js`،
`msp/period-adapter.js`، `msp/voice-report-tab.js`، `utilities/JalaliDate.js`) — حدود
۲۹۰ کیلوبایت. این فایل‌ها بدون ورود قابل دریافت‌اند. صفحه‌های HTML داشبورد پشت ورود
هستند و خوانده نشدند، پس هرچه اینجا آمده از کد سمت کلاینت است، نه از بک‌اند میزبان.

---

## ۱. قرارداد اتصال ما در سایت اصلی وجود ندارد — بحرانی

در هیچ‌کدام از یازده اسکریپت، هیچ‌یک از این سه نیست:

```
window.__BAMBO_FINANCE_CONTEXT__      ← ماژول بدون آن راه نمی‌افتد
رویداد bambo:project-context-changed  ← ماژول بدون آن تعویض پروژه را نمی‌فهمد
عنصر #finance-module-root             ← ماژول بدون آن جایی برای رندر ندارد
```

**سایت اصلی به‌جای آن، دامنهٔ پروژه را این‌طور نگه می‌دارد** (`ProjectScopeSelector.js`):

```js
// ترتیب تقدم: پارامتر URL بر localStorage می‌چربد
?project=<id>  در query string        ← صریح و قابل اشتراک‌گذاری
localStorage['bambo:project']         ← انتخاب قبلی کاربر
localStorage['bambo:org']             ← سازمان

export function currentProjectId()    ← تنها منبع حقیقت برای «پروژهٔ جاری»
```

و شناسه را با `history.replaceState` به URL برمی‌گرداند تا صفحهٔ بعد هم همان دامنه را
داشته باشد.

**نتیجه:** اگر امروز ماژول را mount کنند، کارت خطای «اطلاعات پروژه از سایت اصلی دریافت
نشده است» می‌بینند و هیچ صفحه‌ای بالا نمی‌آید.

**چه لازم است:** حدود پانزده خط چسب در صفحهٔ میزبان، پیش از اجرای `bootstrap.js` —
خواندن `currentProjectId()`، گرفتن سازمان و مجوزها، و ساختن آن شیء. کار کوچکی است، ولی
**کسی ننوشته و از کسی خواسته هم نشده.**

---

## ۲. تومان در برابر ریال — ریسک خطای ده‌برابری، بحرانی

`dashboard.js` خطوط ۸۵۲–۸۶۵ یک هشدار دارد که **مستقیماً خطاب به تیم ماست**:

> ستون `cost_unit` در `app/schema.sql` برچسب `'IRR'` (ریال) دارد و با یک CHECK قفل شده،
> **ولی هیچ‌جای این کدبیس هرگز ریال ذخیره نکرده**: فیلد «برآورد هزینهٔ پروژه (تومان)» در
> `project-settings.html` عددی را که کاربر تایپ می‌کند بدون هیچ تبدیلی می‌فرستد — پس عدد
> ذخیره‌شده سرتاسر **تومان** است.
>
> «… تا اگر روزی **یک ماژول مالی** از همین فیلد بنویسد بی‌صدا خراب نشود: هرچه
> `estimated_cost`/`actual_cost_to_date` را می‌نویسد **باید تومان ساده بنویسد، نه ریال**،
> تا وقتی schema و CHECK ستون `cost_unit` درست migrate شود.»

خودشان یک‌بار همین باگ را داشته‌اند و در «Wave-4 owner defect A2-3» با عنوان
**«REAL 10x BUG»** اصلاحش کرده‌اند: یک تقسیم بر ۱۰ اضافه، هر عدد را یک‌دهم نشان می‌داد.

**در برابرش، قاعدهٔ قطعی ماژول ما** (`README.md`، `FINANCE_HANDOFF.md`):

> پول رسمی IRR است، در API رشتهٔ Decimal و در دیتابیس `numeric(18,0)`؛ محاسبهٔ پول با
> float مجاز نیست.

یعنی دو سیستم همسایه، یکی تومان و یکی ریال، **با ضریب ۱۰ اختلاف** — و ستونی که برچسبش
دروغ می‌گوید. هر جریان داده‌ای بین این دو باید صریحاً تبدیل کند.

---

## ۳. «فایل مبنا» و «دوره» در سایت اصلی از قبل ساخته شده — پاسخ سؤال باز ما

بزرگ‌ترین مجهول در سند [ESTIMATE_SOURCE_REQUEST_FA.md](../../ESTIMATE_SOURCE_REQUEST_FA.md)
این بود: «فایل مبنا چطور تشخیص داده می‌شود؟»

**جواب: یک API کامل برایش هست** (`msp/period-adapter.js`):

```
GET    /projects/{pid}/msp/baseline-revisions
       → { revisions: [...], currentRevisionId, plannedFinishJalali }
POST   /projects/{pid}/msp/baseline-revisions
       { snapshotId, effectiveFromJalali, label }     ← «برنامه مبنا» از این تاریخ به بعد
DELETE /projects/{pid}/msp/baseline-revisions/{id}

GET    /projects/{pid}/msp/reporting-calendar
PUT    /projects/{pid}/msp/reporting-calendar
POST   /projects/{pid}/msp/reporting-calendar/regenerate

GET    /projects/{pid}/msp/reporting-periods[?scope=all|reportable]
       → [{ id, sequenceNumber, periodStartJalali, periodEndJalali,
             targetSnapshotId, actualSnapshotId, baselineRevisionId,
             status, isManual, targetLabelFa, actualLabelFa, targetIsDerived }]
POST   /projects/{pid}/msp/reporting-periods
GET    /projects/{pid}/msp/reporting-periods/{id}/target
POST   /projects/{pid}/msp/reporting-periods/{id}/actual
```

سه نکته که مدل ما ندارد:

1. **مبنا یکی نیست، تاریخچه دارد.** هر بازنگری مبنا یک `effectiveFromJalali` دارد و
   `currentRevisionId` می‌گوید کدام امروز معتبر است.
2. **هر دوره سه‌تایی است:** `baselineRevisionId` + `targetSnapshotId` + `actualSnapshotId`.
   سه کلاس صریح: مبنا / هدف مشتق‌شده / واقعیِ پیوست‌شده.
3. **`scope=reportable`** فهرست را تا آخرین دوره‌ای که واقعاً Actual دارد کوتاه می‌کند، تا
   انتخاب‌گر گزارش دوره‌ای را پیشنهاد ندهد که گزارش رویش اجرا نمی‌شود.

**در برابرش ماژول ما:** جدول `progress_snapshot_refs` با `reporting_date` و
`snapshotType: ACTUAL | TARGET`. **نه مفهوم مبنا، نه دوره، نه تاریخچهٔ بازنگری.**

و بدتر: صفحهٔ گزارش سطح ۱ ما Snapshot را این‌طور انتخاب می‌کند
([level-one-page.js:38](../src/features/level-one/level-one-page.js#L38)):

```js
const snapshot = snapshots.find((entry) => entry.status === "ready") ?? null;
```

**اولین Snapshot آماده — نه مبنا، نه دوره‌ای مشخص.** یعنی حتی وقتی داده درست شود، ممکن
است گزارش ما به فایلی تکیه کند که سایت اصلی آن را مبنا نمی‌داند.

---

## ۴. مدیر بامبو: میان‌بری که فقط یک طرف دارد

**سایت اصلی** (`rbac.js`) — همان قاعده‌ای که همهٔ گیت‌های سایدبار می‌خوانند:

```js
GET /api/rbac/my-permissions  →  { isBamboAdmin, permissions: [...] }
isBamboAdmin || permissions.includes(code)
```

**بک‌اند مالی** (`coreint/security.py`، `CoreRbacPermissionAuthorizer`) — **هیچ میان‌بری
ندارد.** هر درخواست، `user_roles → role_permissions → permissions` را دوباره می‌خواند و
کدی را که آن ردیف نداده رد می‌کند، هرکس که باشد.

پس اگر فرانت پرچم `isBamboAdmin` را محترم بشمارد، دکمه‌هایی می‌کشد که **تنها جواب
ممکنشان ۴۰۳ است** — دقیقاً همان چیزی که `capabilities.js` برای جلوگیری از آن نوشته شده.

**نتیجه: فرانت نباید این پرچم را ترجمه کند، و نمی‌کند.** اگر قرار است ادمین بامبو به
مالی دسترسی داشته باشد، باید **کدهای مالی به نقش ادمین در Core داده شوند** — همان تصمیم
Seed که `finance_report.issue` هم منتظرش است.

> این بند در نسخهٔ اول این سند وارونه نوشته شده بود («ماژول ما باگ دارد»). تغییری هم که
> بر اساس آن نوشته شده بود، در `host-context-discovery.js` برداشته شد.

---

## ۵. زیربنای ناخالص، دو منبع دارد

| کجا | ستون / فیلد | چه کسی ویرایش می‌کند |
|---|---|---|
| سایت اصلی | `projects.built_area_sqm` | صفحهٔ `project-settings.html` |
| ماژول ما | `finance_project_settings.gross_built_area` | صفحهٔ تنظیمات مالی، با بازنگری |

هر دو «مساحت ناخالص پروژه» را نگه می‌دارند و هیچ‌کدام از دیگری خبر ندارد. ماژول ما دو
سنجهٔ کلیدی روی این عدد می‌سازد: «هزینهٔ واقعی هر مترمربع» و «پیش‌بینی هزینه هر مترمربع».
اگر دو عدد از هم فاصله بگیرند، **داشبورد و گزارش مالی دو رقم متفاوت برای یک پروژه**
نشان می‌دهند و هیچ‌چیز روی صفحه توضیحش نمی‌دهد.

`GET /api/projects/{pid}` هر سه را برمی‌گرداند: `built_area_sqm`، `estimatedCost`،
`actualCostToDate`، `costUnit`.

---

## ۶. تعریف «سطح ۱» — مسئلهٔ اصلی که این بررسی از آن شروع شد

**سایت اصلی:** سرور حساب می‌کند، و **هر دو باند از پیش آماده‌اند**:

```js
{ key: 'level1', label: 'پیشرفت برنامه‌ای/واقعی سطح ۱' }
{ key: 'level2', label: ... }

const BAND_HEAD = ['کد', 'عنوان', 'تعداد', 'وزن', 'برنامه', 'واقعی', 'این دوره'];

GET /api/projects/{pid}/msp/reports/complete?...   → payload.level1 / payload.level2
GET /api/projects/{pid}/msp/reports/charts/level1  → تصویر نمودار، رندرشده در سرور
```

نام تابع پایتونی‌شان در کامنت‌ها آمده: **`build_level1_contribution(..., cumulative=True)`**.

**ماژول ما:** [`domain/wbs.py:152`](../../../finance-backend/backend/app/finance/domain/wbs.py#L152)

```python
chosen = [code for code in nodes if level_of(code) == depth]   # depth = 1
```

یعنی «سطح ۱» = کدهایی که یک بخش دارند. در فایل واقعی این پروژه، آن‌ها گرهٔ خودِ پروژه‌اند
(`0` و `1`)، نه مراحل. مراحل در `1.1`، `1.2`، … هستند.

**سه تفاوت، نه یکی:**

1. **عمق:** آن‌ها مرحله می‌دهند، ما پروژه.
2. **پیمایش:** آن‌ها دو باند آماده دارند؛ ما با کلیک و تغییر آدرس یک سطح پایین می‌رویم.
3. **ستون «وزن»:** آن‌ها دارند، **ما اصلاً نداریم.** وزن در گزارش کنترل پروژه معنای
   مشخصی دارد (جمع وزن‌ها ۱۰۰) و گزارش مالی بدون آن، ستونی کم دارد که خواننده انتظارش را
   دارد.

---

## ۷. شکل صفحه در سایدبار

`sidebar.js` خط ۹۶–۹۷ — **دو ورودی ما از قبل تعریف شده‌اند، غیرفعال:**

```js
// Coming-soon (disabled, «به‌زودی»).
{ key: 'finance',        label: 'امور مالی',   icon: ICONS.finance,       disabled: true },
{ key: 'finance-report', label: 'گزارش مالی',  icon: ICONS.financeReport, disabled: true },
```

ورودی فعال در همان فایل این شکل را دارد:

```js
{ key: 'project-control', label: 'کنترل پروژه', href: '/msp.html', icon: ..., gate: 'projectControl' }
```

**یعنی الگوی میزبان: هر ورودی سایدبار = یک فایل HTML جدا.** پس ماژول ما احتمالاً دو صفحه
می‌شود (`/finance.html` و `/finance-report.html`)، هرکدام یک نمونهٔ مستقل از ماژول.

ماژول ما اما **یک SPA با ۱۸ مسیر hash** است. این قابل حل است — هر صفحه روی
`homeRouteFor(surface)` خودش باز شود — ولی **هیچ‌جا نوشته نشده** و کسی تصمیمش را نگرفته.
ضمناً تابع `activeKey()` در `sidebar.js` باید مسیرهای ما را هم بشناسد، وگرنه لینک سایدبار
هایلایت نمی‌شود.

---

## ۸. ابزارهای تکراری — ریسک کم، ولی واگرایی خاموش

میزبان `scripts/utilities/JalaliDate.js` دارد با این توابع:

```
d2j · g2j · j2g · jalaliMonthLength · jalaliWeekday
parseJalaliKey · jalaliKey · faDigits · formatJalaliLabel
```

ماژول ما `shared/dates/persian-date.js` و `shared/formatters/display.js` را دارد که
همان کارها را می‌کنند. **دو پیاده‌سازی از یک تقویم.** اگر در یک تاریخ مرزی اختلاف پیدا
کنند، دو صفحه در یک سایت دو تاریخ می‌گویند.

نکتهٔ مثبت: هر دو `Asia/Tehran` را صریح می‌دهند —
`fa-IR-u-ca-persian` با `timeZone: 'Asia/Tehran'` در هر دو طرف. این یکی می‌خواند.

---

## ۹. جاهایی که **می‌خوانیم** ✅

| موضوع | میزبان | ما |
|---|---|---|
| قالب خطا | `{ code, messageFa }` | هر دو قالب پشتیبانی می‌شود |
| احراز هویت درخواست | `credentials: 'same-origin'` | همان |
| **CSRF** | **هیچ توکنی نمی‌فرستد** | ما هم نمی‌فرستیم — **پرسش باز ما جواب گرفت** |
| ریشهٔ API | `/api` | `/api/projects/{pid}/finance` |
| منطقهٔ زمانی | `Asia/Tehran` صریح | همان |
| فونت و Token‌ها | Vazirmatn، `data-theme` روی `html` | ۸۹ از ۹۰ Token یکسان |

---

## ۱۰. یک تفاوت کوچک‌تر

**آپلود:** میزبان برای پیشرفت بایت‌به‌بایت از `XMLHttpRequest` استفاده می‌کند، چون
`fetch` پیشرفت آپلود را گزارش نمی‌دهد. ماژول ما با `fetch` آپلود می‌کند، پس **نوار پیشرفت
ندارد**. برای فایل اکسل کوچک مهم نیست؛ برای عکس ۱۰ مگابایتی یا صوت ۲۵ مگابایتی روی
اینترنت کند، کاربر نمی‌داند چیزی در حال ارسال است.

---

## اولویت‌بندی

| # | موضوع | ریسک | مالک |
|---|---|---|---|
| ۱ | قرارداد اتصال وجود ندارد | ماژول اصلاً بالا نمی‌آید | میزبان (۱۵ خط) |
| ۲ | تومان در برابر ریال | خطای ده‌برابری در پول | هر دو — تصمیم مشترک |
| ۳ | مبنا و دوره در ما نیست | برآورد به فایل غلط تکیه می‌کند | ما، با API آمادهٔ آن‌ها |
| ۴ | `isBamboAdmin` | ادمین پشت در می‌ماند | میزبان، هنگام ساخت Context |
| ۵ | تعریف سطح ۱ | دو فهرست متفاوت از مراحل | بک‌اند ما، هماهنگ با آن‌ها |
| ۶ | زیربنا، دو منبع | دو رقم برای یک پروژه | تصمیم محصولی |
| ۷ | یک HTML به‌ازای هر لینک | تصمیم نگرفته | میزبان + ما |
| ۸ | تقویم تکراری | واگرایی خاموش | کم‌اهمیت |
