import { financeBase, jsonOptions } from "./api-utils.js";

/**
 * FinanceSettingsResponse carries the current revision; the append-only trail
 * comes from GET /settings/revisions, which the Backend added alongside it.
 */
function mapSettings(value) {
  if (!value) return null;
  return {
    settingsId: value.id,
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
    actorName: null,
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
