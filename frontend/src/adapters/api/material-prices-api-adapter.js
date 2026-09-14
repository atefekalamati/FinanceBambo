import { financeBase, jsonOptions } from "./api-utils.js";

/* Material prices, read from the Finance backend and from nowhere else.
 *
 * There is deliberately no Google Sheets call in this file, and there must never be one.
 * The sheet is read by a server-side import; a page that fetched a spreadsheet per row
 * would be slow, would leak the sheet's address to every viewer, and would let whoever
 * can edit that sheet decide what a Finance page displays. What the browser sees is what
 * the database holds.
 *
 * Every money value arrives as an exact decimal STRING and is passed through untouched.
 * Nothing here parses one into a Number: a rial amount that went through JavaScript's
 * float would come back subtly wrong, and the one place that would show is a total. */

function mapPrice(value) {
  return {
    providerItemId: value.providerItemId,
    externalId: value.externalId,
    name: value.externalName,
    category: value.category,
    providerName: value.providerName,
    active: value.active,
    inactiveReason: value.inactiveReason ?? null,
    worksheet: value.worksheet ?? null,

    /* null means "we have no price for this", never zero. Every caller must branch on
       it rather than default it, which is why it is left null rather than made "0". */
    currentPriceIRR: value.currentPriceIrr ?? null,
    rawPrice: value.rawPrice ?? null,
    sourceCurrency: value.sourceCurrency ?? null,
    secondaryPriceIRR: value.secondaryPriceIrr ?? null,
    secondaryPriceBasis: value.secondaryPriceBasis ?? null,

    sourceUnit: value.sourceUnit ?? null,
    displayUnit: value.displayUnit ?? null,
    conversionFactor: value.conversionFactor ?? null,
    conversionNote: value.conversionNote ?? null,

    workflowDateRaw: value.workflowDateRaw ?? null,
    workflowDateJalali: value.workflowDateJalali ?? null,
    workflowDate: value.workflowDateGregorian ?? null,
    observedAt: value.observedAt ?? null,
    observedAtSource: value.observedAtSource ?? "unknown",
    fetchedAt: value.fetchedAt ?? null,

    validationStatus: value.validationStatus,
    validationReasons: value.validationReasons ?? [],
    /* resolved | unresolved_price | unresolved_unit | unmapped | stale */
    resolutionStatus: value.resolutionStatus,
    resolutionReason: value.resolutionReason ?? null,

    sourceRowNumber: value.sourceRowNumber ?? null,
    sourceUrl: value.sourceUrl ?? null,
  };
}

function mapObservation(value) {
  return {
    observationId: value.id,
    priceIRR: value.normalizedPriceIrr ?? null,
    rawPrice: value.rawPrice ?? null,
    sourceCurrency: value.sourceCurrency,
    workflowDateRaw: value.workflowDateRaw ?? null,
    workflowDateJalali: value.workflowDateJalali ?? null,
    workflowDate: value.workflowDateGregorian ?? null,
    observedAt: value.observedAt,
    observedAtSource: value.observedAtSource,
    fetchedAt: value.fetchedAt,
    validationStatus: value.validationStatus,
    validationReasons: value.validationReasons ?? [],
    worksheet: value.sourceWorksheet ?? null,
    rowNumber: value.sourceRowNumber ?? null,
  };
}

function mapRun(value) {
  return {
    runId: value.id,
    status: value.status,
    startedAt: value.startedAt,
    finishedAt: value.finishedAt ?? null,
    publishedAt: value.publishedAt ?? null,
    totalItems: value.totalItems,
    successfulItems: value.successfulItems,
    failedItems: value.failedItems,
    rejectedItems: value.rejectedItems,
    errorMessage: value.errorMessage ?? null,
    worksheetReport: value.worksheetReport ?? {},
  };
}

function mapUnitSetting(value) {
  return {
    settingId: value.id,
    category: value.category,
    resourceId: value.resourceId ?? null,
    version: value.version,
    displayUnit: value.displayUnit,
    reason: value.reason,
    actorId: value.createdBy,
    actorName: value.createdByName ?? null,
    createdAt: value.createdAt,
  };
}

export function createMaterialPricesApiAdapter(context, { client }) {
  const base = financeBase(context);

  return Object.freeze({
    async listCategories() {
      const payload = await client.request(`${base}/material-prices/categories`);
      return (payload.items ?? []).map((item) => ({
        category: item.category,
        itemCount: item.itemCount,
        activeCount: item.activeCount,
        inactiveCount: item.inactiveCount,
      }));
    },

    async listCurrentPrices({ category = null, asOf = null, includeInactive = false,
                              page = 1, pageSize = 50 } = {}) {
      const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
      if (category) query.set("category", category);
      /* asOf is what turns freshness on. Without it the backend calls nothing stale,
         because a page that does not say which day it means cannot say a price is old. */
      if (asOf) query.set("asOf", asOf);
      if (includeInactive) query.set("includeInactive", "true");
      const payload = await client.request(`${base}/material-prices/current?${query}`);
      return {
        items: (payload.items ?? []).map(mapPrice),
        page: payload.page,
        pageSize: payload.pageSize,
        totalItems: payload.totalItems,
        totalPages: payload.totalPages,
      };
    },

    async listPriceHistory(providerItemId, { page = 1, pageSize = 50 } = {}) {
      const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
      const payload = await client.request(
        `${base}/material-prices/${encodeURIComponent(providerItemId)}/history?${query}`);
      return {
        items: (payload.items ?? []).map(mapObservation),
        page: payload.page,
        pageSize: payload.pageSize,
        totalItems: payload.totalItems,
        totalPages: payload.totalPages,
      };
    },

    async listImportRuns({ page = 1, pageSize = 50 } = {}) {
      const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
      const payload = await client.request(`${base}/material-prices/runs?${query}`);
      return {
        items: (payload.items ?? []).map(mapRun),
        page: payload.page,
        pageSize: payload.pageSize,
        totalItems: payload.totalItems,
        totalPages: payload.totalPages,
      };
    },

    async listInvalidRows({ page = 1, pageSize = 50 } = {}) {
      const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
      const payload = await client.request(`${base}/material-prices/invalid-rows?${query}`);
      return {
        items: (payload.items ?? []).map(mapObservation),
        page: payload.page,
        pageSize: payload.pageSize,
        totalItems: payload.totalItems,
        totalPages: payload.totalPages,
      };
    },

    async listUnitSettings({ category = null } = {}) {
      const query = category ? `?category=${encodeURIComponent(category)}` : "";
      const payload = await client.request(`${base}/material-prices/unit-settings${query}`);
      return (payload.items ?? []).map(mapUnitSetting);
    },

    async setUnit({ category, resourceId = null, displayUnit, reason }) {
      const payload = await client.request(`${base}/material-prices/unit-settings`,
        jsonOptions("POST", { category, resourceId, displayUnit, reason }));
      return mapUnitSetting(payload);
    },
  });
}
