import { ApiError } from "../../core/api/api-error.js";
import { validateInvoiceFile } from "../../features/ai-review/file-upload-validation.js";
import { financeBase, formDataWithFile, jsonOptions } from "./api-utils.js";

export function createApiAttachmentsAdapter(context, client, invoiceAdapter) {
  const base = financeBase(context);
  const sessionFiles = [];
  const sessionDrafts = [];
  async function getFiles() {
    return structuredClone(sessionFiles);
  }
  async function uploadFile({ file, logicalType }) {
    const validation = validateInvoiceFile(file, logicalType);
    if (!validation.valid) throw new ApiError({ status: 422, code: "ATTACHMENT_VALIDATION_FAILED", message: Object.values(validation.errors).join(" "), details: validation.errors });
    const result = await client.request(`${base}/files`, { method: "POST", body: formDataWithFile(file, { logicalType }) });
    sessionFiles.unshift(result);
    return structuredClone(result);
  }
  async function startExtraction() {
    throw new ApiError({ status: 501, code: "BACKEND_EXTRACTION_START_MISSING", message: "Endpoint شروع استخراج فایل در Backend فعلی تعریف نشده است." });
  }
  async function getExtractions() {
    return structuredClone(sessionDrafts);
  }
  async function retryExtraction(draftId) {
    const result = await client.request(`${base}/extractions/${encodeURIComponent(draftId)}/retry`, jsonOptions("POST", { hints: {} }));
    sessionDrafts.unshift(result);
    return result;
  }
  async function rejectExtraction() {
    throw new ApiError({ status: 501, code: "BACKEND_EXTRACTION_REJECT_MISSING", message: "Endpoint رد استخراج در Backend فعلی تعریف نشده است." });
  }
  async function confirmExtraction(payload) {
    return client.request(`${base}/extractions/${encodeURIComponent(payload.draftId)}/confirm`, jsonOptions("POST", { expectedVersion: payload.expectedVersion, idempotencyKey: payload.idempotencyKey, fieldConfirmations: payload.fieldConfirmations, invoice: payload.invoice }));
  }
  async function getInvoiceTargets() {
    return invoiceAdapter.getInvoiceTargets();
  }
  return Object.freeze({ getFiles, uploadFile, startExtraction, getExtractions, retryExtraction, rejectExtraction, confirmExtraction, getInvoiceTargets });
}
