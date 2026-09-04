import { ApiError } from "../../core/api/api-error.js";
import { validateInvoiceFile } from "../../features/ai-review/file-upload-validation.js";
import { financeBase, formDataWithFile, jsonOptions } from "./api-utils.js";

export function createApiAttachmentsAdapter(context, client, invoiceAdapter) {
  const base = financeBase(context);
  async function getFiles({ page = 1, pageSize = 50, logicalType = "", processingStatus = "", uploaderId = "" } = {}) {
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    if (logicalType) params.set("logicalType", logicalType);
    if (processingStatus) params.set("processingStatus", processingStatus);
    if (uploaderId) params.set("uploaderId", uploaderId);
    const payload = await client.request(`${base}/files?${params.toString()}`);
    return payload.items;
  }
  async function uploadFile({ file, logicalType }) {
    const validation = validateInvoiceFile(file, logicalType);
    if (!validation.valid) throw new ApiError({ status: 422, code: "ATTACHMENT_VALIDATION_FAILED", message: Object.values(validation.errors).join(" "), details: validation.errors });
    return client.request(`${base}/files`, { method: "POST", body: formDataWithFile(file, { logicalType }) });
  }
  // The async route. The synchronous one held the request open for the whole OCR run --
  // about 35 seconds cold -- so the browser saw a hanging request, and the dev host, which
  // serialises requests behind one lock, stalled every other call behind it. This answers
  // 202 as soon as the work is queued and reports the attachment's own status; the caller
  // watches that status rather than the response.
  async function startExtraction(fileId) {
    return client.request(`${base}/files/${encodeURIComponent(fileId)}/extractions/async`, jsonOptions("POST", { hints: { locale: context.locale ?? "fa-IR" } }));
  }
  async function getExtractions({ page = 1, pageSize = 50, reviewStatus = "", source = "", fileId = "", linkedInvoiceId = "" } = {}) {
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    if (reviewStatus) params.set("reviewStatus", reviewStatus);
    if (source) params.set("source", source);
    if (fileId) params.set("fileId", fileId);
    if (linkedInvoiceId) params.set("linkedInvoiceId", linkedInvoiceId);
    const payload = await client.request(`${base}/extractions?${params.toString()}`);
    return payload.items;
  }
  async function getExtraction(draftId) {
    return client.request(`${base}/extractions/${encodeURIComponent(draftId)}`);
  }
  async function retryExtraction(draftId) {
    return client.request(`${base}/extractions/${encodeURIComponent(draftId)}/retry`, jsonOptions("POST", { hints: { locale: context.locale ?? "fa-IR" } }));
  }
  async function rejectExtraction({ draftId, expectedVersion, reason = null }) {
    return client.request(`${base}/extractions/${encodeURIComponent(draftId)}/reject`, jsonOptions("POST", { expectedVersion, reason }));
  }
  /**
   * The review form yields a single total, which maps to InvoiceLineCreate's
   * lineAmountIrr. The Backend restricts that field: _calculate_lines raises
   * "direct line amount requires a general_cost resource", and the extraction
   * confirm route reaches it through prepare_extracted. Sending the total
   * against a quantified line would be rejected; sending a quantified line
   * without quantity and unitPriceIrr is worse — the same function scores it
   * as (1 x 0) and would silently book a zero-amount line. So the guard below
   * mirrors a Backend rule and must not be relaxed until the extraction
   * contract carries quantity, unit and unit price.
   */
  async function confirmExtraction(payload) {
    const targets = await invoiceAdapter.getInvoiceTargets();
    const target = targets.find((item) => item.targetId === payload.invoice.resourceId);
    if (!target) throw new ApiError({ status: 422, code: "INVOICE_TARGET_INVALID", message: "اتصال داده استخراج‌شده به قلم مالی معتبر نیست." });
    if (target.targetType !== "general_cost") throw new ApiError({ status: 422, code: "EXTRACTION_QUANTIFIED_LINE_DATA_MISSING", message: "برای ثبت روی قلم مقداری، مقدار، واحد و قیمت واحد باید توسط قرارداد استخراج تأمین شود؛ از ورود دستی فاکتور استفاده کنید." });
    const invoice = {
      invoiceNumber: payload.invoice.invoiceNumber || null,
      invoiceDate: payload.invoice.invoiceDate,
      vendorName: payload.invoice.vendorName,
      description: null,
      duplicateReason: null,
      discountIrr: "0",
      taxIrr: "0",
      shippingIrr: "0",
      otherCostsIrr: "0",
      directAdjustmentAllocations: [],
      lines: [{ estimateLineId: null, resourceId: target.resourceId, quantity: null, unit: null, unitPriceIrr: null, lineAmountIrr: payload.invoice.totalIRR, description: null }],
    };
    return client.request(`${base}/extractions/${encodeURIComponent(payload.draftId)}/confirm`, jsonOptions("POST", { expectedVersion: payload.expectedVersion, idempotencyKey: payload.idempotencyKey, fieldConfirmations: payload.fieldConfirmations, invoice }));
  }
  /**
   * The stored file is never served from a public path; this authorised,
   * same-origin endpoint is. A URL is returned rather than bytes so an <img> or
   * <audio> can stream it directly, with no object URL to leak.
   */
  function getFileContentUrl(fileId) {
    return fileId ? `${base}/files/${encodeURIComponent(fileId)}/content` : null;
  }
  async function getInvoiceTargets() {
    return invoiceAdapter.getInvoiceTargets();
  }
  return Object.freeze({ getFiles, uploadFile, startExtraction, getExtractions, getExtraction, retryExtraction, rejectExtraction, confirmExtraction, getInvoiceTargets, getFileContentUrl });
}
