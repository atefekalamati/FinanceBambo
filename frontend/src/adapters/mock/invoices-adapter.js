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
    duplicateWarning: index % 17 === 0,
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

  return Object.freeze({ getInvoices, getInvoice });
}
