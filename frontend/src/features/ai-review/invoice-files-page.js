import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { validateInvoiceFile } from "./file-upload-validation.js";
import { waitForExtraction } from "./extraction-polling.js";
import { element } from "../../shared/dom/elements.js";

const STATUS_LABELS = Object.freeze({
  uploaded: "بارگذاری‌شده",
  processing: "در حال پردازش",
  ready: "آماده بررسی",
  failed: "پردازش ناموفق",
});

const MIME_LABELS = Object.freeze({
  "image/jpeg": "تصویر جی‌پگ",
  "image/png": "تصویر پی‌ان‌جی",
  "image/webp": "تصویر وب‌پی",
  "audio/mpeg": "صدای ام‌پی‌تری",
  "audio/mp4": "صدای ام‌فور‌ای",
  "audio/wav": "صدای ویو",
  "audio/ogg": "صدای اوجی‌جی",
});

function formatFileSize(value) {
  const bytes = Number(value);
  if (bytes < 1024 * 1024) return `${formatDisplayNumber((bytes / 1024).toFixed(1))} کیلوبایت`;
  return `${formatDisplayNumber((bytes / (1024 * 1024)).toFixed(1))} مگابایت`;
}

function createUploadCard({ logicalType, title, description, accept, limit, adapter, onUploaded, canUpload }) {
  const card = element("section", "file-upload-card");
  const heading = element("h2", "", title);
  const copy = element("p", "", description);
  const limitText = element("small", "file-upload-card__limit", limit);
  const label = element("label", "file-drop-field");
  const prompt = element("span", "file-drop-field__prompt", "فایل را انتخاب کنید");
  const selected = element("span", "file-drop-field__selected", "فایلی انتخاب نشده است");
  const input = element("input", "sr-only");
  input.type = "file";
  input.accept = accept;
  input.disabled = !canUpload;
  label.append(input, prompt, selected);
  const message = element("div", "form-message");
  message.setAttribute("aria-live", "assertive");
  const submit = element("button", "button button--primary", canUpload ? "بارگذاری فایل" : "بدون مجوز بارگذاری");
  submit.type = "button";
  submit.disabled = true;

  input.addEventListener("change", () => {
    message.textContent = "";
    message.className = "form-message";
    const file = input.files?.[0];
    selected.textContent = file ? `${file.name} · ${formatFileSize(file.size)}` : "فایلی انتخاب نشده است";
    const validation = validateInvoiceFile(file, logicalType);
    submit.disabled = !canUpload || !validation.valid;
    if (file && !validation.valid) {
      message.textContent = Object.values(validation.errors).join(" ");
      message.className = "form-message form-message--error";
    }
  });

  submit.addEventListener("click", async () => {
    const file = input.files?.[0];
    const validation = validateInvoiceFile(file, logicalType);
    if (!validation.valid) return;
    submit.disabled = true;
    submit.textContent = "در حال بارگذاری…";
    message.textContent = "";
    try {
      await adapter.uploadFile({ file, logicalType });
      input.value = "";
      selected.textContent = "فایلی انتخاب نشده است";
      message.textContent = "فایل با موفقیت بارگذاری شد و هنوز هیچ اثر مالی ندارد.";
      await onUploaded();
    } catch (error) {
      message.textContent = formatApiErrorMessage(error, "بارگذاری انجام نشد.");
      message.className = "form-message form-message--error";
    } finally {
      submit.textContent = "بارگذاری فایل";
      submit.disabled = true;
    }
  });

  card.append(heading, copy, limitText, label, submit, message);
  return card;
}

function renderFiles(files, { adapter, canUpload, onChanged }) {
  const section = element("section", "uploaded-files");
  const head = element("div", "section-heading");
  const copy = element("div");
  copy.append(element("span", "", "فایل‌های همین نشست"), element("h2", "", "وضعیت فایل‌های بارگذاری‌شده"));
  head.append(copy);
  section.append(head);

  if (!files.length) {
    section.append(element("div", "state-card file-list-empty", "هنوز فایلی در این نشست بارگذاری نشده است."));
    return section;
  }

  const list = element("div", "uploaded-files__list");
  files.forEach((file) => {
    const card = element("article", "uploaded-file-card");
    const title = element("div", "uploaded-file-card__title");
    title.append(
      element("strong", "", file.originalNameSafe),
      element("span", `file-status file-status--${file.processingStatus}`, STATUS_LABELS[file.processingStatus] ?? "نامشخص"),
    );
    const details = element("dl", "uploaded-file-card__details");
    [
      ["نوع ورودی", file.logicalType === "invoice_image" ? "تصویر فاکتور" : "صدای فاکتور"],
      ["حجم دقیق", formatFileSize(file.sizeBytes)],
      ["نوع محتوا", MIME_LABELS[file.mimeType] ?? "نوع تعریف‌نشده"],
      ["زمان بارگذاری", formatSystemDateTime(file.uploadedAt)],
    ].forEach(([term, value]) => {
      details.append(element("dt", "", term), element("dd", "", value));
    });
    card.append(title, details, element("p", "uploaded-file-card__note", "فایل و استخراج احتمالی آن تا تأیید انسانی، اثر مالی ندارد."));
    if (file.processingStatus === "failed") {
      const failure = element("div", "file-processing-failure");
      failure.append(element("strong", "", "پردازش ناموفق بود"), element("p", "", file.processingError || "فایل اصلی حفظ شده است؛ دوباره تلاش کنید یا فاکتور را دستی وارد کنید."));
      card.append(failure);
    }
    const actions = element("div", "uploaded-file-card__actions");
    const process = element("button", "button button--primary", file.processingStatus === "failed" ? "پردازش دوباره" : "شروع پردازش");
    process.type = "button";
    process.disabled = !canUpload || file.processingStatus === "processing";
    process.addEventListener("click", async () => {
      process.disabled = true;
      process.textContent = "در حال پردازش…";
      // The request answers 202 the moment the work is queued, so starting the extraction
      // and finishing it are no longer the same event. A rejected start is deliberately NOT
      // told apart from an accepted one: a duplicate request is refused with 503 while the
      // file really is processing, and the poll below reports what actually happened in
      // either case. A start refused for a permission reason leaves the file `uploaded`,
      // which the poll returns at once.
      try {
        await adapter.startExtraction(file.fileId);
      } catch (error) {
        // Intentionally ignored: the file's own status is the answer, not this rejection.
      }
      const settled = await waitForExtraction({ adapter, fileId: file.fileId });
      // Always refresh. The card renders `ready` or `failed` from the file's own row, and
      // the failure block and the "پردازش دوباره" button already come from that status --
      // so retry needs nothing new here.
      await onChanged();
      if (settled === "ready") window.location.hash = "#/ai-review";
    });
    const reviews = element("a", "button button--ghost", "مشاهده بازبینی‌ها");
    reviews.href = "#/ai-review";
    actions.append(process, reviews);
    card.append(actions);
    list.append(card);
  });
  section.append(list);
  return section;
}

export function createInvoiceFilesPage({ context, adapter }) {
  const root = element("div", "invoice-files-page");
  const canUpload = capabilitiesFor(context).writeFinance;
  let state = createRequestState(REQUEST_STATUS.LOADING);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const files = await adapter.getFiles();
      state = createRequestState(REQUEST_STATUS.SUCCESS, files);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function paint() {
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(
      element("span", "feature-header__eyebrow", "ورودی هوشمند فاکتور"),
      element("h1", "", "بارگذاری تصویر و صدا"),
      element("p", "", "فایل فاکتور را برای پردازش بعدی ثبت کنید. بارگذاری یا استخراج به‌تنهایی هیچ اثر مالی ایجاد نمی‌کند."),
    );
    const actions = element("div", "feature-header__actions feature-header__other-actions");
    const manual = element("a", "button button--ghost", "ورود دستی فاکتور");
    manual.href = "#/invoices";
    actions.append(manual);
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.classList.add("finance-back-link");
    back.href = "#/finance";
    const navigation = element("div", "feature-header__navigation");
    navigation.append(actions, back);
    header.append(copy, navigation);

    root.replaceChildren(header, renderPageState(state, { renderContent, onRetry: load }));
  }

  function renderContent(files) {
    const fragment = document.createDocumentFragment();
    const permissionNote = canUpload ? document.createDocumentFragment() : element("div", "state-card state-card--danger", "این صفحه فقط برای مشاهده است؛ مجوز ویرایش مالی برای بارگذاری لازم است.");
    const uploadGrid = element("div", "file-upload-grid");
    uploadGrid.append(
      createUploadCard({ logicalType: "invoice_image", title: "تصویر فاکتور", description: "تصویر خوانا از فاکتور را بارگذاری کنید.", accept: ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp", limit: "قالب‌های مجاز: جی‌پگ، پی‌ان‌جی و وب‌پی · حداکثر ۱۰ مگابایت", adapter, onUploaded: load, canUpload }),
      createUploadCard({ logicalType: "invoice_voice", title: "صدای فاکتور", description: "شرح فارسی فاکتور را به‌صورت فایل صوتی بارگذاری کنید.", accept: ".mp3,.m4a,.wav,.ogg,audio/mpeg,audio/mp4,audio/wav,audio/ogg", limit: "قالب‌های مجاز: ام‌پی‌تری، ام‌فور‌ای، ویو و اوجی‌جی · حداکثر ۲۵ مگابایت", adapter, onUploaded: load, canUpload }),
    );
    const securityNote = element("aside", "file-security-note");
    securityNote.append(element("strong", "", "کنترل نهایی با سرور است"), element("p", "", "بررسی سمت مرورگر فقط برای راهنمایی سریع کاربر است. سرور باید پسوند، نوع محتوا، امضای واقعی فایل، اندازه و محدوده پروژه را دوباره اعتبارسنجی کند."));
    fragment.append(permissionNote, uploadGrid, securityNote, renderFiles(files, { adapter, canUpload, onChanged: load }));
    return fragment;
  }

  load();
  return root;
}
