import assert from "node:assert/strict";
import test from "node:test";

import { installDom } from "../helpers/dom.js";

installDom();

const { draftWarnings, warningEvidence, warningText, WARNING_KEYS } =
  await import("../../src/features/ai-review/extraction-warnings.js");
const { reviewCard } =
  await import("../../src/features/ai-review/ai-review-page.js");

const draft = (fields) => ({
  draftId: "d-1", version: 1, reviewStatus: "awaitingReview",
  file: { logicalType: "invoice_image", originalNameSafe: "page2.jpg" },
  extractionSource: "ai", confidence: 0.9,
  fields: [{ key: "supplierName", extractedValue: "شرکت تست بام", confidence: 0.9 },
           { key: "totalAmount", extractedValue: "1200000", confidence: 0.9 },
           ...fields],
});

const CURRENCY = {
  key: "currencyWarnings", confidence: 1.0,
  extractedValue: [{ source: "currency-unevidenced",
    message: "a currency was reported that the document does not state, and was not "
           + "recorded; state it during review if this invoice needs one" }],
};

const card = (fields) => reviewCard({
  draft: draft(fields), targets: [], adapter: {}, canEdit: true,
  onChanged: () => {}, root: null,
});

test("every warning family the service emits is recognised as one", () => {
  /* Six keys, all carrying `[{source|code, message}]`. Any one of them missing from this
     set falls through to the field grid and becomes an editable «[object Object]». */
  ["currencyWarnings", "parserWarnings", "aiWarnings",
   "ocrWarnings", "layoutWarnings", "fusionWarnings"].forEach((key) => {
    assert.ok(WARNING_KEYS.has(key), key);
  });
});

test("the identifier decides the wording, not the English sentence", () => {
  assert.match(warningText({ source: "currency-unevidenced", message: "ignored" }),
               /واحد پول روی سند نوشته نشده بود/);
  assert.match(warningText({ code: "INVOICE_TOTAL_MISMATCH", message: "ignored" }),
               /جمع اقلام با مبلغ نهایی سند نمی‌خواند/);
});

test("a warning this build does not know is still shown, in the service's own words", () => {
  /* Silence about a warning the service raised is worse than an unfamiliar sentence on
     screen -- the same rule the report's warnings follow. */
  assert.equal(warningText({ code: "SOMETHING_NEW", message: "a new situation" }),
               "a new situation");
  assert.equal(warningText({ source: "layout-some-future-reason", message: "" }),
               "layout-some-future-reason");
  assert.equal(warningText({}), null);
});

test("evidence travels, because it is figures rather than prose", () => {
  assert.equal(warningEvidence({ evidence: "1100000 != 1200000" }), "1100000 != 1200000");
  assert.equal(warningEvidence({}), null);
});

test("the same sentence reaching two families is said once", () => {
  /* A total the parser could not check and a fusion result that says the readings
     disagree describe one situation; a reviewer reading it twice learns nothing. */
  const rows = draftWarnings(draft([
    { key: "parserWarnings", extractedValue: [{ code: "INVOICE_TOTAL_MISMATCH" }] },
    { key: "fusionWarnings", extractedValue: [{ code: "INVOICE_TOTAL_MISMATCH" }] },
  ]));
  assert.equal(rows.length, 1);
});

test("a currency the document never stated is a sentence, not «[object Object]»", () => {
  /* THE ONE THAT MADE THIS URGENT. The service refuses to record a currency the page does
     not print -- تومان and ریال are a factor of ten apart -- and this card converts every
     amount as تومان regardless. The warning is the only thing standing between a rial
     invoice and a tenfold error, and it used to render as an editable «[object Object]». */
  const rendered = card([CURRENCY]);
  assert.doesNotMatch(rendered.textContent, /\[object Object\]/);
  const rows = [...rendered.querySelectorAll(".ai-warnings__row")];
  assert.equal(rows.length, 1);
  assert.match(rows[0].textContent, /اگر این فاکتور به ریال است/);
  assert.equal(rows[0].dataset.warningKey, "currencyWarnings");
});

test("a warning is read, never typed into", () => {
  /* Outside the field grid AND outside `controls`, so «ذخیره تصحیحات» can never send a
     reviewer's keystrokes back as the confirmed value of a warning. */
  const rendered = card([CURRENCY]);
  assert.equal(rendered.querySelectorAll(".ai-warnings input, .ai-warnings select").length, 0);
  const labels = [...rendered.querySelectorAll(".ai-field__label strong")]
    .map((node) => node.textContent);
  assert.deepEqual(labels, ["فروشنده یا ارائه‌دهنده", "مبلغ نهایی به تومان"]);
});

test("the reader's diagnostic records are folded away, not shown as empty boxes", () => {
  /* `fusionResult` and `validationResult` are whole objects and nothing is typed into
     them. When either requires review the service restates its findings as
     `fusionWarnings`, which IS shown -- so nothing is lost by hiding the record. */
  const rendered = card([
    { key: "validationResult", extractedValue: { requiresReview: true, checks: [] } },
    { key: "fusionResult", extractedValue: { conflictFields: [], requiresReview: false } },
  ]);
  assert.doesNotMatch(rendered.textContent, /\[object Object\]/);
  assert.equal(rendered.querySelectorAll(".ai-field").length, 2, "only the two readings");
});

test("a draft with nothing to warn about grows no empty list", () => {
  const rendered = card([]);
  assert.equal(rendered.querySelector(".ai-warnings"), null);
});
