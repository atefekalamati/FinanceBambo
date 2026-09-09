import { element } from "../dom/elements.js";

/**
 * What an account is told when a control it can see is not one it may use.
 *
 * The alternative — drawing nothing — is what this replaces. A page that hides
 * a button from an account without the right leaves that account looking at a
 * screen it cannot tell apart from a broken one: the record is there, the
 * status says a decision is owed, and nothing on the page says who owes it. The
 * reader then asks a colleague, and the colleague sees a different page.
 *
 * So the control stays where it is, switched off, and this line says why. The
 * wording names the grant in the words the host's own permission list uses, so
 * the reader can ask an administrator for the thing by its name rather than
 * describing a button that did not work.
 */
export function createPermissionNotice(what, { grant = "مدیریت فاکتورها" } = {}) {
  const notice = element(
    "p",
    "inline-notice permission-notice",
    `${what} نیازمند مجوز «${grant}» است. این حساب آن را ندارد و فقط می‌تواند مشاهده کند. برای دریافت دسترسی با مدیر سامانه تماس بگیرید.`,
  );
  // Announced when it appears, not read over whatever the reader is doing:
  // nothing has gone wrong, and the page has not changed under them.
  notice.setAttribute("role", "status");
  return notice;
}
