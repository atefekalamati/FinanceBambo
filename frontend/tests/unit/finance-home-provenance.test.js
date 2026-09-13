import test from "node:test";
import assert from "node:assert/strict";

import { warnOnSnapshotMismatch } from "../../src/features/finance-home/finance-home-page.js";

/* A snapshot as the list gives it. `hostSnapshotId` is the Core identifier and
   `progressSnapshotId` the one Finance mints for a reference of its own; only
   the first answers "which snapshot was this calculated from". */
const selected = {
  progressSnapshotId: "snapshot-3",
  hostSnapshotId: 903,
  version: 3,
  isLatest: true,
  reportingDate: "2026-08-02",
  sourceType: "microsoft_project",
  status: "ready",
  sourceFileNameSafe: "sample-progress-v3.mpp",
  importedAt: "2026-08-03T08:30:00Z",
};

function capture(run) {
  const originalInfo = console.info;
  const originalWarn = console.warn;
  const info = [];
  const warnings = [];
  console.info = (...args) => info.push(args);
  console.warn = (...args) => warnings.push(args);
  try {
    const returned = run();
    return { returned, info, warnings };
  } finally {
    console.info = originalInfo;
    console.warn = originalWarn;
  }
}

test("says nothing when the figures came from the snapshot that was picked", () => {
  const { returned, info, warnings } = capture(() =>
    warnOnSnapshotMismatch({ selected, report: { hostSnapshotId: 903 } }));
  assert.equal(returned, null);
  // The basis of the calculation used to be logged here on every render. It was
  // dropped: a console line nobody reads is not documentation, and every one of
  // those facts is on the progress page where a reader can act on it. Silence on
  // the ordinary path is the point -- a log that always fires is a log nobody
  // looks at when it matters.
  assert.equal(info.length, 0);
  assert.equal(warnings.length, 0);
});

test("a different Core snapshot behind the figures is reported", () => {
  const { warnings } = capture(() =>
    warnOnSnapshotMismatch({ selected, report: { hostSnapshotId: 902 } }));
  assert.equal(warnings.length, 1);
  assert.deepEqual(warnings[0][1], { asked: 903, answered: 902, selectedFinanceId: "snapshot-3" });
});

test("the Finance identifier alone never decides this", () => {
  // Why the comparison moved. `progressSnapshotId` is null on every read of a
  // project that has never issued a report -- the service pins one only when
  // something is written -- so a check on it was switched off in exactly the
  // case it was written for, and nothing said so. A report naming a different
  // Finance id is not a mismatch if the Core snapshot underneath is the same
  // one, and this must not warn about it.
  const { warnings } = capture(() =>
    warnOnSnapshotMismatch({
      selected,
      report: { progressSnapshotId: "snapshot-2", hostSnapshotId: 903 },
    }));
  assert.equal(warnings.length, 0);
});

test("not being able to check is said out loud, never taken for agreement", () => {
  // A quiet console would otherwise read as proof the two matched.
  const missingOnReport = capture(() =>
    warnOnSnapshotMismatch({ selected, report: { hostSnapshotId: null } }));
  assert.equal(missingOnReport.info.length, 1);
  assert.equal(missingOnReport.warnings.length, 0);

  const missingOnSnapshot = capture(() =>
    warnOnSnapshotMismatch({
      selected: { ...selected, hostSnapshotId: null },
      report: { hostSnapshotId: 903 },
    }));
  assert.equal(missingOnSnapshot.info.length, 1);
  assert.equal(missingOnSnapshot.warnings.length, 0);
});

test("no snapshot at all is not something to report on", () => {
  const { returned, info, warnings } = capture(() =>
    warnOnSnapshotMismatch({ selected: null, report: { hostSnapshotId: 903 } }));
  assert.equal(returned, null);
  assert.equal(info.length, 0);
  assert.equal(warnings.length, 0);
});
