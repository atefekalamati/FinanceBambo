import { ApiError } from "../../core/api/api-error.js";

const STATUSES = ["draft", "awaitingConfirmation", "confirmed", "voided", "corrected"];
const SOURCES = ["manual", "image", "voice"];

function clone(value) {
  return structuredClone(value);
}

function wait(duration = 320) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

function makeInvoice(index, context) {
  const number = String(index).padStart(3, "0");
  const status = STATUSES[(index - 1) % STATUSES.length];
  const source = SOURCES[(index - 1) % SOURCES.length];
  const rawTotalIRR = String(120000000 + (index * 1750000));
  return {
    invoiceId: `invoice-demo-${number}`,
    organizationId: context.organizationId,
    projectId: context.projectId,
    invoiceNumber: `ف-${number}`,
    invoiceDate: `2026-07-${String(((index - 1) % 28) + 1).padStart(2, "0")}`,
    vendorName: index % 3 === 0 ? "تأمین تجهیزات سازه نمونه" : index % 2 === 0 ? "شرکت مصالح پایدار نمونه" : "فروشگاه ساختمانی بامبو نمونه",
    description: index % 4 === 0 ? "خرید و تأمین اقلام موردنیاز عملیات اجرایی طبق صورت‌جلسه کارگاه" : "فاکتور نمایشی برای توسعه رابط کاربری",
    source,
    invoiceStatus: status,
    version: status === "draft" ? 1 : status === "awaitingConfirmation" ? 2 : 3,
    idempotencyKey: `seed-invoice-${number}`,
    duplicateWarning: index % 17 === 0,
    duplicateOverrideReason: index % 17 === 0 ? "ادامه ثبت پس از بررسی سند مشابه توسط کارشناس مالی" : null,
    rawLinesTotalIRR: rawTotalIRR,
    discountIRR: index % 4 === 0 ? "500000" : "0",
    taxIRR: index % 3 === 0 ? "1200000" : "0",
    shippingIRR: index % 5 === 0 ? "750000" : "0",
    otherCostsIRR: "0",
    finalAmountIRR: String(BigInt(rawTotalIRR) - BigInt(index % 4 === 0 ? "500000" : "0") + BigInt(index % 3 === 0 ? "1200000" : "0") + BigInt(index % 5 === 0 ? "750000" : "0")),
    submittedBy: context.userId,
    createdAt: `2026-07-${String(((index - 1) % 28) + 1).padStart(2, "0")}T08:30:00Z`,
    confirmedBy: status === "confirmed" || status === "voided" || status === "corrected" ? context.userId : null,
    confirmedAt: status === "confirmed" || status === "voided" || status === "corrected" ? "2026-08-01T09:15:00Z" : null,
    relatedInvoiceId: status === "voided" || status === "corrected" ? "invoice-demo-001" : null,
    lines: [
      { invoiceLineId: `line-${number}-1`, targetType: "estimate_line", targetLabel: "میلگرد فونداسیون نمونه", quantity: "1250.0000", unit: "kg", unitPriceIRR: "80000", lineAmountIRR: "100000000", description: "تحویل مرحله اول" },
      { invoiceLineId: `line-${number}-2`, targetType: "general_cost", targetLabel: "هزینه حمل نمونه", quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: String(BigInt(rawTotalIRR) - 100000000n), description: "هزینه عمومی مرتبط" },
    ],
  };
}

export function createMockInvoicesAdapter(context, { initialState = "success" } = {}) {
  const invoices = initialState === "empty" ? [] : Array.from({ length: 53 }, (_, index) => makeInvoice(index + 1, context));
  const createRequests = new Map();
  const targets = [
    { targetId: "estimate-foundation-rebar", targetType: "estimate_line", label: "میلگرد فونداسیون نمونه", unit: "kg" },
    { targetId: "estimate-formwork-labor", targetType: "estimate_line", label: "اکیپ قالب‌بندی نمونه", unit: "person_hour" },
    { targetId: "general-permit", targetType: "general_cost", label: "هزینه مجوز نمونه", unit: null },
  ];

  function calculateLineAmount(line) {
    if (line.targetType === "general_cost") return line.lineAmountIRR;
    const [integer, fraction = ""] = line.quantity.split(".");
    const scaledQuantity = BigInt(`${integer}${fraction.padEnd(4, "0")}`);
    return ((scaledQuantity * BigInt(line.unitPriceIRR) + 5000n) / 10000n).toString();
  }

  async function getInvoices({ query = "", status = "", source = "", page = 1, pageSize = 50 } = {}) {
    await wait();
    if (initialState === "error") throw new ApiError({ status: 503, code: "INVOICE_LIST_UNAVAILABLE", message: "دریافت فهرست فاکتورها انجام نشد.", requestId: "mock-invoice-list-001" });
    const safePageSize = Math.min(Math.max(Number(pageSize) || 50, 1), 200);
    const normalizedQuery = String(query).trim().toLocaleLowerCase("fa-IR");
    const filtered = invoices.filter((invoice) => {
      const matchesQuery = !normalizedQuery || `${invoice.invoiceNumber} ${invoice.vendorName} ${invoice.description}`.toLocaleLowerCase("fa-IR").includes(normalizedQuery);
      return matchesQuery && (!status || invoice.invoiceStatus === status) && (!source || invoice.source === source);
    });
    const totalPages = Math.max(1, Math.ceil(filtered.length / safePageSize));
    const safePage = Math.min(Math.max(Number(page) || 1, 1), totalPages);
    const offset = (safePage - 1) * safePageSize;
    return clone({ items: filtered.slice(offset, offset + safePageSize).map(({ lines, ...invoice }) => ({ ...invoice, lineCount: lines.length })), page: safePage, pageSize: safePageSize, totalItems: filtered.length, totalPages });
  }

  async function getInvoice(invoiceId) {
    await wait(260);
    const invoice = invoices.find((item) => item.invoiceId === invoiceId);
    if (!invoice) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "فاکتور موردنظر پیدا نشد.", requestId: "mock-invoice-detail-404" });
    return clone(invoice);
  }

  async function getInvoiceTargets() {
    await wait(120);
    return clone(targets);
  }

  function buildPreview(lines, adjustments) {
    const preparedLines = lines.map((line) => ({ ...line, lineAmountIRR: calculateLineAmount(line) }));
    const rawLinesTotalIRR = preparedLines.reduce((sum, line) => sum + BigInt(line.lineAmountIRR), 0n).toString();
    const finalAmountIRR = (BigInt(rawLinesTotalIRR) - BigInt(adjustments.discountIRR) + BigInt(adjustments.taxIRR) + BigInt(adjustments.shippingIRR) + BigInt(adjustments.otherCostsIRR)).toString();
    return { lines: preparedLines, rawLinesTotalIRR, finalAmountIRR, ...adjustments };
  }

  function findSimilarInvoices(header, finalAmountIRR) {
    const vendor = String(header.vendorName).trim().toLocaleLowerCase("fa-IR");
    return invoices.filter((invoice) => invoice.vendorName.trim().toLocaleLowerCase("fa-IR") === vendor
      && invoice.invoiceNumber === header.invoiceNumber
      && invoice.invoiceDate === header.invoiceDate
      && invoice.finalAmountIRR === finalAmountIRR);
  }

  async function previewDraft({ header, lines, adjustments }) {
    await wait(260);
    const preview = buildPreview(lines, adjustments);
    if (BigInt(preview.finalAmountIRR) < 0n) throw new ApiError({ status: 422, code: "INVOICE_NEGATIVE_TOTAL", message: "مبلغ نهایی فاکتور نمی‌تواند منفی باشد." });
    const duplicateMatches = findSimilarInvoices(header, preview.finalAmountIRR).map((invoice) => ({ invoiceId: invoice.invoiceId, invoiceNumber: invoice.invoiceNumber, invoiceDate: invoice.invoiceDate, vendorName: invoice.vendorName, finalAmountIRR: invoice.finalAmountIRR, invoiceStatus: invoice.invoiceStatus }));
    return clone({ ...preview, duplicateMatches });
  }

  async function createDraft({ header, lines, adjustments, duplicateOverrideReason = "", idempotencyKey }) {
    await wait(480);
    if (!context.permissionCodes?.includes("finance.edit")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز ثبت پیش‌نویس فاکتور وجود ندارد.", requestId: "mock-invoice-create-403" });
    const requestKey = String(idempotencyKey ?? "").trim();
    if (!requestKey) throw new ApiError({ status: 422, code: "IDEMPOTENCY_KEY_REQUIRED", message: "شناسه یکتای درخواست الزامی است." });
    const fingerprint = JSON.stringify({ header, lines, adjustments, duplicateOverrideReason: String(duplicateOverrideReason).trim() });
    const repeated = createRequests.get(requestKey);
    if (repeated) {
      if (repeated.fingerprint !== fingerprint) throw new ApiError({ status: 409, code: "IDEMPOTENCY_CONFLICT", message: "این شناسه درخواست قبلاً با اطلاعات متفاوت استفاده شده است.", requestId: "mock-invoice-idempotency-409" });
      return clone(repeated.invoice);
    }
    if (!header?.invoiceNumber || !header.invoiceDate || !header.vendorName || !Array.isArray(lines) || !lines.length) throw new ApiError({ status: 422, code: "INVOICE_VALIDATION_FAILED", message: "اطلاعات فاکتور کامل نیست." });
    const preview = buildPreview(lines, adjustments);
    if (BigInt(preview.finalAmountIRR) < 0n) throw new ApiError({ status: 422, code: "INVOICE_NEGATIVE_TOTAL", message: "مبلغ نهایی فاکتور نمی‌تواند منفی باشد." });
    const duplicateMatches = findSimilarInvoices(header, preview.finalAmountIRR);
    const auditedReason = String(duplicateOverrideReason).trim();
    if (duplicateMatches.length && auditedReason.length < 3) throw new ApiError({ status: 422, code: "INVOICE_DUPLICATE_REASON_REQUIRED", message: "برای ادامه ثبت فاکتور مشابه، دلیل ممیزی الزامی است.", details: duplicateMatches.map((invoice) => ({ invoiceId: invoice.invoiceId })) });
    const preparedLines = preview.lines.map((line, index) => ({ ...line, invoiceLineId: `draft-line-${Date.now()}-${index + 1}` }));
    const invoice = { invoiceId: `invoice-draft-${Date.now()}`, organizationId: context.organizationId, projectId: context.projectId, ...header, source: "manual", invoiceStatus: "draft", version: 1, idempotencyKey: requestKey, duplicateWarning: duplicateMatches.length > 0, duplicateOverrideReason: duplicateMatches.length ? auditedReason : null, duplicateOfInvoiceIds: duplicateMatches.map((item) => item.invoiceId), rawLinesTotalIRR: preview.rawLinesTotalIRR, ...adjustments, finalAmountIRR: preview.finalAmountIRR, submittedBy: context.userId, createdAt: new Date().toISOString(), confirmedBy: null, confirmedAt: null, relatedInvoiceId: null, lines: preparedLines };
    invoices.unshift(invoice);
    createRequests.set(requestKey, { fingerprint, invoice: clone(invoice) });
    return clone(invoice);
  }

  async function submitDraft({ invoiceId, expectedVersion }) {
    await wait(360);
    if (!context.permissionCodes?.includes("finance.edit")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز ارسال پیش‌نویس برای تأیید وجود ندارد." });
    const invoice = invoices.find((item) => item.invoiceId === invoiceId);
    if (!invoice) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "فاکتور موردنظر پیدا نشد." });
    if (invoice.invoiceStatus !== "draft" || invoice.version !== expectedVersion) throw new ApiError({ status: 409, code: "STALE_VERSION", message: "نسخه فاکتور تغییر کرده است؛ اطلاعات را دوباره دریافت کنید.", requestId: "mock-invoice-stale-409" });
    invoice.invoiceStatus = "awaitingConfirmation";
    invoice.version += 1;
    return clone(invoice);
  }

  return Object.freeze({ getInvoices, getInvoice, getInvoiceTargets, previewDraft, createDraft, submitDraft });
}
