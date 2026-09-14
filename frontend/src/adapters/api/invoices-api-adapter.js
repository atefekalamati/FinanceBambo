import { ApiError } from "../../core/api/api-error.js";
import { financeBase, jsonOptions, mapResource } from "./api-utils.js";

/**
 * InvoiceLineResponse carries estimateLineId and resourceId but no human
 * label, so the label is resolved from the same target list the create form
 * uses. Falling back to the line description showed the note the user typed
 * where the item name belongs.
 */
function mapInvoice(value, targets = []) {
  return {
    invoiceId: value.id,
    // Two forms of one number, both from the service. `invoiceSeq` is the integer
    // the counter allocated -- what to sort and compare on -- and `invoiceNumber`
    // is that number written for a reader, zero-padded to three. Deriving one from
    // the other here would be a second opinion about a fact the service already
    // settled.
    invoiceSeq: value.invoiceSeq ?? null,
    invoiceNumber: value.invoiceNumber,
    invoiceDate: value.invoiceDate,
    vendorName: value.vendorName,
    description: value.description,
    source: value.source,
    invoiceStatus: value.status,
    discountIRR: value.discountIrr,
    taxIRR: value.taxIrr,
    shippingIRR: value.shippingIrr,
    otherCostsIRR: value.otherCostsIrr,
    finalAmountIRR: value.finalAmountIrr,
    financialEffectSign: value.financialEffectSign ?? 1,
    originalInvoiceId: value.originalInvoiceId,
    idempotencyKey: value.idempotencyKey,
    version: value.version,
    submittedBy: value.submittedBy,
    confirmedBy: value.confirmedBy,
    confirmedAt: value.confirmedAt,
    createdAt: value.createdAt,
    rawLinesTotalIRR: value.lines.reduce((sum, line) => sum + BigInt(line.rawAmountIrr), 0n).toString(),
    lines: value.lines.map((line, index) => {
      const targetType = line.estimateLineId ? "estimate_line" : "general_cost";
      const target = targets.find((item) => (line.estimateLineId && item.estimateLineId === line.estimateLineId))
        ?? targets.find((item) => !line.estimateLineId && item.targetType === "general_cost" && item.resourceId === line.resourceId);
      return {
        invoiceLineId: `${value.id}-${index + 1}`,
        targetType,
        targetLabel: target?.label || line.description || "خط فاکتور",
        estimateLineId: line.estimateLineId,
        resourceId: line.resourceId,
        quantity: line.quantity,
        unit: line.unit,
        unitPriceIRR: line.unitPriceIrr,
        lineAmountIRR: line.finalLineAmountIrr,
        description: line.description,
      };
    }),
  };
}

function exactPreview(lines, adjustments) {
  const prepared = lines.map((line) => {
    if (line.targetType === "general_cost") return { ...line, lineAmountIRR: line.lineAmountIRR };
    const [integer, fraction = ""] = line.quantity.split(".");
    const scaled = BigInt(`${integer}${fraction.padEnd(4, "0")}`);
    return { ...line, lineAmountIRR: ((scaled * BigInt(line.unitPriceIRR) + 5000n) / 10000n).toString() };
  });
  const rawLinesTotalIRR = prepared.reduce((sum, line) => sum + BigInt(line.lineAmountIRR), 0n).toString();
  const finalAmountIRR = (BigInt(rawLinesTotalIRR) - BigInt(adjustments.discountIRR) + BigInt(adjustments.taxIRR) + BigInt(adjustments.shippingIRR) + BigInt(adjustments.otherCostsIRR)).toString();
  return { lines: prepared, rawLinesTotalIRR, finalAmountIRR, ...adjustments, duplicateMatches: [] };
}

export function createApiInvoicesAdapter(context, client) {
  const base = financeBase(context);
  let targetCache = [];
  async function getInvoiceTargets() {
    const [resourcePayload, linePayload] = await Promise.all([client.request(`${base}/resources`), client.request(`${base}/estimate-lines`)]);
    const resources = resourcePayload.map(mapResource);
    const estimateTargets = linePayload.map((line) => {
      const resource = resources.find((item) => item.resourceId === line.resourceId);
      return { targetId: line.id, targetType: "estimate_line", label: `${line.activityExternalId || "خط برآورد"} · ${resource?.title ?? "قلم مالی"}`, unit: resource?.baseUnit ?? null, resourceId: line.resourceId, estimateLineId: line.id };
    });
    const generalTargets = resources.filter((item) => item.type === "general_cost").map((item) => ({ targetId: item.resourceId, targetType: "general_cost", label: item.title, unit: null, resourceId: item.resourceId, estimateLineId: null }));
    targetCache = [...estimateTargets, ...generalTargets];
    return structuredClone(targetCache);
  }
  async function getInvoices({ query = "", status = "", source = "", page = 1, pageSize = 50 } = {}) {
    const size = Math.min(Math.max(Number(pageSize) || 50, 1), 200);
    const params = new URLSearchParams({ page: String(Math.max(Number(page) || 1, 1)), pageSize: String(size) });
    if (query.trim()) params.set("query", query.trim());
    if (status) params.set("status", status);
    if (source) params.set("source", source);
    const payload = await client.request(`${base}/invoices?${params.toString()}`);
    return {
      items: payload.items.map((item) => mapInvoice(item, targetCache)).map(({ lines, ...item }) => ({ ...item, lineCount: lines.length })),
      page: payload.page,
      pageSize: payload.pageSize,
      totalItems: payload.totalItems,
      totalPages: payload.totalPages,
    };
  }
  async function getInvoice(invoiceId) {
    if (!targetCache.length) await getInvoiceTargets();
    return mapInvoice(await client.request(`${base}/invoices/${encodeURIComponent(invoiceId)}`), targetCache);
  }
  async function previewDraft({ lines, adjustments }) {
    return exactPreview(lines, adjustments);
  }
  async function linePayload(lines) {
    if (!targetCache.length) await getInvoiceTargets();
    return lines.map((line) => {
      const target = targetCache.find((item) => item.targetId === line.targetId);
      if (!target) throw new ApiError({ status: 422, code: "INVOICE_TARGET_INVALID", message: "اتصال خط فاکتور به قلم مالی معتبر نیست." });
      return { estimateLineId: target.estimateLineId, resourceId: target.resourceId, quantity: line.targetType === "general_cost" ? null : line.quantity, unit: line.targetType === "general_cost" ? null : line.unit, unitPriceIrr: line.targetType === "general_cost" ? null : line.unitPriceIRR, lineAmountIrr: line.targetType === "general_cost" ? line.lineAmountIRR : null, description: line.description || null };
    });
  }
  async function createDraft({ header, lines, adjustments, duplicateOverrideReason, idempotencyKey }) {
    // No invoiceNumber: the endpoint refuses the field (422, "Extra inputs are not
    // permitted") because the number is the project's to allocate, not the client's.
    const payload = { invoiceDate: header.invoiceDate, vendorName: header.vendorName, description: header.description || null, source: "manual", discountIrr: adjustments.discountIRR, taxIrr: adjustments.taxIRR, shippingIrr: adjustments.shippingIRR, otherCostsIrr: adjustments.otherCostsIRR, idempotencyKey, duplicateReason: duplicateOverrideReason || null, directAdjustmentAllocations: [], lines: await linePayload(lines) };
    return mapInvoice(await client.request(`${base}/invoices`, jsonOptions("POST", payload)), targetCache);
  }
  async function submitDraft({ invoiceId, expectedVersion }) {
    return mapInvoice(await client.request(`${base}/invoices/${encodeURIComponent(invoiceId)}`, jsonOptions("PATCH", { status: "awaitingConfirmation", expectedVersion })), targetCache);
  }
  async function confirmInvoice({ invoiceId, expectedVersion, idempotencyKey }) {
    return mapInvoice(await client.request(`${base}/invoices/${encodeURIComponent(invoiceId)}/confirm`, jsonOptions("POST", { expectedVersion, idempotencyKey })), targetCache);
  }
  async function voidInvoice({ invoiceId, expectedVersion, idempotencyKey, reason }) {
    return mapInvoice(await client.request(`${base}/invoices/${encodeURIComponent(invoiceId)}/void`, jsonOptions("POST", { expectedVersion, idempotencyKey, reason })), targetCache);
  }
  async function createCorrective({ originalInvoiceId, header, lines, adjustments, financialEffectSign, reason, idempotencyKey }) {
    // Same as the create above: a corrective document is its own invoice and takes the
    // project's next number.
    const payload = { invoiceDate: header.invoiceDate, vendorName: header.vendorName, description: header.description || null, source: "corrective", discountIrr: adjustments.discountIRR, taxIrr: adjustments.taxIRR, shippingIrr: adjustments.shippingIRR, otherCostsIrr: adjustments.otherCostsIRR, idempotencyKey, duplicateReason: null, directAdjustmentAllocations: [], lines: await linePayload(lines), financialEffectSign, reason };
    return mapInvoice(await client.request(`${base}/invoices/${encodeURIComponent(originalInvoiceId)}/corrective`, jsonOptions("POST", payload)), targetCache);
  }
  return Object.freeze({ getInvoices, getInvoice, getInvoiceTargets, previewDraft, createDraft, submitDraft, confirmInvoice, voidInvoice, createCorrective });
}
