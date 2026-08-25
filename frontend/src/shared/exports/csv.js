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

export function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
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
