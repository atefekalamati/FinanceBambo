import test from "node:test";
import assert from "node:assert/strict";
import { createApiClient } from "../../src/core/api/api-client.js";

test("request and download preserve both server error contracts", async (t) => {
  const previous = globalThis.window;
  globalThis.window = { location: { origin: "https://finance.test" } };
  t.after(() => { globalThis.window = previous; });
  const details = [{ field: "quantity", message: "مقدار نامعتبر است" }];
  const cases = [
    { body: { error: { code: "VALIDATION_ERROR", message: "بررسی مقدار", request_id: "finance-id", details } }, status: 422, code: "VALIDATION_ERROR", message: "بررسی مقدار", id: "finance-id", details },
    { body: { code: "PROJECT_NOT_FOUND", messageFa: "پروژه یافت نشد.", requestId: "host-id", details }, status: 404, code: "PROJECT_NOT_FOUND", message: "پروژه یافت نشد.", id: "host-id", details },
    { body: { error: { code: "DENIED", messageFa: "دسترسی ندارید", message: "Forbidden" }, requestId: "outer-id" }, status: 403, code: "DENIED", message: "دسترسی ندارید", id: "outer-id" },
    { body: { code: "", messageFa: "", details: {} }, status: 503, code: "HTTP_503", id: "header-id" },
    { raw: "<html>Gateway unavailable</html>", status: 502, code: "HTTP_502", id: "header-id" },
    { raw: "", status: 401, code: "HTTP_401", id: "header-id" },
  ];
  for (const method of ["request", "download"]) {
    for (const item of cases) {
      const client = createApiClient({ fetchImpl: async (_url, options) => {
        assert.equal(options.credentials, "same-origin");
        return new Response(item.raw ?? JSON.stringify(item.body), { status: item.status, headers: { "X-Request-ID": "header-id" } });
      } });
      await assert.rejects(client[method]("/api/projects/terrace/finance/resources"), (error) => {
        assert.equal(error.name, "ApiError");
        assert.equal(error.status, item.status);
        assert.equal(error.code, item.code);
        assert.equal(error.requestId, item.id);
        assert.deepEqual(error.details, item.details ?? []);
        if (item.message) assert.equal(error.message, item.message);
        else assert.ok(error.message && !error.message.includes("<html>"));
        return true;
      });
    }
  }
});

test("successful requests, downloads, cancellation and origin boundary stay intact", async (t) => {
  const previous = globalThis.window;
  globalThis.window = { location: { origin: "https://finance.test" } };
  t.after(() => { globalThis.window = previous; });
  const client = createApiClient({ fetchImpl: async () => new Response('{"items":[]}', { headers: { "Content-Disposition": 'attachment; filename="report.csv"' } }) });
  assert.deepEqual(await client.request("/api/test"), { items: [] });
  const file = await client.download("/api/test");
  assert.equal(file.fileName, "report.csv");
  assert.equal(await file.blob.text(), '{"items":[]}');
  const empty = createApiClient({ fetchImpl: async () => new Response(null, { status: 204 }) });
  assert.equal(await empty.request("/api/test"), null);
  const abort = new DOMException("Cancelled", "AbortError");
  const cancelled = createApiClient({ fetchImpl: async () => { throw abort; } });
  await assert.rejects(cancelled.request("/api/test"), (error) => error === abort);
  await assert.rejects(client.request("https://elsewhere.test/api"), (error) => error.code === "CROSS_ORIGIN_BLOCKED");
});
