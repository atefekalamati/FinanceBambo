import test from "node:test";
import assert from "node:assert/strict";

import { GoogleSheetError, looksLikeSheetLink, requireSheetLink }
  from "../../src/shared/imports/google-sheet.js";

/* The fetch itself moved to the service: the browser must not call Google, because
   this module's client refuses any address outside the page's origin and the host's
   CSP names `connect-src 'self'`. What is left here is the guess a person can be
   told about without a round trip. */

test("a sheets link is recognised, with or without a tab", () => {
  assert.ok(looksLikeSheetLink("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"));
  assert.ok(looksLikeSheetLink("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=42"));
  assert.ok(looksLikeSheetLink("  https://docs.google.com/spreadsheets/d/e/2PACX-1vABC/pubhtml  "));
});

test("anything that is not a sheets link is refused before a request is made", () => {
  for (const value of ["", "   ", null, undefined, "not a url",
                       "https://example.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz",
                       "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
                       // A host that merely ends in something google-ish.
                       "https://docs.google.com.evil.example/spreadsheets/d/1AbC"]) {
    assert.equal(looksLikeSheetLink(value), false, `looksLikeSheetLink(${String(value)})`);
  }
});

test("an empty box and a wrong link are different things to be told", () => {
  assert.throws(() => requireSheetLink("   "),
    (error) => error instanceof GoogleSheetError && error.message.includes("وارد کنید"));
  assert.throws(() => requireSheetLink("https://example.com/x"),
    (error) => error instanceof GoogleSheetError && error.message.includes("معتبر"));
});

test("a good link comes back trimmed, ready to send", () => {
  const link = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=7";
  assert.equal(requireSheetLink(`  ${link}  `), link);
});

/* Where the link actually goes. The browser probe can only prove that nothing
   left the origin -- the mock adapter answers in process. This names the path. */
test("the adapters send the link to this module's own service, never to Google", async () => {
  const { createApiPricesAdapter } = await import("../../src/adapters/api/prices-api-adapter.js");
  const { createApiFinancialItemsAdapter } = await import("../../src/adapters/api/financial-items-api-adapter.js");

  const seen = [];
  const client = {
    async request(path, options) {
      seen.push({ path, body: options?.body, method: options?.method });
      return { previewId: "11111111-1111-4111-8111-111111111111", kind: "prices", rows: [], errors: [], canCommit: true };
    },
    async download() { throw new Error("not used"); },
  };
  const context = { projectId: "terrace", organizationId: "org", permissionCodes: [] };
  const link = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=3";

  await createApiPricesAdapter(context, client).previewPriceImportFromLink(link);
  await createApiFinancialItemsAdapter(context, client).previewEstimateImportFromLink(link);

  assert.deepEqual(seen.map((call) => call.path), [
    "/api/projects/terrace/finance/imports/prices/preview-link",
    "/api/projects/terrace/finance/imports/estimate/preview-link",
  ]);
  for (const call of seen) {
    assert.equal(call.method, "POST");
    // The link travels as data in the body -- it is never part of an address the
    // browser resolves, which is the whole reason this moved to the service.
    assert.deepEqual(JSON.parse(call.body), { sourceUrl: link });
  }
});
