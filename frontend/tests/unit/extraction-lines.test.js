import test from "node:test";
import assert from "node:assert/strict";

import { draftItems, fieldValue, invoiceLines, linesTotalIrr, proposedLines, reconcile,
         rowAmountIrr, unattachedRows }
  from "../../src/features/ai-review/extraction-lines.js";

/* The invoice lines a draft proposes, and what a reviewer may do to them.
 *
 * The review card used to confirm every extraction as ONE line carrying the total, with
 * no quantity and no rate, and refused to attach it to anything but a general cost. A
 * general cost carries no estimate line, so no activity and no WBS stage can be derived
 * for it — every invoice read from a document or a recording landed outside the
 * level-one chart, and the message told the reader to type it in by hand instead.
 */

const field = (key, value, confidence = 0.9) =>
  ({ key, extractedValue: value, confirmedValue: null, confidence });

const DRAFT = {
  fields: [
    field("supplierName", "آهن‌فروشی رضایی"),
    field("invoiceDate", "2026-08-10"),
    field("totalAmount", "11778600"),
    field("items", [
      { name: "میلگرد ۱۶", quantity: "2.5", unit: "kg", unitPrice: "1000", amount: "2500" },
      { name: "سیمان", quantity: null, unit: null, unitPrice: null, amount: "9276100" },
    ]),
  ],
};

const TARGETS = [
  { targetId: "t-line", targetType: "estimate_line", estimateLineId: "line-1",
    resourceId: "res-1", unit: "kg", label: "آرماتوربندی · میلگرد" },
  { targetId: "t-general", targetType: "general_cost", estimateLineId: null,
    resourceId: "res-general", unit: null, label: "مجوز ساخت" },
];

/* ─────────────────────────── reading the draft ─────────────────────────── */

test("a reviewer's own edit wins over the reading", () => {
  const edited = { fields: [{ key: "supplierName", extractedValue: "رضائی",
                              confirmedValue: "رضایی", confidence: 0.4 }] };
  assert.equal(fieldValue(edited, "supplierName"), "رضایی");
  assert.equal(fieldValue(DRAFT, "supplierName"), "آهن‌فروشی رضایی");
  assert.equal(fieldValue(DRAFT, "nothing"), null);
});

test("an item that states no money at all is dropped, never priced at zero", () => {
  /* It would reach the service as a line worth nothing and be counted as one. */
  const noisy = { fields: [field("items", [
    { name: "قلم واقعی", amount: "500" },
    { name: "قلم بی‌معنا" },
    { name: "مقدار بدون نرخ", quantity: "3" },
  ])] };
  assert.deepEqual(draftItems(noisy).map((item) => item.description), ["قلم واقعی"]);
});

test("a quantity and a rate are money even with no stated amount", () => {
  const paired = { fields: [field("items", [{ name: "x", quantity: "2", unitPrice: "50" }])] };
  assert.equal(draftItems(paired).length, 1);
});

test("items that are not a list are no items, not a crash", () => {
  assert.deepEqual(draftItems({ fields: [field("items", "متن")] }), []);
  assert.deepEqual(draftItems({ fields: [] }), []);
  assert.deepEqual(draftItems(null), []);
});

/* ─────────────────────────── the rows a card starts from ─────────────────────────── */

test("one row per item the reader found", () => {
  const rows = proposedLines(DRAFT);
  assert.deepEqual(rows.map((row) => row.description), ["میلگرد ۱۶", "سیمان"]);
  assert.deepEqual(rows.map((row) => row.targetId), [null, null],
                   "nothing guesses which activity a purchase belongs to");
});

test("a draft with no items still offers a row, carrying the total", () => {
  /* Every document that states only a total, and possibly most spoken ones. An empty
     table would leave the reviewer nothing to attach. */
  const rows = proposedLines({ fields: [field("totalAmount", "5000")] });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].amount, "5000");
  assert.equal(rows[0].quantity, null);
});

/* ─────────────────────────── what a row is worth ─────────────────────────── */

test("a stated amount wins over the product, as the service resolves it", () => {
  /* `_calculate_lines` reads `line_amount_irr` first and never multiplies when it is
     present. Deriving a different figure here would show the reviewer one number and
     write another. */
  assert.equal(rowAmountIrr({ amount: "100", quantity: "2", unitPrice: "999" }), "1000");
});

test("the product is exact at a fractional quantity", () => {
  /* 2.5 × 1,000 toman = 25,000 rial. Through a float this is where a rial goes missing. */
  assert.equal(rowAmountIrr({ quantity: "2.5", unitPrice: "1000" }), "25000");
  assert.equal(rowAmountIrr({ quantity: "0.001", unitPrice: "1" }), "0");
});

test("a row that states no money is worth nothing, not zero", () => {
  assert.equal(rowAmountIrr({ quantity: "3" }), null, "a quantity with no rate measures nothing");
  assert.equal(rowAmountIrr({ unitPrice: "100" }), null);
  assert.equal(rowAmountIrr({}), null);
  assert.equal(linesTotalIrr([{ amount: "100" }, {}]), "1000", "and contributes nothing to the sum");
});

/* ─────────────────────────── the draft against itself ─────────────────────────── */

test("lines that add up to the stated total say so", () => {
  const rows = [{ amount: "1000" }, { amount: "177860" }];
  const check = reconcile(rows, { fields: [field("totalAmount", "178860")] });
  assert.equal(check.matches, true);
  assert.equal(check.differenceIrr, "0");
});

test("lines that do not add up name the difference and its direction", () => {
  const check = reconcile(proposedLines(DRAFT), DRAFT);
  assert.equal(check.matches, false);
  assert.equal(check.over, false, "the lines fall short of the stated total");
  assert.equal(check.statedIrr, "117786000");
  assert.equal(check.linesIrr, "92786000");
  assert.equal(check.differenceIrr, "25000000");
});

test("nothing is compared when there is nothing to compare with", () => {
  /* A note about the difference between a number and an absence is noise. */
  assert.equal(reconcile([{ amount: "100" }], { fields: [] }), null, "no stated total");
  assert.equal(reconcile([{}], DRAFT), null, "no priced row");
});

test("the comparison never looks outside this draft", () => {
  /* The service is explicit that two uploads cannot be assumed to describe the same
     document, so no image draft is ever weighed against a voice one. */
  const source = reconcile.toString();
  assert.doesNotMatch(source, /fetch|adapter|other|linked/i);
});

/* ─────────────────────────── what a confirmation sends ─────────────────────────── */

test("a line attached to an estimate line carries it, which is what reaches the chart", () => {
  const rows = [{ key: "a", description: "میلگرد", quantity: "2.5", unit: "kg",
                  unitPrice: "1000", amount: null, targetId: "t-line" }];
  const [line] = invoiceLines(rows, TARGETS);
  assert.equal(line.estimateLineId, "line-1");
  assert.equal(line.resourceId, "res-1");
  assert.equal(line.quantity, "2.5");
  assert.equal(line.unit, "kg");
  assert.equal(line.unitPriceIrr, "10000");
  assert.equal(line.lineAmountIrr, "25000",
               "stated as well as derived, so the service never re-multiplies");
});

test("a general cost carries no estimate line and no quantity", () => {
  /* It genuinely belongs to no activity, and the service refuses a quantity on one. */
  const rows = [{ key: "a", quantity: "3", unitPrice: "100", amount: "500",
                  targetId: "t-general" }];
  const [line] = invoiceLines(rows, TARGETS);
  assert.equal(line.estimateLineId, null);
  assert.equal(line.quantity, null);
  assert.equal(line.unitPriceIrr, null);
  assert.equal(line.lineAmountIrr, "5000");
});

test("a quantity with no rate travels as neither", () => {
  /* The two are one statement. Sending a quantity alone would have the service score the
     line as quantity times nothing. */
  const rows = [{ key: "a", quantity: "3", amount: "500", targetId: "t-line" }];
  const [line] = invoiceLines(rows, TARGETS);
  assert.equal(line.quantity, null);
  assert.equal(line.unitPriceIrr, null);
  assert.equal(line.lineAmountIrr, "5000", "but the amount still travels");
});

test("a row nobody attached, or nobody priced, is not sent", () => {
  assert.deepEqual(invoiceLines([{ key: "a", amount: "500", targetId: null }], TARGETS), []);
  assert.deepEqual(invoiceLines([{ key: "a", amount: null, targetId: "t-line" }], TARGETS), []);
  assert.deepEqual(invoiceLines([{ key: "a", amount: "1", targetId: "gone" }], TARGETS), []);
});

test("the rows still waiting for an answer are named", () => {
  const rows = [{ key: "item-0", targetId: "t-line" }, { key: "item-1", targetId: null }];
  assert.deepEqual(unattachedRows(rows), ["item-1"]);
  assert.deepEqual(unattachedRows([]), []);
});

test("the unit falls back to the target's when the reading states none", () => {
  const rows = [{ key: "a", quantity: "2", unitPrice: "100", targetId: "t-line" }];
  assert.equal(invoiceLines(rows, TARGETS)[0].unit, "kg");
});

/* ─────────────────────── the transcript is evidence, not a field ─────────────────────── */

const pageSource = await import("node:fs/promises")
  .then((fs) => fs.readFile(new URL("../../src/features/ai-review/ai-review-page.js",
                                    import.meta.url), "utf8"));

test("the transcript never reaches the editable field grid", () => {
  /* The service keeps it because a spoken amount and a printed one can disagree, and it
     is the only evidence they do. A box a reviewer can type into is not evidence — and a
     one-line input holding a paragraph of speech is not readable either. */
  const provenance = pageSource.slice(pageSource.indexOf("PROVENANCE_KEYS"),
                                      pageSource.indexOf("PROVENANCE_KEYS") + 300);
  assert.match(provenance, /voiceTranscript/, "the transcript is classified as provenance");
  assert.match(provenance, /rawText/, "and so is the OCR text");
  assert.match(pageSource, /LINE_EDITOR_KEYS = Object\.freeze\(new Set\(\["items"\]\)\)/,
               "`items` became the line editor rather than an input");
  assert.match(pageSource, /!LINE_EDITOR_KEYS\.has\(field\.key\)/, "the grid renders neither");
  assert.match(pageSource, /!PROVENANCE_KEYS\.has\(field\.key\)/);
});

test("an unmeasured confidence is stated, never printed as zero percent", () => {
  /* The speech provider reports no per-segment probability and the service sends null
     rather than a figure invented beside it. `Math.round(Number(null) * 100)` is 0, so
     the old form claimed «۰ درصد اطمینان» about a reading nobody had scored. */
  assert.match(pageSource, /اطمینان اندازه‌گیری نشده/);
  assert.match(pageSource, /measured && field\.confidence < 0\.8/,
               "an unscored field is not coloured as a low-confidence one");
});

test("the confirmation sends the service's own key names", () => {
  /* `vendorName` and `totalIRR` were this page's names, from the mock adapter it was
     built against; the backend has never sent either. Three tests read `undefined`, so
     the confirm button could not succeed on any real extraction. */
  assert.match(pageSource, /values\.supplierName/, "the supplier is read under the service's key");
  assert.doesNotMatch(pageSource, /values\.vendorName/, "the mock adapter's names are gone");
  assert.doesNotMatch(pageSource, /values\.totalIRR/);
});

/* ─────────────────── correcting a draft before deciding on it ─────────────────── */

test("a correction can be saved without confirming anything", () => {
  /* The step that used to be impossible: the correction and the irreversible act were
     one button, so a reviewer could not fix a misheard amount, look at what they fixed,
     and only then decide. */
  assert.match(pageSource, /adapter\.editExtraction\(/, "the save button calls the edit route");
  assert.match(pageSource, /ذخیره تصحیحات/);
  assert.match(pageSource, /پیش‌نویس هنوز تأیید نشده و اثر مالی ندارد/,
               "and says so, because a button that writes must account for what it wrote");
});

test("a saved correction carries the new version forward", () => {
  /* The service moves the version on every edit. A card holding the old one would have
     its next write refused as stale -- which is what an optimistic version is for. */
  assert.match(pageSource, /draft\.version = updated\?\.version \?\? draft\.version/);
  assert.match(pageSource, /mine\.confirmedValue = field\.confirmedValue/,
               "and the saved values, so the card stops offering to save them again");
});

test("saving does not repaint the card", () => {
  /* The reviewer's line targets and amounts live in the card. Reloading after a save
     would throw away the work they came to do -- the same mistake the schedule panel
     made and was measured making. */
  const handler = pageSource.slice(pageSource.indexOf("adapter.editExtraction("),
                                   pageSource.lastIndexOf("const confirm = element"));
  assert.doesNotMatch(handler, /onChanged\(\)/);
});

test("the service owns which fields may not be corrected, and says so itself", () => {
  /* `PROVENANCE_KEYS` lives in the service and it refuses an edit to one with a 422. A
     second list kept here would disagree with it the first time either changed, and the
     reader would be told the wrong reason. */
  const handler = pageSource.slice(pageSource.indexOf("adapter.editExtraction("),
                                   pageSource.lastIndexOf("const confirm = element"));
  assert.match(handler, /formatApiErrorMessage\(error/);
});

test("a correction already saved is still sent when the invoice is confirmed", () => {
  /* `confirm` rebuilds its fields from `edits.get(key, extracted_value)` -- note the
     fallback is what the MODEL read, not what the reviewer saved. A correction left out
     of the confirmation would silently revert. Comparing against `extractedValue` is
     what keeps it in. */
  assert.match(pageSource, /values\[field\.key\] !== String\(field\.extractedValue \?\? ""\)/);
  assert.match(pageSource, /const fieldConfirmations = corrections\(\)/,
               "one definition, used by the save button and the confirmation alike");
});
