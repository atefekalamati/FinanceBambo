import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "../helpers/dom.js";

installDom();

const { renderPageState } = await import("../../src/shared/components/page-state.js");
const { createRequestState, REQUEST_STATUS } = await import("../../src/core/state/request-state.js");
const { createApiClient } = await import("../../src/core/api/api-client.js");

/* THE PAGE THAT NEVER LEFT «در حال بارگذاری».
 *
 * Every feature page paints the loading card first and replaces it when the render
 * returns. Two things kept the replacement from ever happening, and neither said so on
 * screen: the render threw, or a request never answered. Both now end in a card.
 */

test("a render that throws becomes a card, not a page stuck on the loading state", () => {
  const seen = [];
  const original = console.error;
  console.error = (...args) => seen.push(args);
  try {
    const node = renderPageState(createRequestState(REQUEST_STATUS.SUCCESS, { metrics: null }), {
      renderContent: (data) => data.metrics.initialEstimateIrr,   // TypeError on null
    });
    assert.equal(node.tagName, "SECTION");
    assert.match(node.textContent, /نمایش اطلاعات انجام نشد/);
    assert.match(node.textContent, /CLIENT_RENDER_ERROR/);
    assert.equal(node.getAttribute("role"), "alert");
    /* The card hides the exception on purpose; the console is where it goes. */
    assert.equal(seen.length, 1);
    assert.ok(seen[0][1] instanceof TypeError);
  } finally {
    console.error = original;
  }
});

test("a render that succeeds is returned untouched", () => {
  const node = renderPageState(createRequestState(REQUEST_STATUS.SUCCESS, { ok: true }), {
    renderContent: () => document.createElement("article"),
  });
  assert.equal(node.tagName, "ARTICLE");
});

function withWindow(t) {
  const previous = globalThis.window;
  globalThis.window = { location: { origin: "https://finance.test" } };
  t.after(() => { globalThis.window = previous; });
}

test("a request the service never answers is given up on, retryably", async (t) => {
  withWindow(t);
  const client = createApiClient({
    requestTimeoutMs: 20,
    fetchImpl: (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }),
  });
  await assert.rejects(client.request("/api/slow"), (error) => {
    assert.equal(error.name, "ApiError");
    assert.equal(error.code, "REQUEST_TIMEOUT");
    assert.equal(error.status, 0);
    return true;
  });
});

test("a fetch the browser could not make is a transport error, not a display fault", async (t) => {
  withWindow(t);
  const client = createApiClient({ fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
  await assert.rejects(client.request("/api/unreachable"), (error) => {
    assert.equal(error.name, "ApiError");
    assert.equal(error.code, "NETWORK_UNREACHABLE");
    return true;
  });
  const { presentApiError } = await import("../../src/shared/errors/error-presentation.js");
  const shown = presentApiError(await client.request("/api/unreachable").catch((e) => e));
  assert.equal(shown.title, "ارتباط با سرویس مالی برقرار نشد");
  assert.equal(shown.retryable, true, "the reader may try again; a display fault could not be");
});

test("the caller's own cancellation still passes through as itself", async (t) => {
  withWindow(t);
  const abort = new DOMException("Cancelled", "AbortError");
  const client = createApiClient({ fetchImpl: async () => { throw abort; } });
  await assert.rejects(client.request("/api/test"), (error) => error === abort);
});
