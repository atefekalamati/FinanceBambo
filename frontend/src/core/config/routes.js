/**
 * The module lights up two sidebar links in the host, and every route belongs to
 * exactly one of them.
 *
 *   operations — امور مالی. The internal side: what the numbers are built from.
 *                Items and estimates, day prices, progress, the documents people
 *                upload, the audit trail, and the settings that change results.
 *   report     — گزارش مالی. The customer's side: what the numbers turned out to
 *                be. Charts, amounts, warnings and variances, invoice entry, the
 *                period report, and only the settings that change nothing —
 *                which currency to read amounts in, and what this account may do.
 *
 * The split is about authorship, not secrecy: the report surface reads what the
 * operations surface writes, through the same adapters and the same service, so
 * a change made on one side is on the other as soon as it is saved.
 */

export const SURFACES = Object.freeze({
  OPERATIONS: "operations",
  REPORT: "report",
});

export const SURFACE_LABELS = Object.freeze({
  [SURFACES.OPERATIONS]: "امور مالی",
  [SURFACES.REPORT]: "گزارش مالی",
});

export const ROUTES = Object.freeze([
  // ── امور مالی ────────────────────────────────────────────────────────────
  { key: "finance-home", path: "/finance", label: "امور مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, home: true, enabled: true },
  { key: "financial-items", path: "/financial-items", label: "اقلام و برآورد", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "prices", path: "/prices", label: "قیمت روز", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "progress", path: "/progress", label: "پیشرفت مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "invoice-files", path: "/invoice-files", label: "ورودی تصویر و صدا", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "ai-review", path: "/ai-review", label: "بررسی هوشمند فاکتور", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "audit", path: "/audit", label: "تاریخچه تغییرات مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "settings", path: "/settings", label: "تنظیمات مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },

  // ── گزارش مالی ───────────────────────────────────────────────────────────
  { key: "report-home", path: "/finance-report", label: "گزارش مالی", permission: "finance.view", surface: SURFACES.REPORT, home: true, enabled: true },
  { key: "reports", path: "/reports", label: "گزارش وضعیت مالی", permission: "finance_report.view", surface: SURFACES.REPORT, enabled: true },
  { key: "period-report", path: "/period-report", label: "گزارش دوره‌ای", permission: "finance_report.view", surface: SURFACES.REPORT, enabled: true },
  { key: "invoices", path: "/invoices", label: "فاکتورها", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
  { key: "report-settings", path: "/report-settings", label: "تنظیمات نمایش", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
]);

export const DEFAULT_ROUTE = "/finance";

export function routesForSurface(surface) {
  return ROUTES.filter((route) => route.enabled && route.surface === surface);
}

export function homeRouteFor(surface) {
  return ROUTES.find((route) => route.home && route.surface === surface) ?? null;
}

export function surfaceOfPath(path) {
  return ROUTES.find((route) => route.path === path)?.surface ?? null;
}
