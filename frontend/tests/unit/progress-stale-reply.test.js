import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

/**
 * Two clicks, answered out of order.
 *
 * #finance/progress loads a version's feed by awaiting the adapter and then writing the answer
 * into `feedState`. Nothing said the answer still belonged to the version on screen: a
 * reader who clicks version A and then version B can be shown A's 727 rows under B's
 * heading, with B's card reading «در حال نمایش». Both halves are real data and the
 * combination is a lie — precisely the mixed-source display this page exists to prevent.
 *
 * This is a STRUCTURAL check, and says so plainly: the page builds a live DOM through
 * `element()` and there is no DOM harness in this suite to drive it through two overlapping
 * clicks. What it does guarantee is that neither the success path nor the failure path can
 * write `feedState` without first checking that the reply is still the selected one — so
 * deleting the guard fails the suite. The behaviour it stands for is worth a real
 * end-to-end check the day this suite grows a DOM.
 */

const SOURCE = await readFile(
  fileURLToPath(new URL("../../src/features/progress/progress-page.js", import.meta.url)),
  "utf-8",
);

/** The body of `selectSnapshot`, up to the closing of its function. */
function selectSnapshotBody() {
  const start = SOURCE.indexOf("async function selectSnapshot(snapshotId) {");
  assert.notEqual(start, -1, "selectSnapshot has been renamed; this test must follow it");
  const end = SOURCE.indexOf("\n  }", start);
  assert.notEqual(end, -1, "could not find the end of selectSnapshot");
  return SOURCE.slice(start, end);
}

test("a feed that arrives for an abandoned version is not rendered", () => {
  const body = selectSnapshotBody();
  const guard = "if (selectedId !== snapshotId) return;";
  const writes = [...body.matchAll(/feedState = createRequestState\(/g)].map((m) => m.index);
  const guards = [...body.matchAll(/if \(selectedId !== snapshotId\) return;/g)].map((m) => m.index);
  assert.ok(body.includes(guard), "selectSnapshot must discard a reply it no longer wants");

  // The first write is the LOADING state, set before the request goes out; every write
  // after the await must be preceded by a guard.
  const afterAwait = body.indexOf("await adapter.getFeed(snapshotId)");
  const late = writes.filter((at) => at > afterAwait);
  assert.equal(late.length, 2, "expected a success write and a failure write after the await");
  for (const write of late) {
    assert.ok(
      guards.some((at) => at < write && at > afterAwait),
      "a state write after the await is not guarded against a stale reply",
    );
  }
});

test("the guard covers failure as well as success", () => {
  // An error from an abandoned request would mark the version now on screen as broken when
  // nothing was ever wrong with it — the same lie in the other direction.
  const body = selectSnapshotBody();
  const catchAt = body.indexOf("} catch (error) {");
  assert.notEqual(catchAt, -1);
  const guardInCatch = body.indexOf("if (selectedId !== snapshotId) return;", catchAt);
  const errorWrite = body.indexOf("REQUEST_STATUS.ERROR", catchAt);
  assert.ok(guardInCatch !== -1 && guardInCatch < errorWrite,
    "the failure path must discard a stale reply before recording an error");
});
