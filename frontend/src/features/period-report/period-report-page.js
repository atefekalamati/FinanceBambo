import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { createReportHeader, projectFacts } from "../../shared/reports/report-header.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { IDENTITY, PRIMARY, SECONDARY, createDataTableWithControl, defaultVisibleColumns }
  from "../../shared/components/data-table.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { compactMoneyFromIrr, formatCompactMoneyFromIrr, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import {
  buildBreakdownComparison,
  buildPeriodComparison,
  buildPeriodPresets,
  isWithinPeriod,
  matchPreset,
  openingDateFor,
  periodDayCount,
  summarizeEvents,
  totalInvoicedIrr,
  validatePeriod,
} from "./period-report.js";
import { buildPeriodReportCsv, periodReportFileName } from "./period-report-csv.js";

/**
 * The period report: what the project's money did between two dates.
 *
 * It is assembled from readings the Backend already serves. Two calls to the
 * live report — one the day before the period opens, one on the day it closes —
 * give the two ends to compare, because every input of that calculation is
 * bound by the reporting date. The audit trail and the invoice list fill in
 * what happened in between.
 */

const SECTIONS = Object.freeze([
  { key: "metrics", label: "شاخص‌های کلان", hint: "مقایسه ابتدا و پایان دوره" },
  { key: "breakdown", label: "تفکیک نوع قلم", hint: "مصالح، نیروی انسانی، تجهیزات و هزینه عمومی" },
  { key: "invoices", label: "فاکتورهای دوره", hint: "اسناد مالی با تاریخ داخل بازه" },
  { key: "events", label: "رویدادهای دوره", hint: "تغییرات ثبت‌شده در تاریخچه مالی" },
  { key: "warnings", label: "هشدارهای پایان دوره", hint: "مواردی که محاسبه را ناقص می‌کند" },
]);

const WARNING_LABELS = Object.freeze({
  UNIT_CONVERSION_MISSING: "تبدیل واحد لازم برای بخشی از محاسبات تعریف نشده است.",
  PROGRESS_MISSING: "برای یکی از ردیف‌های برآورد، مقدار معتبر پیشرفت موجود نیست.",
  QUANTITY_OVERRUN: "مقدار انجام‌شده یکی از ردیف‌ها از آخرین مقدار برآورد بیشتر است.",
  CURRENT_PRICE_MISSING: "قیمت روز یکی از اقلام ثبت نشده و آن ردیف از محاسبات کنار گذاشته شده است.",
  GENERAL_COST_OVERRUN: "هزینه واقعی عمومی پروژه از آخرین برآورد آن بیشتر است.",
  GROSS_AREA_MISSING: "زیربنای کل ثبت نشده و شاخص‌های هر مترمربع قابل محاسبه نیستند.",
});

const EVENT_LABELS = Object.freeze({
  "invoice.created": "ثبت فاکتور",
  "invoice.confirmed": "تأیید نهایی فاکتور",
  "invoice.voided": "ابطال فاکتور",
  "invoice.corrected": "سند اصلاحی فاکتور",
  "price_version.created": "ثبت قیمت روز",
  "estimate_line.created": "افزودن ردیف برآورد",
  "estimate_line.revised": "بازنگری مقدار برآورد",
  "progress_override.created": "اصلاح دستی پیشرفت",
  "settings.revised": "اصلاح زیربنای کل",
  "unit_conversion.created": "تعریف تبدیل واحد",
  "unit_conversion.revised": "اصلاح تبدیل واحد",
  "report_snapshot.issued": "صدور گزارش دوره‌ای",
  "attachment.accessed": "مشاهده فایل پیوست",
});

const INVOICE_STATUS_LABELS = Object.freeze({
  draft: "پیش‌نویس",
  awaitingConfirmation: "در انتظار تأیید",
  confirmed: "تأییدشده",
  voided: "ابطال‌شده",
  corrected: "اصلاح‌شده",
});

/** The API pages invoices; this is how many pages the report will pull. */
const INVOICE_PAGE_SIZE = 200;
const INVOICE_PAGE_LIMIT = 10;
const EVENT_PAGE_SIZE = 200;

function moneyCell(value, { compact = true } = {}) {
  const display = element("span", "money-display");
  if (!/^-?\d+$/.test(String(value ?? ""))) {
    display.textContent = "قابل محاسبه نیست";
    display.classList.add("money-display--unavailable");
    return display;
  }
  const compactValue = compact ? compactMoneyFromIrr(value) : null;
  const unit = element("span", "money-display__unit", compactValue?.unit ?? getDisplayCurrencyLabel());
  const amount = element("bdi", "money-display__amount numeric", compactValue?.amount ?? formatTomanFromIrr(value, { withCurrency: false }));
  amount.dir = "ltr";
  display.append(unit, amount);
  if (compactValue?.compact) {
    display.classList.add("compact-money");
    display.title = compactValue.exact;
  }
  return display;
}

function changeCell(changeIrr, direction) {
  const wrapper = element("span", `period-change period-change--${direction ?? "unknown"}`);
  if (changeIrr === null) {
    wrapper.textContent = "قابل محاسبه نیست";
    return wrapper;
  }
  const sign = direction === "up" ? "+" : direction === "down" ? "−" : "";
  const magnitude = changeIrr.startsWith("-") ? changeIrr.slice(1) : changeIrr;
  const amount = element("bdi", "numeric", `${sign}${formatCompactMoneyFromIrr(magnitude)}`);
  amount.dir = "ltr";
  amount.title = formatTomanFromIrr(magnitude);
  wrapper.append(amount);
  return wrapper;
}

/* ── Report blocks ──────────────────────────────────────────────────────── */

function renderHeader({ context, period, generatedAt, dayCount }) {
  const header = element("section", "period-report-header");
  header.append(createReportHeader({
    title: "گزارش دوره‌ای مالی",
    facts: [
      ...projectFacts({ project: { name: context.projectName, code: context.projectCode }, period }),
      ["طول دوره", `${formatDisplayNumber(String(dayCount))} روز`],
      ["مبنای ابتدای دوره", formatBusinessDate(period.opening)],
      ["زمان ساخت", formatSystemDateTime(generatedAt)],
    ],
  }));
  header.append(element("p", "period-report-header__note", "این گزارش زنده است و از داده‌های فعلی پروژه ساخته می‌شود؛ برای نسخه قفل‌شده و تغییرناپذیر، از «ثبت گزارش دوره‌ای» در صفحه گزارش مالی استفاده کنید."));
  return header;
}

function renderMetrics(metrics, period) {
  const section = element("section", "report-section period-metrics");
  const heading = element("div", "section-heading");
  heading.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(metrics.length))));
  heading.firstElementChild.append(
    element("h2", "", "شاخص‌های کلان دوره"),
    element("p", "", "شاخص‌های انباشتی تفاضلشان «مقدار همین دوره» است؛ شاخص‌های وضعیتی فقط جابه‌جایی وضعیت را نشان می‌دهند، نه هزینه دوره."),
  );
  section.append(heading);

  const grid = element("div", "period-metric-grid");
  metrics.forEach((metric) => {
    const card = element("article", `period-metric period-metric--${metric.kind}`);
    const head = element("div", "period-metric__head");
    head.append(
      element("h3", "", metric.label),
      element("span", "period-metric__kind", metric.kind === "cumulative" ? "انباشتی" : "وضعیتی"),
    );
    const change = element("div", "period-metric__change");
    change.append(
      element("span", "period-metric__change-label", metric.kind === "cumulative" ? "در این دوره" : "تغییر وضعیت"),
      changeCell(metric.changeIrr, metric.direction),
    );
    const ends = element("dl", "period-metric__ends");
    [["ابتدای دوره", metric.openingIrr], ["پایان دوره", metric.closingIrr]].forEach(([label, value]) => {
      const group = element("div");
      const dd = element("dd", "");
      dd.append(moneyCell(value));
      group.append(element("dt", "", label), dd);
      ends.append(group);
    });
    card.append(head, change, ends);
    grid.append(card);
  });
  section.append(grid, renderMetricTable(metrics, period));
  return section;
}

/** The alternative table the chartless cards owe print and assistive tech. */
function renderMetricTable(metrics, period) {
  const wrapper = element("div", "table-scroll period-metric-table");
  const table = element("table", "data-table");
  table.append(
    tableCaption(`شاخص‌های مالی در ابتدا و پایان دوره ${period.from} تا ${period.to}`),
    tableHead(["شاخص", "جنس", "ابتدای دوره", "پایان دوره", "تغییر"]),
  );
  const body = document.createElement("tbody");
  metrics.forEach((metric) => {
    const row = document.createElement("tr");
    const opening = element("td", "");
    opening.append(moneyCell(metric.openingIrr));
    const closing = element("td", "");
    closing.append(moneyCell(metric.closingIrr));
    const change = element("td", "");
    change.append(changeCell(metric.changeIrr, metric.direction));
    row.append(
      element("td", "", metric.label),
      element("td", "", metric.kind === "cumulative" ? "انباشتی" : "وضعیتی"),
      opening,
      closing,
      change,
    );
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

function renderBreakdown(groups, period) {
  const section = element("section", "report-section");
  const heading = element("div", "section-heading");
  heading.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(groups.length))));
  heading.firstElementChild.append(
    element("h2", "", "تفکیک دوره بر اساس نوع قلم"),
    element("p", "", "هزینه واقعی و برآورد هر نوع قلم، در دو سر بازه"),
  );
  const breakdown = createDataTableWithControl({
    name: "period-breakdown",
    className: "period-breakdown-table",
    caption: `تفکیک مالی هر نوع قلم در بازه ${period.from} تا ${period.to}`,
    scrollLabel: "جدول تفکیک مالی هر نوع قلم در این دوره",
    columns: PERIOD_BREAKDOWN_COLUMNS,
    visible: visiblePeriodBreakdownColumns,
    rows: groups,
    cells: (group) => ({
      identity: group.label,
      actual: changeCell(group.measures.actualCostIrr.changeIrr, group.measures.actualCostIrr.direction),
      estimate: changeCell(group.measures.initialEstimateIrr.changeIrr, group.measures.initialEstimateIrr.direction),
      remaining: moneyCell(group.measures.remainingPhysicalCostIrr.closingIrr),
      forecast: moneyCell(group.measures.forecastFinalIrr.closingIrr),
    }),
  });
  section.append(heading, breakdown);
  return section;
}

const PERIOD_BREAKDOWN_COLUMNS = Object.freeze([
  { key: "identity", label: "نوع قلم", tier: IDENTITY },
  { key: "actual", label: "هزینه واقعی دوره", tier: PRIMARY },
  { key: "estimate", label: "برآورد افزوده دوره", tier: PRIMARY },
  { key: "remaining", label: "کار باقی‌مانده (پایان)", tier: SECONDARY, keepOnTablet: true },
  { key: "forecast", label: "پیش‌بینی نهایی (پایان)", tier: SECONDARY },
]);
const visiblePeriodBreakdownColumns = defaultVisibleColumns(PERIOD_BREAKDOWN_COLUMNS);

const PERIOD_INVOICE_COLUMNS = Object.freeze([
  { key: "identity", label: "شماره", tier: IDENTITY },
  { key: "date", label: "تاریخ", tier: SECONDARY, keepOnTablet: true },
  { key: "vendor", label: "فروشنده", tier: PRIMARY },
  { key: "status", label: "وضعیت", tier: PRIMARY },
  { key: "amount", label: "مبلغ نهایی", tier: PRIMARY },
]);
const visiblePeriodInvoiceColumns = defaultVisibleColumns(PERIOD_INVOICE_COLUMNS);

function renderInvoices({ invoices, truncated, period }) {
  const section = element("section", "report-section");
  const heading = element("div", "section-heading");
  heading.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(invoices.length))));
  heading.firstElementChild.append(
    element("h2", "", "فاکتورهای این دوره"),
    element("p", "", "اسنادی که تاریخشان داخل بازه است؛ همان تاریخی که موتور گزارش برای هزینه واقعی به آن نگاه می‌کند."),
  );
  section.append(heading);

  if (!invoices.length) {
    section.append(element("p", "inline-notice", "در این بازه فاکتوری با تاریخ داخل دوره ثبت نشده است."));
    return section;
  }

  const total = element("p", "period-invoice-total");
  total.append(element("span", "", "جمع اثر مالی اسناد این دوره"), moneyCell(totalInvoicedIrr(invoices), { compact: false }));
  const invoiceTable = createDataTableWithControl({
    name: "period-invoices",
    className: "period-invoice-table",
    caption: `فاکتورهای ثبت‌شده در بازه ${period.from} تا ${period.to}`,
    scrollLabel: "جدول فاکتورهای این دوره",
    columns: PERIOD_INVOICE_COLUMNS,
    visible: visiblePeriodInvoiceColumns,
    rows: invoices,
    cells: (invoice) => ({
      identity: invoice.invoiceNumber ?? "—",
      date: formatBusinessDate(invoice.invoiceDate),
      vendor: invoice.vendorName ?? "—",
      status: INVOICE_STATUS_LABELS[invoice.invoiceStatus] ?? invoice.invoiceStatus ?? "—",
      amount: moneyCell(invoice.finalAmountIRR ?? invoice.finalAmountIrr),
    }),
  });
  section.append(total, invoiceTable);

  if (truncated) {
    section.append(element("p", "inline-notice", `فهرست فاکتورها به ${formatDisplayNumber(String(INVOICE_PAGE_SIZE * INVOICE_PAGE_LIMIT))} سند اخیر محدود شد. سرویس مالی هنوز فیلتر بازه تاریخ روی فهرست فاکتورها ندارد و این گزارش ناچار است اسناد را صفحه‌به‌صفحه بگیرد و خودش کنار بگذارد.`));
  }
  return section;
}

function renderEvents({ events, total, period }) {
  const section = element("section", "report-section");
  const heading = element("div", "section-heading");
  heading.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(total))));
  heading.firstElementChild.append(
    element("h2", "", "رویدادهای این دوره"),
    element("p", "", "هر تغییری که در این بازه روی داده‌های مالی پروژه ثبت شده است"),
  );
  section.append(heading);

  if (!events.length) {
    section.append(element("p", "inline-notice", "در این بازه رویدادی در تاریخچه مالی ثبت نشده است."));
    return section;
  }

  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table period-event-table");
  table.append(
    tableCaption(`شمار رویدادهای مالی به تفکیک نوع، در بازه ${period.from} تا ${period.to}`),
    tableHead(["رویداد", "تعداد"]),
  );
  const body = document.createElement("tbody");
  events.forEach((event) => {
    const row = document.createElement("tr");
    row.append(
      element("td", "", EVENT_LABELS[event.action] ?? event.action),
      element("td", "numeric", formatDisplayNumber(String(event.count))),
    );
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

function renderWarnings(report) {
  const section = element("section", "finance-warnings period-warnings");
  section.setAttribute("aria-label", "هشدارهای مؤثر بر محاسبات پایان دوره");
  section.append(element("h2", "", "هشدارهای پایان دوره"));
  const warnings = [...(report?.warnings ?? [])];
  if (report?.calculationStatus === "incomplete") {
    warnings.unshift({
      code: "CALCULATION_INCOMPLETE",
      message: `محاسبات این گزارش کامل نیست؛ ${formatDisplayNumber(String(report.missingPriceCount ?? 0))} قیمت و ${formatDisplayNumber(String(report.excludedEstimateLineCount ?? 0))} ردیف برآورد در نتیجه لحاظ نشده است.`,
    });
  }
  if (!warnings.length) {
    section.append(element("p", "", "در پایان این دوره هشداری روی محاسبات مالی وجود ندارد."));
    return section;
  }
  const list = element("ul", "");
  warnings.forEach((warning) => {
    list.append(element("li", "", WARNING_LABELS[warning.code] ?? warning.message ?? warning.code));
  });
  section.append(list);
  return section;
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export function createPeriodReportPage({ context, reportsAdapter, auditAdapter, invoicesAdapter, progressAdapter }) {
  const root = element("div", "period-report-page");
  const today = getTehranTodayIso();
  const presets = buildPeriodPresets(today);
  const initial = presets.find((preset) => preset.key === "thisMonth")?.range ?? { from: today, to: today };

  let period = { from: initial.from, to: initial.to };
  let selected = new Set(SECTIONS.map((section) => section.key));
  let state = createRequestState(REQUEST_STATUS.IDLE);
  let errors = {};
  let actionError = "";
  let built = null;
  let earliestReportable = null;
  // The date picker writes its value through a calendar dialog rather than a
  // change event, so the fields are read when the report is built — the same
  // way the live report page reads its own picker.
  let fromPicker = null;
  let toPicker = null;

  function readPeriod() {
    if (fromPicker && toPicker) period = { from: fromPicker.getValue(), to: toPicker.getValue() };
  }

  async function collectInvoices() {
    // GET /invoices has no date filter yet, so the period is applied here. The
    // page cap is declared rather than silent: a report that quietly dropped
    // documents would understate the period's money.
    const collected = [];
    let page = 1;
    let truncated = false;
    for (; page <= INVOICE_PAGE_LIMIT; page += 1) {
      const result = await invoicesAdapter.getInvoices({ page, pageSize: INVOICE_PAGE_SIZE });
      collected.push(...(result.items ?? []));
      if (page >= (result.totalPages ?? 1)) break;
      if (page === INVOICE_PAGE_LIMIT) truncated = true;
    }
    return {
      invoices: collected
        .filter((invoice) => isWithinPeriod(invoice.invoiceDate, period))
        .sort((left, right) => String(right.invoiceDate).localeCompare(String(left.invoiceDate))),
      truncated,
    };
  }

  /**
   * The live report is built on top of a progress snapshot, so it answers 404
   * for any date before the project's first one. That is not a failure — it is
   * the project not having started reporting yet — and the reader is better
   * served by being told the earliest date they can report from than by an
   * error card.
   */
  async function readReport(reportingDate) {
    try {
      return { report: await reportsAdapter.getLiveReport({ reportingDate }), missing: false };
    } catch (error) {
      if (error?.status === 404) return { report: null, missing: true };
      throw error;
    }
  }

  async function earliestReportableDate() {
    if (!progressAdapter?.getSnapshots) return null;
    try {
      const snapshots = await progressAdapter.getSnapshots();
      // getSnapshots hands them back newest first.
      return snapshots.at(-1)?.reportingDate ?? null;
    } catch {
      return null;
    }
  }

  async function collectEvents() {
    const first = await auditAdapter.getEvents({
      page: 1,
      pageSize: EVENT_PAGE_SIZE,
      occurredFrom: period.from,
      occurredTo: period.to,
    });
    return { events: first.items ?? [], total: first.totalItems ?? (first.items ?? []).length };
  }

  async function build() {
    readPeriod();
    const validation = validatePeriod(period);
    errors = validation.errors;
    if (!validation.valid) {
      paint();
      return;
    }
    actionError = "";
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();

    const opening = openingDateFor(period.from);
    try {
      const [openingRead, closingRead] = await Promise.all([readReport(opening), readReport(period.to)]);
      const openingReport = openingRead.report;
      const closingReport = closingRead.report;
      if (!closingReport) {
        earliestReportable = closingRead.missing ? await earliestReportableDate() : null;
        state = createRequestState(REQUEST_STATUS.EMPTY);
        paint();
        return;
      }
      // An opening the project cannot supply leaves the period's figures
      // standing alone: they are reported as end-of-period readings, and the
      // comparison is declared impossible rather than quietly turned into a
      // change measured from zero.
      earliestReportable = openingRead.missing ? await earliestReportableDate() : null;
      const [{ invoices, truncated }, { events, total }] = await Promise.all([
        selected.has("invoices") ? collectInvoices() : Promise.resolve({ invoices: [], truncated: false }),
        selected.has("events") ? collectEvents() : Promise.resolve({ events: [], total: 0 }),
      ]);

      built = {
        period: { ...period, opening },
        generatedAt: new Date().toISOString(),
        dayCount: periodDayCount(period),
        metrics: buildPeriodComparison({ opening: openingReport?.metrics, closing: closingReport.metrics }),
        breakdown: buildBreakdownComparison({ opening: openingReport?.breakdown, closing: closingReport.breakdown }),
        invoices,
        invoicesTruncated: truncated,
        events: summarizeEvents(events),
        eventTotal: total,
        closingReport,
        openingMissing: openingRead.missing,
      };
      state = createRequestState(REQUEST_STATUS.SUCCESS, built);
    } catch (error) {
      built = null;
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function downloadCsv() {
    actionError = "";
    try {
      const csv = buildPeriodReportCsv({
        project: { name: context.projectName, code: context.projectCode },
        period: built.period,
        generatedAt: built.generatedAt,
        metrics: built.metrics,
        breakdown: built.breakdown,
        events: built.events,
        invoices: built.invoices,
      });
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = periodReportFileName({ project: { code: context.projectCode }, period: built.period });
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      actionError = formatApiErrorMessage(error, "ساخت خروجی CSV انجام نشد.");
      paint();
    }
  }

  function renderBuilder() {
    const builder = element("section", "period-builder");
    const head = element("div", "period-builder__head");
    head.append(
      element("h2", "", "ساخت گزارش"),
      element("p", "", "بازه را انتخاب کنید و مشخص کنید گزارش شامل چه بخش‌هایی باشد."),
    );

    const form = element("form", "period-builder__form");
    form.noValidate = true;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      build();
    });

    const quick = element("div", "period-presets");
    quick.setAttribute("role", "group");
    quick.setAttribute("aria-label", "دوره‌های آماده");
    const activePreset = matchPreset(presets, period);
    presets.forEach((preset) => {
      const button = element("button", `button button--small ${activePreset === preset.key ? "button--primary" : "button--ghost"}`, preset.label);
      button.type = "button";
      button.setAttribute("aria-pressed", String(activePreset === preset.key));
      button.addEventListener("click", () => {
        period = { ...preset.range };
        errors = {};
        fromPicker = toPicker = null;
        paint();
      });
      quick.append(button);
    });

    const dates = element("div", "period-builder__dates");
    fromPicker = createPersianDatePicker({ id: "periodFrom", label: "از تاریخ", value: period.from, hint: "اولین روزی که در گزارش حساب می‌شود." });
    toPicker = createPersianDatePicker({ id: "periodTo", label: "تا تاریخ", value: period.to, hint: "آخرین روزی که در گزارش حساب می‌شود." });
    if (errors.from) fromPicker.error.textContent = errors.from;
    if (errors.to) toPicker.error.textContent = errors.to;
    dates.append(fromPicker.field, toPicker.field);

    const sections = element("fieldset", "period-builder__sections");
    sections.append(element("legend", "", "بخش‌های گزارش"));
    SECTIONS.forEach((section) => {
      const option = element("label", "period-section-toggle");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "section";
      input.value = section.key;
      input.checked = selected.has(section.key);
      input.addEventListener("change", () => {
        if (input.checked) selected.add(section.key);
        else selected.delete(section.key);
      });
      const copy = element("span", "period-section-toggle__copy");
      copy.append(element("strong", "", section.label), element("small", "", section.hint));
      option.append(input, copy);
      sections.append(option);
    });

    const actions = element("div", "period-builder__actions");
    const submit = element("button", "button button--primary", "ساخت گزارش");
    submit.type = "submit";
    actions.append(submit);

    form.append(quick, dates, sections, actions);
    builder.append(head, form);
    return builder;
  }

  function renderOutputActions() {
    const actions = element("div", "period-report-actions");
    const print = element("button", "button button--ghost", "چاپ یا ذخیره PDF");
    print.type = "button";
    print.addEventListener("click", () => window.print());
    const csv = element("button", "button button--primary", "دریافت CSV");
    csv.type = "button";
    csv.addEventListener("click", downloadCsv);
    actions.append(print, csv);
    return actions;
  }

  function renderOpeningGap(period) {
    const notice = element("p", "inline-notice period-opening-gap");
    notice.setAttribute("role", "status");
    notice.append(element("strong", "", "ابتدای دوره قابل اندازه‌گیری نیست"));
    notice.append(document.createTextNode(earliestReportable
      ? ` پروژه در ${formatBusinessDate(period.opening)} هنوز نسخه پیشرفتی نداشته است، پس مقایسه با ابتدای دوره ممکن نیست و ارقام زیر وضعیت پایان دوره‌اند. اولین تاریخ قابل گزارش این پروژه ${formatBusinessDate(earliestReportable)} است.`
      : ` پروژه در ${formatBusinessDate(period.opening)} هنوز نسخه پیشرفتی نداشته است، پس مقایسه با ابتدای دوره ممکن نیست و ارقام زیر وضعیت پایان دوره‌اند.`));
    return notice;
  }

  function renderContent(report) {
    const fragment = document.createDocumentFragment();
    const output = element("section", "period-report-output");
    output.append(renderHeader({ context, period: report.period, generatedAt: report.generatedAt, dayCount: report.dayCount }));
    if (report.openingMissing) output.append(renderOpeningGap(report.period));
    if (selected.has("metrics")) output.append(renderMetrics(report.metrics, report.period));
    if (selected.has("breakdown")) output.append(renderBreakdown(report.breakdown, report.period));
    if (selected.has("invoices")) output.append(renderInvoices({ invoices: report.invoices, truncated: report.invoicesTruncated, period: report.period }));
    if (selected.has("events")) output.append(renderEvents({ events: report.events, total: report.eventTotal, period: report.period }));
    if (selected.has("warnings")) output.append(renderWarnings(report.closingReport));
    output.append(renderOutputActions());
    if (actionError) output.append(element("p", "inline-notice state-card--danger", actionError));
    fragment.append(output);
    return fragment;
  }

  function renderIdle() {
    const card = element("section", "state-card period-report-idle");
    card.append(
      element("h2", "", "هنوز گزارشی ساخته نشده است"),
      element("p", "", "بازه دلخواهتان را انتخاب کنید و «ساخت گزارش» را بزنید تا وضعیت مالی پروژه در آن دوره ساخته شود."),
    );
    return card;
  }

  function renderEmpty() {
    const card = element("section", "state-card period-report-idle");
    card.append(element("h2", "", "برای این بازه گزارشی ساخته نمی‌شود"));
    card.append(element("p", "", earliestReportable
      ? `تا پایان این بازه هنوز هیچ نسخه پیشرفتی برای پروژه ثبت نشده بود. اولین تاریخ قابل گزارش این پروژه ${formatBusinessDate(earliestReportable)} است؛ بازه‌ای بعد از آن انتخاب کنید.`
      : "تا پایان این بازه هنوز داده‌ای برای ساخت گزارش مالی پروژه وجود نداشت. بازه دیرتری را امتحان کنید."));
    return card;
  }

  function paint() {
    const header = element("div", "finance-page-header period-report-topbar");
    const heading = element("div");
    heading.append(element("h1", "", "گزارش دوره‌ای"), element("p", "", "وضعیت مالی پروژه بین دو تاریخ، از داده‌های واقعی همین پروژه"));
    const back = element("a", "button button--ghost finance-back-link", `بازگشت به ${SURFACE_LABELS[SURFACES.REPORT]}`);
    back.href = `#${homeRouteFor(SURFACES.REPORT)?.path ?? "/finance-report"}`;
    header.append(heading, back);
    const body = state.status === REQUEST_STATUS.IDLE
      ? renderIdle()
      : renderPageState(state, { renderContent, renderEmpty, onRetry: build });
    root.replaceChildren(header, renderBuilder(), body);
  }

  paint();
  return root;
}
