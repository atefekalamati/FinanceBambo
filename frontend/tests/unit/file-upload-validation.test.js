import test from "node:test";
import assert from "node:assert/strict";
import { validateInvoiceFile } from "../../src/features/ai-review/file-upload-validation.js";

function file(name, type, size) {
  return { name, type, size };
}

test("accepts every image and voice format in the version 1.1 allowlist", () => {
  const cases = [
    [file("invoice.jpg", "image/jpeg", 1200), "invoice_image"],
    [file("invoice.png", "image/png", 1200), "invoice_image"],
    [file("invoice.webp", "image/webp", 1200), "invoice_image"],
    [file("invoice.mp3", "audio/mpeg", 1200), "invoice_voice"],
    [file("invoice.m4a", "audio/mp4", 1200), "invoice_voice"],
    [file("invoice.wav", "audio/wav", 1200), "invoice_voice"],
    [file("invoice.ogg", "audio/ogg", 1200), "invoice_voice"],
  ];
  cases.forEach(([candidate, logicalType]) => assert.equal(validateInvoiceFile(candidate, logicalType).valid, true));
});

test("rejects forbidden formats and mismatched declared MIME", () => {
  assert.equal(validateInvoiceFile(file("invoice.svg", "image/svg+xml", 1200), "invoice_image").valid, false);
  assert.equal(validateInvoiceFile(file("invoice.gif", "image/gif", 1200), "invoice_image").valid, false);
  assert.equal(validateInvoiceFile(file("invoice.webm", "audio/webm", 1200), "invoice_voice").valid, false);
  assert.ok(validateInvoiceFile(file("invoice.png", "image/jpeg", 1200), "invoice_image").errors.mimeType);
});

test("enforces exact image and voice size limits", () => {
  assert.equal(validateInvoiceFile(file("invoice.png", "image/png", 10 * 1024 * 1024), "invoice_image").valid, true);
  assert.ok(validateInvoiceFile(file("invoice.png", "image/png", 10 * 1024 * 1024 + 1), "invoice_image").errors.size);
  assert.equal(validateInvoiceFile(file("invoice.mp3", "audio/mpeg", 25 * 1024 * 1024), "invoice_voice").valid, true);
  assert.ok(validateInvoiceFile(file("invoice.mp3", "audio/mpeg", 25 * 1024 * 1024 + 1), "invoice_voice").errors.size);
});
