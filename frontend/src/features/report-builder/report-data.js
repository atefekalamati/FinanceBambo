import { datasetsFor } from "./report-catalog.js";

// Do not silently print a truncated or changing register as a complete report.
export async function loadAllInvoices(adapter) {
  const first = await adapter.getInvoices({ page: 1, pageSize: 200 });
  const pages = first.totalPages ?? 1;
  if (!Number.isSafeInteger(pages) || pages < 1) throw new Error("صفحه‌بندی اسناد مالی معتبر نیست.");
  const items = [...first.items];
  for (let page = 2; page <= pages; page += 1) {
    const next = await adapter.getInvoices({ page, pageSize: 200 });
    if (next.page !== page || next.totalItems !== first.totalItems || next.totalPages !== pages) {
      throw new Error("فهرست اسناد هنگام دریافت تغییر کرد؛ گزارش را دوباره بسازید.");
    }
    items.push(...next.items);
  }
  if (new Set(items.map((item) => item.invoiceId)).size !== items.length
    || (first.totalItems != null && items.length !== first.totalItems)) {
    throw new Error("فهرست کامل اسناد دریافت نشد؛ گزارش را دوباره بسازید.");
  }
  return { ...first, items };
}

export async function loadReportData({ adapters, selection, period, today }) {
  const wanted = new Set(datasetsFor(selection));
  let snapshot = null;
  if (wanted.has("overview") || wanted.has("wbs")) {
    const snapshots = await adapters.progress.getSnapshots();
    snapshot = snapshots.filter((item) => item.status === "ready")
      .sort((a, b) => String(b.reportingDate).localeCompare(String(a.reportingDate)))[0] ?? null;
    if (!snapshot) return null;
  }
  const reportingDate = snapshot?.reportingDate ?? today;
  const query = { reportingDate, progressSnapshotId: snapshot?.progressSnapshotId };
  const [overview, monthly, invoices, audit, prices, financialItems, wbs] = await Promise.all([
    wanted.has("overview") ? adapters.reports.getOverview(query) : null,
    wanted.has("monthly") ? adapters.reports.getMonthlyTrend({ reportingDate }) : null,
    wanted.has("invoices") ? loadAllInvoices(adapters.invoices) : null,
    wanted.has("audit") ? adapters.audit.getEvents({ occurredFrom: period?.from, occurredTo: period?.to, pageSize: 200 }) : null,
    wanted.has("prices") ? adapters.prices.getPrices() : null,
    wanted.has("financialItems") ? adapters.financialItems.getWorkspace() : null,
    wanted.has("wbs") ? adapters.reports.getWbsRollup({ ...query, level: 1 }) : null,
  ]);
  return { snapshot, reportingDate, asOfDate: today, overview, monthly, invoices, audit, prices, financialItems, wbs, period };
}
