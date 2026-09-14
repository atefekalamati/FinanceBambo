import { ApiError } from "../../core/api/api-error.js";

const STATUSES = ["draft", "awaitingConfirmation", "confirmed", "voided", "corrected"];
const SOURCES = ["manual", "image", "voice"];

function clone(value) {
  return structuredClone(value);
}

function wait(duration = 320) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

/**
 * The seed spans twelve Gregorian months so the monthly trend has a real shape.
 * Amounts and statuses are untouched; only the calendar position of each
 * invoice moves.
 *
 * The window ends on the month the rest of the dataset lives in rather than
 * running past it. A future-dated invoice is excluded by every report — they
 * are all built as of a reporting date — so it would be money that exists in
 * the list and nowhere else, and the month it sits in would draw as empty.
 *
 * Twelve is also what the monthly report asks the service for by default, so
 * every column the chart draws has something behind it.
 */
const SEED_MONTH_SPAN = 12;
const SEED_FIRST_YEAR = 2025;
const SEED_FIRST_MONTH = 9; // 2025-09 through 2026-08, ending in مرداد ۱۴۰۵

function seedInvoiceDate(index) {
  const offset = SEED_FIRST_MONTH - 1 + ((index - 1) % SEED_MONTH_SPAN);
  const year = SEED_FIRST_YEAR + Math.floor(offset / 12);
  const month = (offset % 12) + 1;
  const day = ((index * 7) % 27) + 1;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/**
 * A reversal is not a document of its own making.
 *
 * `InvoiceService.void` builds it from the invoice it cancels and gives it that
 * invoice's own `invoice_date`, so the −X always lands in the same month as the
 * +X it undoes and the two cancel where they happened. A seed that dated its
 * reversals independently was subtracting money in months where nothing had
 * been added, which is a state the service cannot produce.
 *
 * The statuses cycle draft, awaitingConfirmation, confirmed, voided, corrected,
 * so the confirmed invoice a reversal belongs to is always the one before it.
 */
function reversalSourceIndex(index) {
  return STATUSES[(index - 1) % STATUSES.length] === "voided" ? index - 1 : index;
}

/**
 * The number as the service writes it: an integer the counter allocated, and that
 * integer zero-padded to three for a reader. Both travel on the invoice because
 * both are in the API's response -- the preview must not be the one place where a
 * number is composed differently from production.
 */
const INVOICE_NUMBER_WIDTH = 3;

function formatInvoiceNumber(seq) {
  return seq === null || seq === undefined ? null : String(seq).padStart(INVOICE_NUMBER_WIDTH, "0");
}

function makeInvoice(index, context) {
  const number = String(index).padStart(3, "0");
  const status = STATUSES[(index - 1) % STATUSES.length];
  const sourceIndex = reversalSourceIndex(index);
  const invoiceDate = seedInvoiceDate(sourceIndex);
  const source = SOURCES[(index - 1) % SOURCES.length];
  const rawTotalIRR = String(120000000 + (sourceIndex * 1750000));
  return {
    invoiceId: `invoice-demo-${number}`,
    organizationId: context.organizationId,
    projectId: context.projectId,
    invoiceSeq: index,
    invoiceNumber: formatInvoiceNumber(index),
    invoiceDate,
    vendorName: index % 3 === 0 ? "تأمین تجهیزات سازه نمونه" : index % 2 === 0 ? "شرکت مصالح پایدار نمونه" : "فروشگاه ساختمانی بامبو نمونه",
    description: index % 4 === 0 ? "خرید و تأمین اقلام موردنیاز عملیات اجرایی طبق صورت‌جلسه کارگاه" : "فاکتور نمایشی برای توسعه رابط کاربری",
    source,
    invoiceStatus: status,
    version: status === "draft" ? 1 : status === "awaitingConfirmation" ? 2 : 3,
    idempotencyKey: `seed-invoice-${number}`,
    duplicateWarning: index % 17 === 0,
    duplicateOverrideReason: index % 17 === 0 ? "ادامه ثبت پس از بررسی سند مشابه توسط کارشناس مالی" : null,
    rawLinesTotalIRR: rawTotalIRR,
    discountIRR: sourceIndex % 4 === 0 ? "500000" : "0",
    taxIRR: sourceIndex % 3 === 0 ? "1200000" : "0",
    shippingIRR: sourceIndex % 5 === 0 ? "750000" : "0",
    otherCostsIRR: "0",
    finalAmountIRR: String(BigInt(rawTotalIRR) - BigInt(sourceIndex % 4 === 0 ? "500000" : "0") + BigInt(sourceIndex % 3 === 0 ? "1200000" : "0") + BigInt(sourceIndex % 5 === 0 ? "750000" : "0")),
    submittedBy: context.userId,
    createdAt: `${invoiceDate}T08:30:00Z`,
    confirmedBy: status === "confirmed" || status === "voided" || status === "corrected" ? context.userId : null,
    // Confirmed on the day it is dated. A fixed timestamp would sit before the
    // invoice date for anything later than it, and read as a document approved
    // before it existed.
    confirmedAt: status === "confirmed" || status === "voided" || status === "corrected" ? `${invoiceDate}T09:15:00Z` : null,
    // The document this one acts on: the confirmed invoice before it, not a
    // single invoice that every reversal in the project claims to cancel.
    relatedInvoiceId: status === "voided" || status === "corrected" ? `invoice-demo-${String(index - 1).padStart(3, "0")}` : null,
    originalInvoiceId: status === "voided" || status === "corrected" ? `invoice-demo-${String(index - 1).padStart(3, "0")}` : null,
    financialEffectSign: status === "voided" ? -1 : 1,
    lines: [
      { invoiceLineId: `line-${number}-1`, targetType: "estimate_line", targetLabel: "میلگرد فونداسیون نمونه", quantity: "1250.0000", unit: "kg", unitPriceIRR: "80000", lineAmountIRR: "100000000", description: "تحویل مرحله اول" },
      { invoiceLineId: `line-${number}-2`, targetType: "general_cost", targetLabel: "هزینه حمل نمونه", quantity: null, unit: null, unitPriceIRR: null, lineAmountIRR: String(BigInt(rawTotalIRR) - 100000000n), description: "هزینه عمومی مرتبط" },
    ],
  };
}

/** Shared with the mock reports adapter so both read one seed, not two. */
export function buildSeedInvoices(context) {
  return Array.from({ length: 53 }, (unused, index) => makeInvoice(index + 1, context));
}

export function createMockInvoicesAdapter(context, { initialState = "success" } = {}) {
  const invoices = initialState === "empty" ? [] : buildSeedInvoices(context);
  /* The project's counter. One function for every path that writes an invoice, the
     way the service keeps one statement for both of its writing transactions: a
     second place to take the next number is a second place for the rule to drift.
     Single-threaded here, so the row lock production needs has nothing to do. */
  let nextInvoiceSeq = invoices.reduce((highest, invoice) => Math.max(highest, invoice.invoiceSeq ?? 0), 0) + 1;
  const allocateInvoiceNumber = () => {
    const seq = nextInvoiceSeq;
    nextInvoiceSeq += 1;
    return { invoiceSeq: seq, invoiceNumber: formatInvoiceNumber(seq) };
  };
  const createRequests = new Map();
  const confirmationKeys = new Map();
  const linkedOperationKeys = new Map();
  const extractedConfirmationKeys = new Map();
  const reversedOriginals = new Set(invoices.filter((invoice) => invoice.source === "reversal").map((invoice) => invoice.originalInvoiceId));
  const targets = [
    { targetId: "estimate-foundation-rebar", targetType: "estimate_line", label: "میلگرد فونداسیون نمونه", unit: "kg" },
    { targetId: "estimate-formwork-labor", targetType: "estimate_line", label: "اکیپ قالب‌بندی نمونه", unit: "hour" },
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
    // Not the number: every invoice has its own now, so matching on it would never
    // find anything and the duplicate warning would go quiet instead of going away.
    return invoices.filter((invoice) => invoice.vendorName.trim().toLocaleLowerCase("fa-IR") === vendor
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
    if (!header?.invoiceDate || !header.vendorName || !Array.isArray(lines) || !lines.length) throw new ApiError({ status: 422, code: "INVOICE_VALIDATION_FAILED", message: "اطلاعات فاکتور کامل نیست." });
    // A client that still sends a number is told, exactly as the service tells it: the
    // endpoint answers 422 naming the field, and a demo surface that accepted what the
    // real one refuses would hide the very defect this change exists to fix.
    if (header.invoiceNumber != null) throw new ApiError({ status: 422, code: "INVOICE_VALIDATION_FAILED", message: "شماره فاکتور را سرویس تعیین می‌کند و نباید ارسال شود." });
    const preview = buildPreview(lines, adjustments);
    if (BigInt(preview.finalAmountIRR) < 0n) throw new ApiError({ status: 422, code: "INVOICE_NEGATIVE_TOTAL", message: "مبلغ نهایی فاکتور نمی‌تواند منفی باشد." });
    const duplicateMatches = findSimilarInvoices(header, preview.finalAmountIRR);
    const auditedReason = String(duplicateOverrideReason).trim();
    if (duplicateMatches.length && auditedReason.length < 3) throw new ApiError({ status: 422, code: "INVOICE_DUPLICATE_REASON_REQUIRED", message: "برای ادامه ثبت فاکتور مشابه، دلیل ممیزی الزامی است.", details: duplicateMatches.map((invoice) => ({ invoiceId: invoice.invoiceId })) });
    const preparedLines = preview.lines.map((line, index) => ({ ...line, invoiceLineId: `draft-line-${Date.now()}-${index + 1}` }));
    const invoice = { invoiceId: `invoice-draft-${Date.now()}`, organizationId: context.organizationId, projectId: context.projectId, ...header, ...allocateInvoiceNumber(), source: "manual", invoiceStatus: "draft", version: 1, idempotencyKey: requestKey, duplicateWarning: duplicateMatches.length > 0, duplicateOverrideReason: duplicateMatches.length ? auditedReason : null, duplicateOfInvoiceIds: duplicateMatches.map((item) => item.invoiceId), rawLinesTotalIRR: preview.rawLinesTotalIRR, ...adjustments, finalAmountIRR: preview.finalAmountIRR, submittedBy: context.userId, createdAt: new Date().toISOString(), confirmedBy: null, confirmedAt: null, relatedInvoiceId: null, lines: preparedLines };
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

  async function confirmInvoice({ invoiceId, expectedVersion, idempotencyKey }) {
    await wait(420);
    if (!context.permissionCodes?.includes("finance.edit")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز تأیید فاکتور وجود ندارد.", requestId: "mock-invoice-confirm-403" });
    const invoice = invoices.find((item) => item.invoiceId === invoiceId);
    if (!invoice) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "فاکتور موردنظر پیدا نشد." });
    // No submitter check. The service dropped that rule -- confirming is settled by
    // holding «مدیریت فاکتورها», and `confirmedBy` records who did it -- and a preview
    // that refuses what the real API accepts teaches the wrong flow. The uploader rule
    // on `createConfirmedExtractedInvoice` below is a different rule and is still live.
    const key = String(idempotencyKey ?? "").trim();
    if (!key) throw new ApiError({ status: 422, code: "IDEMPOTENCY_KEY_REQUIRED", message: "شناسه یکتای تأیید الزامی است." });
    if (invoice.invoiceStatus === "confirmed") {
      if (confirmationKeys.get(invoiceId) === key) return clone(invoice);
      throw new ApiError({ status: 409, code: "INVOICE_ALREADY_CONFIRMED", message: "این فاکتور قبلاً تأیید شده است.", requestId: "mock-invoice-confirmed-409" });
    }
    if (invoice.invoiceStatus !== "awaitingConfirmation" || invoice.version !== expectedVersion) throw new ApiError({ status: 409, code: "STALE_VERSION", message: "فاکتور در وضعیت یا نسخه قابل تأیید نیست؛ اطلاعات را دوباره دریافت کنید.", requestId: "mock-invoice-confirm-stale-409" });
    invoice.invoiceStatus = "confirmed";
    invoice.version += 1;
    invoice.confirmedBy = context.userId;
    invoice.confirmedAt = new Date().toISOString();
    confirmationKeys.set(invoiceId, key);
    return clone(invoice);
  }

  async function voidInvoice({ invoiceId, expectedVersion, idempotencyKey, reason }) {
    await wait(460);
    if (!context.permissionCodes?.includes("finance.edit")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز ابطال فاکتور وجود ندارد." });
    const key = String(idempotencyKey ?? "").trim();
    const auditedReason = String(reason ?? "").trim();
    if (!key || !auditedReason) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "شناسه یکتا و دلیل ابطال الزامی است." });
    if (linkedOperationKeys.has(key)) return clone(linkedOperationKeys.get(key));
    const original = invoices.find((item) => item.invoiceId === invoiceId);
    if (!original) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "فاکتور اصلی پیدا نشد." });
    if (original.invoiceStatus !== "confirmed" || original.version !== expectedVersion || reversedOriginals.has(invoiceId)) throw new ApiError({ status: 409, code: "INVOICE_OPERATION_CONFLICT", message: "فقط نسخه جاری یک فاکتور تأییدشده و بدون سند برگشت قابل ابطال است.", requestId: "mock-invoice-void-409" });
    const occurredAt = new Date().toISOString();
    const reversal = { ...clone(original), ...allocateInvoiceNumber(), invoiceId: `invoice-reversal-${Date.now()}`, source: "reversal", invoiceStatus: "voided", version: 1, idempotencyKey: key, description: auditedReason, financialEffectSign: -1, originalInvoiceId: original.invoiceId, relatedInvoiceId: original.invoiceId, submittedBy: context.userId, confirmedBy: context.userId, confirmedAt: occurredAt, createdAt: occurredAt };
    invoices.unshift(reversal);
    reversedOriginals.add(original.invoiceId);
    linkedOperationKeys.set(key, clone(reversal));
    return clone(reversal);
  }

  async function createCorrective({ originalInvoiceId, header, lines, adjustments, financialEffectSign, reason, idempotencyKey }) {
    await wait(500);
    if (!context.permissionCodes?.includes("finance.edit")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز ثبت سند اصلاحی وجود ندارد." });
    const key = String(idempotencyKey ?? "").trim();
    const auditedReason = String(reason ?? "").trim();
    if (!key || auditedReason.length < 3 || ![-1, 1].includes(financialEffectSign)) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "دلیل و جهت اثر مالی سند اصلاحی معتبر نیست." });
    if (linkedOperationKeys.has(key)) return clone(linkedOperationKeys.get(key));
    const original = invoices.find((item) => item.invoiceId === originalInvoiceId);
    if (!original) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "فاکتور اصلی پیدا نشد." });
    if (original.invoiceStatus !== "confirmed" || reversedOriginals.has(originalInvoiceId)) throw new ApiError({ status: 409, code: "INVOICE_OPERATION_CONFLICT", message: "سند اصلاحی فقط برای فاکتور تأییدشده و برگشت‌نخورده مجاز است." });
    const preview = buildPreview(lines, adjustments);
    if (BigInt(preview.finalAmountIRR) < 0n) throw new ApiError({ status: 422, code: "INVOICE_NEGATIVE_TOTAL", message: "مبلغ سند اصلاحی نمی‌تواند منفی باشد." });
    const occurredAt = new Date().toISOString();
    const preparedLines = preview.lines.map((line, index) => ({ ...line, invoiceLineId: `corrective-line-${Date.now()}-${index + 1}` }));
    const corrective = { invoiceId: `invoice-corrective-${Date.now()}`, organizationId: context.organizationId, projectId: context.projectId, ...header, ...allocateInvoiceNumber(), source: "corrective", invoiceStatus: "corrected", version: 1, idempotencyKey: key, correctionReason: auditedReason, financialEffectSign, originalInvoiceId, relatedInvoiceId: originalInvoiceId, duplicateWarning: false, duplicateOverrideReason: null, duplicateOfInvoiceIds: [], rawLinesTotalIRR: preview.rawLinesTotalIRR, ...adjustments, finalAmountIRR: preview.finalAmountIRR, submittedBy: context.userId, confirmedBy: context.userId, confirmedAt: occurredAt, createdAt: occurredAt, lines: preparedLines };
    invoices.unshift(corrective);
    linkedOperationKeys.set(key, clone(corrective));
    return clone(corrective);
  }

  async function createConfirmedExtractedInvoice({ logicalType, invoice, idempotencyKey, submittedBy }) {
    await wait(260);
    if (!context.permissionCodes?.includes("finance.edit")) throw new ApiError({ status: 403, code: "FINANCE_PERMISSION_DENIED", message: "مجوز ثبت فاکتور استخراج‌شده وجود ندارد." });
    const key = String(idempotencyKey ?? "").trim();
    if (!key) throw new ApiError({ status: 422, code: "IDEMPOTENCY_KEY_REQUIRED", message: "شناسه یکتای درخواست الزامی است." });
    if (extractedConfirmationKeys.has(key)) return clone(extractedConfirmationKeys.get(key));
    if (submittedBy !== context.userId) throw new ApiError({ status: 403, code: "INVOICE_CONFIRMATION_FORBIDDEN", message: "فقط بارگذار فایل می‌تواند فاکتور استخراج‌شده را تأیید کند." });
    if (!invoice?.invoiceDate || !String(invoice.vendorName ?? "").trim() || !/^\d+$/.test(String(invoice.totalIRR ?? "")) || !invoice.resourceId) throw new ApiError({ status: 422, code: "INVOICE_VALIDATION_FAILED", message: "اطلاعات و تخصیص فاکتور استخراج‌شده کامل نیست." });
    const target = targets.find((item) => item.targetId === invoice.resourceId);
    if (!target) throw new ApiError({ status: 422, code: "INVOICE_TARGET_INVALID", message: "قلم مالی انتخاب‌شده معتبر نیست." });
    const occurredAt = new Date().toISOString();
    const confirmed = {
      invoiceId: `invoice-extracted-${Date.now()}`,
      organizationId: context.organizationId,
      projectId: context.projectId,
      // The fourth path, and it takes the next number like the other three. What the
      // extractor read off the supplier's document is their number, not this
      // project's, and the reviewed payload no longer carries it.
      ...allocateInvoiceNumber(),
      invoiceDate: invoice.invoiceDate,
      vendorName: String(invoice.vendorName).trim(),
      description: "ثبت‌شده پس از بازبینی انسانی استخراج هوشمند",
      source: logicalType === "invoice_image" ? "image" : "voice",
      invoiceStatus: "confirmed",
      version: 1,
      idempotencyKey: key,
      duplicateWarning: false,
      duplicateOverrideReason: null,
      rawLinesTotalIRR: String(invoice.totalIRR),
      discountIRR: "0",
      taxIRR: "0",
      shippingIRR: "0",
      otherCostsIRR: "0",
      finalAmountIRR: String(invoice.totalIRR),
      submittedBy,
      createdAt: occurredAt,
      confirmedBy: context.userId,
      confirmedAt: occurredAt,
      relatedInvoiceId: null,
      originalInvoiceId: null,
      financialEffectSign: 1,
      lines: [{ invoiceLineId: `extracted-line-${Date.now()}`, targetId: target.targetId, targetType: target.targetType, targetLabel: target.label, quantity: target.targetType === "general_cost" ? null : "1.0000", unit: target.targetType === "general_cost" ? null : target.unit, unitPriceIRR: target.targetType === "general_cost" ? null : String(invoice.totalIRR), lineAmountIRR: String(invoice.totalIRR), description: "مبلغ و تخصیص تأییدشده توسط کاربر" }],
    };
    invoices.unshift(confirmed);
    extractedConfirmationKeys.set(key, clone(confirmed));
    return clone(confirmed);
  }

  return Object.freeze({ getInvoices, getInvoice, getInvoiceTargets, previewDraft, createDraft, submitDraft, confirmInvoice, voidInvoice, createCorrective, createConfirmedExtractedInvoice });
}
