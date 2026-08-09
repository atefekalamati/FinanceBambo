import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { hasPermission } from "../../core/auth/permissions.js";
import { formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { validateInvoiceFile } from "./file-upload-validation.js";

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

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

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
      message.textContent = `${error.message || "بارگذاری انجام نشد."}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
      message.className = "form-message form-message--error";
    } finally {
      submit.textContent = "بارگذاری فایل";
      submit.disabled = true;
    }
  });

  card.append(heading, copy, limitText, label, submit, message);
  return card;
}

function renderFiles(files) {
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
    list.append(card);
  });
  section.append(list);
  return section;
}

export function createInvoiceFilesPage({ context, adapter }) {
  const root = element("div", "invoice-files-page");
  const canUpload = hasPermission(context, "finance.edit");
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
    const actions = element("div", "feature-header__actions");
    const manual = element("a", "button button--ghost", "ورود دستی فاکتور");
    manual.href = "#/invoices";
    actions.append(manual);
    header.append(copy, actions);

    if (state.status === REQUEST_STATUS.LOADING) {
      root.replaceChildren(header, element("section", "state-card", "در حال دریافت وضعیت فایل‌ها…"));
      return;
    }
    if (state.status === REQUEST_STATUS.DENIED || state.status === REQUEST_STATUS.ERROR) {
      const card = element("section", `state-card${state.status === REQUEST_STATUS.ERROR ? " state-card--danger" : ""}`);
      card.append(element("h2", "", state.status === REQUEST_STATUS.DENIED ? "دسترسی ندارید" : "دریافت اطلاعات انجام نشد"), element("p", "", state.error?.message ?? "دوباره تلاش کنید."));
      if (state.status === REQUEST_STATUS.ERROR) {
        const retry = element("button", "button button--primary", "تلاش دوباره");
        retry.type = "button";
        retry.addEventListener("click", load);
        card.append(retry);
      }
      root.replaceChildren(header, card);
      return;
    }

    const permissionNote = canUpload ? document.createDocumentFragment() : element("div", "state-card state-card--danger", "این صفحه فقط برای مشاهده است؛ مجوز ویرایش مالی برای بارگذاری لازم است.");
    const uploadGrid = element("div", "file-upload-grid");
    uploadGrid.append(
      createUploadCard({ logicalType: "invoice_image", title: "تصویر فاکتور", description: "تصویر خوانا از فاکتور را بارگذاری کنید.", accept: ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp", limit: "قالب‌های مجاز: جی‌پگ، پی‌ان‌جی و وب‌پی · حداکثر ۱۰ مگابایت", adapter, onUploaded: load, canUpload }),
      createUploadCard({ logicalType: "invoice_voice", title: "صدای فاکتور", description: "شرح فارسی فاکتور را به‌صورت فایل صوتی بارگذاری کنید.", accept: ".mp3,.m4a,.wav,.ogg,audio/mpeg,audio/mp4,audio/wav,audio/ogg", limit: "قالب‌های مجاز: ام‌پی‌تری، ام‌فور‌ای، ویو و اوجی‌جی · حداکثر ۲۵ مگابایت", adapter, onUploaded: load, canUpload }),
    );
    const securityNote = element("aside", "file-security-note");
    securityNote.append(element("strong", "", "کنترل نهایی با سرور است"), element("p", "", "بررسی سمت مرورگر فقط برای راهنمایی سریع کاربر است. سرور باید پسوند، نوع محتوا، امضای واقعی فایل، اندازه و محدوده پروژه را دوباره اعتبارسنجی کند."));
    root.replaceChildren(header, permissionNote, uploadGrid, securityNote, renderFiles(state.data));
  }

  load();
  return root;
}
