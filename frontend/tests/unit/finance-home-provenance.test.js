import test from "node:test";
import assert from "node:assert/strict";

import { logSnapshotProvenance } from "../../src/features/finance-home/finance-home-page.js";

const selected = {
  progressSnapshotId: "snapshot-3",
  version: 3,
  isLatest: true,
  reportingDate: "2026-08-02",
  sourceType: "microsoft_project",
  status: "ready",
  sourceFileNameSafe: "sample-progress-v3.mpp",
  importedAt: "2026-08-03T08:30:00Z",
};

test("logs snapshot provenance without returning customer-facing content", () => {
  const originalInfo = console.info;
  const originalWarn = console.warn;
  const info = [];
  const warnings = [];
  console.info = (...args) => info.push(args);
  console.warn = (...args) => warnings.push(args);
  try {
    const rendered = logSnapshotProvenance({
      selected,
      report: { progressSnapshotId: "snapshot-3" },
    });
    assert.equal(rendered, null);
    assert.equal(info.length, 1);
    assert.equal(info[0][1]["وضعیت"], "آماده");
    assert.equal(info[0][1]["فایل مبدأ"], "sample-progress-v3.mpp");
    assert.equal(info[0][1]["شناسه نسخه استفاده‌شده در گزارش"], "snapshot-3");
    assert.equal(warnings.length, 0);
  } finally {
    console.info = originalInfo;
    console.warn = originalWarn;
  }
});

test("keeps a snapshot mismatch visible to developers", () => {
  const originalInfo = console.info;
  const originalWarn = console.warn;
  const warnings = [];
  console.info = () => {};
  console.warn = (...args) => warnings.push(args);
  try {
    logSnapshotProvenance({
      selected,
      report: { progressSnapshotId: "snapshot-2" },
    });
    assert.equal(warnings.length, 1);
    assert.deepEqual(warnings[0][1], {
      selected: "snapshot-3",
      answered: "snapshot-2",
    });
  } finally {
    console.info = originalInfo;
    console.warn = originalWarn;
  }
});
