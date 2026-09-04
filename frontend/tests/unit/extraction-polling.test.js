import test from "node:test";
import assert from "node:assert/strict";
import { createApiAttachmentsAdapter } from "../../src/adapters/api/attachments-api-adapter.js";
import { DEFAULT_ATTEMPTS, DEFAULT_INTERVAL_MS, waitForExtraction } from "../../src/features/ai-review/extraction-polling.js";

const context = { organizationId: "org-1", projectId: "project-1", locale: "fa-IR" };

/** A fake clock: the poll never actually sleeps, so these tests run instantly. */
const nowait = async () => {};

/** An adapter whose `getFiles` walks a scripted list of statuses, one per call. */
function adapterReporting(statuses, { fileId = "file-1", failEveryCall = 0 } = {}) {
  let call = 0;
  return {
    calls: () => call,
    async getFiles() {
      const index = call;
      call += 1;
      if (index < failEveryCall) throw new Error("network hiccup");
      const status = statuses[Math.min(index, statuses.length - 1)];
      return status === null ? [] : [{ fileId, processingStatus: status }];
    },
  };
}

test("the adapter posts to the async extraction route, not the blocking one", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); return { processingStatus: "processing" }; } };
  await createApiAttachmentsAdapter(context, client).startExtraction("file-1");
  const call = calls[0];
  assert.ok(call.path.endsWith("/files/file-1/extractions/async"), `posted to ${call.path}`);
  assert.equal(call.options.method, "POST");
  // The synchronous route must not be what the page reaches for any more: it held the
  // request open for the whole OCR run.
  assert.ok(!call.path.endsWith("/files/file-1/extractions"));
});

test("the async start still carries the locale hint the backend expects", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); return {}; } };
  await createApiAttachmentsAdapter(context, client).startExtraction("file-1");
  assert.deepEqual(JSON.parse(calls[0].options.body), { hints: { locale: "fa-IR" } });
});

test("polling reports ready once the file settles", async () => {
  const adapter = adapterReporting(["processing", "processing", "ready"]);
  const settled = await waitForExtraction({ adapter, fileId: "file-1", wait: nowait });
  assert.equal(settled, "ready");
  assert.equal(adapter.calls(), 3, "stops asking as soon as it settles");
});

test("polling reports failed so the card can show the failure and offer a retry", async () => {
  const adapter = adapterReporting(["processing", "failed"]);
  assert.equal(await waitForExtraction({ adapter, fileId: "file-1", wait: nowait }), "failed");
});

test("a file that never left uploaded is reported, not waited on", async () => {
  // What a refused start looks like: nothing was ever claimed, so there is nothing to wait
  // for. Returning it immediately is what lets the caller refresh and stop.
  const adapter = adapterReporting(["uploaded"]);
  assert.equal(await waitForExtraction({ adapter, fileId: "file-1", wait: nowait }), "uploaded");
  assert.equal(adapter.calls(), 1);
});

test("a duplicate request resolves to the running extraction's real outcome", async () => {
  // The second request is refused with 503 while the file genuinely is processing. The
  // page ignores that rejection and polls; this is the behaviour it depends on.
  const adapter = adapterReporting(["processing", "processing", "ready"]);
  assert.equal(await waitForExtraction({ adapter, fileId: "file-1", wait: nowait }), "ready");
});

test("one failed poll does not end the wait", async () => {
  // The work continues on the server whatever the browser's connection did.
  const adapter = adapterReporting(["ready"], { failEveryCall: 2 });
  assert.equal(await waitForExtraction({ adapter, fileId: "file-1", wait: nowait }), "ready");
  assert.equal(adapter.calls(), 3, "two rejections, then the real answer");
});

test("a file that never settles times out rather than polling forever", async () => {
  const adapter = adapterReporting(["processing"]);
  const settled = await waitForExtraction({ adapter, fileId: "file-1", attempts: 4, wait: nowait });
  assert.equal(settled, "timeout");
  assert.equal(adapter.calls(), 4);
});

test("a file that disappears from the list ends the wait", async () => {
  const adapter = adapterReporting([null]);
  assert.equal(await waitForExtraction({ adapter, fileId: "file-1", wait: nowait }), "timeout");
});

test("the defaults cover a cold local OCR run", () => {
  // A cold PaddleOCR run measured ~35s and a warm one ~12s; the window has to clear both
  // with room, or the page would give up on work that is about to finish.
  assert.ok(DEFAULT_ATTEMPTS * DEFAULT_INTERVAL_MS >= 60_000);
});
