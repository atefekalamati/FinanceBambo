import { hasPermission } from "../../core/auth/permissions.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";

const METRICS = Object.freeze([
  ["initialEstimateIrr", "برآورد اولیه"],
  ["actualCostIrr", "هزینه واقعی"],
  ["currentExecutedValueIrr", "ارزش روز کار اجراشده"],
  ["remainingPhysicalCostIrr", "هزینه فیزیکی باقیمانده"],
  ["moneyRequiredToContinueIrr", "پول موردنیاز برای ادامه"],
  ["forecastFinalCostIrr", "پیش‌بینی هزینه نهایی"],
  ["actualCostPerSquareMeterIrr", "هزینه واقعی هر مترمربع"],
  ["forecastPerSquareMeterIrr", "پیش‌بینی هر مترمربع"],
]);

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
    card.append(element("h2", "", label), element("p", "summary-card__value", formatTomanFromIrr(metrics?.[key])), element("span", "summary-card__unit", getDisplayCurrencyLabel()));
    grid.append(card);
  });
  return grid;
}

function renderBreakdown(rows = []) {
  const section = element("section", "report-section");
  section.append(element("h2", "", "تفکیک مالی بر اساس نوع قلم"));
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table report-table");
  table.innerHTML = `<colgroup><col class="report-table__type"><col><col><col></colgroup><thead><tr><th>نوع قلم</th><th>برآورد اولیه</th><th>هزینه واقعی</th><th>پیش‌بینی نهایی</th></tr></thead>`;
  const labels = { material: "مصالح", labor: "نیروی انسانی", equipment: "تجهیزات و ماشین‌آلات", general_cost: "هزینه عمومی" };
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [labels[row.resourceType] ?? "نوع تعریف‌نشده", formatTomanFromIrr(row.initialEstimateIrr), formatTomanFromIrr(row.actualCostIrr), formatTomanFromIrr(row.forecastFinalIrr)].forEach((value, index) => tr.append(element("td", index ? "numeric" : "", value)));
    body.append(tr);
  });
  table.append(body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

function renderSnapshot(snapshot, { canExport, onDownload }) {
  const section = element("section", "report-section report-snapshot");
  const head = element("div", "section-heading");
  const title = element("div");
  title.append(element("span", "", "نسخه صادرشده"), element("h2", "", "گزارش تغییرناپذیر"));
  const badge = element("span", "type-badge", snapshot.immutable ? "قفل‌شده و تغییرناپذیر" : "وضعیت نامشخص");
  head.append(title, badge);
  const details = element("dl", "report-snapshot__details");
  const fields = [
    ["شناسه گزارش", snapshot.reportSnapshotId],
    ["زمان صدور", formatSystemDateTime(snapshot.issuedAt)],
    ["صادرکننده", snapshot.issuedBy],
    ["نسخه پیشرفت", snapshot.progressSnapshotId],
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
    const title = element("h2", "", "تأیید صدور گزارش");
    title.id = "report-issue-title";
    const warning = element("p", "", `گزارش تاریخ ${formatBusinessDate(reportingDate)} با ورودی‌ها و شاخص‌های فعلی تثبیت می‌شود و بعداً قابل تغییر نیست.`);
    const actions = element("div", "dialog-actions");
    const cancel = element("button", "button button--ghost", "انصراف");
    const confirm = element("button", "button button--primary", "صدور نسخه تغییرناپذیر");
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
    dialog.showModal();
  }

  function renderContent(report) {
    const fragment = document.createDocumentFragment();
    const toolbar = element("section", "report-toolbar");
    const heading = element("div");
    heading.append(element("h1", "", "گزارش مالی"), element("p", "", "گزارش زنده پروژه بر پایه داده‌های قطعی مالی و نسخه پیشرفت انتخاب‌شده"));
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
      const issueButton = element("button", "button button--primary", "صدور گزارش");
      issueButton.type = "button";
      issueButton.addEventListener("click", openIssueDialog);
      controls.append(issueButton);
    }
    toolbar.append(heading, controls);
    fragment.append(toolbar, renderMetrics(report.metrics), renderBreakdown(report.breakdown));
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
