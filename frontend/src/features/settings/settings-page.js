import { hasPermission } from "../../core/auth/permissions.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatArea, formatBusinessDate, formatSystemDateTime } from "../../shared/formatters/display.js";
import { getDisplayCurrencyCode, getDisplayCurrencyLabel, setDisplayCurrencyCode } from "../../shared/preferences/currency-preference.js";
import { validateSettingsRevision } from "./settings-validation.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function createField({ id, label, type = "text", value = "", hint, inputMode, required = false }) {
  const field = element("div", "form-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = id;
  const input = document.createElement("input");
  input.id = id;
  input.name = id;
  input.type = type;
  input.value = value;
  input.required = required;
  if (inputMode) input.inputMode = inputMode;
  input.setAttribute("aria-describedby", `${id}-hint ${id}-error`);
  const hintNode = element("small", "form-hint", hint);
  hintNode.id = `${id}-hint`;
  const errorNode = element("small", "form-error");
  errorNode.id = `${id}-error`;
  errorNode.setAttribute("aria-live", "polite");
  field.append(labelNode, input, hintNode, errorNode);
  return { field, input, error: errorNode };
}

function createRevisionTable(revisions) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table settings-history");
  const caption = element("caption", "sr-only", "تاریخچه تغییر زیربنای کل");
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["تاریخ اثر", "مقدار قبلی", "مقدار جدید", "دلیل", "ثبت‌کننده", "زمان ثبت"].forEach((title) => headerRow.append(element("th", "", title)));
  head.append(headerRow);
  const body = document.createElement("tbody");
  revisions.forEach((revision) => {
    const row = document.createElement("tr");
    row.append(
      element("td", "", formatBusinessDate(revision.effectiveDate)),
      element("td", "numeric", revision.previousValue ? formatArea(revision.previousValue) : "ثبت اولیه"),
      element("td", "numeric", formatArea(revision.newValue)),
      element("td", "", revision.reason),
      element("td", "", revision.actorName || revision.actorId),
      element("td", "", formatSystemDateTime(revision.occurredAt)),
    );
    body.append(row);
  });
  table.append(caption, head, body);
  wrapper.append(table);
  return wrapper;
}

export function createSettingsPage({ context, adapter, onSettingsUpdated = () => {} }) {
  const root = element("div", "settings-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let settings = null;

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      settings = await adapter.getSettings();
      state = createRequestState(settings ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, settings);
    } catch (error) {
      state = createRequestState(REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader() {
    const header = element("header", "feature-header");
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.href = "#/finance";
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "تنظیمات سطح پروژه"), element("h1", "", "تنظیمات مالی"), element("p", "", "زیربنای کل و سیاست نمایش پول پروژه را مدیریت کنید. تمام تغییرات زیربنا با دلیل و تاریخ اثر ثبت می‌شوند."));
    header.append(copy, back);
    return header;
  }

  function renderEmpty() {
    const card = element("section", "state-card settings-empty");
    card.append(element("h2", "", "تنظیمات مالی هنوز ثبت نشده است"), element("p", "", `برای شروع، زیربنای کل پروژه را ثبت کنید. واحد پول رسمی به‌صورت ثابت ${CURRENCY_LABELS.IRR} خواهد بود.`));
    const button = element("button", "button button--primary", "ثبت اولین تنظیمات");
    button.type = "button";
    button.addEventListener("click", () => root.replaceChildren(renderHeader(), renderEditor(null)));
    card.append(button);
    return card;
  }

  function renderCurrencyPolicy() {
    const section = element("section", "settings-card currency-policy");
    const title = element("div", "settings-card__head");
    title.append(element("div", "settings-card__icon", "﷼"), element("div", "", ""));
    title.lastElementChild.append(element("h2", "", "واحد نمایش مبالغ"), element("p", "", "واحدی را انتخاب کنید که مبالغ در تمام بخش‌های مالی با آن نمایش داده شوند."));
    const grid = element("div", "currency-grid");
    const selectedCode = getDisplayCurrencyCode();
    [["TOMAN", "تومان", "نمایش ساده‌تر و پیش‌فرض سامانه"], ["IRR", "ریال", "نمایش مبلغ رسمی بدون تبدیل"]].forEach(([code, label, description]) => {
      const option = element("button", `currency-item currency-choice${selectedCode === code ? " currency-item--active" : ""}`);
      option.type = "button";
      option.setAttribute("role", "radio");
      option.setAttribute("aria-checked", String(selectedCode === code));
      option.append(element("span", "currency-item__label", selectedCode === code ? "انتخاب‌شده" : "انتخاب واحد"), element("strong", "", label), element("small", "", description));
      option.addEventListener("click", () => {
        if (getDisplayCurrencyCode() !== code) setDisplayCurrencyCode(code);
      });
      grid.append(option);
    });
    grid.setAttribute("role", "radiogroup");
    grid.setAttribute("aria-label", "انتخاب واحد نمایش مبالغ مالی");
    section.append(title, grid);
    return section;
  }

  function renderEditor(current) {
    const section = element("section", "settings-card settings-editor");
    const head = element("div", "settings-card__head");
    head.append(element("div", "settings-card__icon", "م²"), element("div", "", ""));
    head.lastElementChild.append(element("h2", "", current ? "اصلاح زیربنای کل" : "ثبت زیربنای کل"), element("p", "", current ? `مقدار فعلی: ${formatArea(current.grossBuiltArea)} · بازنگری ${current.revision}` : "مقدار مثبت و دقیق زیربنای کل پروژه را وارد کنید."));

    const form = element("form", "settings-form");
    form.noValidate = true;
    const area = createField({ id: "grossBuiltArea", label: "زیربنای کل (مترمربع)", value: current?.grossBuiltArea ?? "", hint: "عدد مثبت با حداکثر چهار رقم اعشار؛ ارقام فارسی نیز پذیرفته می‌شوند.", inputMode: "decimal", required: true });
    const date = createPersianDatePicker({ id: "effectiveDate", label: "تاریخ اثر", value: getTehranTodayIso(), hint: "تاریخ را براساس تقویم جلالی و زمان ایران انتخاب کنید." });
    const reasonField = element("div", "form-field form-field--wide");
    const reasonLabel = element("label", "form-label", "دلیل تغییر");
    reasonLabel.htmlFor = "reason";
    const reason = document.createElement("textarea");
    reason.id = "reason";
    reason.name = "reason";
    reason.rows = 3;
    reason.required = true;
    reason.placeholder = current ? "برای مثال: اصلاح زیربنا براساس نقشه مصوب جدید" : "برای مثال: ثبت اولیه براساس نقشه مصوب پروژه";
    reason.setAttribute("aria-describedby", "reason-hint reason-error");
    const reasonHint = element("small", "form-hint", "دلیل در تاریخچه مالی ذخیره می‌شود و بعداً قابل حذف نیست.");
    reasonHint.id = "reason-hint";
    const reasonError = element("small", "form-error");
    reasonError.id = "reason-error";
    reasonError.setAttribute("aria-live", "polite");
    reasonField.append(reasonLabel, reason, reasonHint, reasonError);

    const status = element("div", "form-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const submit = element("button", "button button--primary", current ? "ثبت بازنگری جدید" : "ثبت تنظیمات");
    submit.type = "submit";
    const actions = element("div", "form-actions");
    actions.append(submit, status);
    form.append(area.field, date.field, reasonField, actions);

    const dialog = document.createElement("dialog");
    dialog.className = "confirm-dialog";
    dialog.setAttribute("aria-labelledby", "settings-confirm-title");
    const dialogTitle = element("h2", "", "تأیید تغییر زیربنا");
    dialogTitle.id = "settings-confirm-title";
    const dialogMessage = element("p", "", "این تغییر به‌صورت بازنگری جدید ثبت می‌شود و نسخه‌های ثبت‌شده قبلی گزارش‌ها را تغییر نمی‌دهد.");
    const dialogActions = element("div", "dialog-actions");
    const cancel = element("button", "button button--ghost", "لغو");
    cancel.type = "button";
    const confirm = element("button", "button button--primary", "تأیید و ثبت");
    confirm.type = "button";
    dialogActions.append(cancel, confirm);
    dialog.append(dialogTitle, dialogMessage, dialogActions);

    let pendingValues = null;
    function showErrors(errors) {
      area.error.textContent = errors.grossBuiltArea;
      date.error.textContent = errors.effectiveDate;
      reasonError.textContent = errors.reason;
      area.input.setAttribute("aria-invalid", String(Boolean(errors.grossBuiltArea)));
      date.input.setAttribute("aria-invalid", String(Boolean(errors.effectiveDate)));
      reason.setAttribute("aria-invalid", String(Boolean(errors.reason)));
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const validation = validateSettingsRevision({ grossBuiltArea: area.input.value, effectiveDate: date.getValue(), reason: reason.value });
      showErrors(validation.errors);
      if (!validation.valid) {
        status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
        form.querySelector('[aria-invalid="true"]')?.focus();
        return;
      }
      pendingValues = validation.values;
      dialog.showModal();
    });
    cancel.addEventListener("click", () => dialog.close());
    confirm.addEventListener("click", async () => {
      if (!pendingValues) return;
      confirm.disabled = true;
      cancel.disabled = true;
      status.textContent = "در حال ثبت بازنگری…";
      try {
        settings = await adapter.updateGrossBuiltArea({ ...pendingValues, expectedRevision: current?.revision ?? 0 });
        state = createRequestState(REQUEST_STATUS.SUCCESS, settings);
        dialog.close();
        onSettingsUpdated(settings);
        paint();
      } catch (error) {
        dialog.close();
        status.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
      } finally {
        confirm.disabled = false;
        cancel.disabled = false;
      }
    });

    section.append(head, form, dialog);
    return section;
  }

  function renderContent(data) {
    const fragment = document.createDocumentFragment();
    const overview = element("section", "settings-overview");
    const areaCard = element("article", "settings-overview__item");
    areaCard.append(element("span", "", "زیربنای کل فعلی"), element("strong", "numeric", formatArea(data.grossBuiltArea)), element("small", "", `بازنگری ${data.revision}`));
    const currencyCard = element("article", "settings-overview__item");
    currencyCard.append(element("span", "", "واحد نمایش مبالغ"), element("strong", "", getDisplayCurrencyLabel()), element("small", "", "قابل تغییر برای تمام بخش‌های مالی"));
    overview.append(areaCard, currencyCard);

    const history = element("section", "settings-card settings-history-card");
    const historyHead = element("div", "settings-card__head");
    historyHead.append(element("div", "settings-card__icon", "↺"), element("div", "", ""));
    historyHead.lastElementChild.append(element("h2", "", "تاریخچه تغییر زیربنا"), element("p", "", "مقدار اولیه و همه بازنگری‌ها به‌صورت تغییرناپذیر نمایش داده می‌شوند."));
    history.append(historyHead, createRevisionTable(data.revisions));
    fragment.append(overview, renderCurrencyPolicy(), renderEditor(data), history);
    return fragment;
  }

  function paint() {
    const contentState = hasPermission(context, "finance.edit") ? state : createRequestState(REQUEST_STATUS.DENIED);
    root.replaceChildren(renderHeader(), renderPageState(contentState, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
