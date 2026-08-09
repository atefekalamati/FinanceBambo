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

  return Object.freeze({ getFiles, uploadFile });
}
