/**
 * One project, one schedule — asked once and answered the same way everywhere.
 *
 * The bug these cover is not hypothetical. A project had four snapshots ingested from the
 * host (AB11_V13.mpp, terrace.mpp, B10.mpp) and one imported by Finance from the schedule
 * its estimate is actually mapped to (test_progress.mpp). The host snapshots carried later
 * reporting dates, so every page that chose "the newest ready one" read progress from a
 * file the estimate knows nothing about, and the item table — which prices from the active
 * source version — read the other. Both were internally consistent. Neither said so.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { defaultSnapshot, reportableSnapshots } from "../../src/shared/progress/project-snapshot.js";

/** As /progress-snapshots returns them: newest reporting date first. */
const LISTING = [
  { progressSnapshotId: "cebd1462", status: "ready", reportingDate: "2026-10-22", sourceFileNameSafe: "AB11_V13.mpp", isActiveSource: false },
  { progressSnapshotId: "afe50159", status: "ready", reportingDate: "2026-09-05", sourceFileNameSafe: "terrace.mpp", isActiveSource: false },
  { progressSnapshotId: "4709c97c", status: "superseded", reportingDate: "2026-08-22", sourceFileNameSafe: "B10.mpp", isActiveSource: false },
  { progressSnapshotId: "bf456698", status: "ready", reportingDate: "2025-10-02", sourceFileNameSafe: "test_progress.mpp", isActiveSource: true },
];

test("the project's own schedule is chosen over a later-dated snapshot of another file", () => {
  const chosen = defaultSnapshot(LISTING);
  assert.equal(chosen.progressSnapshotId, "bf456698");
  assert.equal(chosen.sourceFileNameSafe, "test_progress.mpp");
});

test("a snapshot that is not ready is never chosen, however recent", () => {
  const listing = [
    { progressSnapshotId: "half-read", status: "processing", reportingDate: "2026-12-01", isActiveSource: true },
    { progressSnapshotId: "usable", status: "ready", reportingDate: "2026-01-01", isActiveSource: false },
  ];
  // Even the active source is unreadable while it is still being imported: asking for it
  // is answered with a 404, and half a schedule reported as a whole one is worse than an
  // older complete one.
  assert.equal(defaultSnapshot(listing).progressSnapshotId, "usable");
});

test("with no active source the newest ready one is still the answer", () => {
  // A project that has imported no schedule of its own — every row came from the host.
  const listing = LISTING.map((row) => ({ ...row, isActiveSource: false }));
  assert.equal(defaultSnapshot(listing).progressSnapshotId, "cebd1462");
});

test("a Backend that has not been told about the flag behaves as it did before", () => {
  // isActiveSource absent, not false: an older Backend, or a mock adapter.
  const listing = LISTING.map(({ isActiveSource, ...row }) => row);
  assert.equal(defaultSnapshot(listing).progressSnapshotId, "cebd1462");
});

test("nothing reportable is an absent answer, not the first row", () => {
  assert.equal(defaultSnapshot([]), null);
  assert.equal(defaultSnapshot(undefined), null);
  assert.equal(defaultSnapshot([{ progressSnapshotId: "x", status: "superseded" }]), null);
});

test("the order the Backend gave is the order kept", () => {
  // Re-sorting on the client is how the report builder came to disagree with the page
  // that linked to it. The filter removes rows; it must not reorder them.
  assert.deepEqual(
    reportableSnapshots(LISTING).map((row) => row.progressSnapshotId),
    ["cebd1462", "afe50159", "bf456698"],
  );
});

test("two projects do not answer for each other", () => {
  // Each page holds one project's listing; the rule reads no shared state, so a second
  // project's active source cannot leak into the first project's answer.
  const terrace = LISTING;
  const other = [
    { progressSnapshotId: "s1", status: "ready", reportingDate: "2026-11-01", isActiveSource: false },
    { progressSnapshotId: "s2", status: "ready", reportingDate: "2026-10-01", isActiveSource: true },
  ];
  assert.equal(defaultSnapshot(terrace).progressSnapshotId, "bf456698");
  assert.equal(defaultSnapshot(other).progressSnapshotId, "s2");
  assert.equal(defaultSnapshot(terrace).progressSnapshotId, "bf456698");
});
