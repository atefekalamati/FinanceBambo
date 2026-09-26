import { financeBase, jsonOptions } from "./api-utils.js";

/**
 * FinanceSettingsResponse carries the current revision; the append-only trail
 * comes from GET /settings/revisions, which the Backend added alongside it.
 *
 * `canEdit` is the Backend's own verdict on whether this actor may revise the
 * area — it ships it so the UI does not have to reimplement the role policy and
 * then disagree with the API. It is carried through as null when absent, which
 * is not the same as false: null means nobody asked, so the local permission
 * still decides.
 */
function mapSettings(value) {
  if (!value) return null;
  return {
    settingsId: value.id,
    canEdit: value.canEdit ?? null,
    currency: value.currency,
    displayCurrency: "TOMAN",
    grossBuiltArea: value.grossBuiltArea,
    grossBuiltAreaUnit: "m2",
    revision: value.revision,
    effectiveFrom: value.effectiveFrom,
    reason: value.reason,
    createdBy: value.createdBy,
    createdAt: value.createdAt,
  };
}

function mapRevision(value) {
  return {
    revisionId: value.id,
    revisionNumber: value.revision,
    previousValue: value.previousGrossBuiltArea,
    newValue: value.grossBuiltArea,
    effectiveDate: value.effectiveFrom,
    reason: value.reason,
    actorId: value.createdBy,
    actorName: value.createdByName ?? null,
    occurredAt: value.createdAt,
  };
}

/* What the mapping made of the project's schedule.
 *
 * `total` is what the file states; the three counts below it say what became of each row,
 * and they add up to it. `unclassified` is the one a person can act on — an assignment
 * whose resource no estimate line names, which since the service types WORK resources on
 * its own (0038) should be empty — so it is carried even when zero, because «۰» is an
 * answer and a blank is not.
 *
 * Provenance travels with the counts and never separately: the service reads the file's
 * name from the same statement that chose the version it counted, so a reader cannot be
 * shown one file's name beside another file's numbers, and this must not undo that by
 * merging the two from different calls.
 */
function mapMppStatus(value) {
  if (!value) return null;
  return {
    sourceVersionId: value.sourceVersionId ?? null,
    sourceFileName: value.sourceFileName ?? null,
    importedAt: value.importedAt ?? null,
    reportingDate: value.reportingDate ?? null,
    rowCount: value.rowCount ?? null,
    total: value.total ?? 0,
    assignmentMapped: value.assignmentMapped ?? 0,
    activityOnly: value.activityOnly ?? 0,
    unclassified: value.unclassified ?? 0,
    stageLabelRows: value.activityOnlyDetail?.stageLabelRows ?? 0,
    assignmentsWithoutResource: value.activityOnlyDetail?.assignmentsWithoutResource ?? 0,
  };
}

/* What one run of the mapping did.
 *
 * Every counter is carried, including the zeros: a run that created nothing and matched
 * everything is the NORMAL result of a second press, and a panel that showed only what
 * changed would report that run as silence. `fixedCostResidueFileUnits` is a decimal
 * string in the file's own currency and is passed through untouched -- it is evidence of
 * the rounding, and parsing it into a Number here would round the evidence.
 */
function mapRemapResult(value) {
  if (!value) return null;
  return {
    resourcesCreated: value.resourcesCreated ?? 0,
    resourcesMatched: value.resourcesMatched ?? 0,
    linesCreated: value.linesCreated ?? 0,
    linesMatched: value.linesMatched ?? 0,
    fixedCostLinesCreated: value.fixedCostLinesCreated ?? 0,
    fixedCostLinesMatched: value.fixedCostLinesMatched ?? 0,
    fixedCostIrr: value.fixedCostIrr ?? null,
    fixedCostResidueRows: value.fixedCostResidueRows ?? 0,
    fixedCostResidueFileUnits: value.fixedCostResidueFileUnits ?? null,
    unmappedRows: value.unmappedRows ?? 0,
  };
}

export function createApiSettingsAdapter(context, client) {
  const base = financeBase(context);

  async function loadRevisions() {
    // The trail is append-only and short by design, so it is fetched whole.
    const payload = await client.request(`${base}/settings/revisions`);
    return (payload ?? []).map(mapRevision).sort((left, right) => right.revisionNumber - left.revisionNumber);
  }

  async function getSettings() {
    const [settings, revisions] = await Promise.all([client.request(`${base}/settings`), loadRevisions()]);
    const mapped = mapSettings(settings);
    return mapped && { ...mapped, revisions };
  }

  async function updateGrossBuiltArea({ grossBuiltArea, reason, effectiveDate, expectedRevision }) {
    const updated = mapSettings(await client.request(`${base}/settings`, jsonOptions("PATCH", { grossBuiltArea, reason, effectiveFrom: effectiveDate, expectedRevision })));
    return updated && { ...updated, revisions: await loadRevisions() };
  }

  /** Reads only. A project that has imported no schedule answers zeros, not an error. */
  async function getMppStatus() {
    return mapMppStatus(await client.request(`${base}/mpp/status`));
  }

  /* Re-runs the mapping over the project's active schedule.
   *
   * WRITES, and is meant to: this is how a schedule already in the database becomes
   * estimate lines. Safe to repeat -- the service keys every write on the file's own
   * identifiers, so a second call reports what it matched and inserts nothing.
   */
  async function remapMpp() {
    return mapRemapResult(await client.request(`${base}/mpp/remap`, jsonOptions("POST", {})));
  }

  return Object.freeze({ getSettings, updateGrossBuiltArea, getMppStatus, remapMpp });
}
