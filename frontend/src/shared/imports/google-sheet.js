/**
 * A Google Sheets link, on its way to an import the server performs.
 *
 * The browser never calls Google. It sends the link to this module's own
 * service, which fetches the sheet and hands the workbook to the same parser an
 * upload reaches. That is not a preference:
 *
 *   * this module's API client resolves every path against the page's own origin
 *     and refuses anything else;
 *   * the repo's stated constraints forbid an external browser request outright;
 *   * the BAMBO dashboard's Content-Security-Policy names `connect-src 'self'`,
 *     so a fetch to docs.google.com from this page would stop working the day
 *     that header stops being report-only -- silently, on a page nobody watches.
 *
 * What comes back is an ordinary import preview: the same shape, the same
 * `previewId`, committed by the same endpoint. A link and an upload differ only
 * in how the workbook reached the parser.
 *
 * The only thing left on this side is the guess a person can be told about
 * immediately. Whether the sheet is readable, whether it is a workbook at all,
 * and which tab to export are the server's to answer.
 */

/** A link this module can act on, told apart from a request that simply failed. */
export class GoogleSheetError extends Error {}

/**
 * Enough of a check to answer without a round trip.
 *
 * Deliberately loose: it says "that is not a Google Sheets address" for a
 * mistyped link, and lets everything else through to the service, which
 * validates properly and is the only side that can.
 */
export function looksLikeSheetLink(value) {
  const text = String(value ?? "").trim();
  if (!text) return false;
  let url;
  try {
    url = new URL(text);
  } catch {
    return false;
  }
  return /(^|\.)google\.com$/i.test(url.hostname) && /\/spreadsheets\/d\//.test(url.pathname);
}

/** The link, or a refusal a person can act on. Callers pass the result to their adapter. */
export function requireSheetLink(value) {
  const text = String(value ?? "").trim();
  if (!text) throw new GoogleSheetError("نشانی گوگل شیت را وارد کنید.");
  if (!looksLikeSheetLink(text)) {
    throw new GoogleSheetError("نشانی معتبر گوگل شیت نیست. نشانی کامل برگه را از نوار آدرس مرورگر کپی کنید.");
  }
  return text;
}
