import test from "node:test";
import assert from "node:assert/strict";

import { fetchGoogleSheetAsFile, GoogleSheetError, googleSheetExportUrl, parseGoogleSheetUrl }
  from "../../src/shared/imports/google-sheet.js";

/* A .xlsx is a zip, so it opens with "PK". Everything downstream leans on that. */
const XLSX = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0, 0, 0, 0]).buffer;
const HTML = new TextEncoder().encode("<!doctype html><title>Sign in</title>").buffer;
const ok = (body) => async () => ({ ok: true, status: 200, arrayBuffer: async () => body });

test("a sheet link gives up its document, and its tab when it names one", () => {
  assert.deepEqual(parseGoogleSheetUrl("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=1842"),
    { id: "1AbCdEfGhIjKlMnOpQrStUvWxYz", gid: "1842" });
  assert.deepEqual(parseGoogleSheetUrl("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"),
    { id: "1AbCdEfGhIjKlMnOpQrStUvWxYz", gid: null });
});

test("anything that is not a Google Sheets link is refused rather than fetched", () => {
  for (const value of ["", "   ", null, undefined, "not a url", "https://example.com/a.xlsx",
                       "https://docs.evil.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
                       "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"]) {
    assert.equal(parseGoogleSheetUrl(value), null, `parseGoogleSheetUrl(${String(value)})`);
  }
});

test("the tab travels to the export, which is what stops the wrong sheet being read", () => {
  assert.equal(googleSheetExportUrl({ id: "ABC", gid: "77" }),
    "https://docs.google.com/spreadsheets/d/ABC/export?format=xlsx&gid=77");
  assert.equal(googleSheetExportUrl({ id: "ABC", gid: null }),
    "https://docs.google.com/spreadsheets/d/ABC/export?format=xlsx");
});

test("a workbook comes back as the .xlsx file the import endpoint already takes", async () => {
  const file = await fetchGoogleSheetAsFile("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
    { fetchImpl: ok(XLSX), name: "price-import" });
  assert.equal(file.name, "price-import.xlsx");
  assert.equal(file.type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  assert.equal(file.size, 8);
});

test("a private sheet answers with a sign-in page, and that is said in those terms", async () => {
  // Google returns 200 and HTML rather than an error status, so the status code
  // cannot be what tells these apart -- the first two bytes can.
  await assert.rejects(
    () => fetchGoogleSheetAsFile("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit", { fetchImpl: ok(HTML) }),
    (error) => error instanceof GoogleSheetError && error.message.includes("عمومی"));
});

test("a refusal and a blocked request each say something a reader can act on", async () => {
  await assert.rejects(
    () => fetchGoogleSheetAsFile("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
      { fetchImpl: async () => ({ ok: false, status: 403, arrayBuffer: async () => XLSX }) }),
    (error) => error instanceof GoogleSheetError && error.message.includes("عمومی"));
  await assert.rejects(
    () => fetchGoogleSheetAsFile("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
      { fetchImpl: async () => { throw new TypeError("Failed to fetch"); } }),
    (error) => error instanceof GoogleSheetError && error.message.includes("اینترنت"));
});

test("a link that is not a sheet never reaches the network", async () => {
  let called = false;
  await assert.rejects(
    () => fetchGoogleSheetAsFile("https://example.com/x", { fetchImpl: async () => { called = true; return ok(XLSX)(); } }),
    (error) => error instanceof GoogleSheetError);
  assert.equal(called, false, "a non-sheet link must not be fetched");
});
