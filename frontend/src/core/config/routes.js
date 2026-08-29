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

/**
 * What an account must hold to be on a surface at all.
 *
 * امور مالی is a workspace, not a longer version of the report: everything on it
 * exists to change a number. Letting an account that cannot change anything walk
 * around inside it means every page there has to keep proving, control by
 * control, that it is harmless — and one of them eventually forgets.
 *
 * So the door is checked once, here, and گزارش مالی carries its own read-only
 * copy of anything a reader legitimately needs. Reading is never taken away;
 * it is moved to the surface built for reading.
 */
export const SURFACE_REQUIREMENTS = Object.freeze({
  [SURFACES.OPERATIONS]: "finance.edit",
  [SURFACES.REPORT]: "finance.view",
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
  { key: "level-one", path: "/level-one", label: "گزارش مالی سطح ۱", permission: "finance_report.view", surface: SURFACES.REPORT, enabled: true },
  { key: "invoices", path: "/invoices", label: "فاکتورها", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
  // The two tables a reader is sent to from the deviation cards. Same pages as
  // on امور مالی, opened in a mode that offers no way to change anything.
  { key: "report-prices", path: "/report-prices", label: "جدول قیمت‌ها", permission: "finance.view", surface: SURFACES.REPORT, readOnlyTwinOf: "prices", enabled: true },
  { key: "report-items", path: "/report-items", label: "جدول اقلام و برآورد", permission: "finance.view", surface: SURFACES.REPORT, readOnlyTwinOf: "financial-items", enabled: true },
  { key: "report-builder", path: "/report-builder", label: "گزارش اختصاصی مالی", permission: "finance_report.view", surface: SURFACES.REPORT, enabled: true },
  { key: "report-settings", path: "/report-settings", label: "تنظیمات نمایش", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
]);

export function routesForSurface(surface) {
  return ROUTES.filter((route) => route.enabled && route.surface === surface);
}

export function homeRouteFor(surface) {
  return ROUTES.find((route) => route.home && route.surface === surface) ?? null;
}

export function surfaceOfPath(path) {
  return ROUTES.find((route) => route.path === path)?.surface ?? null;
}

/**
 * The read-only route showing the same table as an operations one, if there is
 * one. Typing `#/prices` without the right to be on امور مالی is not a mistake
 * worth answering with a locked door when the same rows are one route away.
 */
export function readOnlyTwinOf(path) {
  const source = ROUTES.find((route) => route.path === path);
  if (!source) return null;
  return ROUTES.find((route) => route.enabled && route.readOnlyTwinOf === source.key) ?? null;
}
