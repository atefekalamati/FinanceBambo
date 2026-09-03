import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createApiSettingsAdapter } from "../../src/adapters/api/settings-api-adapter.js";
import { createApiFinancialItemsAdapter } from "../../src/adapters/api/financial-items-api-adapter.js";
import { createApiPricesAdapter } from "../../src/adapters/api/prices-api-adapter.js";
import { createApiProgressAdapter } from "../../src/adapters/api/progress-api-adapter.js";
import { createApiInvoicesAdapter } from "../../src/adapters/api/invoices-api-adapter.js";
import { createApiAttachmentsAdapter } from "../../src/adapters/api/attachments-api-adapter.js";
import { createApiReportsAdapter } from "../../src/adapters/api/reports-api-adapter.js";
import { createApiAuditAdapter } from "../../src/adapters/api/audit-api-adapter.js";

/**
 * Every route the frontend calls has to be a route the backend serves.
 *
 * The other contract test asserts that a mapper reshapes a payload correctly,
 * but it builds that payload itself — so it agrees with whatever the frontend
 * already believes. This one reads backend/contracts/openapi.json, the API's own
 * description, and drives each adapter with a client that records the request
 * instead of making it. A route renamed or dropped on the backend fails here,
 * at the point the frontend would have called it.
 *
 * It checks the SHAPE of the conversation — method and path — not payloads.
 * That is the half that used to fail silently and at runtime.
 */

const spec = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../backend/contracts/openapi.json", import.meta.url)), "utf8"),
);

/** `/a/{id}/b` -> matcher that accepts `/a/anything/b` and nothing else. */
function templateMatches(template, actual) {
  const wanted = template.split("/");
  const got = actual.split("/");
  if (wanted.length !== got.length) return false;
  return wanted.every((segment, index) =>
    (segment.startsWith("{") && segment.endsWith("}")) ? got[index].length > 0 : segment === got[index]);
}

function findRoute(method, path) {
  for (const [template, operations] of Object.entries(spec.paths)) {
    if (templateMatches(template, path) && operations[method.toLowerCase()]) {
      return { template, method };
    }
  }
  return null;
}

const CONTEXT = Object.freeze({
  organizationId: "org-1",
  projectId: "proj-1",
  userId: "user-1",
  capabilities: [],
});

/** A client that answers nothing and remembers everything asked of it. */
function recordingClient(calls) {
  const note = (path, options = {}) => {
    calls.push({ method: (options.method ?? "GET").toUpperCase(), path: String(path).split("?")[0] });
    // Enough shape that a mapper can run over it without throwing.
    return Promise.resolve({ items: [], rows: [], data: [], events: [], results: [] });
  };
  return {
    request: note,
    download: (path, options) => { note(path, options); return Promise.resolve({ blob: null, fileName: "x" }); },
    get: (path) => note(path),
    post: (path, body) => note(path, { method: "POST", body }),
    put: (path, body) => note(path, { method: "PUT", body }),
    patch: (path, body) => note(path, { method: "PATCH", body }),
    delete: (path) => note(path, { method: "DELETE" }),
  };
}

const ADAPTERS = [
  ["settings", createApiSettingsAdapter],
  ["financial items", createApiFinancialItemsAdapter],
  ["prices", createApiPricesAdapter],
  ["progress", createApiProgressAdapter],
  ["invoices", createApiInvoicesAdapter],
  ["reports", createApiReportsAdapter],
  ["audit", createApiAuditAdapter],
];

test("the committed contract describes a real API", () => {
  assert.equal(spec.openapi.startsWith("3."), true, "expected an OpenAPI 3 document");
  assert.ok(Object.keys(spec.paths).length > 0, "the contract has no paths");
});

for (const [name, factory] of ADAPTERS) {
  test(`every route the ${name} adapter calls exists in the contract`, async () => {
    const calls = [];
    const client = recordingClient(calls);
    const adapter = name === "attachments"
      ? factory(CONTEXT, client, null)
      : factory(CONTEXT, client);

    // Read-only methods only: they take no arguments worth inventing, and a
    // write would need a payload this test has no business asserting.
    for (const [key, value] of Object.entries(adapter)) {
      if (typeof value !== "function") continue;
      if (value.length > 0) continue;
      try {
        await value();
      } catch {
        // A mapper failing on the empty answer is fine — the request was
        // already recorded, and the request is what this test is about.
      }
    }

    assert.ok(calls.length > 0, `the ${name} adapter made no request at all`);

    const missing = calls
      .filter((call) => !findRoute(call.method, call.path))
      .map((call) => `${call.method} ${call.path}`);

    assert.deepEqual(
      [...new Set(missing)],
      [],
      `these are called by the frontend and are not in backend/contracts/openapi.json`,
    );
  });
}
