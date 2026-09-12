/**
 * CSV, written so a spreadsheet opens it correctly in Persian.
 *
 * The byte-order mark is what makes Excel read the file as UTF-8 instead of the
 * local code page, and CRLF is what it expects between records. Money is
 * written as the exact integer rial string the API returned — never the
 * compacted or localised form on screen — so a cell holds a number, not a
 * caption.
 */

const BOM = "﻿";
const CRLF = "\r\n";

/**
 * A cell a spreadsheet reads as a value, never as an instruction.
 *
 * Excel, LibreOffice and Sheets all treat a cell opening with `=`, `+`, `-` or
 * `@` as a formula, and CSV quoting does not stop them: the quotes belong to the
 * CSV parser and are gone before the formula detector looks. So an item named
 * `=HYPERLINK("http://…","اینجا")` -- a name a colleague can type into the
 * module and nobody would query -- becomes a live link in the workbook of
 * whoever opens the export.
 *
 * The guard is a leading apostrophe, which every one of them reads as "the rest
 * is text" and none of them prints.
 *
 * WHY A NUMBER IS LEFT ALONE
 * `-` opens a formula and also opens every negative amount in this module: a
 * reversal's effect, a downward revision, a variance below the estimate.
 * Guarding those would turn a column of money into a column of captions and
 * break every SUM in the sheet the export exists to feed -- which is the whole
 * reason money is written here as the exact integer rial rather than the
 * compacted form on screen. A plain number, signed or not, stays a number.
 */
const FORMULA_LEAD = /^[=+\-@\t\r]/;
const PLAIN_NUMBER = /^[-+]?\d+(\.\d+)?$/;

export function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  const guarded = FORMULA_LEAD.test(text) && !PLAIN_NUMBER.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(guarded) ? `"${guarded.replaceAll('"', '""')}"` : guarded;
}

export function csvRow(values) {
  return values.map(csvCell).join(",");
}

export function csvDocument(lines) {
  return BOM + lines.join(CRLF) + CRLF;
}

/** Strips a project code down to what is safe in a file name on any platform. */
export function csvFileNamePart(value, fallback = "project") {
  const cleaned = String(value ?? "").replace(/[^A-Za-z0-9_-]/g, "");
  return cleaned || fallback;
}

/**
 * Hands the file to the browser. The object URL is revoked on the next frame
 * rather than immediately: some browsers have not started reading the blob by
 * the time click() returns, and revoking too early gives an empty file.
 */
export function downloadCsvFile(csv, fileName) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  requestAnimationFrame(() => URL.revokeObjectURL(url));
}
