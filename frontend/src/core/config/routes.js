export const ROUTES = Object.freeze([
  { key: "finance-home", path: "/finance", label: "امور مالی", permission: "finance.view", enabled: true },
  { key: "financial-items", path: "/financial-items", label: "اقلام و برآورد", permission: "finance.view", enabled: true },
  { key: "prices", path: "/prices", label: "قیمت روز", permission: "finance.view", enabled: true },
  { key: "progress", path: "/progress", label: "پیشرفت مالی", permission: "finance.view", enabled: true },
  { key: "invoices", path: "/invoices", label: "فاکتورها", permission: "finance.view", enabled: true },
  { key: "invoice-files", path: "/invoice-files", label: "ورودی تصویر و صدا", permission: "finance.view", enabled: true },
  { key: "ai-review", path: "/ai-review", label: "بررسی هوشمند فاکتور", permission: "finance.view", enabled: true },
  { key: "reports", path: "/reports", label: "گزارش مالی", permission: "finance_report.view", enabled: true },
  { key: "audit", path: "/audit", label: "تاریخچه تغییرات مالی", permission: "finance.view", enabled: true },
  { key: "settings", path: "/settings", label: "تنظیمات مالی", permission: "finance.edit", enabled: true },
]);

export const DEFAULT_ROUTE = "/finance";
