/**
 * Which snapshot a page reads when the reader has not picked one.
 *
 * Five surfaces used to answer this for themselves — the finance home, the operations
 * home, the level-one drilldown, the report builder and the progress page — and they did
 * not answer it the same way. One took the first ready row, one re-sorted by reporting
 * date first, one took the first row of any status. On a project whose snapshots all came
 * from one file the three agree, which is why the difference went unnoticed; on a project
 * that has received snapshots from more than one schedule they diverge, and then the
 * headline figures are computed from one file while the chart beside them reads another,
 * with nothing on screen saying so.
 *
 * The rule, in one place:
 *
 *   1. Only a READY snapshot can be reported on. Asking for a superseded one is answered
 *      with a 404, so an unready row is not a candidate however recent it is.
 *   2. The project's ACTIVE SOURCE wins. `isActiveSource` is the Backend saying "this
 *      snapshot came from the schedule this project's estimate is mapped to and priced
 *      from" — the same source version the item table and the activity catalogue read.
 *      A later-dated snapshot of an unrelated file does not displace it.
 *   3. Otherwise the newest. A project that has imported no schedule of its own has no
 *      active source to prefer, and the Backend hands these back newest first.
 *
 * Nothing here re-sorts. Ordering is the Backend's, and re-deriving it on the client was
 * how the report builder came to disagree with the page linking to it.
 */

/** The ready snapshots, in the order the Backend gave them: newest first. */
export function reportableSnapshots(snapshots) {
  return (snapshots ?? []).filter((snapshot) => snapshot?.status === "ready");
}

/** The one snapshot a page should open on, or null when none can be reported on. */
export function defaultSnapshot(snapshots) {
  const reportable = reportableSnapshots(snapshots);
  return (
    reportable.find((snapshot) => snapshot.isActiveSource === true) ??
    reportable[0] ??
    null
  );
}
