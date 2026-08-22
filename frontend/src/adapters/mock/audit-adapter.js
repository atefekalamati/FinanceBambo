import { ApiError } from "../../core/api/api-error.js";

function clone(value) {
  return structuredClone(value);
}

const RECENT_EVENTS = Object.freeze([
  { id: "90000000-0000-4000-8000-000000000001", actorUserId: "00000000-0000-4000-8000-000000000001", action: "report_snapshot.issued", entityType: "report_snapshots", entityId: "80000000-0000-4000-8000-000000000001", reason: null, beforeValues: null, afterValues: { reportingDate: "2026-08-10", progressSnapshotId: "70000000-0000-4000-8000-000000000001" }, occurredAt: "2026-08-10T10:30:00Z" },
  { id: "90000000-0000-4000-8000-000000000002", actorUserId: "00000000-0000-4000-8000-000000000001", action: "invoice.confirmed", entityType: "invoices", entityId: "60000000-0000-4000-8000-000000000001", reason: null, beforeValues: { status: "awaitingConfirmation", version: 2 }, afterValues: { status: "confirmed", version: 3, finalAmountIrr: "624000000" }, occurredAt: "2026-08-09T12:15:00Z" },
  { id: "90000000-0000-4000-8000-000000000003", actorUserId: "00000000-0000-4000-8000-000000000001", action: "progress_override.created", entityType: "progress_overrides", entityId: "50000000-0000-4000-8000-000000000001", reason: "اصلاح مقدار اجرا براساس صورت‌جلسه کارگاه", beforeValues: { computedValue: "118.5000" }, afterValues: { overrideValue: "124.0000", progressSnapshotId: "70000000-0000-4000-8000-000000000001" }, occurredAt: "2026-08-08T08:45:00Z" },
  { id: "90000000-0000-4000-8000-000000000004", actorUserId: "00000000-0000-4000-8000-000000000001", action: "price_version.created", entityType: "price_versions", entityId: "40000000-0000-4000-8000-000000000001", reason: "به‌روزرسانی قیمت تأمین‌کننده", beforeValues: null, afterValues: { version: 4, unitPriceIrr: "302000" }, occurredAt: "2026-08-07T09:10:00Z" },
  { id: "90000000-0000-4000-8000-000000000005", actorUserId: "00000000-0000-4000-8000-000000000001", action: "attachment.accessed", entityType: "finance_attachments", entityId: "30000000-0000-4000-8000-000000000001", reason: null, beforeValues: null, afterValues: { fileId: "30000000-0000-4000-8000-000000000001" }, occurredAt: "2026-08-06T15:20:00Z" },
]);

const HISTORY_TEMPLATES = Object.freeze([
  { action: "estimate_line.revised", entityType: "estimate_lines", reason: "اصلاح متره براساس نقشه اجرایی", before: (step) => ({ version: step }), after: (step) => ({ version: step + 1 }) },
  { action: "price_version.created", entityType: "price_versions", reason: "ثبت قیمت روز بازار", before: () => null, after: (step) => ({ version: step, unitPriceIrr: String(280000 + step * 1500) }) },
  { action: "invoice.created", entityType: "invoices", reason: null, before: () => null, after: (step) => ({ status: "draft", version: 1, finalAmountIrr: String(120000000 + step * 2500000) }) },
  { action: "invoice.confirmed", entityType: "invoices", reason: null, before: () => ({ status: "awaitingConfirmation", version: 2 }), after: (step) => ({ status: "confirmed", version: 3, finalAmountIrr: String(120000000 + step * 2500000) }) },
  { action: "settings.revised", entityType: "finance_settings", reason: "اصلاح زیربنای کل پس از بازبینی نقشه", before: (step) => ({ version: step }), after: (step) => ({ version: step + 1 }) },
  { action: "unit_conversion.revised", entityType: "unit_conversions", reason: "به‌روزرسانی ساعت کاری روز دستگاه", before: () => ({ version: 1 }), after: () => ({ version: 2 }) },
  { action: "invoice.voided", entityType: "invoices", reason: "ابطال سند به‌دلیل ثبت اشتباه فروشنده", before: () => ({ status: "confirmed", version: 3 }), after: () => ({ status: "voided", version: 4 }) },
  { action: "attachment.accessed", entityType: "finance_attachments", reason: null, before: () => null, after: (step) => ({ fileId: `30000000-0000-4000-8000-${String(step).padStart(12, "0")}` }) },
]);

const HISTORY_EVENT_COUNT = 128;
const HISTORY_BASE_UTC = Date.UTC(2026, 7, 5); // 2026-08-05, one day before the oldest recent event.
const DAY_MS = 86400000;

function buildHistoryEvents() {
  return Array.from({ length: HISTORY_EVENT_COUNT }, (unused, index) => {
    const template = HISTORY_TEMPLATES[index % HISTORY_TEMPLATES.length];
    const step = Math.floor(index / HISTORY_TEMPLATES.length) + 1;
    const dayOffset = Math.floor(index / 2);
    const hour = index % 2 === 0 ? 14 : 9;
    const occurredAt = new Date(HISTORY_BASE_UTC - dayOffset * DAY_MS + hour * 3600000 + (index % 5) * 60000).toISOString();
    const serial = String(index + 6).padStart(12, "0");
    return {
      id: `90000000-0000-4000-8000-${serial}`,
      actorUserId: `00000000-0000-4000-8000-${String((index % 3) + 1).padStart(12, "0")}`,
      action: template.action,
      entityType: template.entityType,
      entityId: `a0000000-0000-4000-8000-${serial}`,
      reason: template.reason,
      beforeValues: template.before(step),
      afterValues: template.after(step),
      occurredAt: occurredAt.replace(".000Z", "Z"),
    };
  });
}

/** Newest first, matching the ordering the audit service guarantees. */
const EVENTS = Object.freeze([...RECENT_EVENTS, ...buildHistoryEvents()]);

export function createMockAuditAdapter(context, { initialState = "success" } = {}) {
  /**
   * Mirrors GET /audit-events: page/pageSize are clamped the way the router
   * declares them (page ge 1, pageSize 1..200 default 50) and the response is
   * the same paged envelope, so a filter cannot mistake an unfetched page for
   * an empty history.
   */
  async function getEvents({ page = 1, pageSize = 50 } = {}) {
    await new Promise((resolve) => setTimeout(resolve, 320));
    if (initialState === "error") throw new ApiError({ status: 503, code: "AUDIT_UNAVAILABLE", message: "دریافت تاریخچه تغییرات مالی انجام نشد.", requestId: "mock-audit-001" });
    const safePageSize = Math.min(Math.max(Number(pageSize) || 50, 1), 200);
    const safePage = Math.max(Number(page) || 1, 1);
    const source = initialState === "empty" ? [] : EVENTS;
    const offset = (safePage - 1) * safePageSize;
    return clone({
      items: source.slice(offset, offset + safePageSize).map((event) => ({ ...event, organizationId: context.organizationId, projectId: context.projectId })),
      page: safePage,
      pageSize: safePageSize,
      totalItems: source.length,
      totalPages: Math.ceil(source.length / safePageSize),
    });
  }

  return Object.freeze({ getEvents });
}
