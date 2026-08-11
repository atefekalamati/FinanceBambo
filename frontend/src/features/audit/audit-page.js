import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { ACTION_LABELS, ENTITY_LABELS, filterAuditEvents } from "./audit-model.js";

const VALUE_LABELS = Object.freeze({
  computedValue: "مقدار محاسبه‌شده",
  fileId: "شناسه فایل",
  finalAmountIrr: "مبلغ نهایی",
  overrideValue: "مقدار جایگزین",
  progressSnapshotId: "شناسه نسخه پیشرفت",
  reportingDate: "تاریخ گزارش",
  status: "وضعیت",
  unitPriceIrr: "قیمت واحد",
  version: "نسخه",
});

const STATUS_LABELS = Object.freeze({ awaitingConfirmation: "در انتظار تأیید", confirmed: "تأییدشده", draft: "پیش‌نویس", voided: "باطل‌شده", corrected: "اصلاح‌شده" });

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatValue(key, value) {
  if (value === null || value === undefined) return "—";
  if (/irr$/i.test(key) && /^-?\d+$/.test(String(value))) return formatTomanFromIrr(value);
  if (key === "status") return STATUS_LABELS[value] ?? "وضعیت تعریف‌نشده";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderValueSet(title, values) {
  const section = element("section", "audit-detail__values");
  section.append(element("h3", "", title));
  if (!values || !Object.keys(values).length) {
    section.append(element("p", "missing-value", "مقداری ثبت نشده است."));
    return section;
  }
  const list = element("dl", "audit-change-list");
  Object.entries(values).forEach(([key, value]) => {
    const row = element("div");
    row.append(element("dt", "", VALUE_LABELS[key] ?? "فیلد ثبت‌شده"), element("dd", "numeric", formatValue(key, value)));
    list.append(row);
  });
  section.append(list);
  return section;
}

function createDetailDialog(event) {
  const dialog = element("dialog", "confirm-dialog audit-detail-dialog");
  dialog.setAttribute("aria-labelledby", "audit-detail-title");
  const head = element("header", "audit-detail__head");
  const title = element("div");
  const heading = element("h2", "", ACTION_LABELS[event.action] ?? "رویداد ممیزی");
  heading.id = "audit-detail-title";
  title.append(heading, element("p", "", `${ENTITY_LABELS[event.entityType] ?? "موجودیت مالی"} · ${formatSystemDateTime(event.occurredAt)}`));
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن جزئیات ممیزی");
  close.addEventListener("click", () => dialog.close());
  head.append(title, close);
  const identity = element("dl", "audit-detail__identity");
  [["شناسه رویداد", event.id], ["کاربر", event.actorUserId], ["شناسه موجودیت", event.entityId]].forEach(([label, value]) => {
    const row = element("div");
    row.append(element("dt", "", label), element("dd", "numeric", value));
    identity.append(row);
  });
  dialog.append(head, identity);
  if (event.reason) dialog.append(element("div", "inline-notice", `دلیل ثبت‌شده: ${event.reason}`));
  const comparison = element("div", "audit-detail__comparison");
  comparison.append(renderValueSet("مقدار قبل", event.beforeValues), renderValueSet("مقدار بعد", event.afterValues));
  dialog.append(comparison);
  return dialog;
}

function createSelect(label, options) {
  const select = element("select", "app-select");
  select.setAttribute("aria-label", label);
  select.append(Object.assign(document.createElement("option"), { value: "", textContent: label }));
  options.forEach(([value, text]) => select.append(Object.assign(document.createElement("option"), { value, textContent: text })));
  return select;
}

export function createAuditPage({ adapter }) {
  const root = element("div", "audit-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let filters = { query: "", action: "", entityType: "", from: "", to: "" };

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const events = await adapter.getEvents();
      state = events.length ? createRequestState(REQUEST_STATUS.SUCCESS, events) : createRequestState(REQUEST_STATUS.EMPTY);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderContent(events) {
    const fragment = document.createDocumentFragment();
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "ردیابی تغییرات حساس"), element("h1", "", "تاریخچه و ممیزی"), element("p", "", "رویدادها فقط‌خواندنی و براساس زمان ثبت Backend نمایش داده می‌شوند."));
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.href = "#/finance";
    header.append(copy, back);

    const form = element("form", "audit-filters");
    const query = element("input", "app-input");
    query.type = "search";
    query.value = filters.query;
    query.placeholder = "جست‌وجوی کاربر، شناسه یا دلیل";
    query.setAttribute("aria-label", "جست‌وجوی رویدادهای ممیزی");
    const actions = [...new Set(events.map((event) => event.action))].sort().map((value) => [value, ACTION_LABELS[value] ?? "عملیات تعریف‌نشده"]);
    const entities = [...new Set(events.map((event) => event.entityType))].sort().map((value) => [value, ENTITY_LABELS[value] ?? "موجودیت تعریف‌نشده"]);
    const action = createSelect("همه عملیات", actions);
    const entity = createSelect("همه موجودیت‌ها", entities);
    action.value = filters.action;
    entity.value = filters.entityType;
    const from = createPersianDatePicker({ id: "auditFrom", label: "از تاریخ", value: filters.from, hint: "اختیاری" });
    const to = createPersianDatePicker({ id: "auditTo", label: "تا تاریخ", value: filters.to, hint: "اختیاری" });
    const submit = element("button", "button button--primary", "اعمال فیلتر");
    submit.type = "submit";
    const reset = element("button", "button button--ghost", "پاک‌کردن");
    reset.type = "button";
    reset.addEventListener("click", () => { filters = { query: "", action: "", entityType: "", from: "", to: "" }; paint(); });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      filters = { query: query.value.trim(), action: action.value, entityType: entity.value, from: from.getValue(), to: to.getValue() };
      paint();
    });
    form.append(query, action, entity, from.field, to.field, submit, reset);

    const filtered = filterAuditEvents(events, filters);
    const summary = element("p", "audit-result-count", `${formatDisplayNumber(String(filtered.length))} رویداد از ${formatDisplayNumber(String(events.length))} رویداد نمایش داده می‌شود.`);
    const wrapper = element("div", "table-scroll");
    const table = element("table", "data-table audit-table");
    table.append(element("caption", "sr-only", "فهرست رویدادهای ممیزی مالی"));
    const head = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["زمان", "عملیات", "موجودیت", "کاربر", "دلیل", "جزئیات"].forEach((label) => headerRow.append(element("th", "", label)));
    head.append(headerRow);
    const body = document.createElement("tbody");
    filtered.forEach((auditEvent) => {
      const row = document.createElement("tr");
      const detailCell = document.createElement("td");
      const detail = element("button", "table-action table-action--primary", "مشاهده");
      detail.type = "button";
      detail.addEventListener("click", () => {
        const dialog = createDetailDialog(auditEvent);
        root.append(dialog);
        dialog.addEventListener("close", () => dialog.remove(), { once: true });
        dialog.showModal();
      });
      detailCell.append(detail);
      row.append(
        element("td", "", formatSystemDateTime(auditEvent.occurredAt)),
        element("td", "", ACTION_LABELS[auditEvent.action] ?? "عملیات تعریف‌نشده"),
        element("td", "", ENTITY_LABELS[auditEvent.entityType] ?? "موجودیت تعریف‌نشده"),
        element("td", "numeric", auditEvent.actorUserId),
        element("td", "", auditEvent.reason || "بدون دلیل ثبت‌شده"),
        detailCell,
      );
      body.append(row);
    });
    if (!filtered.length) {
      const row = document.createElement("tr");
      const cell = element("td", "audit-table__empty", "رویدادی مطابق فیلترهای انتخاب‌شده پیدا نشد.");
      cell.colSpan = 6;
      row.append(cell);
      body.append(row);
    }
    table.append(head, body);
    wrapper.append(table);
    fragment.append(header, form, summary, wrapper);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderPageState(state, { renderContent, onRetry: load }));
  }

  load();
  return root;
}
