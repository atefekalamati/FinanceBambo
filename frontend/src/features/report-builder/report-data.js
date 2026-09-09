import { datasetsFor } from "./report-catalog.js";
import { defaultSnapshot } from "../../shared/progress/project-snapshot.js";

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
    // A printed report has to be the same figures the screen showed. It therefore asks
    // the shared question instead of re-sorting the list into an order of its own.
    snapshot = defaultSnapshot(await adapters.progress.getSnapshots());
    if (!snapshot) return null;
  }
  const reportingDate = snapshot?.reportingDate ?? today;
  const query = { reportingDate, progressSnapshotId: snapshot?.progressSnapshotId };
  const monthlyQuery = snapshot ? query : { reportingDate };
  const [overview, monthly, invoices, audit, prices, financialItems, wbs] = await Promise.all([
    wanted.has("overview") ? adapters.reports.getOverview(query) : null,
    wanted.has("monthly") ? adapters.reports.getMonthlyTrend(monthlyQuery) : null,
    wanted.has("invoices") ? loadAllInvoices(adapters.invoices) : null,
    wanted.has("audit") ? adapters.audit.getEvents({ occurredFrom: period?.from, occurredTo: period?.to, pageSize: 200 }) : null,
    wanted.has("prices") ? adapters.prices.getPrices() : null,
    wanted.has("financialItems") ? adapters.financialItems.getWorkspace() : null,
    wanted.has("wbs") ? adapters.reports.getWbsRollup({ ...query, level: 1 }) : null,
  ]);
  return { snapshot, reportingDate, asOfDate: today, overview, monthly, invoices, audit, prices, financialItems, wbs, period };
}
