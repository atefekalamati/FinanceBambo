import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { ACTION_LABELS, ENTITY_LABELS, filterAuditEvents } from "./audit-model.js";
import { element } from "../../shared/dom/elements.js";

/** GET /audit-events default; the endpoint accepts 1..200 and returns a paged envelope. */
const AUDIT_PAGE_SIZE = 50;

const VALUE_LABELS = Object.freeze({
  computedValue: "مقدار محاسبه‌شده",
  fileId: "شناسه فایل",
  finalAmountIrr: "مبلغ نهایی",
  overrideValue: "مقدار جایگزین",
  progressSnapshotId: "شناسه نسخه پیشرفت پروژه",
  reportingDate: "تاریخ گزارش",
  status: "وضعیت",
  unitPriceIrr: "قیمت واحد",
  version: "نسخه",
});

const STATUS_LABELS = Object.freeze({ awaitingConfirmation: "در انتظار تأیید", confirmed: "تأییدشده", draft: "پیش‌نویس", voided: "باطل‌شده", corrected: "اصلاح‌شده" });

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
  const heading = element("h2", "", ACTION_LABELS[event.action] ?? "رویداد تغییر");
  heading.id = "audit-detail-title";
  title.append(heading, element("p", "", `${ENTITY_LABELS[event.entityType] ?? "موجودیت مالی"} · ${formatSystemDateTime(event.occurredAt)}`));
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن جزئیات تغییر");
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
  let loadedPages = 0;
  let totalItems = 0;
  let hasOlderEvents = false;
  let loadingOlder = false;
  let olderError = "";

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    loadedPages = 0;
    totalItems = 0;
    hasOlderEvents = false;
    loadingOlder = false;
    olderError = "";
    paint();
    try {
      const page = await adapter.getEvents({ page: 1, pageSize: AUDIT_PAGE_SIZE });
      loadedPages = 1;
      totalItems = page.totalItems ?? page.items.length;
      hasOlderEvents = page.items.length < totalItems;
      state = page.items.length ? createRequestState(REQUEST_STATUS.SUCCESS, page.items) : createRequestState(REQUEST_STATUS.EMPTY);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  async function loadOlder() {
    if (loadingOlder || !hasOlderEvents) return;
    loadingOlder = true;
    olderError = "";
    paint();
    try {
      const older = await adapter.getEvents({ page: loadedPages + 1, pageSize: AUDIT_PAGE_SIZE });
      loadedPages += 1;
      totalItems = older.totalItems ?? totalItems;
      const merged = [...state.data, ...older.items];
      hasOlderEvents = merged.length < totalItems;
      state = createRequestState(REQUEST_STATUS.SUCCESS, merged);
    } catch (error) {
      olderError = formatApiErrorMessage(error, "دریافت رویدادهای قدیمی‌تر انجام نشد.");
    }
    loadingOlder = false;
    paint();
  }

  function renderContent(events) {
    const fragment = document.createDocumentFragment();
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "ردیابی تغییرات حساس"), element("h1", "", "تاریخچه تغییرات مالی"), element("p", "", "رویدادهای تغییر فقط‌خواندنی و براساس زمان ثبت سیستم نمایش داده می‌شوند."));
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.classList.add("finance-back-link");
    back.href = "#/finance";
    const navigation = element("div", "feature-header__navigation");
    const otherActions = element("div", "feature-header__other-actions");
    navigation.append(otherActions, back);
    header.append(copy, navigation);

    const form = element("form", "audit-filters");
    const query = element("input", "app-input");
    query.type = "search";
    query.value = filters.query;
    query.placeholder = "جست‌وجوی کاربر، شناسه یا دلیل";
    query.setAttribute("aria-label", "جست‌وجوی رویدادهای تغییر");
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
    const summary = element("p", "audit-result-count", `${formatDisplayNumber(String(filtered.length))} رویداد از ${formatDisplayNumber(String(totalItems))} رویداد ثبت‌شده نمایش داده می‌شود.`);
    if (hasOlderEvents) {
      summary.append(element("span", "audit-result-count__note", `${formatDisplayNumber(String(events.length))} رویداد بارگذاری شده است؛ فیلترها تا بارگذاری بقیه فقط روی همین‌ها اعمال می‌شوند.`));
    }
    const wrapper = element("div", "table-scroll");
    const table = element("table", "data-table audit-table");
    table.append(element("caption", "sr-only", "فهرست رویدادهای تغییر مالی"));
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
        showAccessibleDialog(dialog);
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

    const pagination = element("div", "audit-pagination");
    if (hasOlderEvents) {
      const more = element("button", "button button--ghost", loadingOlder ? "در حال دریافت رویدادها…" : "بارگذاری رویدادهای قدیمی‌تر");
      more.type = "button";
      more.disabled = loadingOlder;
      more.addEventListener("click", loadOlder);
      pagination.append(more);
    } else if (loadedPages > 1) {
      pagination.append(element("p", "audit-pagination__end", "تمام رویدادهای ثبت‌شده بارگذاری شده‌اند."));
    }
    if (olderError) {
      const notice = element("p", "inline-notice", olderError);
      notice.setAttribute("role", "alert");
      pagination.append(notice);
    }

    fragment.append(header, form, summary, wrapper, pagination);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderPageState(state, { renderContent, onRetry: load }));
  }

  load();
  return root;
}
