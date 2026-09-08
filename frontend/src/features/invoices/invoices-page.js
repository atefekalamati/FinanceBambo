import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, irrToDisplayValue, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { getDialogOpener, showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { createReportHeader, projectFacts } from "../../shared/reports/report-header.js";
import { validateInvoiceAdjustments, validateInvoiceHeader, validateInvoiceLine } from "./invoices-validation.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { IDENTITY, PRIMARY, SECONDARY, applyColumnVisibility, createColumnControl, createDataTable, defaultVisibleColumns }
  from "../../shared/components/data-table.js";

const STATUS_LABELS = Object.freeze({ draft: "پیش‌نویس", awaitingConfirmation: "در انتظار تأیید", confirmed: "تأییدشده", voided: "باطل‌شده", corrected: "اصلاح‌شده" });
const SOURCE_LABELS = Object.freeze({ manual: "ورود دستی", image: "تصویر", voice: "صدای فارسی", reversal: "سند برگشت", corrective: "سند اصلاحی" });

function getInvoiceEffect(invoice) {
  if (["draft", "awaitingConfirmation"].includes(invoice.invoiceStatus)) {
    return { tone: "pending", label: "بدون اثر فعلی", description: "این سند تا پیش از تأیید نهایی در هزینه واقعی پروژه محاسبه نمی‌شود." };
  }
  if (Number(invoice.financialEffectSign ?? 1) < 0) {
    return { tone: "negative", label: "اثر کاهنده", description: "این سند از هزینه واقعی پروژه کسر می‌شود." };
  }
  return { tone: "positive", label: "اثر افزاینده", description: "این سند در هزینه واقعی پروژه اثر افزاینده دارد." };
}

/* The four ways this list is read, and now the only filter it has. Three of them
   are a status the server already filters on; the fourth has no server filter --
   /invoices takes page, pageSize, query, status, source and a date range, and
   nothing about duplicates -- so that one is picked out of the loaded set. */
const INVOICE_VIEWS = Object.freeze([
  { key: "all", label: "کل فاکتورها", tone: "neutral" },
  { key: "draft", label: "پیش‌نویس", tone: "neutral", status: "draft" },
  { key: "awaiting", label: "در انتظار تأیید", tone: "pending", status: "awaitingConfirmation" },
  { key: "confirmed", label: "تأییدشده", tone: "positive", status: "confirmed" },
  { key: "corrected", label: "اصلاح‌شده", tone: "warning", status: "corrected" },
  { key: "duplicates", label: "نیازمند بررسی تکرار", tone: "warning", duplicates: true },
]);

/* The lines of one invoice, inside its dialog. The row number is the identity --
   it is how a line is referred to when someone asks about one. */
const INVOICE_LINE_COLUMNS = Object.freeze([
  { key: "identity", label: "ردیف", tier: IDENTITY },
  { key: "target", label: "اتصال مالی", tier: PRIMARY },
  { key: "quantity", label: "مقدار و واحد", tier: PRIMARY, cellClass: "numeric" },
  { key: "unitPrice", label: "قیمت واحد", tier: SECONDARY, keepOnTablet: true, cellClass: "numeric" },
  { key: "lineAmount", label: "مبلغ خط", tier: PRIMARY, cellClass: "numeric" },
  { key: "description", label: "توضیح", tier: SECONDARY },
]);

/** The most the list endpoint will return in one page, and so the most this can
 *  count exactly. `totalItems` is the project's real total either way. */
const SUMMARY_PAGE_SIZE = 200;

function countInvoiceViews(items, totalItems) {
  const withStatus = (status) => items.filter((invoice) => invoice.invoiceStatus === status).length;
  return {
    all: totalItems,
    draft: withStatus("draft"),
    awaiting: withStatus("awaitingConfirmation"),
    confirmed: withStatus("confirmed"),
    corrected: withStatus("corrected"),
    duplicates: items.filter((invoice) => invoice.duplicateWarning).length,
  };
}

function renderInvoiceListSummary(counts, activeKey, onSelect) {
  const section = element("section", "invoice-list-summary");
  section.setAttribute("aria-label", "فیلتر فاکتورها بر اساس وضعیت");
  INVOICE_VIEWS.forEach((view) => {
    const item = element("button", `invoice-summary-item invoice-summary-item--${view.tone}`);
    item.type = "button";
    item.dataset.view = view.key;
    const active = view.key === activeKey;
    item.setAttribute("aria-pressed", String(active));
    item.append(
      element("span", "invoice-summary-item__label", view.label),
      element("strong", "invoice-summary-item__value numeric", formatDisplayNumber(String(counts[view.key] ?? 0))),
    );
    item.addEventListener("click", () => onSelect(view.key));
    section.append(item);
  });
  return section;
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

function createInvoiceWizard({ adapter, onSaved, mode = "manual", originalInvoice = null }) {
  const isCorrective = mode === "corrective";
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-wizard";
  dialog.setAttribute("aria-labelledby", "invoice-wizard-title");
  const head = element("header", "invoice-detail-dialog__head");
  const heading = element("div");
  const title = element("h2", "", isCorrective ? "ثبت سند اصلاحی مرتبط" : "ثبت فاکتور دستی");
  title.id = "invoice-wizard-title";
  heading.append(title, element("p", "invoice-wizard__subtitle", isCorrective ? `سند اصلاحی به فاکتور ${originalInvoice.invoiceNumber} متصل و مستقل ثبت می‌شود.` : "پیش‌نویس تا قبل از تأیید، اثر مالی ندارد."));
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
  let correctionReason = "";
  let financialEffectSign = -1;
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
    number.input.value = headerData?.invoiceNumber ?? (isCorrective ? `${originalInvoice.invoiceNumber}-اصلاح` : "");
    const vendor = inputField("فروشنده یا ارائه‌دهنده", "vendorName");
    vendor.input.value = headerData?.vendorName ?? (isCorrective ? originalInvoice.vendorName : "");
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
    targetField.append(element("span", "form-label", "اتصال به ردیف برآورد یا هزینه‌های عمومی پروژه"));
    const targetSelect = element("select", "app-select");
    targetSelect.append(option("", "انتخاب کنید"), ...targets.map((target) => option(target.targetId, `${target.label} · ${target.targetType === "general_cost" ? "هزینه‌های عمومی پروژه" : formatUnitLabel(target.unit)}`)));
    targetField.append(targetSelect);
    const quantity = inputField("مقدار", "quantity", { inputMode: "decimal" });
    const unitPrice = inputField(`قیمت واحد به ${getDisplayCurrencyLabel()}`, "unitPriceIRR", { inputMode: "decimal" });
    const amount = inputField(`مبلغ هزینه عمومی پروژه به ${getDisplayCurrencyLabel()}`, "amountIRR", { inputMode: "decimal" });
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
      const validation = validateInvoiceLine({ quantity: quantity.input.value, unitPriceIRR: tomanInputToIrr(unitPrice.input.value), amountIRR: tomanInputToIrr(amount.input.value), description: lineDescription.input.value }, target);
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
      card.append(element("strong", "", `${formatDisplayNumber(String(index + 1))}. ${line.targetLabel}`), element("span", "numeric", line.targetType === "general_cost" ? formatTomanFromIrr(line.lineAmountIRR) : `${formatDisplayNumber(line.quantity)} ${formatUnitLabel(line.unit)} × ${formatTomanFromIrr(line.unitPriceIRR)}`));
      const remove = element("button", "button button--ghost", "حذف خط");
      remove.type = "button";
      remove.addEventListener("click", () => { lines.splice(index, 1); paintStep(); });
      card.append(remove);
      list.append(card);
    });
    const adjustmentGrid = element("div", "invoice-adjustments");
    const adjustmentFields = [[`تخفیف به ${getDisplayCurrencyLabel()}`, "discountIRR"], [`مالیات به ${getDisplayCurrencyLabel()}`, "taxIRR"], [`حمل به ${getDisplayCurrencyLabel()}`, "shippingIRR"], [`سایر هزینه‌ها به ${getDisplayCurrencyLabel()}`, "otherCostsIRR"]].map(([label, key]) => {
      const field = inputField(label, key, { inputMode: "numeric" });
      field.input.value = irrToDisplayValue(adjustments[key]) ?? "0";
      adjustmentGrid.append(field.field);
      return [key, field.input];
    });
    section.append(editor, list, adjustmentGrid, actions({ back: true, nextLabel: "مشاهده پیش‌نمایش", onNext: async (button) => {
      if (!lines.length) { showMessage("حداقل یک خط فاکتور اضافه کنید.", true); return; }
      const validation = validateInvoiceAdjustments(Object.fromEntries(adjustmentFields.map(([key, input]) => [key, tomanInputToIrr(input.value)])));
      if (!validation.valid) { showMessage(Object.values(validation.errors).join(" "), true); return; }
      adjustments = validation.values;
      button.disabled = true;
      button.textContent = "در حال محاسبه…";
      try { preview = await adapter.previewDraft({ header: headerData, lines, adjustments }); currentStep = 3; paintStep(); }
      catch (error) { showMessage(formatApiErrorMessage(error), true); button.disabled = false; button.textContent = "مشاهده پیش‌نمایش"; }
    } }));
    return section;
  }

  function renderPreviewStep() {
    const section = element("div", "invoice-preview");
    const summary = element("dl", "invoice-detail-grid");
    [["شماره", headerData.invoiceNumber], ["تاریخ", formatBusinessDate(headerData.invoiceDate)], ["فروشنده", headerData.vendorName], ["منبع", "ورود دستی"]].forEach(([label, value]) => { const item = element("div", "invoice-detail-grid__item"); item.append(element("dt", "", label), element("dd", "", value)); summary.append(item); });
    const lineList = element("div", "invoice-draft-lines");
    preview.lines.forEach((line, index) => { const card = element("article", "invoice-draft-line"); card.append(element("strong", "", `${formatDisplayNumber(String(index + 1))}. ${line.targetLabel}`), element("span", "numeric", formatTomanFromIrr(line.lineAmountIRR))); lineList.append(card); });
    const totals = element("dl", "invoice-totals");
    [["جمع خام خطوط", preview.rawLinesTotalIRR], ["تخفیف", preview.discountIRR], ["مالیات", preview.taxIRR], ["حمل", preview.shippingIRR], ["سایر هزینه‌ها", preview.otherCostsIRR], ["مبلغ نهایی", preview.finalAmountIRR]].forEach(([label, value]) => totals.append(element("dt", "", label), element("dd", "numeric", formatTomanFromIrr(value))));
    section.append(element("div", "inline-notice", isCorrective ? "این سند پس از ثبت، با اثر مالی انتخاب‌شده و ارتباط صریح با فاکتور اصلی اعمال می‌شود؛ فاکتور اصلی تغییر نمی‌کند." : "با ثبت این مرحله فقط پیش‌نویس ساخته می‌شود و هزینه واقعی پروژه تغییر نمی‌کند."), summary, lineList, totals);
    let correctionReasonInput = null;
    let effectSelect = null;
    if (isCorrective) {
      const correction = element("section", "invoice-correction-fields");
      const effectField = element("label", "form-field");
      effectField.append(element("span", "form-label", "جهت اثر مالی"));
      effectSelect = element("select", "app-select");
      [["-1", "کاهنده هزینه واقعی"], ["1", "افزاینده هزینه واقعی"]].forEach(([value, label]) => effectSelect.append(option(value, label)));
      effectSelect.value = String(financialEffectSign);
      effectField.append(effectSelect);
      const reasonField = element("label", "form-field");
      reasonField.append(element("span", "form-label", "دلیل اصلاح فاکتور"));
      correctionReasonInput = element("textarea", "app-textarea");
      correctionReasonInput.rows = 3;
      correctionReasonInput.maxLength = 500;
      correctionReasonInput.value = correctionReason;
      reasonField.append(correctionReasonInput);
      correction.append(effectField, reasonField);
      section.append(correction);
    }
    let reasonInput = null;
    if (preview.duplicateMatches.length) {
      const warning = element("section", "invoice-duplicate-warning");
      warning.setAttribute("role", "alert");
      warning.append(element("h3", "", "فاکتور مشابه پیدا شد"), element("p", "", "ادامه ثبت مجاز است، اما باید سند مشابه را بررسی و دلیل ادامه را ثبت کنید."));
      const matches = element("ul", "invoice-duplicate-matches");
      preview.duplicateMatches.forEach((match) => matches.append(element("li", "", `${match.invoiceNumber} · ${match.vendorName} · ${formatBusinessDate(match.invoiceDate)} · ${formatTomanFromIrr(match.finalAmountIRR)} · ${STATUS_LABELS[match.invoiceStatus]}`)));
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
    section.append(actions({ back: true, nextLabel: isCorrective ? "ثبت سند اصلاحی" : "ثبت پیش‌نویس", onNext: async (button) => {
      duplicateOverrideReason = reasonInput?.value.trim() ?? "";
      if (preview.duplicateMatches.length && duplicateOverrideReason.length < 3) { showMessage("دلیل ادامه با وجود فاکتور مشابه باید حداقل سه نویسه داشته باشد.", true); reasonInput.focus(); return; }
      if (isCorrective) {
        correctionReason = correctionReasonInput.value.trim();
        financialEffectSign = Number(effectSelect.value);
        if (correctionReason.length < 3) { showMessage("دلیل اصلاح باید حداقل سه نویسه داشته باشد.", true); correctionReasonInput.focus(); return; }
      }
      button.disabled = true;
      button.textContent = "در حال ثبت…";
      try {
        if (isCorrective) await adapter.createCorrective({ originalInvoiceId: originalInvoice.invoiceId, header: headerData, lines, adjustments, financialEffectSign, reason: correctionReason, idempotencyKey });
        else await adapter.createDraft({ header: headerData, lines, adjustments, duplicateOverrideReason, idempotencyKey });
        dialog.close();
        onSaved();
      }
      catch (error) { showMessage(formatApiErrorMessage(error), true); button.disabled = false; button.textContent = isCorrective ? "ثبت سند اصلاحی" : "ثبت پیش‌نویس"; }
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

function renderDetail(invoice, { canEdit, currentUserId, project, onSubmit, onConfirm, onVoid, onCorrective }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-detail-dialog";
  dialog.setAttribute("aria-labelledby", "invoice-detail-title");
  // On screen this is a dialog. Printed, it is a document leaving the company,
  // so it goes out under the same band as every other one.
  const letterhead = createReportHeader({
    title: `فاکتور ${invoice.invoiceNumber ?? ""}`.trim(),
    facts: projectFacts({ project, reportingDate: invoice.invoiceDate }),
  });
  letterhead.classList.add("report-header--print-only");
  dialog.append(letterhead);
  // Two rows, one rule between them: the title against the way out, then the
  // status against the way to paper. Both rows carry the same class, so what
  // governs the spacing of one governs the other.
  const head = element("header", "invoice-detail-dialog__head");
  const titleRow = element("div", "invoice-detail-dialog__head-row");
  const title = element("h2", "", `جزئیات فاکتور ${invoice.invoiceNumber}`);
  title.id = "invoice-detail-title";
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن جزئیات فاکتور");
  close.addEventListener("click", () => dialog.close());
  titleRow.append(title, close);
  const metaRow = element("div", "invoice-detail-dialog__head-row");
  const print = element("button", "button button--ghost invoice-print-button", "چاپ فاکتور");
  print.type = "button";
  print.addEventListener("click", () => window.print());
  metaRow.append(element("span", `invoice-status invoice-status--${invoice.invoiceStatus}`, STATUS_LABELS[invoice.invoiceStatus] ?? "وضعیت نامشخص"), print);
  head.append(titleRow, metaRow);

  const metadata = element("dl", "invoice-detail-grid");
  [
    ["تاریخ فاکتور", formatBusinessDate(invoice.invoiceDate)], ["فروشنده یا ارائه‌دهنده", invoice.vendorName],
    ["منبع ثبت", SOURCE_LABELS[invoice.source] ?? "نامشخص"], ["تعداد خطوط", formatDisplayNumber(String(invoice.lines.length))],
    ["نسخه سند", formatDisplayNumber(String(invoice.version))], ["شناسه یکتای ثبت", invoice.idempotencyKey],
    ["ثبت‌کننده", invoice.submittedBy], ["زمان ثبت", formatSystemDateTime(invoice.createdAt)],
    ["تأییدکننده", invoice.confirmedBy ?? "تأیید نشده"], ["زمان تأیید", invoice.confirmedAt ? formatSystemDateTime(invoice.confirmedAt) : "تأیید نشده"],
  ].forEach(([label, value], index) => {
    const printSecondary = [5, 6, 7].includes(index) ? " invoice-detail-grid__item--print-secondary" : "";
    const item = element("div", `invoice-detail-grid__item${printSecondary}`);
    item.append(element("dt", "", label), element("dd", "", value));
    metadata.append(item);
  });
  const effect = getInvoiceEffect(invoice);
  const effectNotice = element("section", `invoice-effect-notice invoice-effect-notice--${effect.tone}`);
  effectNotice.append(element("strong", "", effect.label), element("span", "", effect.description));
  if (invoice.description) dialog.append(head, metadata, element("p", "inline-notice", invoice.description));
  else dialog.append(head, metadata);
  dialog.append(effectNotice);
  if (invoice.duplicateWarning) dialog.append(element("div", "invoice-warning", "این سند دارای هشدار شباهت با فاکتور دیگری است."));
  if (invoice.duplicateOverrideReason) dialog.append(element("div", "inline-notice", `دلیل ادامه ثبت: ${invoice.duplicateOverrideReason}`));
  if (invoice.relatedInvoiceId) dialog.append(element("div", "inline-notice numeric", `شناسه سند مرتبط: ${invoice.relatedInvoiceId}`));
  if (invoice.originalInvoiceId) dialog.append(element("div", "inline-notice numeric", `فاکتور اصلی: ${invoice.originalInvoiceId} · اثر مالی: ${invoice.financialEffectSign === -1 ? "کاهنده" : "افزاینده"}`));
  if (invoice.correctionReason) dialog.append(element("div", "inline-notice", `دلیل اصلاح: ${invoice.correctionReason}`));

  const linesTable = createDataTable({
    className: "invoice-lines-table",
    caption: "ریز خطوط فاکتور انتخاب‌شده",
    scrollLabel: "جدول ریز خطوط فاکتور",
    columns: INVOICE_LINE_COLUMNS,
    rows: invoice.lines,
    visible: defaultVisibleColumns(INVOICE_LINE_COLUMNS),
    cells: (line) => ({
      identity: formatDisplayNumber(String(invoice.lines.indexOf(line) + 1)),
      target: `${line.targetLabel} · ${line.targetType === "general_cost" ? "هزینه‌های عمومی پروژه" : "ردیف برآورد"}`,
      quantity: line.quantity === null ? "بدون مقدار فیزیکی" : `${formatDisplayNumber(line.quantity)} ${formatUnitLabel(line.unit)}`,
      unitPrice: line.unitPriceIRR === null ? "—" : formatTomanFromIrr(line.unitPriceIRR),
      lineAmount: formatTomanFromIrr(line.lineAmountIRR),
      description: line.description || "—",
    }),
  });

  const totals = element("dl", "invoice-totals");
  [["جمع خام خطوط", invoice.rawLinesTotalIRR], ["تخفیف", invoice.discountIRR], ["مالیات", invoice.taxIRR], ["حمل", invoice.shippingIRR], ["سایر هزینه‌ها", invoice.otherCostsIRR], ["مبلغ نهایی", invoice.finalAmountIRR]].forEach(([label, value]) => totals.append(element("dt", "", label), element("dd", "numeric", formatTomanFromIrr(value))));
  dialog.append(linesTable, totals);
  // The detail dialog is a record anyone who can read the invoice may open.
  // What it offers to do with it is another matter.
  if (canEdit && invoice.invoiceStatus === "draft") {
    const actions = element("div", "dialog-actions invoice-detail-actions");
    const submit = element("button", "button button--primary", "ارسال برای تأیید");
    submit.type = "button";
    submit.addEventListener("click", () => onSubmit(invoice, dialog));
    actions.append(submit);
    dialog.append(actions);
  }
  if (canEdit && invoice.invoiceStatus === "awaitingConfirmation") {
    const isSubmitter = invoice.submittedBy === currentUserId;
    const actions = element("div", "dialog-actions invoice-detail-actions");
    // Being unable to confirm your own submission is a rule about this
    // invoice, not about this account, so that one stays visible and disabled:
    // the label is the explanation.
    const confirm = element("button", "button button--primary", isSubmitter ? "تأیید نهایی فاکتور" : "فقط ثبت‌کننده مجاز است");
    confirm.type = "button";
    confirm.disabled = !isSubmitter;
    confirm.addEventListener("click", () => onConfirm(invoice, dialog));
    actions.append(confirm);
    dialog.append(actions);
  }
  if (canEdit && invoice.invoiceStatus === "confirmed") {
    const actions = element("div", "dialog-actions invoice-detail-actions");
    const corrective = element("button", "button button--ghost", "ثبت سند اصلاحی");
    corrective.type = "button";
    corrective.addEventListener("click", () => onCorrective(invoice, dialog));
    const voidButton = element("button", "button button--danger", "ابطال با سند برگشت");
    voidButton.type = "button";
    voidButton.addEventListener("click", () => onVoid(invoice, dialog));
    actions.append(corrective, voidButton);
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
      message.textContent = formatApiErrorMessage(error);
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

function createConfirmInvoiceDialog({ invoice, adapter, onSaved }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-confirm-dialog";
  dialog.setAttribute("aria-labelledby", "invoice-confirm-title");
  const title = element("h2", "", "تأیید نهایی فاکتور");
  title.id = "invoice-confirm-title";
  const warning = element("div", "invoice-warning", "پس از تأیید، فاکتور در هزینه واقعی پروژه اثر می‌گذارد و دیگر قابل ویرایش یا حذف مستقیم نیست. اصلاح فقط با سند ابطال، برگشت یا اصلاحی مرتبط انجام می‌شود.");
  const summary = element("dl", "invoice-confirm-summary");
  [["شماره فاکتور", invoice.invoiceNumber], ["فروشنده", invoice.vendorName], ["مبلغ نهایی", formatTomanFromIrr(invoice.finalAmountIRR)], ["نسخه مورد تأیید", formatDisplayNumber(String(invoice.version))]].forEach(([label, value]) => summary.append(element("dt", "", label), element("dd", "", value)));
  const message = element("div", "form-message");
  message.setAttribute("aria-live", "assertive");
  const actions = element("div", "dialog-actions");
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const confirm = element("button", "button button--primary", "تأیید و قفل فاکتور");
  confirm.type = "button";
  const idempotencyKey = crypto.randomUUID();
  confirm.addEventListener("click", async () => {
    confirm.disabled = true;
    cancel.disabled = true;
    confirm.textContent = "در حال تأیید…";
    try {
      await adapter.confirmInvoice({ invoiceId: invoice.invoiceId, expectedVersion: invoice.version, idempotencyKey });
      dialog.close();
      onSaved();
    } catch (error) {
      message.textContent = formatApiErrorMessage(error);
      message.className = "form-message form-message--error";
      confirm.disabled = false;
      cancel.disabled = false;
      confirm.textContent = "تأیید و قفل فاکتور";
    }
  });
  actions.append(cancel, confirm);
  dialog.append(title, warning, summary, message, actions);
  return dialog;
}

function createVoidInvoiceDialog({ invoice, adapter, onSaved }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-confirm-dialog";
  dialog.setAttribute("aria-labelledby", "invoice-void-title");
  const title = element("h2", "", "ابطال فاکتور با سند برگشت");
  title.id = "invoice-void-title";
  const warning = element("div", "invoice-warning", "فاکتور اصلی حذف یا ویرایش نمی‌شود. یک سند برگشت مرتبط با اثر مالی منفی ایجاد خواهد شد.");
  const reasonField = element("label", "form-field");
  reasonField.append(element("span", "form-label", "دلیل ابطال فاکتور"));
  const reason = element("textarea", "app-textarea");
  reason.rows = 4;
  reason.maxLength = 500;
  reasonField.append(reason);
  const message = element("div", "form-message");
  message.setAttribute("aria-live", "assertive");
  const actions = element("div", "dialog-actions");
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--danger", "ایجاد سند برگشت");
  submit.type = "button";
  const idempotencyKey = crypto.randomUUID();
  submit.addEventListener("click", async () => {
    const auditedReason = reason.value.trim();
    if (auditedReason.length < 3) { message.textContent = "دلیل ابطال باید حداقل سه نویسه داشته باشد."; message.className = "form-message form-message--error"; reason.focus(); return; }
    submit.disabled = true;
    cancel.disabled = true;
    submit.textContent = "در حال ثبت…";
    try { await adapter.voidInvoice({ invoiceId: invoice.invoiceId, expectedVersion: invoice.version, idempotencyKey, reason: auditedReason }); dialog.close(); onSaved(); }
    catch (error) { message.textContent = formatApiErrorMessage(error); message.className = "form-message form-message--error"; submit.disabled = false; cancel.disabled = false; submit.textContent = "ایجاد سند برگشت"; }
  });
  actions.append(cancel, submit);
  dialog.append(title, warning, reasonField, message, actions);
  return dialog;
}

/* The columns this list has always shown, in the order it has always shown them.
   `tier` decides nothing on a wide screen -- it only picks what a narrow one
   starts with. Every column stays reachable from the column control and every
   value stays in the detail dialog, so nothing is lost to a small viewport. */
const INVOICE_COLUMNS = Object.freeze([
  { key: "identity", label: "شماره", tier: IDENTITY },
  // Kept on a tablet though it is secondary: a date is how these are told apart
  // once there are more of them than a screen holds.
  { key: "date", label: "تاریخ", tier: SECONDARY, keepOnTablet: true },
  { key: "vendor", label: "فروشنده یا ارائه‌دهنده", tier: PRIMARY },
  { key: "source", label: "منبع", tier: SECONDARY },
  { key: "status", label: "وضعیت", tier: PRIMARY },
  { key: "lineCount", label: "تعداد ردیف", tier: SECONDARY, cellClass: "numeric" },
  { key: "amount", label: "مبلغ نهایی", tier: PRIMARY, cellClass: "numeric" },
]);

function renderTable(items, onDetail, visible) {
  return createDataTable({
    className: "invoices-table",
    caption: "فهرست فاکتورهای پروژه",
    scrollLabel: "جدول فاکتورها",
    columns: INVOICE_COLUMNS,
    rows: items,
    visible,
    cells: (invoice) => {
      const identity = element("div", "data-table-identity");
      identity.append(element("strong", "", invoice.invoiceNumber));
      // The same control as before, in the cell that carries the number rather
      // than in a column of its own: the two travel together, so the way into an
      // invoice is still on screen when the table is scrolled sideways.
      const action = element("button", "button button--small button--ghost invoice-detail-button", "جزئیات");
      action.type = "button";
      action.setAttribute("aria-label", `جزئیات فاکتور ${invoice.invoiceNumber}`);
      action.addEventListener("click", (event) => onDetail(invoice.invoiceId, event.currentTarget));
      identity.append(action);
      // The duplicate flag is the cell's, not the identity row's: a third thing
      // inside that row would share the width the number and the button need.
      const cell = document.createDocumentFragment();
      cell.append(identity);
      if (invoice.duplicateWarning) cell.append(element("span", "invoice-table-warning", "نیازمند بررسی تکرار"));
      return {
        identity: cell,
        date: formatBusinessDate(invoice.invoiceDate),
        vendor: invoice.vendorName,
        source: SOURCE_LABELS[invoice.source] ?? "نامشخص",
        status: element("span", `invoice-status invoice-status--${invoice.invoiceStatus}`, STATUS_LABELS[invoice.invoiceStatus] ?? "نامشخص"),
        lineCount: formatDisplayNumber(String(invoice.lineCount)),
        amount: formatTomanFromIrr(invoice.finalAmountIRR),
      };
    },
  });
}

export function createInvoicesPage({ context, adapter }) {
  const root = element("div", "invoices-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);
  const filters = { status: "", page: 1, pageSize: 50 };
  // Which chip is pressed, and the counts behind all four. The counts describe
  // the project, not the current view, so they are read once per data change and
  // left alone while the reader moves between chips.
  let activeView = "all";
  let summary = null;
  // Lives with the page, not with a render: paint() replaces the whole tree on
  // every load, so a choice held inside a render would last until the next filter.
  const visibleColumns = defaultVisibleColumns(INVOICE_COLUMNS);
  const canCreate = capabilitiesFor(context).writeFinance;
  const detailMessage = element("div", "form-message invoice-detail-message");
  detailMessage.setAttribute("aria-live", "assertive");

  async function load({ refreshCounts = false } = {}) {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      if (refreshCounts || summary === null) {
        const everything = await adapter.getInvoices({ status: "", page: 1, pageSize: SUMMARY_PAGE_SIZE });
        summary = {
          items: everything.items,
          counts: countInvoiceViews(everything.items, everything.totalItems),
          capped: everything.totalItems > everything.items.length,
        };
      }
      // The duplicate view is assembled here rather than asked for, because the
      // endpoint cannot answer it. One page, because the set it draws from is one
      // page -- pagination that promised more would be promising the untrue.
      const view = INVOICE_VIEWS.find((entry) => entry.key === activeView);
      let data;
      if (view?.duplicates) {
        const flagged = summary.items.filter((invoice) => invoice.duplicateWarning);
        data = { items: flagged, page: 1, pageSize: Math.max(flagged.length, 1), totalItems: flagged.length, totalPages: 1 };
      } else {
        data = await adapter.getInvoices(filters);
      }
      state = createRequestState(data.totalItems ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, data);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function selectView(key) {
    if (key === activeView) return;
    activeView = key;
    const view = INVOICE_VIEWS.find((entry) => entry.key === key);
    filters.status = view?.status ?? "";
    filters.page = 1;
    load();
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
        project: { name: context.projectName, code: context.projectCode },
        currentUserId: context.userId,
        onSubmit: (draft, detailDialog) => {
          const opener = getDialogOpener(detailDialog);
          detailDialog.close();
          const confirmation = createSubmitDraftDialog({ invoice: draft, adapter, onSaved: load });
          root.append(confirmation);
          confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
          showAccessibleDialog(confirmation, { opener });
        },
        onConfirm: (awaitingInvoice, detailDialog) => {
          const opener = getDialogOpener(detailDialog);
          detailDialog.close();
          const confirmation = createConfirmInvoiceDialog({ invoice: awaitingInvoice, adapter, onSaved: load });
          root.append(confirmation);
          confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
          showAccessibleDialog(confirmation, { opener });
        },
        onVoid: (confirmedInvoice, detailDialog) => {
          const opener = getDialogOpener(detailDialog);
          detailDialog.close();
          const voidDialog = createVoidInvoiceDialog({ invoice: confirmedInvoice, adapter, onSaved: load });
          root.append(voidDialog);
          voidDialog.addEventListener("close", () => voidDialog.remove(), { once: true });
          showAccessibleDialog(voidDialog, { opener });
        },
        onCorrective: (confirmedInvoice, detailDialog) => {
          const opener = getDialogOpener(detailDialog);
          detailDialog.close();
          const correctiveDialog = createInvoiceWizard({ adapter, onSaved: () => load({ refreshCounts: true }), mode: "corrective", originalInvoice: confirmedInvoice });
          root.append(correctiveDialog);
          correctiveDialog.addEventListener("close", () => correctiveDialog.remove(), { once: true });
          showAccessibleDialog(correctiveDialog, { opener });
        },
      });
      root.append(dialog);
      dialog.addEventListener("close", () => dialog.remove(), { once: true });
      showAccessibleDialog(dialog);
    } catch (error) {
      detailMessage.textContent = formatApiErrorMessage(error, "دریافت جزئیات انجام نشد.");
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
    const navigation = element("div", "feature-header__navigation");
    const actions = element("div", "feature-header__actions feature-header__other-actions");
    if (canCreate) {
      const create = element("button", "button button--primary", "ثبت فاکتور دستی");
      create.type = "button";
      create.addEventListener("click", () => {
        const dialog = createInvoiceWizard({ adapter, onSaved: () => { filters.page = 1; load({ refreshCounts: true }); } });
        root.append(dialog);
        dialog.addEventListener("close", () => dialog.remove(), { once: true });
        showAccessibleDialog(dialog);
      });
      // Reading an invoice happens on گزارش مالی; producing one from a file is
      // work, and the page that does it is on امور مالی. Only an account that
      // can do that work is sent there.
      const upload = element("a", "button button--ghost", "ورود از تصویر یا صدا");
      upload.href = "#/invoice-files";
      actions.append(create, upload);
    }
    const back = element("a", "button button--ghost", `بازگشت به ${SURFACE_LABELS[SURFACES.REPORT]}`);
    back.classList.add("finance-back-link");
    back.href = `#${homeRouteFor(SURFACES.REPORT)?.path ?? "/finance-report"}`;
    navigation.append(actions, back);
    header.append(copy, navigation);
    return header;
  }

  /* Only the body goes through the state switch. The heading -- and with it the
     chips, which are the only filter this page has -- is rendered either way,
     because a filter that empties the list must not leave with it. */
  function renderListBody(data) {
    const body = element("div", "invoices-list-body");
    const table = renderTable(data.items, showDetail, visibleColumns);
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
    body.append(table, pagination);
    return body;
  }

  function renderSection() {
    const section = element("section", "invoices-section");
    const heading = element("div", "invoice-list-heading");
    const title = element("div", "");
    title.append(element("h2", "", "فهرست فاکتورها"), element("p", "", `تمام مبالغ این صفحه برای کاربر به ${getDisplayCurrencyLabel()} نمایش داده می‌شوند.`));
    const meta = element("div", "invoice-list-heading__meta");
    meta.append(
      renderInvoiceListSummary(summary.counts, activeView, selectView),
      createColumnControl({
        name: "invoices",
        columns: INVOICE_COLUMNS,
        visible: visibleColumns,
        onToggle: (key, on) => {
          if (on) visibleColumns.add(key);
          else visibleColumns.delete(key);
          applyColumnVisibility(root.querySelector(".invoices-table"), key, on);
        },
      }),
    );
    heading.append(title, meta);
    section.append(heading, detailMessage, renderPageState(state, { renderContent: renderListBody, renderEmpty, onRetry: load }));
    return section;
  }

  function renderEmpty() {
    const section = element("section", "state-card");
    section.append(element("h2", "", "فاکتوری پیدا نشد"), element("p", "", "برای این پروژه فاکتوری مطابق فیلترهای انتخاب‌شده وجود ندارد."));
    return section;
  }

  function paint() {
    // Before the first read there are no counts to show, so there is no heading
    // to show them in -- the loading or error card is the whole page, as it was.
    root.replaceChildren(renderHeader(), summary
      ? renderSection()
      : renderPageState(state, { renderContent: renderListBody, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
