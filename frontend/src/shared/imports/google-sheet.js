/**
 * A Google Sheets link, turned into the .xlsx file the import endpoint already takes.
 *
 * The import contract does not change: the server still receives a multipart
 * .xlsx and parses it exactly as it parses one picked off a disk. What changes
 * is only where the bytes came from.
 *
 * The fetch happens in the browser rather than on the server. That is worth
 * stating plainly, because the module's architecture note says the frontend does
 * not call an external provider directly, and this does. It is here because it
 * needs no backend and no new contract; if the host's CSP forbids the request,
 * this feature stops working and the file picker beside it still does.
 *
 * Only a sheet shared as "anyone with the link can view" can be read. A private
 * one answers with Google's sign-in page, which is HTML -- caught here rather
 * than sent to the server to come back as "invalid Excel workbook".
 */

/** A Google Sheets URL carries the document in its path and the tab in its fragment. */
const SHEET_ID = /\/spreadsheets\/d\/(?:e\/)?([a-zA-Z0-9_-]{20,})/;
const GID = /[#&?]gid=(\d+)/;

/**
 * The document id and, if the link names one, the tab.
 *
 * Returns null for anything that is not a Google Sheets link, so the caller can
 * say so rather than fetching something arbitrary.
 */
export function parseGoogleSheetUrl(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  let url;
  try { url = new URL(text); } catch { return null; }
  if (!/(^|\.)google\.com$/.test(url.hostname)) return null;
  const id = SHEET_ID.exec(url.pathname);
  if (!id) return null;
  const gid = GID.exec(text);
  return { id: id[1], gid: gid ? gid[1] : null };
}

/**
 * Where Google serves the workbook for a link.
 *
 * The tab is passed on when the link named one, which also settles the "the data
 * has to be on the first sheet" problem: a link copied while looking at the
 * right tab exports that tab and nothing else.
 */
export function googleSheetExportUrl({ id, gid }) {
  const params = new URLSearchParams({ format: "xlsx" });
  if (gid) params.set("gid", gid);
  return `https://docs.google.com/spreadsheets/d/${id}/export?${params.toString()}`;
}

/** Every way this can fail, said in the reader's terms rather than the network's. */
export class GoogleSheetError extends Error {}

/**
 * Fetch the sheet and hand back a File the import flow can send unchanged.
 *
 * `fetchImpl` is injectable so this can be tested without a network.
 */
export async function fetchGoogleSheetAsFile(value, { fetchImpl = fetch, name = "google-sheet" } = {}) {
  const parsed = parseGoogleSheetUrl(value);
  if (!parsed) throw new GoogleSheetError("نشانی معتبر گوگل شیت نیست. نشانی کامل برگه را از نوار آدرس مرورگر کپی کنید.");

  let response;
  try {
    response = await fetchImpl(googleSheetExportUrl(parsed));
  } catch {
    // A blocked request and an offline machine look the same from here.
    throw new GoogleSheetError("دریافت برگه از گوگل انجام نشد. اتصال اینترنت سرور یا دسترسی به گوگل را بررسی کنید.");
  }

  if (response.status === 401 || response.status === 403) {
    throw new GoogleSheetError("این برگه عمومی نیست. در گوگل شیت دسترسی را روی «هر کسی که لینک را دارد» بگذارید.");
  }
  if (!response.ok) {
    throw new GoogleSheetError(`گوگل به این نشانی پاسخ نداد (کد ${response.status}). نشانی و دسترسی برگه را بررسی کنید.`);
  }

  const buffer = await response.arrayBuffer();
  // An .xlsx is a zip and starts with "PK". Google answers a private sheet with
  // its sign-in page, which is HTML and starts with "<" -- worth telling apart
  // here, because the server would only be able to call it a broken workbook.
  const head = new Uint8Array(buffer.slice(0, 2));
  if (head[0] !== 0x50 || head[1] !== 0x4b) {
    throw new GoogleSheetError("پاسخ گوگل یک فایل اکسل نبود. معمولاً یعنی برگه عمومی نیست و صفحهٔ ورود برگشته است.");
  }

  return new File([buffer], `${name}.xlsx`, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}
