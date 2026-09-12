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

  return Object.freeze({ getSettings, updateGrossBuiltArea });
}
