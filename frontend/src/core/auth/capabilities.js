import { hasPermission } from "./permissions.js";

/**
 * The host decides who may do what. This module does not, and must never grow a
 * permission model of its own: a second answer to "may this account write?"
 * would be a second answer for the Backend to disagree with, and the Backend's
 * is the one that counts.
 *
 * What lives here is the single translation between the permission codes the
 * host hands over and the questions the interface actually asks. One file, so
 * that a code the host renames is one edit, and so that no page can quietly
 * invent a rule of its own — a test forbids naming a permission code anywhere
 * else under `features/`.
 *
 * None of this is enforcement, and none of it should be mistaken for it. Every
 * write goes to an endpoint that checks the same permission again and refuses
 * without it. This only decides what is worth putting on the screen, so that
 * nobody is offered a button whose only possible answer is 403.
 */
export function capabilitiesFor(context) {
  return Object.freeze({
    // Reading the project's financial data. Every route in the module is behind
    // this, because every page opens with a GET.
    viewFinance: hasPermission(context, "finance.view"),
    // Changing the cost model: prices, estimate lines, quantities, the gross
    // built area and the conversion rules. It no longer covers invoices --
    // maintaining a cost breakdown and approving a supplier's bill are different
    // jobs, and in most organizations different people.
    writeFinance: hasPermission(context, "finance.edit"),
    // Invoices, their uploaded images and recordings, and the extraction drafts
    // between them -- including opening the original file. Separate from
    // writeFinance in BOTH directions: neither implies the other, and the
    // interface must not offer either as a substitute for the other, because the
    // Backend will not accept one for the other.
    manageInvoice: hasPermission(context, "finance.manage_invoice"),
    viewReport: hasPermission(context, "finance_report.view"),
    // Freezing a report into an immutable record, and taking a copy away.
    issueReport: hasPermission(context, "finance_report.issue"),
    exportReport: hasPermission(context, "finance_report.export"),
  });
}

/** Shown wherever an invoice control is disabled, so the reason is not a mystery. */
export const MANAGE_INVOICE_NOTICE =
  "نیازمند مجوز مدیریت فاکتورها؛ این حساب می‌تواند اطلاعات را ببیند ولی فاکتور ثبت، تأیید یا اصلاح نکند.";

/**
 * The codes the host can grant, in the order the settings page lists them.
 * Kept beside the mapping above so a code cannot be added to one and forgotten
 * in the other.
 */
export const FINANCE_PERMISSIONS = Object.freeze([
  Object.freeze({ code: "finance.view", label: "مشاهده اطلاعات مالی" }),
  Object.freeze({ code: "finance.edit", label: "ویرایش اطلاعات و تنظیمات مالی" }),
  Object.freeze({ code: "finance.manage_invoice", label: "مدیریت فاکتورها و فایل‌های اصلی" }),
  Object.freeze({ code: "finance_report.view", label: "مشاهده گزارش‌های مالی" }),
  Object.freeze({ code: "finance_report.issue", label: "ثبت گزارش دوره‌ای" }),
  Object.freeze({ code: "finance_report.export", label: "دریافت خروجی گزارش‌ها" }),
]);

/** What to show an account about its own access, read back from the host. */
export function describeAccess(context) {
  return FINANCE_PERMISSIONS.map((permission) => ({
    ...permission,
    allowed: hasPermission(context, permission.code),
  }));
}
