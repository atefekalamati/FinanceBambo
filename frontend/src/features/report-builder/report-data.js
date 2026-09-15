import { datasetsFor } from "./report-catalog.js";
import { defaultSnapshot } from "../../shared/progress/project-snapshot.js";
import { openingDateFor } from "../../shared/dates/reporting-periods.js";

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

/**
 * The two pictures a period is made of.
 *
 * Every input the service reads is bound by the reporting date, so a period is
 * the project as it stood the day before it opened and the day it closed. The
 * opening is asked for separately and is allowed to be missing: a project with
 * no reportable day before the range still has an end-of-period reading, and
 * saying so beats measuring a change from zero the project never had.
 */
async function readPeriodOverview(adapter, period) {
  if (!period?.from || !period?.to) return null;
  const read = async (reportingDate) => {
    try {
      return await adapter.getOverview({ reportingDate });
    } catch (error) {
      // A date the project cannot report on is an answer, not a failure: it answers 404,
      // the renderer says which end is missing, and a thrown error would take the whole
      // document down over one absent day.
      //
      // A 422 is not that. It is the service saying the request itself was wrong -- an
      // impossible day, a malformed one -- and swallowing it printed a finished report
      // for a period nobody had asked for. It goes up.
      if (error?.status === 422) throw error;
      return null;
    }
  };
  const [opening, closing] = await Promise.all([
    read(openingDateFor(period.from)),
    read(period.to),
  ]);
  return { opening, closing, openingDate: openingDateFor(period.from), closingDate: period.to };
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
  // A source snapshot fixes progress reality.  The live financial cutoff remains the
  // requested as-of day, otherwise an old schedule date hides later estimates/invoices.
  const reportingDate = today;
  const query = { reportingDate, progressSnapshotId: snapshot?.progressSnapshotId };
  const monthlyQuery = snapshot ? query : { reportingDate };
  const [overview, monthly, invoices, audit, prices, financialItems, wbs, periodOverview] = await Promise.all([
    wanted.has("overview") ? adapters.reports.getOverview(query) : null,
    wanted.has("monthly") ? adapters.reports.getMonthlyTrend(monthlyQuery) : null,
    wanted.has("invoices") ? loadAllInvoices(adapters.invoices) : null,
    wanted.has("audit") ? adapters.audit.getEvents({ occurredFrom: period?.from, occurredTo: period?.to, pageSize: 200 }) : null,
    wanted.has("prices") ? adapters.prices.getPrices() : null,
    wanted.has("financialItems") ? adapters.financialItems.getWorkspace() : null,
    wanted.has("wbs") ? adapters.reports.getWbsRollup({ ...query, level: 1 }) : null,
    wanted.has("periodOverview") ? readPeriodOverview(adapters.reports, period) : null,
  ]);
  return { snapshot, reportingDate, asOfDate: today, overview, monthly, invoices, audit, prices, financialItems, wbs, periodOverview, period };
}
