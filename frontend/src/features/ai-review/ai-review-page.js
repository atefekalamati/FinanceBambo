import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { createPermissionNotice } from "../../shared/components/permission-notice.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, irrToDisplayValue, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { element } from "../../shared/dom/elements.js";
import { fieldValue, invoiceLines, linesTotalIrr, proposedLines, reconcile,
         rowAmountIrr, unattachedRows } from "./extraction-lines.js";

// The keys the BACKEND emits. `vendorName` and `totalIRR` were this page's names for
// them and the backend has never sent either: they came from the mock adapter this
// screen was built against, so every real extraction rendered "اطلاعات خوانده‌شده" for
// the supplier and the total, and the currency-aware total label never appeared at all.
// `resourceId` stays -- it is chosen by the reviewer here, not extracted.
const FIELD_LABELS = Object.freeze({
  invoiceNumber: "شماره فاکتور",
  invoiceDate: "تاریخ فاکتور",
  supplierName: "فروشنده یا ارائه‌دهنده",
  buyerName: "خریدار",
  currency: "واحد پول",
  totalAmount: "مبلغ نهایی",
  taxAmount: "مالیات",
  items: "اقلام فاکتور",
  rawText: "متن خوانده‌شده",
  voiceTranscript: "رونوشت گفتار",
  speechProvider: "موتور تبدیل گفتار",
  validationStatus: "وضعیت بررسی خودکار",
  parserWarnings: "هشدارهای خواندن",
  resourceId: "تخصیص به قلم هزینه",
});

/* Read from the document, not asked of the reviewer.
 *
 * `items` became the line editor below and must not also appear as a single-line input
 * holding «[object Object]». The rest are PROVENANCE: which engine read this, how sure it
 * said it was, and — for speech — the transcript itself.
 *
 * The transcript is the load-bearing one. The service keeps it precisely because a spoken
 * amount and a printed one can disagree, and it is the only evidence they do; an input a
 * reviewer can type into is not evidence. It is shown beside the recording instead, whole
 * and read-only. */
const LINE_EDITOR_KEYS = Object.freeze(new Set(["items"]));
const PROVENANCE_KEYS = Object.freeze(new Set([
  "voiceTranscript", "rawText", "speechProvider", "source",
  "extractionSource", "extractionConfidence",
  "tableRows", "tablePageKind", "tableConfidence", "tableColumnSource",
]));

const REVIEW_LABELS = Object.freeze({
  awaitingReview: "نیازمند بررسی",
  accepted: "پذیرفته‌شده",
  rejected: "ردشده",
});

/* «۸۷ درصد اطمینان», or the honest gap.
 *
 * The speech provider reports no per-segment probability and the service sends null
 * rather than a figure invented beside it -- «a missing confidence is a fact; a
 * fabricated one is a claim». `Math.round(Number(null) * 100)` is 0, so the old form
 * printed «۰ درصد اطمینان» on a reading nobody had scored, which is a worse claim than
 * either. */
function confidenceLabel(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "اطمینان اندازه‌گیری نشده";
  return `${formatDisplayNumber(String(Math.round(value * 100)))} درصد اطمینان`;
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

/* Exported for the test that holds the original-file rule still: the card must
   not ask the service for a document this account may not have. */
export function reviewCard({ draft, targets, adapter, canEdit, onChanged, root }) {
  const card = element("article", "ai-review-card");
  const header = element("header", "ai-review-card__header");
  const title = element("div");
  title.append(element("span", "feature-header__eyebrow", draft.file.logicalType === "invoice_image" ? "پردازش تصویر فاکتور" : "پردازش صدای فارسی"), element("h2", "", draft.file.originalNameSafe));
  header.append(title, element("span", `file-status ai-review-status--${draft.reviewStatus}`, REVIEW_LABELS[draft.reviewStatus] ?? "نامشخص"));
  card.append(header);

  const zeroEffect = element("div", "ai-zero-effect");
  zeroEffect.append(element("strong", "", draft.reviewStatus === "accepted" ? "اثر مالی پس از تأیید انسانی" : `اثر مالی فعلی: صفر ${getDisplayCurrencyLabel()}`), element("span", "", draft.reviewStatus === "accepted" ? formatTomanFromIrr(draft.financialEffectIRR) : "این داده هنوز فاکتور تأییدشده نیست."));
  card.append(zeroEffect);

  // PRD section 12 requires the original file beside the extracted fields, and
  // the card's own copy tells the reader to compare against it.
  //
  // The original is the one thing on this card an account may not merely read.
  // Everything else here is data the extractor produced; this is the document
  // itself, and the service answers 404 for an account without the grant — so
  // asking for it anyway would draw a broken image where the invoice should be
  // and leave the reader guessing whether the upload failed. The refusal is
  // stated instead, in the same words as every other one in this module.
  const source = element("figure", "ai-review-source");
  // Not requested at all without the permission. The Backend answers 404 either way, but
  // asking would put a broken image where an explanation belongs, and the reader would be
  // left guessing whether the file is missing or they are.
  const contentUrl = canEdit ? (adapter.getFileContentUrl?.(draft.file.fileId) ?? null) : null;
  if (!canEdit) {
    source.append(element("figcaption", "", "نمایش فایل اصلی نیازمند مجوز «مدیریت فاکتورها» است."));
  } else if (!contentUrl) {
    source.append(element("figcaption", "", "پیش‌نمایش فایل اصلی در این محیط در دسترس نیست."));
  } else if (draft.file.logicalType === "invoice_image") {
    const image = element("img", "ai-review-source__image");
    image.src = contentUrl;
    image.alt = `تصویر اصلی فاکتور: ${draft.file.originalNameSafe}`;
    image.loading = "lazy";
    source.append(image, element("figcaption", "", "تصویر اصلی؛ اطلاعات خوانده‌شده را با آن تطبیق دهید."));
  } else {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = contentUrl;
    audio.className = "ai-review-source__audio";
    source.append(audio, element("figcaption", "", "فایل صوتی اصلی؛ اطلاعات خوانده‌شده را با آن تطبیق دهید."));
  }
  card.append(source);

  /* The transcript, whole and read-only, where the document's image would be.
     It is the evidence that a spoken amount and the figures below it disagree, and a box
     somebody can type into is not evidence. */
  /* Two different things under one block. `voiceTranscript` is what somebody SAID;
     `rawText` on an image path is what the OCR READ off the page. Calling the second one
     «رونوشت گفتار» -- which it was called until a probe showed «فاكتور فروش» sitting under
     that heading on a scanned invoice -- names the wrong act and the wrong evidence. */
  const spoken = fieldValue(draft, "voiceTranscript");
  const transcript = spoken ?? fieldValue(draft, "rawText");
  if (transcript && String(transcript).trim()) {
    /* Open for speech, folded for a scan.
       A transcript IS the evidence on the voice path -- there is nothing else to compare
       a spoken amount against -- so it is open and whole. OCR text is not: the page it
       was read from is right above it, and left open it ran to sixty lines and pushed the
       lines and the buttons off the card. Folded, never hidden: the reader opens it when
       the reading and the figures disagree, which is the only time they need it. */
    const block = element("details", "ai-review-transcript");
    block.open = Boolean(spoken);
    block.append(element("summary", "ai-review-transcript__summary",
                   spoken ? FIELD_LABELS.voiceTranscript : FIELD_LABELS.rawText),
                 element("p", "ai-review-transcript__text", String(transcript).trim()));
    card.append(block);
  }

  const form = element("div", "ai-fields-grid");
  const controls = new Map();
  draft.fields.filter((field) => !LINE_EDITOR_KEYS.has(field.key)
                              && !PROVENANCE_KEYS.has(field.key)).forEach((field) => {
    /* `confidence < 0.8` is false for null, so an UNMEASURED reading used to pass as a
       confident one. The speech provider reports no per-segment probability and the
       service refuses to invent a number for it, so the card says which it is. */
    const measured = typeof field.confidence === "number";
    const wrapper = element("label",
      `ai-field${measured && field.confidence < 0.8 ? " ai-field--low" : ""}`
      + (measured ? "" : " ai-field--unmeasured"));
    const labelRow = element("span", "ai-field__label");
    const fieldLabel = field.key === "totalAmount" ? `${FIELD_LABELS[field.key]} به ${getDisplayCurrencyLabel()}` : FIELD_LABELS[field.key];
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

  /* THE LINES, AND WHERE EACH ONE'S MONEY GOES.
     This is what decides whether the invoice reaches the level-one chart: a line carrying
     an estimate line lands on that activity's stage, and a general cost lands nowhere on
     it. The card cannot choose for the reviewer -- neither a document nor a recording says
     which activity a purchase belongs to -- so each row asks, and a row nobody has
     answered for blocks the confirmation by name. */
  const rows = proposedLines(draft);
  const lineEditor = element("div", "ai-lines");
  const lineTotal = element("p", "ai-lines__total");
  const lineNote = element("p", "ai-lines__note");

  function paintTotals() {
    lineTotal.textContent = `جمع خطوط: ${formatTomanFromIrr(linesTotalIrr(rows))}`;
    const check = reconcile(rows, draft);
    if (!check || check.matches) {
      lineNote.textContent = check
        ? "با مبلغ نهایی خوانده‌شده می‌خواند."
        : "";
      lineNote.className = "ai-lines__note ai-lines__note--ok";
      return;
    }
    /* The draft against ITSELF -- never against another invoice. The service refuses to
       assume two uploads describe the same document, and neither does this. */
    lineNote.textContent = `با مبلغ نهایی خوانده‌شده (${formatTomanFromIrr(check.statedIrr)}) `
      + `${formatTomanFromIrr(check.differenceIrr)} ${check.over ? "بیشتر" : "کمتر"} است.`;
    lineNote.className = "ai-lines__note ai-lines__note--differs";
  }

  rows.forEach((row) => {
    const box = element("div", "ai-line");
    box.append(element("p", "ai-line__name", row.description || "قلم بدون نام"));

    const targetField = element("label", "form-field");
    targetField.append(element("span", "form-label", "این هزینه برای کدام ردیف یا فعالیت است؟"));
    const targetSelect = element("select", "app-select");
    const blank = element("option", "", "انتخاب کنید");
    blank.value = "";
    targetSelect.append(blank);
    targets.forEach((target) => {
      const option = element("option", "",
        `${target.label} · ${target.targetType === "general_cost" ? "هزینه‌های عمومی پروژه" : "ردیف برآورد"}`);
      option.value = target.targetId;
      targetSelect.append(option);
    });
    targetSelect.value = row.targetId ?? "";
    targetField.append(targetSelect);

    /* Said before the money is committed, not discovered afterwards. A general cost is
       not lost money -- it counts in the actual cost, the monthly trend and the breakdown
       by type -- but it belongs to no activity, so `by_wbs` places it in no node and the
       level-one chart cannot draw it. */
    const generalNote = element("p", "invoice-warning",
      "هزینه عمومی به هیچ مرحله‌ای وصل نمی‌شود، پس در نمودار «گزارش مالی سطح ۱» دیده نمی‌شود. "
      + "اگر این خرید برای مرحله مشخصی است، همان ردیف برآورد را انتخاب کنید.");
    generalNote.hidden = true;

    const numbers = element("div", "ai-line__numbers");
    const make = (label, value, key, mode) => {
      const wrap = element("label", "form-field");
      wrap.append(element("span", "form-label", label));
      const input = element("input", "app-input");
      input.value = value ?? "";
      input.inputMode = mode;
      input.addEventListener("input", () => { row[key] = input.value; paintTotals(); });
      wrap.append(input);
      numbers.append(wrap);
      return input;
    };
    make("مقدار", row.quantity, "quantity", "decimal");
    make(`قیمت واحد به ${getDisplayCurrencyLabel()}`, row.unitPrice, "unitPrice", "decimal");
    make(`مبلغ خط به ${getDisplayCurrencyLabel()}`, row.amount, "amount", "decimal");

    targetSelect.addEventListener("change", () => {
      row.targetId = targetSelect.value || null;
      const chosen = targets.find((item) => item.targetId === row.targetId);
      generalNote.hidden = chosen?.targetType !== "general_cost";
      paintTotals();
    });
    [targetSelect, ...numbers.querySelectorAll("input")].forEach((control) => {
      control.disabled = draft.reviewStatus !== "awaitingReview" || !canEdit;
    });
    box.append(targetField, generalNote, numbers);
    lineEditor.append(box);
  });
  paintTotals();
  lineEditor.append(lineTotal, lineNote);
  card.append(element("h3", "ai-lines__heading", "خطوط فاکتور و تخصیص آن‌ها"), lineEditor);
  if (draft.reviewStatus !== "awaitingReview") {
    if (draft.linkedInvoiceId) {
      const invoiceLink = element("a", "button button--ghost", "مشاهده فاکتورهای ثبت‌شده");
      invoiceLink.href = "#finance/invoices";
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
  /* Which readings the reviewer has changed, in the service's own `(key, confirmedValue)`
     shape -- the same one `PATCH` and `confirm` both take, because they are the same act.
     Compared against `extractedValue` and never against `confirmedValue`: `confirm`
     rebuilds its fields from `edits.get(key, extracted_value)`, so a correction saved
     earlier and not resent would silently revert to what the model read. */
  const corrections = () => {
    const values = Object.fromEntries([...controls].map(([key, control]) => [key, control.getValue()]));
    return draft.fields
      .filter((field) => Object.hasOwn(values, field.key)
                      && values[field.key] !== String(field.extractedValue ?? ""))
      .map((field) => ({ key: field.key, confirmedValue: values[field.key] }));
  };

  /* Save without deciding.
     The draft keeps `awaitingReview` and its effect stays zero; this is the step that used
     to be impossible -- correct a misheard amount, look at what you corrected, and only
     then decide. The card is NOT rebuilt afterwards: the reviewer's line targets and
     amounts live here and repainting would throw away the work they came to do. */
  const save = element("button", "button button--ghost", "ذخیره تصحیحات");
  save.type = "button";
  save.disabled = !canEdit;
  save.addEventListener("click", async () => {
    const fieldEdits = corrections();
    if (!fieldEdits.length) {
      feedback.textContent = "تغییری برای ذخیره نیست.";
      feedback.className = "form-message";
      return;
    }
    save.disabled = true;
    try {
      const updated = await adapter.editExtraction({
        draftId: draft.draftId, expectedVersion: draft.version, fieldEdits });
      /* Carry the new version and the saved values forward. Without this the next write
         is refused as stale, which is what an optimistic version is for and not a thing
         to route around. */
      draft.version = updated?.version ?? draft.version;
      (updated?.fields ?? []).forEach((field) => {
        const mine = draft.fields.find((item) => item.key === field.key);
        if (mine) mine.confirmedValue = field.confirmedValue ?? null;
      });
      feedback.textContent = `${formatDisplayNumber(String(fieldEdits.length))} تصحیح ذخیره شد. `
        + "پیش‌نویس هنوز تأیید نشده و اثر مالی ندارد.";
      feedback.className = "form-message form-message--success";
    } catch (error) {
      /* The service's own refusal, verbatim. It owns which fields state provenance and
         cannot be corrected; a second list kept here would disagree with it the first
         time either changed, and the reader would be told the wrong reason. */
      feedback.textContent = formatApiErrorMessage(error, "ذخیره تصحیحات انجام نشد.");
      feedback.className = "form-message form-message--error";
    } finally {
      save.disabled = !canEdit;
    }
  });

  const confirm = element("button", "button button--primary", "تأیید انسانی و ثبت فاکتور");
  confirm.type = "button";
  confirm.disabled = !canEdit;
  confirm.addEventListener("click", () => {
    const values = Object.fromEntries([...controls].map(([key, control]) => [key, control.getValue()]));
    /* The service's own key names. `vendorName` and `totalIRR` were this page's, they came
       from the mock adapter it was built against, and the backend has never sent either --
       so these three tests read `undefined` and the confirmation could not succeed on any
       real extraction. The labels were corrected; this was left behind. */
    const missing = [];
    if (!values.invoiceDate) missing.push("تاریخ فاکتور");
    if (!values.supplierName) missing.push("فروشنده");
    const waiting = unattachedRows(rows);
    if (waiting.length) missing.push(`تخصیص ${formatDisplayNumber(String(waiting.length))} خط`);
    const unpriced = rows.filter((row) => rowAmountIrr(row) === null);
    if (unpriced.length) missing.push(`مبلغ ${formatDisplayNumber(String(unpriced.length))} خط`);
    if (missing.length) {
      feedback.textContent = `برای تأیید لازم است: ${missing.join("، ")}.`;
      feedback.className = "form-message form-message--error";
      return;
    }
    const lines = invoiceLines(rows, targets);
    const fieldConfirmations = corrections();
    const dialog = confirmationDialog({ title: "تأیید نهایی و ایجاد فاکتور", message: "پس از این تأیید، پیش‌نویس بررسی‌شده به فاکتور تأییدشده تبدیل می‌شود و اثر مالی ایجاد می‌کند.", confirmLabel: "تأیید نهایی", onConfirm: async () => { await adapter.confirmExtraction({ draftId: draft.draftId, expectedVersion: draft.version, idempotencyKey: crypto.randomUUID(), fieldConfirmations, invoice: { invoiceDate: values.invoiceDate, vendorName: values.supplierName, lines } }); await onChanged(); } });
    root.append(dialog);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    showAccessibleDialog(dialog);
  });
  actions.append(retry, save, reject, confirm);
  card.append(feedback, actions);
  return card;
}

export function createAiReviewPage({ context, adapter }) {
  const root = element("div", "ai-review-page");
  // Reviewing an extraction IS invoice work: accepting one writes an invoice.
  const canEdit = capabilitiesFor(context).manageInvoice;
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
    const header = createFinancePageHeader("بررسی هوشمند فاکتور");
    const actions = element("div", "finance-page-actions");
    const files = element("a", "button button--ghost", "بازگشت به فایل‌ها");
    files.href = "#finance/invoice-files";
    const manual = element("a", "button button--ghost", "ورود دستی فاکتور");
    manual.href = "#finance/invoices";
    actions.append(files, manual);

    root.replaceChildren(header, actions, renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  function renderContent(data) {
    const fragment = document.createDocumentFragment();
    // The cards already disable every field and button they own. What they
    // cannot say on their own is why all of them are off at once.
    if (!canEdit) fragment.append(createPermissionNotice("بازبینی و تأیید داده استخراج‌شده"));
    const list = element("div", "ai-review-list");
    data.drafts.forEach((draft) => list.append(reviewCard({ draft, targets: data.targets, adapter, canEdit, onChanged: load, root })));
    fragment.append(list);
    return fragment;
  }

  function renderEmpty() {
    const card = element("section", "state-card ai-review-empty");
    card.append(element("h2", "", "پیش‌نویسی برای بررسی وجود ندارد"), element("p", "", "ابتدا یک تصویر یا فایل صوتی بارگذاری و پردازش را شروع کنید."));
    const upload = element("a", "button button--primary", "رفتن به بارگذاری تصویر و صدا");
    upload.href = "#finance/invoice-files";
    card.append(upload);
    return card;
  }

  load();
  return root;
}
