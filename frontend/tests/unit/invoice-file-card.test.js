import assert from "node:assert/strict";
import test from "node:test";

import { installDom } from "../helpers/dom.js";

installDom();

/* The card navigates, and where it navigates is half of what these tests are about. The
   shared DOM stub carries no `window`, so the smallest one that can record a hash is
   installed here rather than widening the helper for one page. */
globalThis.window = { location: { hash: "" } };
const wentTo = () => globalThis.window.location.hash;

const { renderFiles } =
  await import("../../src/features/ai-review/invoice-files-page.js");

const file = (changes = {}) => ({
  fileId: "file-1",
  originalNameSafe: "invoice.png",
  logicalType: "invoice_image",
  mimeType: "image/png",
  sizeBytes: 4096,
  uploadedAt: "2026-09-24T08:00:00+03:30",
  processingStatus: "uploaded",
  processingError: null,
  ...changes,
});

const button = (section) => [...section.querySelectorAll("button")]
  .find((node) => /پردازش|مشاهده نتیجه/.test(node.textContent));

function adapterSaying(outcome) {
  const calls = [];
  return {
    calls,
    async startExtraction(fileId) { calls.push(fileId); return outcome; },
    async getFiles() { return [file({ processingStatus: "ready" })]; },
  };
}

test("a file nobody has read yet is offered as one to start reading", () => {
  const section = renderFiles([file()], { adapter: adapterSaying(null), canUpload: true, onChanged: async () => {} });
  assert.equal(button(section).textContent, "شروع پردازش");
});

test("a failed file is offered as one to read again", () => {
  const section = renderFiles([file({ processingStatus: "failed" })],
    { adapter: adapterSaying(null), canUpload: true, onChanged: async () => {} });
  assert.equal(button(section).textContent, "پردازش دوباره");
});

test("a file the service has already read is not offered as one to start reading", async () => {
  /* It CANNOT be re-read through this route: the service answers 202 naming the draft the
     file already has and queues nothing. «شروع پردازش» promised work that never happened,
     and the press ended on the review page showing the old draft as though it were new. */
  const adapter = adapterSaying(null);
  const section = renderFiles([file({ processingStatus: "ready" })],
    { adapter, canUpload: true, onChanged: async () => {} });
  const control = button(section);
  assert.equal(control.textContent, "مشاهده نتیجهٔ خواندن");
  globalThis.window.location.hash = "";
  control.dispatch("click");
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.deepEqual(adapter.calls, [], "and pressing it asks the service for nothing");
  assert.equal(wentTo(), "#finance/ai-review", "it goes straight to the reading");
});

test("when the service names a draft it already has, nothing is waited for", async () => {
  /* `alreadyExtracted` is an answer, not a failure. Polling a status that will never move
     would spend a minute arriving at what the response already said -- and that is exactly
     what happened while this body was thrown away. */
  let polled = 0;
  const adapter = {
    async startExtraction() { return { alreadyExtracted: true, extractionId: "draft-9" }; },
    async getFiles() { polled += 1; return [file({ processingStatus: "uploaded" })]; },
  };
  let refreshed = 0;
  const section = renderFiles([file({ processingStatus: "uploaded" })],
    { adapter, canUpload: true, onChanged: async () => { refreshed += 1; } });
  button(section).dispatch("click");
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(polled, 0, "the file's status was never polled");
  assert.equal(refreshed, 1, "the list was refreshed once");
  assert.equal(wentTo(), "#finance/ai-review");
});

test("a start that says nothing about a previous reading is still waited for", async () => {
  /* The old path, unchanged: the file's own status is the answer. An absent flag must not
     be read as «already done» -- that would skip to a draft that may not exist. */
  let polled = 0;
  const adapter = {
    async startExtraction() { return { alreadyExtracted: false, extractionId: null }; },
    async getFiles() { polled += 1; return [file({ processingStatus: "ready" })]; },
  };
  const section = renderFiles([file({ processingStatus: "uploaded" })],
    { adapter, canUpload: true, onChanged: async () => {} });
  button(section).dispatch("click");
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.ok(polled >= 1, "the status was polled");
});
