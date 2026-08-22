import test from "node:test";
import assert from "node:assert/strict";
import { createApiAuditAdapter } from "../../src/adapters/api/audit-api-adapter.js";
import { createMockAuditAdapter } from "../../src/adapters/mock/audit-adapter.js";
import { filterAuditEvents } from "../../src/features/audit/audit-model.js";

const context = { organizationId: "org-1", projectId: "project-1" };

const FIXTURE = Object.freeze([
  { id: "e1", actorUserId: "user-1", action: "invoice.confirmed", entityType: "invoices", entityId: "inv-1", reason: null, occurredAt: "2026-08-10T10:30:00Z" },
  { id: "e2", actorUserId: "user-2", action: "price_version.created", entityType: "price_versions", entityId: "price-1", reason: "به‌روزرسانی قیمت تأمین‌کننده", occurredAt: "2026-08-09T12:15:00Z" },
  { id: "e3", actorUserId: "user-1", action: "progress_override.created", entityType: "progress_overrides", entityId: "ovr-1", reason: "اصلاح مقدار اجرا براساس صورت‌جلسه کارگاه", occurredAt: "2026-08-08T08:45:00Z" },
  { id: "e4", actorUserId: "user-3", action: "invoice.confirmed", entityType: "invoices", entityId: "inv-2", reason: null, occurredAt: "2026-07-30T09:00:00Z" },
]);

test("requests the audit endpoint with the paging parameters the Backend declares", async () => {
  const calls = [];
  const payload = { items: [{ id: "event-1" }], page: 1, pageSize: 50, totalItems: 1, totalPages: 1 };
  const client = { async request(path) { calls.push(path); return payload; } };
  const adapter = createApiAuditAdapter(context, client);

  assert.deepEqual(await adapter.getEvents(), payload);
  await adapter.getEvents({ page: 3, pageSize: 120 });

  assert.deepEqual(calls, [
    "/api/projects/project-1/finance/audit-events?page=1&pageSize=50",
    "/api/projects/project-1/finance/audit-events?page=3&pageSize=120",
  ]);
});

test("clamps audit paging to the router bounds instead of forwarding invalid values", async () => {
  const calls = [];
  const client = { async request(path) { calls.push(path); return { items: [], page: 1, pageSize: 50, totalItems: 0, totalPages: 0 }; } };
  const adapter = createApiAuditAdapter(context, client);

  await adapter.getEvents({ page: 0, pageSize: 5000 });
  await adapter.getEvents({ page: -4, pageSize: 0 });

  assert.deepEqual(calls, [
    "/api/projects/project-1/finance/audit-events?page=1&pageSize=200",
    "/api/projects/project-1/finance/audit-events?page=1&pageSize=50",
  ]);
});

test("mock audit pages the envelope the same way the router does", async () => {
  const adapter = createMockAuditAdapter(context);
  const first = await adapter.getEvents({ page: 1, pageSize: 50 });
  const second = await adapter.getEvents({ page: 2, pageSize: 50 });

  assert.deepEqual(Object.keys(first).sort(), ["items", "page", "pageSize", "totalItems", "totalPages"]);
  assert.equal(first.items.length, 50);
  assert.equal(second.items.length, 50);
  assert.equal(first.page, 1);
  assert.equal(second.page, 2);
  assert.equal(first.totalItems, second.totalItems, "the total does not change between pages");
  assert.ok(first.totalItems > 100, "the seed spans more than two pages");
  assert.equal(new Set([...first.items, ...second.items].map((event) => event.id)).size, 100, "pages must not overlap");
  assert.equal(first.items[0].organizationId, context.organizationId);
  assert.equal(first.items[0].projectId, context.projectId);

  const clamped = await adapter.getEvents({ page: 1, pageSize: 5000 });
  assert.ok(clamped.items.length <= 200, "pageSize is capped at the router maximum");

  const tail = await adapter.getEvents({ page: 99, pageSize: 50 });
  assert.deepEqual(tail.items, [], "a page past the end is empty");
  assert.equal(tail.totalItems, first.totalItems, "and still reports the real total, so a filter cannot read it as an empty history");
});

test("mock audit exposes more events than a single page so paging is exercised", async () => {
  const adapter = createMockAuditAdapter(context);
  const full = await adapter.getEvents({ page: 1, pageSize: 200 });
  assert.ok(full.items.length > 50, "seed data must exceed one default page");
  const timestamps = full.items.map((event) => event.occurredAt);
  assert.deepEqual(timestamps, [...timestamps].sort().reverse(), "events are returned newest first");
});

test("filters immutable audit events by action, entity, text and canonical date", () => {
  assert.equal(filterAuditEvents(FIXTURE, { action: "invoice.confirmed" }).length, 2);
  assert.equal(filterAuditEvents(FIXTURE, { entityType: "price_versions" }).length, 1);
  assert.equal(filterAuditEvents(FIXTURE, { query: "صورت‌جلسه" }).length, 1);
  assert.equal(filterAuditEvents(FIXTURE, { from: "2026-08-09", to: "2026-08-10" }).length, 2);
  assert.equal(filterAuditEvents(FIXTURE, { action: "invoice.confirmed", from: "2026-08-01" }).length, 1);
});

test("mock audit supports empty and recoverable error states", async () => {
  const empty = await createMockAuditAdapter(context, { initialState: "empty" }).getEvents();
  assert.deepEqual(empty.items, []);
  assert.equal(empty.totalItems, 0);
  await assert.rejects(createMockAuditAdapter(context, { initialState: "error" }).getEvents(), (error) => error.status === 503 && Boolean(error.requestId));
});
