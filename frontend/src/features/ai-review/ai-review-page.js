import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { hasPermission } from "../../core/auth/permissions.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { normalizeDecimalInput } from "../../shared/validation/decimal-validation.js";

const FIELD_LABELS = Object.freeze({
  invoiceNumber: "شماره فاکتور",
  invoiceDate: "تاریخ فاکتور",
  vendorName: "فروشنده یا ارائه‌دهنده",
  resourceId: "تخصیص به قلم مالی",
  totalIRR: `مبلغ نهایی به ${CURRENCY_LABELS.IRR}`,
});

const REVIEW_LABELS = Object.freeze({
  awaitingReview: "در انتظار بازبینی",
  accepted: "پذیرفته‌شده",
  rejected: "ردشده",
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

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
      feedback.textContent = `${error.message || "عملیات انجام نشد."}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
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
  title.append(element("span", "feature-header__eyebrow", draft.file.logicalType === "invoice_image" ? "استخراج از تصویر" : "استخراج از صدای فارسی"), element("h2", "", draft.file.originalNameSafe));
  header.append(title, element("span", `file-status ai-review-status--${draft.reviewStatus}`, REVIEW_LABELS[draft.reviewStatus] ?? "نامشخص"));
  card.append(header);

  const zeroEffect = element("div", "ai-zero-effect");
  zeroEffect.append(element("strong", "", draft.reviewStatus === "accepted" ? "اثر مالی پس از تأیید انسانی" : `اثر مالی فعلی: صفر ${CURRENCY_LABELS.IRR}`), element("span", "", draft.reviewStatus === "accepted" ? `${formatDisplayNumber(draft.financialEffectIRR)} ${CURRENCY_LABELS.IRR}` : "این داده هنوز فاکتور تأییدشده نیست."));
  card.append(zeroEffect);

  const form = element("div", "ai-fields-grid");
  const controls = new Map();
  draft.fields.forEach((field) => {
    const wrapper = element("label", `ai-field${field.confidence < 0.8 ? " ai-field--low" : ""}`);
    const labelRow = element("span", "ai-field__label");
    labelRow.append(element("strong", "", FIELD_LABELS[field.key] ?? "فیلد استخراج‌شده"), element("small", "", confidenceLabel(field.confidence)));
    let input;
    if (field.key === "invoiceDate") {
      const picker = createPersianDatePicker({ id: `ai-${draft.draftId}-date`, label: "", value: field.confirmedValue ?? field.extractedValue });
      input = picker;
      wrapper.append(labelRow, picker.field);
    } else if (field.key === "resourceId") {
      const select = element("select", "app-select");
      select.append(element("option", "", "انتخاب قلم مالی"));
      targets.forEach((target) => {
        const option = element("option", "", `${target.label} · ${target.targetType === "general_cost" ? "هزینه عمومی" : "خط برآورد"}`);
        option.value = target.targetId;
        select.append(option);
      });
      select.value = field.confirmedValue ?? field.extractedValue ?? "";
      select.disabled = draft.reviewStatus !== "awaitingReview" || !canEdit;
      input = { getValue: () => select.value, input: select };
      wrapper.append(labelRow, select);
    } else {
      const control = element("input", "app-input");
      control.value = field.confirmedValue ?? field.extractedValue ?? "";
      control.disabled = draft.reviewStatus !== "awaitingReview" || !canEdit;
      if (field.key === "totalIRR") control.inputMode = "numeric";
      input = { getValue: () => control.value.trim(), input: control };
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
  const reject = element("button", "button button--danger", "رد استخراج");
  reject.type = "button";
  reject.disabled = !canEdit;
  reject.addEventListener("click", () => {
    const dialog = confirmationDialog({ title: "رد استخراج", message: "استخراج رد می‌شود، اما فایل اصلی حذف نخواهد شد و ورود دستی همچنان در دسترس است.", confirmLabel: "تأیید رد استخراج", onConfirm: async () => { await adapter.rejectExtraction({ draftId: draft.draftId, expectedVersion: draft.version }); await onChanged(); } });
    root.append(dialog);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    dialog.showModal();
  });
  const confirm = element("button", "button button--primary", "تأیید انسانی و ثبت فاکتور");
  confirm.type = "button";
  confirm.disabled = !canEdit;
  confirm.addEventListener("click", () => {
    const values = Object.fromEntries([...controls].map(([key, control]) => [key, control.getValue()]));
    values.totalIRR = normalizeDecimalInput(values.totalIRR);
    if (!values.invoiceDate || !values.vendorName || !values.resourceId || !/^\d+$/.test(values.totalIRR)) {
      feedback.textContent = `تاریخ، فروشنده، تخصیص قلم مالی و مبلغ صحیح ${CURRENCY_LABELS.IRR} برای تأیید الزامی است.`;
      feedback.className = "form-message form-message--error";
      return;
    }
    const fieldConfirmations = draft.fields.filter((field) => values[field.key] !== String(field.extractedValue ?? "")).map((field) => ({ key: field.key, confirmedValue: values[field.key] }));
    const dialog = confirmationDialog({ title: "تأیید استخراج و ایجاد فاکتور", message: "پس از این تأیید، داده بازبینی‌شده به فاکتور تأییدشده تبدیل می‌شود و اثر مالی ایجاد می‌کند.", confirmLabel: "تأیید نهایی", onConfirm: async () => { await adapter.confirmExtraction({ draftId: draft.draftId, expectedVersion: draft.version, idempotencyKey: crypto.randomUUID(), fieldConfirmations, invoice: values }); await onChanged(); } });
    root.append(dialog);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    dialog.showModal();
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
    copy.append(element("span", "feature-header__eyebrow", "کنترل انسانی الزامی"), element("h1", "", "بازبینی استخراج فاکتور"), element("p", "", "مقادیر استخراج‌شده را با فایل اصلی تطبیق دهید؛ فیلدهای کم‌اطمینان را اصلاح و سپس تصمیم نهایی را ثبت کنید."));
    const actions = element("div", "feature-header__actions");
    const files = element("a", "button button--ghost", "بازگشت به فایل‌ها");
    files.href = "#/invoice-files";
    const manual = element("a", "button button--ghost", "ورود دستی فاکتور");
    manual.href = "#/invoices";
    actions.append(files, manual);
    header.append(copy, actions);

    if (state.status === REQUEST_STATUS.LOADING) {
      root.replaceChildren(header, element("section", "state-card", "در حال دریافت پیش‌نویس‌های استخراج…"));
      return;
    }
    if (state.status === REQUEST_STATUS.EMPTY) {
      const empty = element("section", "state-card");
      empty.append(element("h2", "", "استخراجی برای بازبینی وجود ندارد"), element("p", "", "ابتدا یک تصویر یا فایل صوتی بارگذاری و پردازش را شروع کنید."));
      root.replaceChildren(header, empty);
      return;
    }
    if (state.status === REQUEST_STATUS.ERROR || state.status === REQUEST_STATUS.DENIED) {
      const error = element("section", "state-card state-card--danger");
      error.append(element("h2", "", state.status === REQUEST_STATUS.DENIED ? "دسترسی ندارید" : "دریافت بازبینی‌ها انجام نشد"), element("p", "", state.error?.message ?? "دوباره تلاش کنید."));
      root.replaceChildren(header, error);
      return;
    }
    const list = element("div", "ai-review-list");
    state.data.drafts.forEach((draft) => list.append(reviewCard({ draft, targets: state.data.targets, adapter, canEdit, onChanged: load, root })));
    root.replaceChildren(header, list);
  }

  load();
  return root;
}
