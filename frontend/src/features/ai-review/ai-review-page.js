import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { hasPermission } from "../../core/auth/permissions.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, irrToDisplayValue, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { element } from "../../shared/dom/elements.js";

const FIELD_LABELS = Object.freeze({
  invoiceNumber: "شماره فاکتور",
  invoiceDate: "تاریخ فاکتور",
  vendorName: "فروشنده یا ارائه‌دهنده",
  resourceId: "تخصیص به قلم هزینه",
  totalIRR: "مبلغ نهایی",
});

const REVIEW_LABELS = Object.freeze({
  awaitingReview: "نیازمند بررسی",
  accepted: "پذیرفته‌شده",
  rejected: "ردشده",
});

function confidenceLabel(value) {
  return `${formatDisplayNumber(String(Math.round(Number(value) * 100)))} درصد اطمینان`;
}

function confirmationDialog({ title, message, confirmLabel, onConfirm }) {
  const dialog = element("dialog", "confirm-dialog ai-confirm-dialog");
  dialog.setAttribute("aria-labelledby", "ai-confirm-dialog-title");
  const heading = element("h2", "", title);
  heading.id = "ai-confirm-dialog-title";
  const copy = element("p", "", message);
  const feedback = element("div", "form-message");
  feedback.setAttribute("aria-live", "assertive");
  const actions = element("div", "dialog-actions");
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const confirm = element("button", "button button--primary", confirmLabel);
  confirm.type = "button";
  confirm.addEventListener("click", async () => {
    confirm.disabled = true;
    try {
      await onConfirm();
      dialog.close();
    } catch (error) {
      feedback.textContent = formatApiErrorMessage(error, "عملیات انجام نشد.");
      feedback.className = "form-message form-message--error";
    } finally {
      confirm.disabled = false;
    }
  });
  actions.append(cancel, confirm);
  dialog.append(heading, copy, feedback, actions);
  return dialog;
}

function reviewCard({ draft, targets, adapter, canEdit, onChanged, root }) {
  const card = element("article", "ai-review-card");
  const header = element("header", "ai-review-card__header");
  const title = element("div");
  title.append(element("span", "feature-header__eyebrow", draft.file.logicalType === "invoice_image" ? "پردازش تصویر فاکتور" : "پردازش صدای فارسی"), element("h2", "", draft.file.originalNameSafe));
  header.append(title, element("span", `file-status ai-review-status--${draft.reviewStatus}`, REVIEW_LABELS[draft.reviewStatus] ?? "نامشخص"));
  card.append(header);

  const zeroEffect = element("div", "ai-zero-effect");
  zeroEffect.append(element("strong", "", draft.reviewStatus === "accepted" ? "اثر مالی پس از تأیید انسانی" : `اثر مالی فعلی: صفر ${getDisplayCurrencyLabel()}`), element("span", "", draft.reviewStatus === "accepted" ? formatTomanFromIrr(draft.financialEffectIRR) : "این داده هنوز فاکتور تأییدشده نیست."));
  card.append(zeroEffect);

  const form = element("div", "ai-fields-grid");
  const controls = new Map();
  draft.fields.forEach((field) => {
    const wrapper = element("label", `ai-field${field.confidence < 0.8 ? " ai-field--low" : ""}`);
    const labelRow = element("span", "ai-field__label");
    const fieldLabel = field.key === "totalIRR" ? `${FIELD_LABELS[field.key]} به ${getDisplayCurrencyLabel()}` : FIELD_LABELS[field.key];
    labelRow.append(element("strong", "", fieldLabel ?? "اطلاعات خوانده‌شده"), element("small", "", confidenceLabel(field.confidence)));
    let input;
    if (field.key === "invoiceDate") {
      const picker = createPersianDatePicker({ id: `ai-${draft.draftId}-date`, label: "", value: field.confirmedValue ?? field.extractedValue });
      input = picker;
      wrapper.append(labelRow, picker.field);
    } else if (field.key === "resourceId") {
      const select = element("select", "app-select");
      select.append(element("option", "", "انتخاب قلم هزینه"));
      targets.forEach((target) => {
        const option = element("option", "", `${target.label} · ${target.targetType === "general_cost" ? "هزینه‌های عمومی پروژه" : "ردیف برآورد"}`);
        option.value = target.targetId;
        select.append(option);
      });
      select.value = field.confirmedValue ?? field.extractedValue ?? "";
      select.disabled = draft.reviewStatus !== "awaitingReview" || !canEdit;
      input = { getValue: () => select.value, input: select };
      wrapper.append(labelRow, select);
    } else {
      const control = element("input", "app-input");
      const canonicalValue = field.confirmedValue ?? field.extractedValue ?? "";
      control.value = field.key === "totalIRR" ? (irrToDisplayValue(canonicalValue) ?? "") : canonicalValue;
      control.disabled = draft.reviewStatus !== "awaitingReview" || !canEdit;
      if (field.key === "totalIRR") control.inputMode = "numeric";
      input = { getValue: () => field.key === "totalIRR" ? tomanInputToIrr(control.value) : control.value.trim(), input: control };
      wrapper.append(labelRow, control);
    }
    if (input.input) input.input.disabled = draft.reviewStatus !== "awaitingReview" || !canEdit;
    controls.set(field.key, input);
    form.append(wrapper);
  });
  card.append(form);

  const warning = element("p", "ai-confidence-note", "فیلدهای نارنجی اطمینان کمتر از ۸۰ درصد دارند و باید با سند اصلی تطبیق داده شوند.");
  card.append(warning);
  if (draft.reviewStatus !== "awaitingReview") {
    if (draft.linkedInvoiceId) {
      const invoiceLink = element("a", "button button--ghost", "مشاهده فاکتورهای ثبت‌شده");
      invoiceLink.href = "#/invoices";
      card.append(invoiceLink);
    }
    return card;
  }

  const feedback = element("div", "form-message");
  feedback.setAttribute("aria-live", "assertive");
  const actions = element("div", "ai-review-card__actions");
  const retry = element("button", "button button--ghost", "پردازش دوباره");
  retry.type = "button";
  retry.disabled = !canEdit;
  retry.addEventListener("click", async () => {
    retry.disabled = true;
    try {
      await adapter.retryExtraction(draft.draftId);
      await onChanged();
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = "form-message form-message--error";
      retry.disabled = false;
    }
  });
  const reject = element("button", "button button--danger", "رد پیش‌نویس");
  reject.type = "button";
  reject.disabled = !canEdit;
  reject.addEventListener("click", () => {
    const dialog = confirmationDialog({ title: "رد پیش‌نویس هوشمند", message: "پیش‌نویس رد می‌شود، اما فایل اصلی حذف نخواهد شد و ورود دستی همچنان در دسترس است.", confirmLabel: "تأیید رد پیش‌نویس", onConfirm: async () => { await adapter.rejectExtraction({ draftId: draft.draftId, expectedVersion: draft.version }); await onChanged(); } });
    root.append(dialog);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    showAccessibleDialog(dialog);
  });
  const confirm = element("button", "button button--primary", "تأیید انسانی و ثبت فاکتور");
  confirm.type = "button";
  confirm.disabled = !canEdit;
  confirm.addEventListener("click", () => {
    const values = Object.fromEntries([...controls].map(([key, control]) => [key, control.getValue()]));
    if (!values.invoiceDate || !values.vendorName || !values.resourceId || !/^\d+$/.test(values.totalIRR)) {
      feedback.textContent = `تاریخ، فروشنده، تخصیص قلم هزینه و مبلغ صحیح ${getDisplayCurrencyLabel()} برای تأیید الزامی است.`;
      feedback.className = "form-message form-message--error";
      return;
    }
    const fieldConfirmations = draft.fields.filter((field) => values[field.key] !== String(field.extractedValue ?? "")).map((field) => ({ key: field.key, confirmedValue: values[field.key] }));
    const dialog = confirmationDialog({ title: "تأیید نهایی و ایجاد فاکتور", message: "پس از این تأیید، پیش‌نویس بررسی‌شده به فاکتور تأییدشده تبدیل می‌شود و اثر مالی ایجاد می‌کند.", confirmLabel: "تأیید نهایی", onConfirm: async () => { await adapter.confirmExtraction({ draftId: draft.draftId, expectedVersion: draft.version, idempotencyKey: crypto.randomUUID(), fieldConfirmations, invoice: values }); await onChanged(); } });
    root.append(dialog);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    showAccessibleDialog(dialog);
  });
  actions.append(retry, reject, confirm);
  card.append(feedback, actions);
  return card;
}

export function createAiReviewPage({ context, adapter }) {
  const root = element("div", "ai-review-page");
  const canEdit = hasPermission(context, "finance.edit");
  let state = createRequestState(REQUEST_STATUS.LOADING);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const [drafts, targets] = await Promise.all([adapter.getExtractions(), adapter.getInvoiceTargets()]);
      state = createRequestState(drafts.length ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, { drafts, targets });
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function paint() {
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "کنترل انسانی الزامی"), element("h1", "", "بررسی هوشمند فاکتور"), element("p", "", "اطلاعات خوانده‌شده را با فایل اصلی تطبیق دهید؛ موارد کم‌اطمینان را اصلاح و سپس تصمیم نهایی را ثبت کنید."));
    const actions = element("div", "feature-header__actions feature-header__other-actions");
    const files = element("a", "button button--ghost", "بازگشت به فایل‌ها");
    files.href = "#/invoice-files";
    const manual = element("a", "button button--ghost", "ورود دستی فاکتور");
    manual.href = "#/invoices";
    actions.append(files, manual);
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.classList.add("finance-back-link");
    back.href = "#/finance";
    const navigation = element("div", "feature-header__navigation");
    navigation.append(actions, back);
    header.append(copy, navigation);

    root.replaceChildren(header, renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  function renderContent(data) {
    const list = element("div", "ai-review-list");
    data.drafts.forEach((draft) => list.append(reviewCard({ draft, targets: data.targets, adapter, canEdit, onChanged: load, root })));
    return list;
  }

  function renderEmpty() {
    const card = element("section", "state-card ai-review-empty");
    card.append(element("h2", "", "پیش‌نویسی برای بررسی وجود ندارد"), element("p", "", "ابتدا یک تصویر یا فایل صوتی بارگذاری و پردازش را شروع کنید."));
    const upload = element("a", "button button--primary", "رفتن به بارگذاری تصویر و صدا");
    upload.href = "#/invoice-files";
    card.append(upload);
    return card;
  }

  load();
  return root;
}
