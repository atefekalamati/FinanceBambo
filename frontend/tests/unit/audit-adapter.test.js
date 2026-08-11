import test from "node:test";
import assert from "node:assert/strict";
import { createApiAuditAdapter } from "../../src/adapters/api/audit-api-adapter.js";
import { createMockAuditAdapter } from "../../src/adapters/mock/audit-adapter.js";
import { filterAuditEvents } from "../../src/features/audit/audit-model.js";

const context = { organizationId: "org-1", projectId: "project-1" };

test("requests the scoped Backend audit endpoint without invented query parameters", async () => {
  const calls = [];
  const payload = [{ id: "event-1" }];
  const client = { async request(path) { calls.push(path); return payload; } };
  const result = await createApiAuditAdapter(context, client).getEvents();
  assert.equal(result, payload);
  assert.deepEqual(calls, ["/api/projects/project-1/finance/audit-events"]);
});

test("filters immutable audit events by action, entity, text and canonical date", async () => {
  const events = await createMockAuditAdapter(context).getEvents();
  assert.equal(filterAuditEvents(events, { action: "invoice.confirmed" }).length, 1);
  assert.equal(filterAuditEvents(events, { entityType: "price_versions" }).length, 1);
  assert.equal(filterAuditEvents(events, { query: "صورت‌جلسه" }).length, 1);
  assert.equal(filterAuditEvents(events, { from: "2026-08-09", to: "2026-08-10" }).length, 2);
});

test("mock audit supports empty and recoverable error states", async () => {
  assert.deepEqual(await createMockAuditAdapter(context, { initialState: "empty" }).getEvents(), []);
  await assert.rejects(createMockAuditAdapter(context, { initialState: "error" }).getEvents(), (error) => error.status === 503 && Boolean(error.requestId));
});
