import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { hasPermission } from "../../core/auth/permissions.js";
import { validateInvoiceAdjustments, validateInvoiceHeader, validateInvoiceLine } from "./invoices-validation.js";

const STATUS_LABELS = Object.freeze({ draft: "پیش‌نویس", awaitingConfirmation: "در انتظار تأیید", confirmed: "تأییدشده", voided: "باطل‌شده", corrected: "اصلاح‌شده" });
const SOURCE_LABELS = Object.freeze({ manual: "ورود دستی", image: "تصویر", voice: "صدای فارسی" });

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatTomanFromIRR(value) {
  if (!/^\d+$/.test(String(value ?? ""))) return "—";
  const digits = String(value).replace(/^0+(?=\d)/, "") || "0";
  const whole = digits.length > 1 ? digits.slice(0, -1) : "0";
  const remainder = digits.at(-1);
  return `${formatDisplayNumber(remainder === "0" ? whole : `${whole}.${remainder}`)} تومان`;
}

function option(value, label) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

function inputField(label, name, { type = "text", inputMode = "text", placeholder = "" } = {}) {
  const field = element("label", "form-field");
  field.append(element("span", "form-label", label));
  const input = element("input", "app-input");
  input.name = name;
  input.type = type;
  input.inputMode = inputMode;
  input.placeholder = placeholder;
  field.append(input);
  return { field, input };
}

function createInvoiceWizard({ adapter, onSaved }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-wizard";
  dialog.setAttribute("aria-labelledby", "invoice-wizard-title");
  const head = element("header", "invoice-detail-dialog__head");
  const heading = element("div");
  const title = element("h2", "", "ثبت فاکتور دستی");
  title.id = "invoice-wizard-title";
  heading.append(title, element("p", "invoice-wizard__subtitle", "پیش‌نویس تا قبل از تأیید، اثر مالی ندارد."));
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن فرم ثبت فاکتور");
  close.addEventListener("click", () => dialog.close());
  head.append(heading, close);
  const steps = element("ol", "invoice-stepper");
  ["سربرگ", "خطوط", "پیش‌نمایش"].forEach((label, index) => {
    const item = element("li", "", label);
    item.dataset.step = String(index + 1);
    steps.append(item);
  });
  const body = element("div", "invoice-wizard__body");
  const message = element("div", "form-message");
  message.setAttribute("aria-live", "assertive");
  let currentStep = 1;
  let targets = [];
  let headerData = null;
  let lines = [];
  let adjustments = { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" };
  let preview = null;
  let duplicateOverrideReason = "";
  const idempotencyKey = crypto.randomUUID();

  function showMessage(text, error = false) {
    message.textContent = text;
    message.className = `form-message${error ? " form-message--error" : ""}`;
  }

  function updateStepper() {
    [...steps.children].forEach((item, index) => {
      item.classList.toggle("invoice-stepper__active", index + 1 === currentStep);
      item.classList.toggle("invoice-stepper__done", index + 1 < currentStep);
      if (index + 1 === currentStep) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  }

  function actions({ back = false, nextLabel, onNext }) {
    const row = element("div", "dialog-actions invoice-wizard__actions");
    if (back) {
      const previous = element("button", "button button--ghost", "مرحله قبل");
      previous.type = "button";
      previous.addEventListener("click", () => { currentStep -= 1; paintStep(); });
      row.append(previous);
    }
    const next = element("button", "button button--primary", nextLabel);
    next.type = "button";
    next.addEventListener("click", () => onNext(next));
    row.append(next);
    return row;
  }

  function renderHeaderStep() {
    const form = element("div", "invoice-wizard-grid");
    const number = inputField("شماره فاکتور", "invoiceNumber");
    number.input.value = headerData?.invoiceNumber ?? "";
    const vendor = inputField("فروشنده یا ارائه‌دهنده", "vendorName");
    vendor.input.value = headerData?.vendorName ?? "";
    const date = createPersianDatePicker({ id: "invoiceDate", label: "تاریخ فاکتور", value: headerData?.invoiceDate ?? getTehranTodayIso() });
    const description = element("label", "form-field invoice-wizard-grid__wide");
    description.append(element("span", "form-label", "توضیح"));
    const textarea = element("textarea", "app-textarea");
    textarea.rows = 3;
    textarea.maxLength = 500;
    textarea.value = headerData?.description ?? "";
    description.append(textarea);
    form.append(number.field, vendor.field, date.field, description);
    form.append(actions({ nextLabel: "ادامه به خطوط", onNext: () => {
      const validation = validateInvoiceHeader({ invoiceNumber: number.input.value, invoiceDate: date.getValue(), vendorName: vendor.input.value, description: textarea.value });
      if (!validation.valid) { showMessage(Object.values(validation.errors).join(" "), true); return; }
      headerData = validation.values;
      currentStep = 2;
      paintStep();
    } }));
    return form;
  }

  function renderLinesStep() {
    const section = element("div", "invoice-lines-editor");
    const targetField = element("label", "form-field");
    targetField.append(element("span", "form-label", "اتصال به خط برآورد یا هزینه عمومی"));
    const targetSelect = element("select", "app-select");
    targetSelect.append(option("", "انتخاب کنید"), ...targets.map((target) => option(target.targetId, `${target.label} · ${target.targetType === "general_cost" ? "هزینه عمومی" : formatUnitLabel(target.unit)}`)));
    targetField.append(targetSelect);
    const quantity = inputField("مقدار", "quantity", { inputMode: "decimal" });
    const unitPrice = inputField("قیمت واحد به ریال", "unitPriceIRR", { inputMode: "numeric" });
    const amount = inputField("مبلغ خط هزینه عمومی به ریال", "amountIRR", { inputMode: "numeric" });
    amount.field.hidden = true;
    targetSelect.addEventListener("change", () => {
      const target = targets.find((item) => item.targetId === targetSelect.value);
      const general = target?.targetType === "general_cost";
      quantity.field.hidden = general;
      unitPrice.field.hidden = general;
      amount.field.hidden = !general;
    });
    const lineDescription = inputField("توضیح خط", "lineDescription");
    const add = element("button", "button button--ghost", "افزودن خط");
    add.type = "button";
    add.addEventListener("click", () => {
      const target = targets.find((item) => item.targetId === targetSelect.value);
      const validation = validateInvoiceLine({ quantity: quantity.input.value, unitPriceIRR: unitPrice.input.value, amountIRR: amount.input.value, description: lineDescription.input.value }, target);
      if (!validation.valid) { showMessage(Object.values(validation.errors).join(" "), true); return; }
      lines.push(validation.values);
      showMessage("خط به پیش‌نویس اضافه شد.");
      paintStep();
    });
    const editor = element("div", "invoice-line-entry");
    editor.append(targetField, quantity.field, unitPrice.field, amount.field, lineDescription.field, add);
    const list = element("div", "invoice-draft-lines");
    lines.forEach((line, index) => {
      const card = element("article", "invoice-draft-line");
      card.append(element("strong", "", `${formatDisplayNumber(String(index + 1))}. ${line.targetLabel}`), element("span", "numeric", line.targetType === "general_cost" ? `${formatDisplayNumber(line.lineAmountIRR)} ریال` : `${formatDisplayNumber(line.quantity)} ${formatUnitLabel(line.unit)} × ${formatDisplayNumber(line.unitPriceIRR)} ریال`));
      const remove = element("button", "button button--ghost", "حذف خط");
      remove.type = "button";
      remove.addEventListener("click", () => { lines.splice(index, 1); paintStep(); });
      card.append(remove);
      list.append(card);
    });
    const adjustmentGrid = element("div", "invoice-adjustments");
    const adjustmentFields = [["تخفیف به ریال", "discountIRR"], ["مالیات به ریال", "taxIRR"], ["حمل به ریال", "shippingIRR"], ["سایر هزینه‌ها به ریال", "otherCostsIRR"]].map(([label, key]) => {
      const field = inputField(label, key, { inputMode: "numeric" });
      field.input.value = adjustments[key];
      adjustmentGrid.append(field.field);
      return [key, field.input];
    });
    section.append(editor, list, adjustmentGrid, actions({ back: true, nextLabel: "مشاهده پیش‌نمایش", onNext: async (button) => {
      if (!lines.length) { showMessage("حداقل یک خط فاکتور اضافه کنید.", true); return; }
      const validation = validateInvoiceAdjustments(Object.fromEntries(adjustmentFields.map(([key, input]) => [key, input.value])));
      if (!validation.valid) { showMessage(Object.values(validation.errors).join(" "), true); return; }
      adjustments = validation.values;
      button.disabled = true;
      button.textContent = "در حال محاسبه…";
      try { preview = await adapter.previewDraft({ header: headerData, lines, adjustments }); currentStep = 3; paintStep(); }
      catch (error) { showMessage(`${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`, true); button.disabled = false; button.textContent = "مشاهده پیش‌نمایش"; }
    } }));
    return section;
  }

  function renderPreviewStep() {
    const section = element("div", "invoice-preview");
    const summary = element("dl", "invoice-detail-grid");
    [["شماره", headerData.invoiceNumber], ["تاریخ", formatBusinessDate(headerData.invoiceDate)], ["فروشنده", headerData.vendorName], ["منبع", "ورود دستی"]].forEach(([label, value]) => { const item = element("div", "invoice-detail-grid__item"); item.append(element("dt", "", label), element("dd", "", value)); summary.append(item); });
    const lineList = element("div", "invoice-draft-lines");
    preview.lines.forEach((line, index) => { const card = element("article", "invoice-draft-line"); card.append(element("strong", "", `${formatDisplayNumber(String(index + 1))}. ${line.targetLabel}`), element("span", "numeric", formatTomanFromIRR(line.lineAmountIRR))); lineList.append(card); });
    const totals = element("dl", "invoice-totals");
    [["جمع خام خطوط", preview.rawLinesTotalIRR], ["تخفیف", preview.discountIRR], ["مالیات", preview.taxIRR], ["حمل", preview.shippingIRR], ["سایر هزینه‌ها", preview.otherCostsIRR], ["مبلغ نهایی", preview.finalAmountIRR]].forEach(([label, value]) => totals.append(element("dt", "", label), element("dd", "numeric", formatTomanFromIRR(value))));
    section.append(element("div", "inline-notice", "با ثبت این مرحله فقط پیش‌نویس ساخته می‌شود و هزینه واقعی پروژه تغییر نمی‌کند."), summary, lineList, totals);
    let reasonInput = null;
    if (preview.duplicateMatches.length) {
      const warning = element("section", "invoice-duplicate-warning");
      warning.setAttribute("role", "alert");
      warning.append(element("h3", "", "فاکتور مشابه پیدا شد"), element("p", "", "ادامه ثبت مجاز است، اما باید سند مشابه را بررسی و دلیل ادامه را ثبت کنید."));
      const matches = element("ul", "invoice-duplicate-matches");
      preview.duplicateMatches.forEach((match) => matches.append(element("li", "", `${match.invoiceNumber} · ${match.vendorName} · ${formatBusinessDate(match.invoiceDate)} · ${formatTomanFromIRR(match.finalAmountIRR)} · ${STATUS_LABELS[match.invoiceStatus]}`)));
      const reason = element("label", "form-field");
      reason.append(element("span", "form-label", "دلیل ادامه با وجود شباهت"));
      reasonInput = element("textarea", "app-textarea");
      reasonInput.rows = 3;
      reasonInput.maxLength = 500;
      reasonInput.value = duplicateOverrideReason;
      reason.append(reasonInput);
      warning.append(matches, reason);
      section.append(warning);
    }
    section.append(actions({ back: true, nextLabel: "ثبت پیش‌نویس", onNext: async (button) => {
      duplicateOverrideReason = reasonInput?.value.trim() ?? "";
      if (preview.duplicateMatches.length && duplicateOverrideReason.length < 3) { showMessage("دلیل ادامه با وجود فاکتور مشابه باید حداقل سه نویسه داشته باشد.", true); reasonInput.focus(); return; }
      button.disabled = true;
      button.textContent = "در حال ثبت…";
      try { await adapter.createDraft({ header: headerData, lines, adjustments, duplicateOverrideReason, idempotencyKey }); dialog.close(); onSaved(); }
      catch (error) { showMessage(`${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`, true); button.disabled = false; button.textContent = "ثبت پیش‌نویس"; }
    } }));
    return section;
  }

  function paintStep() {
    updateStepper();
    showMessage("");
    body.replaceChildren(currentStep === 1 ? renderHeaderStep() : currentStep === 2 ? renderLinesStep() : renderPreviewStep());
  }

  dialog.append(head, steps, message, body);
  adapter.getInvoiceTargets().then((items) => { targets = items; paintStep(); }).catch((error) => showMessage(error.message, true));
  updateStepper();
  return dialog;
}

function renderDetail(invoice, { canEdit, onSubmit }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-detail-dialog";
  dialog.setAttribute("aria-labelledby", "invoice-detail-title");
  const head = element("header", "invoice-detail-dialog__head");
  const heading = element("div");
  const title = element("h2", "", `جزئیات فاکتور ${invoice.invoiceNumber}`);
  title.id = "invoice-detail-title";
  heading.append(title, element("span", `invoice-status invoice-status--${invoice.invoiceStatus}`, STATUS_LABELS[invoice.invoiceStatus] ?? "وضعیت نامشخص"));
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن جزئیات فاکتور");
  close.addEventListener("click", () => dialog.close());
  head.append(heading, close);

  const metadata = element("dl", "invoice-detail-grid");
  [
    ["تاریخ فاکتور", formatBusinessDate(invoice.invoiceDate)], ["فروشنده یا ارائه‌دهنده", invoice.vendorName],
    ["منبع ثبت", SOURCE_LABELS[invoice.source] ?? "نامشخص"], ["تعداد خطوط", formatDisplayNumber(String(invoice.lines.length))],
    ["نسخه سند", formatDisplayNumber(String(invoice.version))], ["شناسه یکتای ثبت", invoice.idempotencyKey],
    ["ثبت‌کننده", invoice.submittedBy], ["زمان ثبت", formatSystemDateTime(invoice.createdAt)],
    ["تأییدکننده", invoice.confirmedBy ?? "تأیید نشده"], ["زمان تأیید", invoice.confirmedAt ? formatSystemDateTime(invoice.confirmedAt) : "تأیید نشده"],
  ].forEach(([label, value]) => {
    const item = element("div", "invoice-detail-grid__item");
    item.append(element("dt", "", label), element("dd", "", value));
    metadata.append(item);
  });
  if (invoice.description) dialog.append(head, metadata, element("p", "inline-notice", invoice.description));
  else dialog.append(head, metadata);
  if (invoice.duplicateWarning) dialog.append(element("div", "invoice-warning", "این سند دارای هشدار شباهت با فاکتور دیگری است."));
  if (invoice.duplicateOverrideReason) dialog.append(element("div", "inline-notice", `دلیل ادامه ثبت: ${invoice.duplicateOverrideReason}`));
  if (invoice.relatedInvoiceId) dialog.append(element("div", "inline-notice numeric", `شناسه سند مرتبط: ${invoice.relatedInvoiceId}`));

  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table invoice-lines-table");
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  ["ردیف", "اتصال مالی", "مقدار و واحد", "قیمت واحد", "مبلغ خط", "توضیح"].forEach((label) => header.append(element("th", "", label)));
  thead.append(header);
  const tbody = document.createElement("tbody");
  invoice.lines.forEach((line, index) => {
    const row = document.createElement("tr");
    row.append(
      element("td", "numeric", formatDisplayNumber(String(index + 1))),
      element("td", "", `${line.targetLabel} · ${line.targetType === "general_cost" ? "هزینه عمومی" : "خط برآورد"}`),
      element("td", "numeric", line.quantity === null ? "بدون مقدار فیزیکی" : `${formatDisplayNumber(line.quantity)} ${formatUnitLabel(line.unit)}`),
      element("td", "numeric", line.unitPriceIRR === null ? "—" : formatTomanFromIRR(line.unitPriceIRR)),
      element("td", "numeric", formatTomanFromIRR(line.lineAmountIRR)),
      element("td", "", line.description || "—"),
    );
    tbody.append(row);
  });
  table.append(thead, tbody);
  wrapper.append(table);

  const totals = element("dl", "invoice-totals");
  [["جمع خام خطوط", invoice.rawLinesTotalIRR], ["تخفیف", invoice.discountIRR], ["مالیات", invoice.taxIRR], ["حمل", invoice.shippingIRR], ["سایر هزینه‌ها", invoice.otherCostsIRR], ["مبلغ نهایی", invoice.finalAmountIRR]].forEach(([label, value]) => totals.append(element("dt", "", label), element("dd", "numeric", formatTomanFromIRR(value))));
  dialog.append(wrapper, totals);
  if (invoice.invoiceStatus === "draft") {
    const actions = element("div", "dialog-actions invoice-detail-actions");
    const submit = element("button", "button button--primary", canEdit ? "ارسال برای تأیید" : "بدون مجوز ویرایش");
    submit.type = "button";
    submit.disabled = !canEdit;
    submit.addEventListener("click", () => onSubmit(invoice, dialog));
    actions.append(submit);
    dialog.append(actions);
  }
  return dialog;
}

function createSubmitDraftDialog({ invoice, adapter, onSaved }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-submit-dialog";
  dialog.setAttribute("aria-labelledby", "invoice-submit-title");
  const title = element("h2", "", "ارسال پیش‌نویس برای تأیید");
  title.id = "invoice-submit-title";
  dialog.append(title, element("p", "", `فاکتور ${invoice.invoiceNumber} با نسخه ${formatDisplayNumber(String(invoice.version))} به وضعیت «در انتظار تأیید» منتقل می‌شود. این عملیات هنوز هزینه واقعی ایجاد نمی‌کند.`));
  const message = element("div", "form-message");
  message.setAttribute("aria-live", "assertive");
  const actions = element("div", "dialog-actions");
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "تأیید ارسال");
  submit.type = "button";
  submit.addEventListener("click", async () => {
    submit.disabled = true;
    cancel.disabled = true;
    submit.textContent = "در حال ارسال…";
    try {
      await adapter.submitDraft({ invoiceId: invoice.invoiceId, expectedVersion: invoice.version });
      dialog.close();
      onSaved();
    } catch (error) {
      message.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
      message.className = "form-message form-message--error";
      submit.disabled = false;
      cancel.disabled = false;
      submit.textContent = "تأیید ارسال";
    }
  });
  actions.append(cancel, submit);
  dialog.append(message, actions);
  return dialog;
}

function renderTable(items, onDetail) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table invoices-table");
  table.append(element("caption", "sr-only", "فهرست فاکتورهای پروژه"));
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  ["شماره", "تاریخ", "فروشنده یا ارائه‌دهنده", "منبع", "وضعیت", "تعداد خطوط", "مبلغ نهایی", "هشدار", "عملیات"].forEach((label) => header.append(element("th", "", label)));
  thead.append(header);
  const tbody = document.createElement("tbody");
  items.forEach((invoice) => {
    const row = document.createElement("tr");
    const action = element("button", "button button--small button--ghost", "مشاهده جزئیات");
    action.type = "button";
    action.addEventListener("click", (event) => onDetail(invoice.invoiceId, event.currentTarget));
    row.append(
      element("td", "", invoice.invoiceNumber), element("td", "", formatBusinessDate(invoice.invoiceDate)),
      element("td", "", invoice.vendorName), element("td", "", SOURCE_LABELS[invoice.source] ?? "نامشخص"),
      element("td", "", ""), element("td", "numeric", formatDisplayNumber(String(invoice.lineCount))),
      element("td", "numeric", formatTomanFromIRR(invoice.finalAmountIRR)),
      element("td", "", invoice.duplicateWarning ? "مشکوک به تکرار" : "ندارد"), element("td", "", ""),
    );
    row.children[4].append(element("span", `invoice-status invoice-status--${invoice.invoiceStatus}`, STATUS_LABELS[invoice.invoiceStatus] ?? "نامشخص"));
    row.children[8].append(action);
    tbody.append(row);
  });
  table.append(thead, tbody);
  wrapper.append(table);
  return wrapper;
}

export function createInvoicesPage({ context, adapter }) {
  const root = element("div", "invoices-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);
  const filters = { query: "", status: "", source: "", page: 1, pageSize: 50 };
  const canCreate = hasPermission(context, "finance.edit");
  const detailMessage = element("div", "form-message invoice-detail-message");
  detailMessage.setAttribute("aria-live", "assertive");

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const data = await adapter.getInvoices(filters);
      state = createRequestState(data.totalItems ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, data);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  async function showDetail(invoiceId, trigger) {
    detailMessage.textContent = "";
    detailMessage.className = "form-message invoice-detail-message";
    trigger.disabled = true;
    const previous = trigger.textContent;
    trigger.textContent = "در حال دریافت…";
    try {
      const invoice = await adapter.getInvoice(invoiceId);
      const dialog = renderDetail(invoice, {
        canEdit: canCreate,
        onSubmit: (draft, detailDialog) => {
          detailDialog.close();
          const confirmation = createSubmitDraftDialog({ invoice: draft, adapter, onSaved: load });
          root.append(confirmation);
          confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
          confirmation.showModal();
        },
      });
      root.append(dialog);
      dialog.addEventListener("close", () => dialog.remove(), { once: true });
      dialog.showModal();
    } catch (error) {
      detailMessage.textContent = `${error.message || "دریافت جزئیات انجام نشد."}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
      detailMessage.className = "form-message form-message--error invoice-detail-message";
    } finally {
      trigger.disabled = false;
      trigger.textContent = previous;
    }
  }

  function renderHeader() {
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "اسناد هزینه پروژه"), element("h1", "", "فاکتورها"), element("p", "", "فاکتورهای پروژه را براساس وضعیت، منبع و مشخصات سند جست‌وجو و جزئیات ثبت‌شده را مشاهده کنید."));
    const actions = element("div", "feature-header__actions");
    const create = element("button", "button button--primary", canCreate ? "ثبت فاکتور دستی" : "بدون مجوز ثبت");
    create.type = "button";
    create.disabled = !canCreate;
    create.addEventListener("click", () => {
      const dialog = createInvoiceWizard({ adapter, onSaved: () => { filters.page = 1; load(); } });
      root.append(dialog);
      dialog.addEventListener("close", () => dialog.remove(), { once: true });
      dialog.showModal();
    });
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.href = "#/finance";
    actions.append(create, back);
    header.append(copy, actions);
    return header;
  }

  function renderFilters() {
    const form = element("form", "invoice-filters");
    const search = element("input", "app-input");
    search.type = "search";
    search.placeholder = "شماره، فروشنده یا توضیح";
    search.value = filters.query;
    search.setAttribute("aria-label", "جست‌وجوی فاکتور");
    const status = element("select", "app-select");
    status.setAttribute("aria-label", "فیلتر وضعیت فاکتور");
    status.append(option("", "همه وضعیت‌ها"), ...Object.entries(STATUS_LABELS).map(([value, label]) => option(value, label)));
    status.value = filters.status;
    const source = element("select", "app-select");
    source.setAttribute("aria-label", "فیلتر منبع فاکتور");
    source.append(option("", "همه منابع"), ...Object.entries(SOURCE_LABELS).map(([value, label]) => option(value, label)));
    source.value = filters.source;
    const submit = element("button", "button button--primary", "اعمال فیلتر");
    submit.type = "submit";
    const reset = element("button", "button button--ghost", "پاک‌کردن");
    reset.type = "button";
    reset.addEventListener("click", () => { Object.assign(filters, { query: "", status: "", source: "", page: 1 }); load(); });
    form.addEventListener("submit", (event) => { event.preventDefault(); Object.assign(filters, { query: search.value, status: status.value, source: source.value, page: 1 }); load(); });
    form.append(search, status, source, submit, reset);
    return form;
  }

  function renderContent(data) {
    const section = element("section", "invoices-section");
    const heading = element("div", "invoice-list-heading");
    heading.append(element("div", "", ""), element("span", "section-count numeric", `${formatDisplayNumber(String(data.totalItems))} فاکتور`));
    heading.firstElementChild.append(element("h2", "", "فهرست فاکتورها"), element("p", "", "مبلغ رسمی ریال است و در این صفحه با واحد پیش‌فرض تومان نمایش داده می‌شود."));
    const table = renderTable(data.items, showDetail);
    const pagination = element("nav", "invoice-pagination");
    pagination.setAttribute("aria-label", "صفحه‌بندی فاکتورها");
    const previous = element("button", "button button--ghost", "صفحه قبل");
    previous.type = "button";
    previous.disabled = data.page <= 1;
    previous.addEventListener("click", () => { filters.page = data.page - 1; load(); });
    const label = element("span", "numeric", `صفحه ${formatDisplayNumber(String(data.page))} از ${formatDisplayNumber(String(data.totalPages))}`);
    const next = element("button", "button button--ghost", "صفحه بعد");
    next.type = "button";
    next.disabled = data.page >= data.totalPages;
    next.addEventListener("click", () => { filters.page = data.page + 1; load(); });
    pagination.append(previous, label, next);
    section.append(heading, detailMessage, table, pagination);
    return section;
  }

  function renderEmpty() {
    const section = element("section", "state-card");
    section.append(element("h2", "", "فاکتوری پیدا نشد"), element("p", "", "برای این پروژه فاکتوری مطابق فیلترهای انتخاب‌شده وجود ندارد."));
    return section;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderFilters(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
