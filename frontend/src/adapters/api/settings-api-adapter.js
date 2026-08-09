import { financeBase, jsonOptions } from "./api-utils.js";

function mapSettings(value) {
  if (!value) return null;
  return {
    currency: value.currency,
    displayCurrency: "TOMAN",
    grossBuiltArea: value.grossBuiltArea,
    grossBuiltAreaUnit: "m2",
    revision: value.revision,
    revisions: [{
      revisionId: value.id,
      previousValue: null,
      newValue: value.grossBuiltArea,
      effectiveDate: value.effectiveFrom,
      reason: value.reason,
      actorId: value.createdBy,
      actorName: null,
      occurredAt: value.createdAt,
    }],
  };
}

export function createApiSettingsAdapter(context, client) {
  const base = financeBase(context);
  async function getSettings() {
    return mapSettings(await client.request(`${base}/settings`));
  }
  async function updateGrossBuiltArea({ grossBuiltArea, reason, effectiveDate, expectedRevision }) {
    return mapSettings(await client.request(`${base}/settings`, jsonOptions("PATCH", { grossBuiltArea, reason, effectiveFrom: effectiveDate, expectedRevision })));
  }
  return Object.freeze({ getSettings, updateGrossBuiltArea });
}
