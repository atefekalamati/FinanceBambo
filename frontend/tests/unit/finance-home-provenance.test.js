import test from "node:test";
import assert from "node:assert/strict";

import { warnOnSnapshotMismatch } from "../../src/features/finance-home/finance-home-page.js";

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

test("says nothing when the service answered from the snapshot that was picked", () => {
  const originalInfo = console.info;
  const originalWarn = console.warn;
  const info = [];
  const warnings = [];
  console.info = (...args) => info.push(args);
  console.warn = (...args) => warnings.push(args);
  try {
    const rendered = warnOnSnapshotMismatch({
      selected,
      report: { progressSnapshotId: "snapshot-3" },
    });
    assert.equal(rendered, null);
    // The basis of the calculation used to be logged here. It was dropped: a
    // console line nobody reads is not documentation, and every one of those
    // facts is on the progress page where a reader can act on it. Silence on
    // the ordinary path is the point -- a log that always fires is a log
    // nobody looks at when it matters.
    assert.equal(info.length, 0);
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
    warnOnSnapshotMismatch({
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
