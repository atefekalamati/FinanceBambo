export const ACTION_LABELS = Object.freeze({
  "attachment.accessed": "مشاهده پیوست مالی",
  "estimate_line.revised": "بازنگری برآورد",
  "invoice.created": "ایجاد فاکتور",
  "invoice.updated": "به‌روزرسانی فاکتور",
  "invoice.confirmed": "تأیید فاکتور",
  "invoice.duplicate_warning_overridden": "ادامه با وجود هشدار تکرار",
  "invoice.voided": "ابطال فاکتور",
  "invoice.corrected": "ثبت سند اصلاحی",
  "price_version.created": "ثبت نسخه قیمت",
  "progress_override.created": "جایگزینی مقدار پیشرفت",
  "report_snapshot.issued": "صدور نسخه گزارش",
  "settings.revised": "بازنگری تنظیمات مالی",
  "unit_conversion.revised": "ثبت نسخه تبدیل واحد",
});

export const ENTITY_LABELS = Object.freeze({
  estimate_lines: "خط برآورد",
  finance_attachments: "پیوست مالی",
  finance_settings: "تنظیمات مالی",
  invoices: "فاکتور",
  price_versions: "نسخه قیمت",
  progress_overrides: "جایگزینی پیشرفت",
  report_snapshots: "نسخه گزارش",
  unit_conversions: "تبدیل واحد",
});

export function filterAuditEvents(events, filters) {
  const query = String(filters.query ?? "").trim().toLocaleLowerCase("fa-IR");
  return events.filter((event) => {
    const searchable = `${event.actorUserId} ${event.entityId} ${event.reason ?? ""} ${ACTION_LABELS[event.action] ?? event.action} ${ENTITY_LABELS[event.entityType] ?? event.entityType}`.toLocaleLowerCase("fa-IR");
    const date = String(event.occurredAt ?? "").slice(0, 10);
    return (!query || searchable.includes(query))
      && (!filters.action || event.action === filters.action)
      && (!filters.entityType || event.entityType === filters.entityType)
      && (!filters.from || date >= filters.from)
      && (!filters.to || date <= filters.to);
  });
}
