import { ApiError } from "../../core/api/api-error.js";
import { validateInvoiceFile } from "../../features/ai-review/file-upload-validation.js";

function wait(duration = 280) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

function safeDisplayName(value) {
  return String(value).replace(/[\\/:*?"<>|\u0000-\u001f]/g, "-").slice(0, 180) || "فایل";
}

export function createMockAttachmentsAdapter(context, { initialState = "success" } = {}) {
  const files = [];
  const drafts = [];
  const confirmationKeys = new Map();

  async function getFiles() {
    await wait(180);
    if (!context.permissionCodes?.includes("finance.view")) {
      throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز مشاهده فایل‌های مالی وجود ندارد." });
    }
    if (initialState === "error") {
      throw new ApiError({ status: 503, code: "FINANCE_FILES_UNAVAILABLE", message: "دریافت فایل‌های مالی انجام نشد.", requestId: "mock-files-001" });
    }
    return structuredClone(files);
  }

  async function uploadFile({ file, logicalType }) {
    await wait(420);
    if (!context.permissionCodes?.includes("finance.edit")) {
      throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز بارگذاری فایل مالی وجود ندارد." });
    }
    const validation = validateInvoiceFile(file, logicalType);
    if (!validation.valid) {
      throw new ApiError({ status: 422, code: "ATTACHMENT_VALIDATION_FAILED", message: Object.values(validation.errors).join(" "), details: validation.errors });
    }
    const fileId = crypto.randomUUID();
    const uploadedAt = new Date().toISOString();
    const record = {
      fileId,
      organizationId: context.organizationId,
      projectId: context.projectId,
      logicalType,
      originalNameSafe: safeDisplayName(file.name),
      storedName: `${fileId}.${validation.values.extension}`,
      mimeType: validation.values.mimeType,
      sizeBytes: validation.values.sizeBytes,
      sha256: "محاسبه و اعتبارسنجی در سرور",
      uploadedBy: context.userId,
      uploadedAt,
      processingStatus: "uploaded",
    };
    files.unshift(record);
    return structuredClone(record);
  }

  function requireEditPermission(message) {
    if (!context.permissionCodes?.includes("finance.edit")) {
      throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message });
    }
  }

  function findFile(fileId) {
    const file = files.find((item) => item.fileId === fileId);
    if (!file) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "فایل مالی پیدا نشد." });
    return file;
  }

  function extractedFields(file) {
    const voice = file.logicalType === "invoice_voice";
    return [
      { key: "invoiceNumber", extractedValue: voice ? "صوتی-۱۴۰۵-۱۲" : "تصویری-۱۴۰۵-۲۱", confirmedValue: null, confidence: voice ? 0.76 : 0.94, editedByUser: false },
      { key: "invoiceDate", extractedValue: "2026-08-09", confirmedValue: null, confidence: 0.91, editedByUser: false },
      { key: "vendorName", extractedValue: voice ? "تأمین‌کننده نمونه صوتی" : "فروشگاه مصالح نمونه", confirmedValue: null, confidence: voice ? 0.58 : 0.83, editedByUser: false },
      { key: "totalIRR", extractedValue: voice ? "185000000" : "248500000", confirmedValue: null, confidence: 0.67, editedByUser: false },
    ];
  }

  async function startExtraction(fileId) {
    requireEditPermission("مجوز شروع پردازش فایل وجود ندارد.");
    const file = findFile(fileId);
    if (file.uploadedBy !== context.userId) throw new ApiError({ status: 403, code: "FINANCE_FORBIDDEN", message: "فقط بارگذار فایل می‌تواند پردازش را شروع کند." });
    if (file.processingStatus === "processing") throw new ApiError({ status: 503, code: "AI_EXTRACTION_FAILED", message: "فایل هم‌اکنون در حال پردازش است." });
    file.processingStatus = "processing";
    await wait(650);
    file.processingStatus = "ready";
    const previousVersions = drafts.filter((item) => item.file.fileId === fileId);
    const draft = {
      draftId: crypto.randomUUID(),
      version: previousVersions.length + 1,
      file: structuredClone(file),
      reviewStatus: "awaitingReview",
      invoiceStatus: "draft",
      providerAdapter: file.logicalType === "invoice_image" ? "درگاه پردازش تصویر" : "درگاه پردازش صدای فارسی",
      fields: extractedFields(file),
      submittedBy: context.userId,
      financialEffectIRR: "0",
      confirmedBy: null,
      confirmedAt: null,
    };
    drafts.unshift(draft);
    return structuredClone(draft);
  }

  async function getExtractions() {
    await wait(220);
    if (!context.permissionCodes?.includes("finance.view")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز مشاهده بازبینی‌های هوشمند وجود ندارد." });
    return structuredClone(drafts);
  }

  async function retryExtraction(draftId) {
    requireEditPermission("مجوز تکرار پردازش وجود ندارد.");
    const current = drafts.find((item) => item.draftId === draftId);
    if (!current) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "پیش‌نویس استخراج پیدا نشد." });
    if (current.submittedBy !== context.userId) throw new ApiError({ status: 403, code: "FINANCE_FORBIDDEN", message: "فقط بارگذار فایل می‌تواند پردازش را تکرار کند." });
    return startExtraction(current.file.fileId);
  }

  async function rejectExtraction({ draftId, expectedVersion }) {
    requireEditPermission("مجوز ردکردن استخراج وجود ندارد.");
    await wait(280);
    const draft = drafts.find((item) => item.draftId === draftId);
    if (!draft) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "پیش‌نویس استخراج پیدا نشد." });
    if (draft.submittedBy !== context.userId) throw new ApiError({ status: 403, code: "FINANCE_FORBIDDEN", message: "فقط بارگذار فایل می‌تواند استخراج را رد کند." });
    if (draft.reviewStatus !== "awaitingReview" || draft.version !== expectedVersion) throw new ApiError({ status: 409, code: "STALE_VERSION", message: "نسخه بازبینی تغییر کرده است؛ اطلاعات را دوباره دریافت کنید." });
    draft.reviewStatus = "rejected";
    draft.version += 1;
    return structuredClone(draft);
  }

  async function confirmExtraction({ draftId, expectedVersion, idempotencyKey, fieldConfirmations, invoice }) {
    requireEditPermission("مجوز تأیید استخراج وجود ندارد.");
    await wait(480);
    const draft = drafts.find((item) => item.draftId === draftId);
    if (!draft) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "پیش‌نویس استخراج پیدا نشد." });
    if (draft.submittedBy !== context.userId) throw new ApiError({ status: 403, code: "FINANCE_FORBIDDEN", message: "فقط بارگذار فایل می‌تواند استخراج را تأیید کند." });
    const requestKey = String(idempotencyKey ?? "").trim();
    if (draft.reviewStatus === "accepted" && confirmationKeys.get(draftId) === requestKey) return structuredClone(draft);
    if (draft.reviewStatus !== "awaitingReview" || draft.version !== expectedVersion) throw new ApiError({ status: 409, code: "STALE_VERSION", message: "نسخه بازبینی تغییر کرده است؛ اطلاعات را دوباره دریافت کنید." });
    if (!requestKey || !invoice?.invoiceDate || !String(invoice.vendorName ?? "").trim() || !/^\d+$/.test(String(invoice.totalIRR ?? ""))) {
      throw new ApiError({ status: 422, code: "AI_EXTRACTION_FAILED", message: "فیلدهای تأییدشده برای ایجاد فاکتور کامل نیستند." });
    }
    const knownKeys = new Set(draft.fields.map((field) => field.key));
    if (fieldConfirmations.some((item) => !knownKeys.has(item.key))) throw new ApiError({ status: 422, code: "AI_EXTRACTION_FAILED", message: "فیلد ناشناخته در اصلاحات بازبینی وجود دارد." });
    const confirmations = new Map(fieldConfirmations.map((item) => [item.key, item.confirmedValue]));
    draft.fields = draft.fields.map((field) => ({ ...field, confirmedValue: confirmations.get(field.key) ?? field.extractedValue, editedByUser: confirmations.has(field.key) && confirmations.get(field.key) !== field.extractedValue }));
    draft.reviewStatus = "accepted";
    draft.invoiceStatus = "confirmed";
    draft.financialEffectIRR = String(invoice.totalIRR);
    draft.confirmedBy = context.userId;
    draft.confirmedAt = new Date().toISOString();
    draft.version += 1;
    confirmationKeys.set(draftId, requestKey);
    return structuredClone(draft);
  }

  return Object.freeze({ getFiles, uploadFile, startExtraction, getExtractions, retryExtraction, rejectExtraction, confirmExtraction });
}
