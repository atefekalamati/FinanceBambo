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
    // Authoring what the figures are built from: prices, estimate lines,
    // quantities, the gross built area and the conversion rules — the whole of
    // امور مالی behind one code, because the account trusted with one of those
    // numbers is trusted with the rest of the same plan.
    writeFinance: hasPermission(context, "finance.edit"),
    // Recording what was actually spent, by every route a document takes into
    // the ledger: typed by hand, photographed, spoken, or read out of a file by
    // the extractor — then reviewed, submitted and confirmed. Separate from the
    // code above because a receipt is not one of the plan's numbers, and an
    // account may be trusted with either without the other.
    manageInvoice: hasPermission(context, "finance.manage_invoice"),
    // Stating something that outlives this project: a conversion rule for the whole
    // organization, a price category the other projects will see. The services check it,
    // never the routes -- the route asks for `finance.edit` and only the WIDER scope is
    // refused -- so it is not a door the interface can find by watching for 403s. It has
    // to ask, or it offers choices whose only possible answer is one.
    manageSettings: hasPermission(context, "finance.manage_settings"),
    viewReport: hasPermission(context, "finance_report.view"),
    // Freezing a report into an immutable record, and taking a copy away.
    issueReport: hasPermission(context, "finance_report.issue"),
    exportReport: hasPermission(context, "finance_report.export"),
  });
}

/**
 * Every code the host can grant, in the order the settings page lists them.
 * Kept beside the mapping above so a code cannot be added to one and forgotten
 * in the other.
 *
 * `finance.manage_settings` was missing from both for as long as it existed. An account
 * could not see whether it held it, and no screen could ask -- so the scope choices it
 * gates were offered to everybody and refused at the end of the form.
 */
export const FINANCE_PERMISSIONS = Object.freeze([
  Object.freeze({ code: "finance.view", label: "مشاهده اطلاعات مالی" }),
  Object.freeze({ code: "finance.edit", label: "ویرایش اطلاعات و تنظیمات مالی" }),
  Object.freeze({ code: "finance.manage_invoice", label: "مدیریت فاکتورها" }),
  Object.freeze({ code: "finance.manage_settings", label: "مدیریت تنظیمات مالی" }),
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
