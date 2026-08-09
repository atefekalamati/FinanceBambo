export const ROUTES = Object.freeze([
  { key: "finance-home", path: "/finance", label: "امور مالی", permission: "finance.view", enabled: true },
  { key: "financial-items", path: "/financial-items", label: "اقلام و متره", permission: "finance.view", enabled: true },
  { key: "prices", path: "/prices", label: "قیمت‌ها", permission: "finance.view", enabled: true },
  { key: "progress", path: "/progress", label: "پیشرفت مالی", permission: "finance.view", enabled: true },
  { key: "invoices", path: "/invoices", label: "فاکتورها", permission: "finance.view", enabled: false },
  { key: "reports", path: "/reports", label: "گزارش مالی", permission: "finance_report.view", enabled: false },
  { key: "settings", path: "/settings", label: "تنظیمات مالی", permission: "finance.edit", enabled: true },
]);

export const DEFAULT_ROUTE = "/finance";
