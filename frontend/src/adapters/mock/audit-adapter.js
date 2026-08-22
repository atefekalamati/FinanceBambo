import { ApiError } from "../../core/api/api-error.js";

function clone(value) {
  return structuredClone(value);
}

const EVENTS = Object.freeze([
  { id: "90000000-0000-4000-8000-000000000001", actorUserId: "00000000-0000-4000-8000-000000000001", action: "report_snapshot.issued", entityType: "report_snapshots", entityId: "80000000-0000-4000-8000-000000000001", reason: null, beforeValues: null, afterValues: { reportingDate: "2026-08-10", progressSnapshotId: "70000000-0000-4000-8000-000000000001" }, occurredAt: "2026-08-10T10:30:00Z" },
  { id: "90000000-0000-4000-8000-000000000002", actorUserId: "00000000-0000-4000-8000-000000000001", action: "invoice.confirmed", entityType: "invoices", entityId: "60000000-0000-4000-8000-000000000001", reason: null, beforeValues: { status: "awaitingConfirmation", version: 2 }, afterValues: { status: "confirmed", version: 3, finalAmountIrr: "624000000" }, occurredAt: "2026-08-09T12:15:00Z" },
  { id: "90000000-0000-4000-8000-000000000003", actorUserId: "00000000-0000-4000-8000-000000000001", action: "progress_override.created", entityType: "progress_overrides", entityId: "50000000-0000-4000-8000-000000000001", reason: "اصلاح مقدار اجرا براساس صورت‌جلسه کارگاه", beforeValues: { computedValue: "118.5000" }, afterValues: { overrideValue: "124.0000", progressSnapshotId: "70000000-0000-4000-8000-000000000001" }, occurredAt: "2026-08-08T08:45:00Z" },
  { id: "90000000-0000-4000-8000-000000000004", actorUserId: "00000000-0000-4000-8000-000000000001", action: "price_version.created", entityType: "price_versions", entityId: "40000000-0000-4000-8000-000000000001", reason: "به‌روزرسانی قیمت تأمین‌کننده", beforeValues: null, afterValues: { version: 4, unitPriceIrr: "302000" }, occurredAt: "2026-08-07T09:10:00Z" },
  { id: "90000000-0000-4000-8000-000000000005", actorUserId: "00000000-0000-4000-8000-000000000001", action: "attachment.accessed", entityType: "finance_attachments", entityId: "30000000-0000-4000-8000-000000000001", reason: null, beforeValues: null, afterValues: { fileId: "30000000-0000-4000-8000-000000000001" }, occurredAt: "2026-08-06T15:20:00Z" },
]);

export function createMockAuditAdapter(context, { initialState = "success" } = {}) {
  async function getEvents() {
    await new Promise((resolve) => setTimeout(resolve, 320));
    if (initialState === "error") throw new ApiError({ status: 503, code: "AUDIT_UNAVAILABLE", message: "دریافت تاریخچه تغییرات مالی انجام نشد.", requestId: "mock-audit-001" });
    if (initialState === "empty") return [];
    return clone(EVENTS.map((event) => ({ ...event, organizationId: context.organizationId, projectId: context.projectId })));
  }

  return Object.freeze({ getEvents });
}
