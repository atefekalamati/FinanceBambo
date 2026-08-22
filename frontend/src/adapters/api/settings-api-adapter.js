import { financeBase, jsonOptions } from "./api-utils.js";

/**
 * FinanceSettingsResponse carries only the current revision — id, projectId,
 * grossBuiltArea, currency, revision, effectiveFrom, reason, createdBy,
 * createdAt — and the router exposes no settings-history endpoint. Earlier
 * revisions are therefore not retrievable; the UI states that instead of
 * rendering an empty history table.
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
