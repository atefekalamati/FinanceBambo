import test from "node:test";
import assert from "node:assert/strict";
import { createApiReportsAdapter } from "../../src/adapters/api/reports-api-adapter.js";
import { createMockReportsAdapter } from "../../src/adapters/mock/reports-adapter.js";

const context = { organizationId: "org-1", projectId: "project-1" };

test("requests the live report with reporting date and selected progress snapshot", async () => {
  const calls = [];
  const payload = { metrics: { initialEstimateIrr: "100" }, warnings: [] };
  const client = { async request(path) { calls.push(path); return payload; } };
  const result = await createApiReportsAdapter(context, client).getLiveReport({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  assert.equal(result, payload);
  assert.equal(calls[0], "/api/projects/project-1/finance/reports/live?reportingDate=2026-08-09&progressSnapshotId=snapshot-1");
});

test("mock live report exposes all eight PRD metrics as exact IRR strings", async () => {
  const report = await createMockReportsAdapter(context).getLiveReport({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  assert.equal(Object.keys(report.metrics).length, 8);
  Object.values(report.metrics).forEach((value) => assert.match(value, /^\d+$/));
});

test("mock live report supports empty and recoverable error states", async () => {
  assert.equal(await createMockReportsAdapter(context, { initialState: "empty" }).getLiveReport({ reportingDate: "2026-08-09" }), null);
  await assert.rejects(
    createMockReportsAdapter(context, { initialState: "error" }).getLiveReport({ reportingDate: "2026-08-09" }),
    (error) => error.status === 503 && Boolean(error.requestId),
  );
});
