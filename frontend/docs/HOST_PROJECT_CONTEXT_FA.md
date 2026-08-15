# قرارداد تغییر پروژه از Host اصلی BAMBO

ماژول مالی انتخاب‌گر پروژه مستقل ندارد. هدر اصلی BAMBO پروژه مجاز را انتخاب می‌کند و Context جدید را به ماژول اعلام می‌کند.

## Context اولیه

Host پیش از اجرای ماژول مقدار زیر را تنظیم می‌کند:

```js
window.__BAMBO_FINANCE_CONTEXT__ = {
  userId: "...",
  organizationId: "...",
  organizationName: "...",
  projectId: "project_01",
  projectName: "پروژه نمونه",
  projectCode: "PRJ-01",
  grossBuiltArea: "4250.0000",
  permissionCodes: ["finance.view"],
  locale: "fa-IR",
  timezone: "Asia/Tehran",
};
```

## اعلام تغییر پروژه

بعد از انتخاب پروژه در هدر اصلی، Host باید Context کامل پروژه جدید را ارسال کند:

```js
window.dispatchEvent(new CustomEvent("bambo:project-context-changed", {
  detail: {
    context: nextFinanceContext,
  },
}));
```

Frontend پس از دریافت Event:

1. Context را اعتبارسنجی و جایگزین می‌کند.
2. تمام API Adapterها را با `projectId` جدید می‌سازد.
3. عنوان و مشخصات پروژه را به‌روزرسانی می‌کند.
4. Route جاری را برای پروژه جدید دوباره بارگذاری می‌کند.
5. Permissionهای پروژه جدید را دوباره اعمال می‌کند.

تمام درخواست‌های مالی از مسیر `/api/projects/{projectId}/finance/...` ارسال می‌شوند. `organizationId` یا `projectId` از داده صفحه قبلی یا Body درخواست گرفته نمی‌شود.

اگر Context جدید نامعتبر باشد، پروژه فعلی جایگزین نمی‌شود و پیام خطا از Live Region ماژول اعلام می‌شود.
