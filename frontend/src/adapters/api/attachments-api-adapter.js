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
  /* A reviewer's corrections, recorded before any decision to confirm.
   *
   * Until this existed the only way to state a better value was to send it INSIDE the
   * confirmation, so a reviewer could not fix a misheard amount, look at the result, and
   * then decide -- the correction and the irreversible act were one button.
   *
   * Changes nothing financial: the draft keeps `awaitingReview`, its effect stays zero,
   * and `confirm` is still the only door to the financial engine. The service writes each
   * edit to `confirmedValue` BESIDE what the model read, so the page reading and the
   * transcript survive every correction.
   *
   * The version moves. The updated draft comes back and the caller must carry it forward,
   * or the next write is refused as stale -- which is the point of an optimistic version
   * and not a thing to work around. */
  async function editExtraction({ draftId, expectedVersion, fieldEdits }) {
    return client.request(`${base}/extractions/${encodeURIComponent(draftId)}`,
      jsonOptions("PATCH", { expectedVersion, fieldEdits }));
  }
  async function rejectExtraction({ draftId, expectedVersion, reason = null }) {
    return client.request(`${base}/extractions/${encodeURIComponent(draftId)}/reject`, jsonOptions("POST", { expectedVersion, reason }));
  }
  /* The reviewed draft, as an invoice.
   *
   * The lines arrive built: the review card asked which estimate line or general cost each
   * one belongs to, and `invoiceLines` turned that into the service's shape. This function
   * used to build a single line itself -- the whole total, no quantity, no rate -- and
   * refuse any target but a general cost, on the stated grounds that «the extraction
   * contract carries quantity, unit and unit price» was not yet true.
   *
   * It was true. `_candidate_fields` maps the model's items to exactly those three, for
   * the image path and the voice path alike. And the refusal it protected had a price:
   * a general cost carries no estimate line, so no activity and no WBS stage can be
   * derived for it, and the level-one chart cannot draw it. Every extracted invoice
   * landed outside that chart, and the message told the reader to type it in by hand.
   *
   * The guard it replaced was real about one thing: a quantified line sent with a null
   * quantity and a null rate would have been read as `1 x 0` and booked as zero. It is not
   * sent that way -- `invoiceLines` sends `lineAmountIrr` on every line, which the service
   * takes as stated and never multiplies. */
  async function confirmExtraction(payload) {
    const lines = payload.invoice.lines ?? [];
    if (!lines.length) {
      throw new ApiError({ status: 422, code: "INVOICE_TARGET_INVALID",
        message: "هیچ خط قابل ثبتی برای این پیش‌نویس ساخته نشد." });
    }
    const invoice = {
      // No invoiceNumber. The extractor still reads the one printed on the supplier's
      // document and the review card still shows it, but it is their number, not this
      // project's: the project's is allocated by the service when the invoice is
      // written. `ReviewedInvoiceCreate` forbids unknown fields, so sending it is a 422.
      invoiceDate: payload.invoice.invoiceDate,
      vendorName: payload.invoice.vendorName,
      description: null,
      duplicateReason: null,
      discountIrr: "0",
      taxIrr: "0",
      shippingIrr: "0",
      otherCostsIrr: "0",
      directAdjustmentAllocations: [],
      lines,
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
  return Object.freeze({ getFiles, uploadFile, startExtraction, getExtractions, getExtraction, editExtraction, retryExtraction, rejectExtraction, confirmExtraction, getInvoiceTargets, getFileContentUrl });
}
