/**
 * CSV for the period report.
 *
 * The layout follows the Backend's own snapshot export in
 * `services/reports.py`: a `section` column first, so several tables of
 * different widths can live in one sheet and still be filterable. Money is
 * written as the exact integer IRR the API returned — never the compacted or
 * localised form on screen — so a spreadsheet reads a number, not a caption.
 */

const BOM = "﻿";
const CRLF = "\r\n";

function cell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function row(values) {
  return values.map(cell).join(",");
}

export function buildPeriodReportCsv({
  project,
  period,
  generatedAt,
  metrics = [],
  breakdown = [],
  events = [],
  invoices = [],
} = {}) {
  const lines = [];

  lines.push(row(["section", "key", "value"]));
  lines.push(row(["report", "نوع گزارش", "گزارش دوره‌ای مالی"]));
  lines.push(row(["report", "پروژه", project?.name ?? ""]));
  lines.push(row(["report", "کد پروژه", project?.code ?? ""]));
  lines.push(row(["report", "شروع دوره", period?.from ?? ""]));
  lines.push(row(["report", "پایان دوره", period?.to ?? ""]));
  lines.push(row(["report", "تاریخ مبنای ابتدای دوره", period?.opening ?? ""]));
  lines.push(row(["report", "زمان ساخت", generatedAt ?? ""]));
  lines.push("");

  lines.push(row(["metric", "شاخص", "جنس", "ابتدای دوره (ریال)", "پایان دوره (ریال)", "تغییر (ریال)"]));
  metrics.forEach((metric) => {
    lines.push(row([
      "metric",
      metric.label,
      metric.kind === "cumulative" ? "انباشتی" : "وضعیتی",
      metric.openingIrr,
      metric.closingIrr,
      metric.changeIrr,
    ]));
  });
  lines.push("");

  lines.push(row(["breakdown", "نوع قلم", "سنجه", "ابتدای دوره (ریال)", "پایان دوره (ریال)", "تغییر (ریال)"]));
  breakdown.forEach((group) => {
    Object.entries(group.measures).forEach(([key, measure]) => {
      lines.push(row(["breakdown", group.label, key, measure.openingIrr, measure.closingIrr, measure.changeIrr]));
    });
  });
  lines.push("");

  lines.push(row(["invoice", "شماره فاکتور", "تاریخ", "فروشنده", "وضعیت", "مبلغ نهایی (ریال)", "اثر مالی"]));
  invoices.forEach((invoice) => {
    lines.push(row([
      "invoice",
      invoice.invoiceNumber,
      invoice.invoiceDate,
      invoice.vendorName,
      invoice.invoiceStatus,
      invoice.finalAmountIRR ?? invoice.finalAmountIrr,
      invoice.financialEffectSign,
    ]));
  });
  lines.push("");

  lines.push(row(["event", "رویداد", "تعداد"]));
  events.forEach((event) => lines.push(row(["event", event.action, event.count])));

  return BOM + lines.join(CRLF) + CRLF;
}

export function periodReportFileName({ project, period } = {}) {
  const code = String(project?.code ?? "project").replace(/[^A-Za-z0-9_-]/g, "");
  return `finance-period-report-${code}-${period?.from ?? ""}_${period?.to ?? ""}.csv`;
}
