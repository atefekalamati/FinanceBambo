import { hasPermission } from "../../core/auth/permissions.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { compactMoneyFromIrr, formatCompactMoneyFromIrr, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { buildPriceVariancePresentation, buildQuantityVariancePresentation } from "./report-analysis.js";

const METRICS = Object.freeze([
  ["initialEstimateIrr", "برآورد اولیه"],
  ["actualCostIrr", "هزینه واقعی ثبت‌شده"],
  ["currentExecutedValueIrr", "ارزش روز کار انجام‌شده"],
  ["remainingPhysicalCostIrr", "هزینه کار باقی‌مانده"],
  ["moneyRequiredToContinueIrr", "بودجه موردنیاز تا تکمیل"],
  ["forecastFinalCostIrr", "پیش‌بینی هزینه نهایی"],
  ["actualCostPerSquareMeterIrr", "هزینه واقعی هر مترمربع"],
  ["forecastPerSquareMeterIrr", "پیش‌بینی هزینه هر مترمربع"],
]);

const REPORT_WARNING_LABELS = Object.freeze({
  UNIT_CONVERSION_MISSING: "تبدیل واحد لازم برای بخشی از محاسبات تعریف نشده است.",
  PROGRESS_MISSING: "برای یکی از ردیف‌های برآورد، مقدار معتبر پیشرفت موجود نیست.",
  QUANTITY_OVERRUN: "مقدار انجام‌شده یکی از ردیف‌ها از آخرین مقدار برآورد بیشتر است.",
  CURRENT_PRICE_MISSING: "قیمت روز یکی از اقلام ثبت نشده و آن ردیف از محاسبات زنده کنار گذاشته شده است.",
  GENERAL_COST_OVERRUN: "هزینه واقعی ثبت‌شده عمومی پروژه از آخرین برآورد هزینه‌های عمومی بیشتر است.",
  GROSS_AREA_MISSING: "زیربنای کل پروژه ثبت نشده و شاخص‌های هر مترمربع قابل محاسبه نیستند.",
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderMetrics(metrics) {
  const grid = element("section", "summary-grid report-metrics");
  grid.setAttribute("aria-label", "شاخص‌های گزارش مالی");
  METRICS.forEach(([key, label]) => {
    const card = element("article", "summary-card");
    const compactValue = compactMoneyFromIrr(metrics?.[key]);
    const value = element("p", `summary-card__value${compactValue?.compact ? " compact-money" : ""}`, compactValue?.amount ?? "—");
    const unit = element("span", "summary-card__unit", compactValue?.unit ?? getDisplayCurrencyLabel());
    if (compactValue?.compact) {
      value.title = compactValue.exact;
      value.dataset.exact = compactValue.exact;
      value.setAttribute("aria-label", compactValue.exact);
      value.tabIndex = 0;
    }
    card.append(element("h2", "", label), value, unit);
    grid.append(card);
  });
  return grid;
}

function renderBreakdown(rows = []) {
  const section = element("section", "report-section");
  section.append(element("h2", "", "تفکیک مالی بر اساس نوع قلم"));
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table report-table");
  table.innerHTML = `<colgroup><col class="report-table__type"><col><col><col><col><col></colgroup><thead><tr><th>نوع قلم</th><th>برآورد اولیه</th><th>برآورد اصلاح‌شده</th><th>هزینه واقعی ثبت‌شده</th><th>باقی‌مانده</th><th>پیش‌بینی هزینه نهایی</th></tr></thead>`;
  const labels = { material: "مصالح", labor: "نیروی انسانی", equipment: "تجهیزات و ماشین‌آلات", general_cost: "هزینه‌های عمومی پروژه" };
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [
      labels[row.resourceType] ?? "نوع تعریف‌نشده",
      formatTomanFromIrr(row.initialEstimateIrr),
      row.revisedEstimateIrr == null ? "—" : formatTomanFromIrr(row.revisedEstimateIrr),
      formatTomanFromIrr(row.actualCostIrr),
      row.remainingPhysicalCostIrr == null ? "—" : formatTomanFromIrr(row.remainingPhysicalCostIrr),
      formatTomanFromIrr(row.forecastFinalIrr),
    ].forEach((value, index) => tr.append(element("td", index ? "numeric" : "", value)));
    body.append(tr);
  });
  table.append(body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

function varianceLink(basePath, row) {
  const query = new URLSearchParams();
  if (row.resourceId) query.set("resourceId", row.resourceId);
  if (row.estimateLineId) query.set("estimateLineId", row.estimateLineId);
  return `${basePath}${query.size ? `?${query.toString()}` : ""}`;
}

function renderPriceVariances(rows = []) {
  const section = element("section", "report-section report-analysis-section");
  const heading = element("div", "report-analysis-heading");
  heading.append(
    element("h2", "", "بیشترین اثر تغییر قیمت"),
    element("p", "", "اقلامی که تغییر قیمت آن‌ها بیشترین اثر افزایشی یا کاهشی را بر برآورد پروژه داشته است."),
  );
  section.append(heading);
  if (!rows.length) {
    section.append(element("p", "report-analysis-empty", "انحراف قیمت معتبری برای این تاریخ گزارش ثبت نشده است."));
    return section;
  }

  const presentation = buildPriceVariancePresentation(rows);
  const chart = element("div", "price-impact-chart");
  chart.setAttribute("aria-label", "نمودار بیشترین اثر تغییر قیمت بر پروژه");
  presentation.forEach((row) => {
    const link = element("a", `price-impact-chart__row price-impact-chart__row--${row.direction}`);
    link.href = varianceLink("#/prices", row);
    const identity = element("span", "price-impact-chart__identity");
    identity.append(element("strong", "", row.resourceTitle || "قلم بدون عنوان"), element("small", "numeric", row.resourceCode || "بدون کد"));
    const track = element("span", "price-impact-chart__track");
    const bar = element("span", "price-impact-chart__bar");
    bar.style.setProperty("--impact-width", `${row.magnitude}%`);
    track.append(bar);
    const value = element("span", "price-impact-chart__value numeric compact-money", formatCompactMoneyFromIrr(row.varianceIrr));
    value.title = formatTomanFromIrr(row.varianceIrr);
    value.dataset.exact = formatTomanFromIrr(row.varianceIrr);
    value.setAttribute("aria-label", formatTomanFromIrr(row.varianceIrr));
    value.append(element("small", "", row.directionLabel));
    link.append(identity, track, value);
    chart.append(link);
  });

  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table report-variance-table");
  table.innerHTML = "<thead><tr><th>قلم هزینه</th><th>نوع هزینه</th><th>اثر تغییر قیمت</th><th>جهت اثر</th><th>جزئیات</th></tr></thead>";
  const body = document.createElement("tbody");
  presentation.forEach((row) => {
    const record = document.createElement("tr");
    const identity = document.createElement("td");
    identity.append(element("strong", "", row.resourceTitle || "قلم بدون عنوان"), element("small", "table-subtext numeric", row.resourceCode || "بدون کد"));
    const detail = element("a", "table-action", "مشاهده قیمت");
    detail.href = varianceLink("#/prices", row);
    record.append(identity, element("td", "", row.resourceTypeLabel), element("td", "numeric", formatTomanFromIrr(row.varianceIrr)), element("td", `variance-direction variance-direction--${row.direction}`, row.directionLabel), element("td", "", ""));
    record.lastElementChild.append(detail);
    body.append(record);
  });
  table.append(body);
  wrapper.append(table);
  section.append(chart, wrapper);
  return section;
}

function renderQuantityVariances(rows = []) {
  const section = element("section", "report-section report-analysis-section");
  const heading = element("div", "report-analysis-heading");
  heading.append(
    element("h2", "", "بیشترین انحراف مقدار"),
    element("p", "", "اختلاف آخرین مقدار برآورد با مقدار مبنای هر ردیف؛ برای مقایسه صحیح، واحد هر قلم باید از Backend ارائه شود."),
  );
  section.append(heading);
  if (!rows.length) {
    section.append(element("p", "report-analysis-empty", "انحراف مقداری برای این تاریخ گزارش ثبت نشده است."));
    return section;
  }
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table report-variance-table");
  table.innerHTML = "<thead><tr><th>قلم هزینه</th><th>نوع هزینه</th><th>انحراف مقدار</th><th>جزئیات ردیف برآورد</th></tr></thead>";
  const body = document.createElement("tbody");
  buildQuantityVariancePresentation(rows).forEach((row) => {
    const record = document.createElement("tr");
    const identity = document.createElement("td");
    identity.append(element("strong", "", row.resourceTitle || "قلم بدون عنوان"), element("small", "table-subtext numeric", row.resourceCode || "بدون کد"));
    const detail = element("a", "table-action", "مشاهده ردیف");
    detail.href = varianceLink("#/financial-items", row);
    record.append(identity, element("td", "", row.resourceTypeLabel), element("td", "numeric", formatDisplayNumber(row.varianceQuantity)), element("td", "", ""));
    record.lastElementChild.append(detail);
    body.append(record);
  });
  table.append(body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

function renderReportWarnings(rows = []) {
  if (!rows.length) return document.createDocumentFragment();
  const section = element("section", "report-section report-warning-section");
  section.append(element("h2", "", "هشدارهای مؤثر بر محاسبات"));
  const list = document.createElement("ul");
  rows.forEach((warning) => {
    const item = document.createElement("li");
    item.append(element("span", "", REPORT_WARNING_LABELS[warning.code] ?? "هشداری برای محاسبات این گزارش ثبت شده است."));
    if (warning.estimateLineId) {
      const detail = element("a", "table-action", "مشاهده ردیف برآورد");
      detail.href = `#/financial-items?estimateLineId=${encodeURIComponent(warning.estimateLineId)}`;
      item.append(detail);
    }
    list.append(item);
  });
  section.append(list);
  return section;
}

function renderSnapshot(snapshot, { canExport, onDownload }) {
  const section = element("section", "report-section report-snapshot");
  const head = element("div", "section-heading");
  const title = element("div");
  title.append(element("span", "", "گزارش دوره‌ای"), element("h2", "", "گزارش ثبت‌شده"));
  const badge = element("span", "type-badge", snapshot.immutable ? "قفل‌شده و تغییرناپذیر" : "وضعیت نامشخص");
  head.append(title, badge);
  const details = element("dl", "report-snapshot__details");
  const fields = [
    ["شناسه گزارش", snapshot.reportSnapshotId],
    ["زمان صدور", formatSystemDateTime(snapshot.issuedAt)],
    ["صادرکننده", snapshot.issuedBy],
    ["نسخه پیشرفت پروژه", snapshot.progressSnapshotId],
    ["نسخه‌های قیمت", formatDisplayNumber(snapshot.priceVersionIds?.length ?? 0)],
    ["فاکتورهای تثبیت‌شده", formatDisplayNumber(snapshot.invoiceIds?.length ?? 0)],
  ];
  fields.forEach(([label, value]) => {
    const group = element("div");
    group.append(element("dt", "", label), element("dd", "numeric", value ?? "—"));
    details.append(group);
  });
  const actions = element("div", "report-actions");
  const print = element("button", "button button--ghost", "چاپ یا ذخیره PDF");
  print.type = "button";
  print.addEventListener("click", () => window.print());
  actions.append(print);
  if (canExport) {
    const csv = element("button", "button button--primary", "دریافت CSV");
    csv.type = "button";
    csv.addEventListener("click", onDownload);
    actions.append(csv);
  }
  section.append(head, details, renderMetrics(snapshot.calculatedMetrics), actions);
  return section;
}

export function createReportsPage({ context, adapter }) {
  const root = element("div", "reports-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let reportingDate = getTehranTodayIso();
  let snapshot = null;
  let actionError = "";

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const report = await adapter.getLiveReport({ reportingDate });
      state = report ? createRequestState(REQUEST_STATUS.SUCCESS, report) : createRequestState(REQUEST_STATUS.EMPTY);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  async function issue() {
    actionError = "";
    try {
      snapshot = await adapter.issueSnapshot({ reportingDate, progressSnapshotId: state.data?.progressSnapshotId ?? null });
    } catch (error) {
      actionError = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
    }
    paint();
  }

  async function downloadCsv() {
    actionError = "";
    try {
      const file = await adapter.downloadSnapshotCsv(snapshot.reportSnapshotId);
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      actionError = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
      paint();
    }
  }

  function openIssueDialog() {
    const dialog = element("dialog", "confirm-dialog report-issue-dialog");
    dialog.setAttribute("aria-labelledby", "report-issue-title");
    const title = element("h2", "", "تأیید ثبت گزارش دوره‌ای");
    title.id = "report-issue-title";
    const warning = element("p", "", `گزارش تاریخ ${formatBusinessDate(reportingDate)} با ورودی‌ها و شاخص‌های فعلی تثبیت می‌شود و بعداً قابل تغییر نیست.`);
    const actions = element("div", "dialog-actions");
    const cancel = element("button", "button button--ghost", "انصراف");
    const confirm = element("button", "button button--primary", "ثبت گزارش دوره‌ای");
    cancel.type = confirm.type = "button";
    cancel.addEventListener("click", () => dialog.close());
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      await issue();
      dialog.close();
    });
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    actions.append(cancel, confirm);
    dialog.append(title, warning, actions);
    root.append(dialog);
    showAccessibleDialog(dialog);
  }

  function renderContent(report) {
    const fragment = document.createDocumentFragment();
    const toolbar = element("section", "report-toolbar");
    const heading = element("div");
    heading.append(element("h1", "", "گزارش مالی"), element("p", "", "گزارش به‌روز پروژه بر پایه داده‌های قطعی مالی و نسخه پیشرفت پروژه"));
    const controls = element("div", "report-toolbar__controls");
    const picker = createPersianDatePicker({ id: "reportingDate", label: "تاریخ گزارش", value: reportingDate, hint: "تاریخ در رابط کاربری جلالی و در API به‌صورت استاندارد ارسال می‌شود." });
    const refresh = element("button", "button button--ghost", "به‌روزرسانی گزارش");
    refresh.type = "button";
    refresh.addEventListener("click", () => {
      reportingDate = picker.getValue();
      snapshot = null;
      load();
    });
    controls.append(picker.field, refresh);
    if (hasPermission(context, "finance_report.issue")) {
      const issueButton = element("button", "button button--primary", "ثبت گزارش دوره‌ای");
      issueButton.type = "button";
      issueButton.addEventListener("click", openIssueDialog);
      controls.append(issueButton);
    }
    toolbar.append(heading, controls);
    const analysis = element("section", "report-analysis-grid");
    analysis.setAttribute("aria-label", "جزئیات اثر تغییرات و انحرافات مالی");
    analysis.append(renderPriceVariances(report.topPriceVariances), renderQuantityVariances(report.topQuantityVariances));
    fragment.append(toolbar, renderMetrics(report.metrics), renderBreakdown(report.breakdown), analysis, renderReportWarnings(report.warnings));
    if (actionError) fragment.append(element("p", "inline-notice state-card--danger", actionError));
    if (snapshot) fragment.append(renderSnapshot(snapshot, { canExport: hasPermission(context, "finance_report.export"), onDownload: downloadCsv }));
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderPageState(state, { renderContent, onRetry: load }));
  }

  load();
  return root;
}
