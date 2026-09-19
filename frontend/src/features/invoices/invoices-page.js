import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel, toPersianCode } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, irrToDisplayValue, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { getDialogOpener, showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { getRowsPerPage } from "../../shared/preferences/rows-per-page.js";
import { createPermissionNotice } from "../../shared/components/permission-notice.js";
import { createReportHeader, projectFacts } from "../../shared/reports/report-header.js";
import { AMOUNT_MODES, amountModesFor, statesTotal, validateInvoiceAdjustments, validateInvoiceHeader, validateInvoiceLine } from "./invoices-validation.js";
import { GENERAL_COST_STAGE, UNSTAGED, buildStageIndex, targetsInStage } from "./invoice-stages.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { actorLabel } from "../../shared/formatters/actor.js";
import { IDENTITY, PRIMARY, SECONDARY, createDataTable, createTablePagination, createTableToolbar, defaultVisibleColumns, repaintPreservingFocus, updateFilterChips }
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
]);

/**
 * The one move a row is waiting for, named by what it does next rather than by
 * the status it is in. «در انتظار تأیید» tells a reader where the document sits;
 * «ثبت نهایی» tells them what pressing this will do.
 *
 * Only two statuses have a next move. A confirmed, voided or corrected invoice
 * is not waiting on anybody, and its remaining operations -- ابطال and سند
 * اصلاحی -- are deliberately not here: they create a second document and are
 * worth the trip through جزئیات, where what they will do is written out.
 */
const NEXT_STEP = Object.freeze({
  draft: Object.freeze({ label: "تایید اولیه", act: "submit", name: (number) => `ارسال فاکتور ${number} برای تأیید` }),
  awaitingConfirmation: Object.freeze({ label: "ثبت نهایی", act: "confirm", name: (number) => `ثبت نهایی فاکتور ${number}` }),
});

/** The eye the host draws for a preview: 24-grid, stroked, no fill. */
function previewIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("fill", "none");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z", "M12 9.2A2.8 2.8 0 1 0 12 14.8 2.8 2.8 0 0 0 12 9.2Z"].forEach((d) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    icon.append(path);
  });
  return icon;
}

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
 *  count exactly. `totalItems` is the project's real total either way.
 *
 *  It is also what «همه» resolves to in the footer below. The register has no
 *  ceiling -- one row per purchase for the life of a project -- so unlike every
 *  other table here, "all of it" is not something a page can ask for. The
 *  footer's own count then reads «۲۰۰ از ۳۰۰۰ سطر», which is the honest
 *  answer. */
const SUMMARY_PAGE_SIZE = 200;

function countInvoiceViews(items, totalItems) {
  const withStatus = (status) => items.filter((invoice) => invoice.invoiceStatus === status).length;
  return {
    all: totalItems,
    draft: withStatus("draft"),
    awaiting: withStatus("awaitingConfirmation"),
    confirmed: withStatus("confirmed"),
    corrected: withStatus("corrected"),
  };
}

/** The counts, written the way the rest of the page writes numbers. */
function invoiceChipCounts(counts) {
  return Object.fromEntries(INVOICE_VIEWS.map((view) => [
    view.key,
    formatDisplayNumber(String(counts?.[view.key] ?? 0)),
  ]));
}

function option(value, label) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

/**
 * How one stage reads in the picker.
 *
 * The count is part of the label because it is what makes the menu navigable: somebody
 * looking for a delivery of rebar wants to know which stage holds forty rows and which
 * holds two before they open either one.
 */
function stageOptionLabel(stage) {
  const count = `${formatDisplayNumber(String(stage.count))} ردیف`;
  if (stage.value === GENERAL_COST_STAGE) return `هزینه‌های عمومی پروژه · ${count}`;
  if (stage.value === UNSTAGED) return `بدون مرحله در فایل زمان‌بندی · ${count}`;
  const number = toPersianCode(stage.value);
  return `${stage.title ? `${number} · ${stage.title}` : `مرحله ${number}`} · ${count}`;
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

/**
 * A saved invoice's lines, in the shape the wizard edits.
 *
 * MATCHED BY IDENTIFIER, NEVER BY LABEL. A line knows which estimate line or which
 * general-cost item it was raised against; the label is built from whatever that item is
 * called today. Matching on the words would re-point a line at a different cost item the
 * first time somebody renames one, and the invoice would move money without anybody
 * touching it.
 *
 * The RAW amount is what goes back in the box. `lineAmountIRR` is the line after the
 * header's discount and tax were distributed across it — putting that in the form would
 * fold this invoice's tax into the typed figure, and fold it in again on the next save.
 *
 * A line whose target no longer exists is dropped rather than guessed at, and the caller
 * is left to notice the count changed: silently pointing it somewhere plausible is how an
 * edit rewrites what an invoice was for.
 */
export function editableLines(invoice, targets) {
  return (invoice.lines ?? []).map((line) => {
    /* An identifier that is ABSENT matches nothing. Comparing two undefined values is true,
       and a line that states no resource would otherwise bind to whichever general-cost
       item happened to be first -- an edit silently re-pointing money at something nobody
       chose. Better to drop the line and have somebody notice it missing. */
    const target = line.estimateLineId
      ? targets.find((item) => item.estimateLineId === line.estimateLineId)
      : (line.resourceId
        ? targets.find((item) => item.targetType === "general_cost" && item.resourceId === line.resourceId)
        : null);
    if (!target) return null;
    /* A SAVED line already says which shape it was billed in: a quantity, or no quantity.
       Reading the target's type instead would reopen an estimate line billed as one figure
       with empty quantity boxes and the amount thrown away -- the edit silently changing
       what the invoice said. */
    const total = line.quantity === null || line.quantity === undefined;
    return {
      targetId: target.targetId,
      targetType: target.targetType,
      targetLabel: target.label,
      quantity: total ? null : line.quantity,
      unit: total ? null : (line.unit ?? target.unit ?? null),
      unitPriceIRR: total ? null : line.unitPriceIRR,
      lineAmountIRR: total ? (line.rawAmountIRR ?? line.lineAmountIRR) : "",
      description: line.description ?? "",
    };
  }).filter(Boolean);
}

function createInvoiceWizard({ adapter, onSaved, mode = "manual", originalInvoice = null }) {
  const isCorrective = mode === "corrective";
  /* Editing an invoice that is not yet confirmed. The same three steps, opened on a
     document that already exists: an edit form that looked different from the entry form
     would be a second place to learn where the vendor goes. */
  const isEdit = mode === "edit";
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog invoice-wizard";
  dialog.setAttribute("aria-labelledby", "invoice-wizard-title");
  const head = element("header", "invoice-detail-dialog__head");
  const heading = element("div");
  const title = element("h2", "", isEdit ? `ویرایش فاکتور ${originalInvoice.invoiceNumber}` : isCorrective ? "ثبت سند اصلاحی مرتبط" : "ثبت فاکتور دستی");
  title.id = "invoice-wizard-title";
  heading.append(title, element("p", "invoice-wizard__subtitle", isEdit ? "تا پیش از ثبت نهایی، هر فیلد این فاکتور قابل تغییر است و سند هنوز اثری بر هزینه واقعی ندارد." : isCorrective ? `سند اصلاحی به فاکتور ${originalInvoice.invoiceNumber} متصل و مستقل ثبت می‌شود.` : "پیش‌نویس تا قبل از تأیید، اثر مالی ندارد."));
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
  /* Kept on the wizard, not inside the step, because adding a line repaints the whole step.
     Somebody entering six lines of one delivery note picks the stage once instead of six
     times, and the filter they set does not silently undo itself between lines. */
  let selectedStage = "";
  let headerData = null;
  let lines = [];
  let adjustments = isEdit
    ? {
      discountIRR: originalInvoice.discountIRR ?? "0",
      taxIRR: originalInvoice.taxIRR ?? "0",
      shippingIRR: originalInvoice.shippingIRR ?? "0",
      otherCostsIRR: originalInvoice.otherCostsIRR ?? "0",
    }
    : { discountIRR: "0", taxIRR: "0", shippingIRR: "0", otherCostsIRR: "0" };
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
    // No number field. The project allocates it when the invoice is written, so
    // there is nothing to collect and nothing yet to show: a box reading "assigned
    // later" is a row of the form spent saying that this form has no say. The
    // number appears where it is useful -- in the register, on the saved invoice.
    const vendor = inputField("فروشنده یا ارائه‌دهنده", "vendorName");
    vendor.input.value = headerData?.vendorName ?? ((isCorrective || isEdit) ? originalInvoice.vendorName : "");
    const date = createPersianDatePicker({ id: "invoiceDate", label: "تاریخ فاکتور", value: headerData?.invoiceDate ?? (isEdit ? originalInvoice.invoiceDate : getTehranTodayIso()) });
    const description = element("label", "form-field invoice-wizard-grid__wide");
    description.append(element("span", "form-label", "توضیح"));
    const textarea = element("textarea", "app-textarea");
    textarea.rows = 3;
    textarea.maxLength = 500;
    textarea.value = headerData?.description ?? (isEdit ? (originalInvoice.description ?? "") : "");
    description.append(textarea);
    form.append(vendor.field, date.field, description);
    form.append(actions({ nextLabel: "ادامه به خطوط", onNext: () => {
      const validation = validateInvoiceHeader({ invoiceDate: date.getValue(), vendorName: vendor.input.value, description: textarea.value });
      if (!validation.valid) { showMessage(Object.values(validation.errors).join(" "), true); return; }
      headerData = validation.values;
      currentStep = 2;
      paintStep();
    } }));
    return form;
  }

  function renderLinesStep() {
    const section = element("div", "invoice-lines-editor");
    /* THE STAGE IS A FILTER, NOT A FIELD.
       Nothing chosen here is sent anywhere. The line still points at an estimate line and
       the stage is still derived from that line's activity, exactly as the reports compute
       it -- see `invoice-stages.js` for why storing it twice would be worse than useless.
       What this buys is the only thing that was actually wrong: 835 estimate lines in one
       flat menu, which is a list nobody reads to the end. Somebody then picks «هزینه عمومی»
       because it is the option they can find, and that money leaves the level-one report
       for good. The fix is a shorter list, not a new column. */
    const stages = buildStageIndex(targets);
    const stageField = element("label", "form-field");
    stageField.append(element("span", "form-label", "مرحله پروژه"));
    const stageSelect = element("select", "app-select");
    stageSelect.append(option("", "انتخاب کنید"), ...stages.map((stage) => option(stage.value, stageOptionLabel(stage))));
    stageField.append(stageSelect);

    const targetField = element("label", "form-field");
    targetField.append(element("span", "form-label", "اتصال به ردیف برآورد یا هزینه‌های عمومی پروژه"));
    const targetSelect = element("select", "app-select");
    targetField.append(targetSelect);
    const quantity = inputField("مقدار", "quantity", { inputMode: "decimal" });
    const unitPrice = inputField(`قیمت واحد به ${getDisplayCurrencyLabel()}`, "unitPriceIRR", { inputMode: "decimal" });
    const amount = inputField(`مبلغ هزینه عمومی پروژه به ${getDisplayCurrencyLabel()}`, "amountIRR", { inputMode: "decimal" });
    /* Said before the amount is typed, not discovered after the invoice is confirmed.
       WHAT IS AND IS NOT TRUE OF A GENERAL COST
       It carries no estimate line, so no activity and therefore no WBS stage can be derived
       for it, and `by_wbs` places it in no node -- the level-one chart cannot draw it. That
       is the whole of the loss. It is NOT money that goes missing: it counts in the project's
       actual cost, in the monthly trend, in the breakdown by resource type, and against the
       general-cost item's own baseline, which pools unattached lines up to its revised
       amount and warns when they pass it. Saying only the first half would send somebody
       hunting for a stage that does not apply to a building permit. */

    /* WHICH OF THE TWO WAYS THIS LINE SAYS WHAT IT COST.
       A delivery note states a quantity and a rate; a contractor's bill for the same
       activity states one number and no breakdown, and the person holding it should not
       have to invent a rate so the form will accept it. The service has always taken
       either -- it refuses only the combination -- so this is a question the form was not
       asking, not a capability that was missing.
       Offered only where there is a choice: a general cost has no quantity to state. */
    const modeField = element("label", "form-field");
    modeField.append(element("span", "form-label", "روش ثبت مبلغ"));
    const modeSelect = element("select", "app-select");
    modeSelect.name = "amountMode";
    modeSelect.append(option(AMOUNT_MODES.COMPUTED, "مقدار × قیمت واحد"),
                      option(AMOUNT_MODES.TOTAL, "فقط مبلغ کل"));
    modeField.append(modeSelect);

    const generalWarning = element("p", "invoice-warning",
      "هزینه عمومی به هیچ مرحله‌ای وصل نمی‌شود، پس در نمودار «گزارش مالی سطح ۱» دیده نمی‌شود. در هزینه واقعی پروژه، روند ماهانه و تفکیک هزینه‌ها کامل حساب می‌شود. اگر این خرید برای مرحله مشخصی است، همان مرحله را انتخاب کنید.");

    function paintTargets() {
      const inStage = targetsInStage(targets, selectedStage);
      targetSelect.replaceChildren(
        option("", selectedStage ? "انتخاب کنید" : "ابتدا مرحله را انتخاب کنید"),
        ...inStage.map((target) => option(target.targetId, `${target.label} · ${target.targetType === "general_cost" ? "هزینه‌های عمومی پروژه" : formatUnitLabel(target.unit)}`)));
      targetSelect.disabled = inStage.length === 0;
      generalWarning.hidden = selectedStage !== GENERAL_COST_STAGE;
      // Nothing is selected yet, so no amount shape applies and none is guessed at.
      paintAmountFields();
    }

    stageSelect.value = selectedStage;
    stageSelect.addEventListener("change", () => {
      selectedStage = stageSelect.value;
      paintTargets();
    });
    function paintAmountFields() {
      const target = targets.find((item) => item.targetId === targetSelect.value);
      const choices = amountModesFor(target);
      /* The control appears only when there is something to choose. On a general cost the
         single amount box IS the only shape, and a menu with one option in it is a question
         with one answer. */
      modeField.hidden = !target || choices.length < 2;
      if (!choices.includes(modeSelect.value)) modeSelect.value = choices[0];
      const total = !target || modeSelect.value === AMOUNT_MODES.TOTAL;
      quantity.field.hidden = !target || total;
      unitPrice.field.hidden = !target || total;
      amount.field.hidden = !target || !total;
      /* Hidden boxes are emptied. A quantity left behind a switched-away field would be
         read back by the validator and sent beside an amount, which the service refuses --
         and the reader would have no idea which number it was talking about. */
      if (total) { quantity.input.value = ""; unitPrice.input.value = ""; }
      else { amount.input.value = ""; }
    }
    targetSelect.addEventListener("change", paintAmountFields);
    modeSelect.addEventListener("change", paintAmountFields);
    paintTargets();
    const lineDescription = inputField("توضیح خط", "lineDescription");
    const add = element("button", "button button--ghost", "افزودن خط");
    add.type = "button";
    add.addEventListener("click", () => {
      const target = targets.find((item) => item.targetId === targetSelect.value);
      const validation = validateInvoiceLine({ quantity: quantity.input.value, unitPriceIRR: tomanInputToIrr(unitPrice.input.value), amountIRR: tomanInputToIrr(amount.input.value), description: lineDescription.input.value }, target, modeSelect.value);
      if (!validation.valid) { showMessage(Object.values(validation.errors).join(" "), true); return; }
      lines.push(validation.values);
      showMessage("خط به پیش‌نویس اضافه شد.");
      paintStep();
    });
    const editor = element("div", "invoice-line-entry");
    editor.append(stageField, targetField, generalWarning, modeField, quantity.field, unitPrice.field, amount.field, lineDescription.field, add);
    const list = element("div", "invoice-draft-lines");
    lines.forEach((line, index) => {
      const card = element("article", "invoice-draft-line");
      card.append(element("strong", "", `${formatDisplayNumber(String(index + 1))}. ${line.targetLabel}`), element("span", "numeric", statesTotal(line) ? formatTomanFromIrr(line.lineAmountIRR) : `${formatDisplayNumber(line.quantity)} ${formatUnitLabel(line.unit)} × ${formatTomanFromIrr(line.unitPriceIRR)}`));
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
    [["تاریخ", formatBusinessDate(headerData.invoiceDate)], ["فروشنده", headerData.vendorName], ["منبع", "ورود دستی"]].forEach(([label, value]) => { const item = element("div", "invoice-detail-grid__item"); item.append(element("dt", "", label), element("dd", "", value)); summary.append(item); });
    const lineList = element("div", "invoice-draft-lines");
    preview.lines.forEach((line, index) => { const card = element("article", "invoice-draft-line"); card.append(element("strong", "", `${formatDisplayNumber(String(index + 1))}. ${line.targetLabel}`), element("span", "numeric", formatTomanFromIrr(line.lineAmountIRR))); lineList.append(card); });
    const totals = element("dl", "invoice-totals");
    [["جمع خام خطوط", preview.rawLinesTotalIRR], ["تخفیف", preview.discountIRR], ["مالیات", preview.taxIRR], ["حمل", preview.shippingIRR], ["سایر هزینه‌ها", preview.otherCostsIRR], ["مبلغ نهایی", preview.finalAmountIRR]].forEach(([label, value]) => totals.append(element("dt", "", label), element("dd", "numeric", formatTomanFromIrr(value))));
    section.append(element("div", "inline-notice", isEdit ? "این تغییرات روی همین فاکتور نوشته می‌شود و سند تازه‌ای ساخته نمی‌شود. تا پیش از ثبت نهایی، هزینه واقعی پروژه تغییر نمی‌کند." : isCorrective ? "این سند پس از ثبت، با اثر مالی انتخاب‌شده و ارتباط صریح با فاکتور اصلی اعمال می‌شود؛ فاکتور اصلی تغییر نمی‌کند." : "با ثبت این مرحله فقط پیش‌نویس ساخته می‌شود و هزینه واقعی پروژه تغییر نمی‌کند."), summary, lineList, totals);
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
    const commitLabel = isEdit ? "ثبت تغییرات" : isCorrective ? "ثبت سند اصلاحی" : "ثبت پیش‌نویس";
    section.append(actions({ back: true, nextLabel: commitLabel, onNext: async (button) => {
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
        /* An edit REWRITES the document it opened; it does not raise a second one. The
           version the person was looking at travels with it, so a save lands on the
           invoice they read and not on one somebody else has moved on since. */
        if (isEdit) await adapter.updateInvoice({ invoiceId: originalInvoice.invoiceId, expectedVersion: originalInvoice.version, header: headerData, lines, adjustments });
        else if (isCorrective) await adapter.createCorrective({ originalInvoiceId: originalInvoice.invoiceId, header: headerData, lines, adjustments, financialEffectSign, reason: correctionReason, idempotencyKey });
        else await adapter.createDraft({ header: headerData, lines, adjustments, duplicateOverrideReason, idempotencyKey });
        dialog.close();
        onSaved();
      }
      catch (error) { showMessage(formatApiErrorMessage(error), true); button.disabled = false; button.textContent = commitLabel; }
    } }));
    return section;
  }

  function paintStep() {
    updateStepper();
    showMessage("");
    body.replaceChildren(currentStep === 1 ? renderHeaderStep() : currentStep === 2 ? renderLinesStep() : renderPreviewStep());
  }

  dialog.append(head, steps, message, body);
  adapter.getInvoiceTargets().then((items) => {
    targets = items;
    /* The saved lines become editable lines only once the targets are here: a line stores
       a `targetId`, and the invoice states what it points AT -- an estimate line or a
       general-cost item. Matching by those identifiers rather than by the label is what
       keeps an edit pointing at the same cost item when somebody renames it. */
    if (isEdit && !lines.length) lines = editableLines(originalInvoice, targets);
    paintStep();
  }).catch((error) => showMessage(error.message, true));
  updateStepper();
  return dialog;
}

/* Exported for the tests that hold the refusal rules still. What a reader is
   shown when they may not act is as much a decision as what they are shown when
   they may, and it is not reachable from the page factory without a Backend. */
export function renderDetail(invoice, { canEdit, project, onSubmit, onConfirm, onVoid, onCorrective, onEdit }) {
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

  /* THE WAY BACK IN, BESIDE THE WAY TO PAPER.
     Until the confirmation locks it, an invoice is a draft of a claim about money, and a
     draft nobody may correct is not a draft. Both statuses before `confirmed` are open:
     «در انتظار تأیید» is precisely where somebody reads it closely enough to find the
     mistake, and a review that cannot lead to a change is a queue, not a review.
     Withheld -- not disabled -- once confirmed, where the document is immutable and the
     corrective workflow is the only honest route. A greyed button there would promise a
     door that does not exist. */
  const EDITABLE = ["draft", "awaitingConfirmation"];
  if (canEdit && onEdit && EDITABLE.includes(invoice.invoiceStatus)) {
    const edit = element("button", "button button--ghost invoice-edit-button", "ویرایش فاکتور");
    edit.type = "button";
    edit.dataset.action = "edit-invoice";
    edit.addEventListener("click", () => onEdit(invoice, dialog));
    metaRow.append(edit);
  }
  head.append(titleRow, metaRow);

  const metadata = element("dl", "invoice-detail-grid");
  [
    ["تاریخ فاکتور", formatBusinessDate(invoice.invoiceDate)], ["فروشنده یا ارائه‌دهنده", invoice.vendorName],
    ["منبع ثبت", SOURCE_LABELS[invoice.source] ?? "نامشخص"], ["تعداد خطوط", formatDisplayNumber(String(invoice.lines.length))],
    ["نسخه سند", formatDisplayNumber(String(invoice.version))], ["شناسه یکتای ثبت", invoice.idempotencyKey],
    ["ثبت‌کننده", actorLabel(invoice.submittedByName, invoice.submittedBy)], ["زمان ثبت", formatSystemDateTime(invoice.createdAt)],
    ["تأییدکننده", actorLabel(invoice.confirmedByName, invoice.confirmedBy, "تأیید نشده")], ["زمان تأیید", invoice.confirmedAt ? formatSystemDateTime(invoice.confirmedAt) : "تأیید نشده"],
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
  // The detail dialog is a record anyone who can read the invoice may open, and
  // it shows every decision this document is waiting on whoever opens it. What
  // an account may not do is switched off rather than taken away: a reader who
  // sees «در انتظار تأیید» and no button at all cannot tell a document waiting
  // on someone else from a page that failed to load.
  const act = (button, handler) => {
    button.type = "button";
    button.disabled = !canEdit;
    if (canEdit) button.addEventListener("click", handler);
    return button;
  };
  const actionsFor = (...buttons) => {
    const actions = element("div", "dialog-actions invoice-detail-actions");
    actions.append(...buttons);
    dialog.append(actions);
    if (!canEdit) dialog.append(createPermissionNotice("انجام عملیات روی فاکتور"));
  };
  if (invoice.invoiceStatus === "draft") {
    actionsFor(act(element("button", "button button--primary", "ارسال برای تأیید"),
      () => onSubmit(invoice, dialog)));
  }
  if (invoice.invoiceStatus === "awaitingConfirmation") {
    // Confirming is authorized, not personal: whoever holds «مدیریت فاکتورها»
    // for this project may confirm any invoice awaiting it, and `confirmedBy`
    // records which of them did.
    //
    // This used to also require that you be the submitter. Two things were
    // wrong with it. The service dropped the rule -- in the guard AND in the
    // UPDATE's WHERE clause, where it had been written a second time -- so the
    // only thing still enforcing it was this line, and a request the button
    // refused would have succeeded. And it inverted its own purpose: the whole
    // draft → submit → confirm ceremony exists so that raising and approving
    // are two people, and requiring the submitter made them one, which is the
    // opposite of the separation it was named for. A رییس سازمان could not
    // approve the invoice a کارشناس had sent them -- the one case the queue is
    // for -- while everyone could approve their own.
    actionsFor(act(element("button", "button button--primary", "تأیید نهایی فاکتور"),
      () => onConfirm(invoice, dialog)));
  }
  if (invoice.invoiceStatus === "confirmed") {
    actionsFor(
      act(element("button", "button button--ghost", "ثبت سند اصلاحی"), () => onCorrective(invoice, dialog)),
      act(element("button", "button button--danger", "ابطال با سند برگشت"), () => onVoid(invoice, dialog)),
    );
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

function renderTable(items, onDetail, visible, { canEdit = false, onAdvance = () => {} } = {}) {
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
      // Both controls in the cell that carries the number rather than in a
      // column of their own: they travel with it, so the way into an invoice --
      // and the move it is waiting for -- are still on screen when the table is
      // scrolled sideways.
      const actions = element("div", "invoice-row-actions");
      // The move first, the way in second. A reviewer going down a filtered
      // queue is pressing the same control on every row, and it should be in the
      // same place each time without the number's width moving it.
      const step = NEXT_STEP[invoice.invoiceStatus];
      if (step && canEdit) {
        // It opens the same dialog the detail view opens, never acting on the
        // press: confirming writes cost into the project and cannot be undone by
        // pressing again, so the sentence saying so is not something a shortcut
        // gets to skip. What it saves is the trip through جزئیات, which for a
        // queue of twenty is the difference between three clicks each and two.
        const advance = element("button", "button button--small button--primary invoice-next-button", step.label);
        advance.type = "button";
        advance.setAttribute("aria-label", step.name(invoice.invoiceNumber));
        advance.addEventListener("click", (event) => onAdvance(step.act, invoice, event.currentTarget));
        actions.append(advance);
      }
      const action = element("button", "button button--small button--ghost invoice-detail-button");
      action.type = "button";
      // The word is gone, the name is not: an icon-only control is anonymous to
      // a screen reader without this, and the row already spends its width on
      // the number and the move.
      action.setAttribute("aria-label", `جزئیات فاکتور ${invoice.invoiceNumber}`);
      action.append(previewIcon());
      action.addEventListener("click", (event) => onDetail(invoice.invoiceId, event.currentTarget));
      actions.append(action);
      identity.append(actions);
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
  // A stored «همه» is this endpoint's maximum, not the word: `getInvoices`
  // would coerce it to NaN and fall back to 50, which is a different number
  // from the one the reader chose.
  // Fifty, not the module's twenty-five: the PRD states the register opens at
  // fifty rows with a ceiling of two hundred, and that is a decision about this
  // list rather than a preference of the interface.
  const storedSize = getRowsPerPage("invoices", 50);
  const filters = { status: "", query: "", page: 1, pageSize: storedSize === "all" ? SUMMARY_PAGE_SIZE : storedSize };
  // Which chip is pressed, and the counts behind all four. The counts describe
  // the project, not the current view, so they are read once per data change and
  // left alone while the reader moves between chips.
  let activeView = "all";
  let summary = null;
  // Lives with the page, not with a render: paint() replaces the whole tree on
  // every load, so a choice held inside a render would last until the next filter.
  const visibleColumns = defaultVisibleColumns(INVOICE_COLUMNS);
  const canCreate = capabilitiesFor(context).manageInvoice;
  const detailMessage = element("div", "form-message invoice-detail-message");
  detailMessage.setAttribute("aria-live", "assertive");

  /* Built once, moved into each repaint. The chips are the only status filter
     this page has and the search is the endpoint's own `query`, so the two are
     applied together by the same read rather than narrowing each other's
     results afterwards. */
  const toolbar = createTableToolbar({
    name: "invoices",
    columns: INVOICE_COLUMNS,
    visible: visibleColumns,
    table: () => root.querySelector(".invoices-table"),
    chips: {
      label: "فیلتر فاکتورها بر اساس وضعیت",
      items: INVOICE_VIEWS.map((view) => ({ key: view.key, label: view.label, tone: view.tone, count: "" })),
      active: activeView,
      onSelect: (key) => selectView(key),
    },
    search: {
      placeholder: "جست‌وجوی شماره، فروشنده یا توضیح",
      label: "جست‌وجو در فاکتورها",
      onSearch: (value) => {
        filters.query = value;
        // A new question deserves its first page, not the page you were on.
        filters.page = 1;
        load();
      },
    },
  });

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

  /**
   * The row's own button, taking the invoice to its next state.
   *
   * It opens the dialog `showDetail` would have opened two clicks later, with
   * the row's copy of the invoice: `createSubmitDraftDialog` and
   * `createConfirmInvoiceDialog` read the number, the version and the amount,
   * and the list carries all three. Fetching the document again to show a
   * sentence about it would put a wait in front of a control whose whole point
   * is that it is already there -- and the version travelling with the row is
   * the one the reader is looking at, so a document that moved underneath them
   * is refused by the service as stale, which is the answer they need.
   */
  function advanceInvoice(act, invoice, trigger) {
    const opener = trigger ?? null;
    const dialog = act === "submit"
      ? createSubmitDraftDialog({ invoice, adapter, onSaved: load })
      : createConfirmInvoiceDialog({ invoice, adapter, onSaved: load });
    root.append(dialog);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    showAccessibleDialog(dialog, { opener });
  }

  async function showDetail(invoiceId, trigger) {
    detailMessage.textContent = "";
    detailMessage.className = "form-message invoice-detail-message";
    // Busy is a class, not a caption. The trigger is an icon now, and writing
    // text into it would replace the drawing -- then restoring the "previous"
    // text, which for an icon-only button is the empty string, would leave a
    // blank square behind for the rest of the session.
    trigger.disabled = true;
    trigger.classList.add("is-busy");
    try {
      const invoice = await adapter.getInvoice(invoiceId);
      const dialog = renderDetail(invoice, {
        canEdit: canCreate,
        project: { name: context.projectName, code: context.projectCode },
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
        /* The same wizard, opened on the document instead of on a blank form. `refreshCounts`
           because an edit can move money between the status columns the toolbar counts --
           the totals above the table are of the register, not of this one invoice. */
        onEdit: (editable, detailDialog) => {
          const opener = getDialogOpener(detailDialog);
          detailDialog.close();
          const editDialog = createInvoiceWizard({ adapter, onSaved: () => load({ refreshCounts: true }), mode: "edit", originalInvoice: editable });
          root.append(editDialog);
          editDialog.addEventListener("close", () => editDialog.remove(), { once: true });
          showAccessibleDialog(editDialog, { opener });
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
      trigger.classList.remove("is-busy");
    }
  }

  function renderHeader() {
    const header = createFinancePageHeader("فاکتورها", "feature-header");
    const actions = element("div", "finance-page-actions");
    // Both ways of recording a document, offered to everyone who can read the
    // register and switched off for whoever may not use them. The upload page
    // makes its own refusal the same way, so following the link never turns a
    // disabled button into an unexplained dead end.
    const create = element("button", "button button--primary", "ثبت فاکتور دستی");
    create.type = "button";
    create.disabled = !canCreate;
    if (canCreate) create.addEventListener("click", () => {
      const dialog = createInvoiceWizard({ adapter, onSaved: () => { filters.page = 1; load({ refreshCounts: true }); } });
      root.append(dialog);
      dialog.addEventListener("close", () => dialog.remove(), { once: true });
      showAccessibleDialog(dialog);
    });
    const upload = element("a", "button button--ghost", "ورود از تصویر یا صدا");
    upload.href = "#finance/invoice-files";
    actions.append(create, upload);

    const fragment = document.createDocumentFragment();
    fragment.append(header, actions);
    if (!canCreate) fragment.append(createPermissionNotice("ثبت فاکتور"));
    return fragment;
  }

  /* Only the body goes through the state switch. The heading -- and with it the
     chips, which are the only filter this page has -- is rendered either way,
     because a filter that empties the list must not leave with it. */
  function renderListBody(data) {
    const body = element("div", "invoices-list-body");
    const table = renderTable(data.items, showDetail, visibleColumns, { canEdit: canCreate, onAdvance: advanceInvoice });
    /* The one table in this module the server pages. Every other table arrives
       whole and slices what it already has; here `totalItems` is the register's
       size and `data.items` is only the page asked for, so both controls send a
       request rather than re-slicing.

       The size is capped at what the endpoint accepts. `getInvoices` clamps to
       200 anyway, so «همه» is 200 here and the footer's count says so -- an
       option that quietly meant something narrower would be worse than one that
       says what it did. */
    body.append(table, createTablePagination({
      name: "invoices",
      page: data.page,
      total: data.totalItems ?? data.items.length,
      pageSize: filters.pageSize,
      label: "صفحه‌بندی فاکتورها",
      onPageChange: (next) => { filters.page = next; load(); },
      onPageSizeChange: (next) => {
        filters.pageSize = next === "all" ? SUMMARY_PAGE_SIZE : next;
        filters.page = 1;
        load();
      },
    }));
    return body;
  }

  function renderSection() {
    const section = element("section", "invoices-section");
    const heading = element("div", "invoice-list-heading");
    const title = element("div", "");
    title.append(element("h2", "", "فهرست فاکتورها"), element("p", "", `پس از ایجاد و بازبینی فاکتور ، تایید و سپس ثبت نهایی را بزنید`));
    heading.append(title);
    // The toolbar is built once and moved, never rebuilt: a repaint that
    // replaced it would take the search box out from under whoever is typing
    // into it, along with their caret.
    updateFilterChips(toolbar.querySelector(".data-table-chips"), {
      active: activeView,
      counts: invoiceChipCounts(summary.counts),
    });
    section.append(heading, detailMessage);
    section.append(toolbar,
      renderPageState(state, { renderContent: renderListBody, renderEmpty, onRetry: load }));
    return section;
  }

  function renderEmpty() {
    const section = element("section", "state-card");
    // "Nothing here" and "nothing matched what you asked for" are different
    // things to be told, and only one of them suggests changing the question.
    const narrowed = Boolean(filters.query) || activeView !== "all";
    section.append(
      element("h2", "", "فاکتوری پیدا نشد"),
      element("p", "", narrowed
        ? "موردی مطابق جست‌وجو یا وضعیت انتخاب‌شده پیدا نشد. عبارت جست‌وجو را تغییر دهید یا چیپ «همه» را بزنید."
        : "برای این پروژه هنوز فاکتوری ثبت نشده است."),
    );
    return section;
  }

  function paint() {
    // Before the first read there are no counts to show, so there is no heading
    // to show them in -- the loading or error card is the whole page, as it was.
    // Wrapped, because this replaces the tree the search box is standing in and
    // the reader may still be typing into it.
    repaintPreservingFocus(() => {
      root.replaceChildren(renderHeader(), summary
        ? renderSection()
        : renderPageState(state, { renderContent: renderListBody, renderEmpty, onRetry: load }));
    });
  }

  load();
  return root;
}
