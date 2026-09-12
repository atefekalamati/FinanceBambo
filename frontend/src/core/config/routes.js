/**
 * The module lights up two sidebar links in the host, and every route belongs to
 * exactly one of them.
 *
 *   operations — امور مالی. The internal side: what the numbers are built from.
 *                Items and estimates, day prices, progress, the audit trail, and
 *                the settings that change results.
 *   report     — گزارش مالی. The customer's side: what the numbers turned out to
 *                be. Charts and amounts, the report builder, every way an invoice
 *                is recorded — typed, photographed or spoken — and only the
 *                settings that change nothing: which currency to read amounts in,
 *                and what this account may do.
 *
 * The split is about authorship, not secrecy: the report surface reads what the
 * operations surface writes, through the same adapters and the same service, so
 * a change made on one side is on the other as soon as it is saved.
 */

export const SURFACES = Object.freeze({
  OPERATIONS: "operations",
  REPORT: "report",
});

/**
 * What opens a surface: any one of the codes listed for it.
 *
 * امور مالی is a workspace, not a longer version of the report: everything on it
 * exists to change a number. Letting an account that cannot change anything walk
 * around inside it means every page there has to keep proving, control by
 * control, that it is harmless — and one of them eventually forgets. So the door
 * is checked once, here, and گزارش مالی carries its own read-only copy of
 * anything a reader legitimately needs. Reading is never taken away; it is moved
 * to the surface built for reading.
 *
 * WHY A LIST AND NOT ONE CODE
 * The host's administrator grants these codes freely, in any combination, and
 * this module never learns which role received which. گزارش مالی answers two
 * separate needs — reading what the project turned out to cost, and recording
 * the documents that made it cost that — and an account may hold either without
 * the other. One code as the door would shut out the account holding the other,
 * and would have made "may record an invoice" quietly depend on "may read a
 * report". Any one of a surface's codes opens it; the routes inside then answer
 * for themselves.
 *
 * WHY finance.view IS NOT ON THE REPORT DOOR
 * Decision pack D-1, decided by the product owner on 2026-09-12: «each surface has its
 * own permission». کارشناس متره و برآورد works inside امور مالی and must not be handed
 * گزارش مالی along with it -- and holding finance.view is exactly how that used to
 * happen, because reading the figures is something that account needs to do its own job.
 *
 * This door was briefly `finance.view` alone, then a list with finance.view in it, and
 * the measurement behind that second version is worth keeping: an account holding
 * finance.view and nothing else was refused at BOTH doors, could read every figure
 * through the API, could open no page at all, and was offered a button to the other
 * closed door at each refusal. That is a real failure and it has not gone away -- what
 * changed is what it means. It is now a misconfiguration rather than a supported state:
 * a reader is given finance_report.view, which is the door to the surface built for
 * reading, and finance.view is what lets them see figures once inside.
 *
 * The codes answer separate needs and none implies another. The routes inside still
 * carry their own permission, so this opens the surface and grants nothing: گزارش مالی
 * سطح ۱ and the report builder keep asking for finance_report.view.
 */
export const SURFACE_REQUIREMENTS = Object.freeze({
  [SURFACES.OPERATIONS]: Object.freeze(["finance.edit"]),
  [SURFACES.REPORT]: Object.freeze(["finance_report.view", "finance.manage_invoice"]),
});

export const ROUTES = Object.freeze([
  // ── امور مالی ────────────────────────────────────────────────────────────
  { key: "finance-home", path: "/finance", label: "امور مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, home: true, enabled: true },
  { key: "financial-items", path: "/financial-items", label: "اقلام و برآورد", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "prices", path: "/prices", label: "قیمت روز", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "progress", path: "/progress", label: "پیشرفت مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "audit", path: "/audit", label: "تاریخچه تغییرات مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },
  { key: "settings", path: "/settings", label: "تنظیمات مالی", permission: "finance.view", surface: SURFACES.OPERATIONS, enabled: true },

  // ── گزارش مالی ───────────────────────────────────────────────────────────
  { key: "report-home", path: "/finance-report", label: "گزارش مالی", permission: "finance.view", surface: SURFACES.REPORT, home: true, enabled: true },
  // Withdrawn from view, not deleted. Everything these two drew is available
  // from the report builder, which is now the module's single way to produce a
  // report — two pages each answering part of the same question was two places
  // to look and two places to keep agreeing with each other. The routes stay
  // declared so the pages behind them keep their dispatch and their tests, and
  // so turning either back on is one word.
  { key: "level-one", path: "/level-one", label: "گزارش مالی سطح ۱", permission: "finance_report.view", surface: SURFACES.REPORT, enabled: true },
  // Every way a document reaches the ledger sits on one surface: typed by hand,
  // photographed, spoken, or read out of a file by the extractor. امور مالی
  // authors the baseline the project is measured against; a receipt is not one
  // of those numbers, so recording it never belonged in that workspace. Both
  // pages below are reached from the فاکتورها card on the board and from the
  // invoice list itself, so neither needs a destination card of its own.
  { key: "invoices", path: "/invoices", label: "فاکتورها", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
  { key: "invoice-files", path: "/invoice-files", label: "ورودی تصویر و صدا", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
  { key: "ai-review", path: "/ai-review", label: "بررسی هوشمند فاکتور", permission: "finance.view", surface: SURFACES.REPORT, enabled: true },
  // The two tables a reader is sent to from the deviation cards. Same pages as
  // on امور مالی, opened in a mode that offers no way to change anything.
  { key: "report-prices", path: "/report-prices", label: "جدول قیمت‌ها", permission: "finance.view", surface: SURFACES.REPORT, readOnlyTwinOf: "prices", enabled: true },
  { key: "report-items", path: "/report-items", label: "جدول اقلام و برآورد", permission: "finance.view", surface: SURFACES.REPORT, readOnlyTwinOf: "financial-items", enabled: true },
  { key: "report-builder", path: "/report-builder", label: "گزارش اختصاصی مالی", permission: "finance_report.view", surface: SURFACES.REPORT, enabled: true },
  // The destinations page listed the pages above. With them withdrawn and the
  // strip that opened it gone, it lists nothing anyone cannot already reach.
  /* Withdrawn with the bar that held its gear. The settings a reader could
     change here were the display ones -- which currency to read amounts in, and
     a read-back of what this account may do -- and neither is worth a page of
     its own on the customer's surface. What changes the figures lives on امور
     مالی and always did. Declared and dispatched, offered nowhere: bringing it
     back is this one word. */
  { key: "report-settings", path: "/report-settings", label: "تنظیمات نمایش", permission: "finance.view", surface: SURFACES.REPORT, enabled: false },
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
