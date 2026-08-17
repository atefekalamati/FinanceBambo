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

test("requests the operational overview through the finance.view endpoint", async () => {
  const calls = [];
  const payload = { metrics: { initialEstimateIrr: "100" }, warnings: [] };
  const client = { async request(path) { calls.push(path); return payload; } };
  const result = await createApiReportsAdapter(context, client).getOverview({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  assert.equal(result, payload);
  assert.equal(calls[0], "/api/projects/project-1/finance/overview?reportingDate=2026-08-09&progressSnapshotId=snapshot-1");
});

test("requests canonical report variances with backend pagination and filters", async () => {
  const calls = [];
  const payload = { items: [], page: 2, pageSize: 25, totalItems: 0, totalPages: 0 };
  const client = { async request(path) { calls.push(path); return payload; } };
  const result = await createApiReportsAdapter(context, client).getVariances({
    reportingDate: "2026-08-09",
    progressSnapshotId: "snapshot-1",
    varianceType: "price",
    resourceType: "material",
    query: "میلگرد",
    page: 2,
    pageSize: 25,
    sortBy: "varianceIrr",
    sortDirection: "asc",
  });
  assert.equal(result, payload);
  assert.equal(calls[0], "/api/projects/project-1/finance/reports/live/variances?reportingDate=2026-08-09&progressSnapshotId=snapshot-1&varianceType=price&page=2&pageSize=25&sortDirection=asc&resourceType=material&query=%D9%85%DB%8C%D9%84%DA%AF%D8%B1%D8%AF&sortBy=varianceIrr");
});

test("uses canonical report snapshot routes and payload", async () => {
  const calls = [];
  const payload = { reportSnapshotId: "report-1", immutable: true };
  const client = {
    async request(path, options) {
      calls.push({ path, options });
      return payload;
    },
    async download(path) {
      calls.push({ path });
      return { blob: new Blob(["csv"]), fileName: "report.csv" };
    },
  };
  const adapter = createApiReportsAdapter(context, client);
  const issued = await adapter.issueSnapshot({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  const loaded = await adapter.getSnapshot("report-1");
  const file = await adapter.downloadSnapshotCsv("report-1");

  assert.equal(issued, payload);
  assert.equal(loaded, payload);
  assert.equal(file.fileName, "report.csv");
  assert.deepEqual(JSON.parse(calls[0].options.body), { reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  assert.equal(calls[0].path, "/api/projects/project-1/finance/report-snapshots");
  assert.equal(calls[1].path, "/api/projects/project-1/finance/report-snapshots/report-1");
  assert.equal(calls[2].path, "/api/projects/project-1/finance/report-snapshots/report-1/csv");
});

test("mock live report exposes all eight PRD metrics as exact IRR strings", async () => {
  const report = await createMockReportsAdapter(context).getLiveReport({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  assert.equal(Object.keys(report.metrics).length, 8);
  Object.values(report.metrics).forEach((value) => assert.match(value, /^\d+$/));
});

test("mock reports preserve API parity for overview and variance pagination", async () => {
  const adapter = createMockReportsAdapter(context);
  const overview = await adapter.getOverview({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  const variances = await adapter.getVariances({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1", varianceType: "price", page: 1, pageSize: 1 });
  assert.equal(overview.calculationStatus, "complete");
  assert.equal(overview.progressQuality.complete, true);
  assert.equal(variances.items.length, 1);
  assert.equal(variances.totalItems, overview.topPriceVariances.length);
});

test("mock live report supports empty and recoverable error states", async () => {
  assert.equal(await createMockReportsAdapter(context, { initialState: "empty" }).getLiveReport({ reportingDate: "2026-08-09" }), null);
  await assert.rejects(
    createMockReportsAdapter(context, { initialState: "error" }).getLiveReport({ reportingDate: "2026-08-09" }),
    (error) => error.status === 503 && Boolean(error.requestId),
  );
});

test("mock report snapshots remain immutable and CSV includes UTF-8 BOM", async () => {
  const adapter = createMockReportsAdapter({ ...context, userId: "user-1" });
  const issued = await adapter.issueSnapshot({ reportingDate: "2026-08-09", progressSnapshotId: "snapshot-1" });
  const loaded = await adapter.getSnapshot(issued.reportSnapshotId);
  const file = await adapter.downloadSnapshotCsv(issued.reportSnapshotId);
  const bytes = new Uint8Array(await file.blob.arrayBuffer());

  assert.equal(loaded, issued);
  assert.equal(issued.immutable, true);
  assert.deepEqual([...bytes.slice(0, 3)], [0xef, 0xbb, 0xbf]);
});
