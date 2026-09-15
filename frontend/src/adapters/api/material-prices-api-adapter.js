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

    /* What the supplier wrote, and what this system was able to make of it. Two fields
       because they answer two questions, and a page that showed only the second would hide
       a spelling nobody has taught the registry yet. */
    sourceUnit: value.sourceUnit ?? null,
    sourceUnitCode: value.sourceUnitCode ?? null,
    displayUnit: value.displayUnit ?? null,
    /* The unit the returned price is actually in. Null when no conversion was possible --
       a reader must never have to infer which unit a number is in. */
    targetUnit: value.targetUnit ?? null,
    conversionFactor: value.conversionFactor ?? null,
    conversionNote: value.conversionNote ?? null,
    factorOrigin: value.factorOrigin ?? null,

    workflowDateRaw: value.workflowDateRaw ?? null,
    workflowDateJalali: value.workflowDateJalali ?? null,
    workflowDate: value.workflowDateGregorian ?? null,
    observedAt: value.observedAt ?? null,
    observedAtSource: value.observedAtSource ?? "unknown",
    fetchedAt: value.fetchedAt ?? null,

    validationStatus: value.validationStatus,
    validationReasons: value.validationReasons ?? [],
    /* resolved | stale | unresolved_price | unresolved_unit | incompatible_unit |
       missing_factor | unresolved_mapping | invalid_source | inactive. Nine rather
       than five because the fixes differ: `missing_factor` needs somebody to measure
       this product, `incompatible_unit` needs a different target unit. */
    resolutionStatus: value.resolutionStatus,
    resolutionReason: value.resolutionReason ?? null,

    sourceRowNumber: value.sourceRowNumber ?? null,
    sourceUrl: value.sourceUrl ?? null,

    /* This product's own worksheet columns, keyed by the sheet's Persian header and
       carrying the value verbatim. A cell the sheet left blank arrives as null and must
       stay blank on screen: 8 of 210 bricks state no square-metre price, and a dash there
       is the truth while a zero would be a claim. */
    specs: value.specs ?? {},

    /* What a person decided about this listing. All null until somebody does. */
    label: value.label ?? null,
    labelDisplayName: value.labelDisplayName ?? null,
    labelProductType: value.labelProductType ?? null,
    labelSourceBasis: value.labelSourceBasis ?? null,
    financeResourceId: value.financeResourceId ?? null,
    mappingApproved: value.mappingApproved ?? false,
    labelledBy: value.labelledBy ?? null,
    labelledByName: value.labelledByName ?? null,
    labelledAt: value.labelledAt ?? null,
    labelVersion: value.labelVersion ?? null,

    /* The MSP/Finance side of the comparison, and the verdict. */
    financeResourceTitle: value.financeResourceTitle ?? null,
    financeResourceUnit: value.financeResourceUnit ?? null,
    unitAlignment: value.unitAlignment ?? "not_mapped",
  };
}

function mapLabel(value) {
  return {
    labelId: value.id,
    providerItemId: value.providerItemId,
    version: value.version,
    label: value.label ?? null,
    displayName: value.displayName ?? null,
    category: value.category ?? null,
    productType: value.productType ?? null,
    sourceUnit: value.sourceUnit ?? null,
    sourceBasis: value.sourceBasis ?? null,
    targetUnit: value.targetUnit ?? null,
    financeResourceId: value.financeResourceId ?? null,
    mappingApproved: value.mappingApproved,
    mappingApprovedBy: value.mappingApprovedBy ?? null,
    mappingApprovedAt: value.mappingApprovedAt ?? null,
    active: value.active,
    notes: value.notes ?? null,
    reason: value.reason,
    actorId: value.createdBy,
    actorName: value.createdByName ?? null,
    createdAt: value.createdAt,
    /* Set when a newer version replaced this one. Null means this is the current label. */
    supersededAt: value.supersededAt ?? null,
  };
}

function mapFactor(value) {
  return {
    factorId: value.id,
    providerItemId: value.providerItemId,
    version: value.version,
    fromUnit: value.fromUnit,
    toUnit: value.toUnit,
    /* An exact decimal string. Never parsed into a Number: a conversion factor that went
       through a float would come back subtly wrong, and it multiplies a price. */
    factor: value.factor,
    factorType: value.factorType ?? null,
    origin: value.origin,
    reason: value.reason,
    actorId: value.createdBy,
    actorName: value.createdByName ?? null,
    createdAt: value.createdAt,
    approvedBy: value.approvedBy ?? null,
    approvedAt: value.approvedAt ?? null,
    supersededAt: value.supersededAt ?? null,
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
        label: item.label ?? item.category,
        /* THIS category's table, as the Backend declares it. The page builds its header
           row from this and holds no list of its own -- which is what stops a column
           from one worksheet appearing over another worksheet's rows. */
        columns: item.columns ?? [],
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

    async listLabels({ providerItemId = null } = {}) {
      const query = providerItemId
        ? `?providerItemId=${encodeURIComponent(providerItemId)}` : "";
      const payload = await client.request(`${base}/material-prices/labels${query}`);
      return (payload.items ?? []).map(mapLabel);
    },

    async listLabelHistory(providerItemId) {
      const payload = await client.request(
        `${base}/material-prices/${encodeURIComponent(providerItemId)}/labels`);
      return (payload.items ?? []).map(mapLabel);
    },

    async saveLabel(providerItemId, values) {
      /* Sent exactly as given. `mappingApprovedBy` is deliberately not in this payload:
         the approver is whoever is authenticated, stamped by the backend, and a client
         that could name one could approve a mapping in somebody else's name. */
      const payload = await client.request(
        `${base}/material-prices/${encodeURIComponent(providerItemId)}/labels`,
        jsonOptions("POST", {
          label: values.label ?? null,
          displayName: values.displayName ?? null,
          category: values.category ?? null,
          productType: values.productType ?? null,
          sourceUnit: values.sourceUnit ?? null,
          sourceBasis: values.sourceBasis ?? null,
          targetUnit: values.targetUnit ?? null,
          financeResourceId: values.financeResourceId ?? null,
          mappingApproved: values.mappingApproved ?? false,
          active: values.active ?? true,
          notes: values.notes ?? null,
          reason: values.reason,
        }));
      return mapLabel(payload);
    },

    async listItemFactors(providerItemId) {
      const payload = await client.request(
        `${base}/material-prices/${encodeURIComponent(providerItemId)}/factors`);
      return (payload.items ?? []).map(mapFactor);
    },

    async saveItemFactor(providerItemId, values) {
      const payload = await client.request(
        `${base}/material-prices/${encodeURIComponent(providerItemId)}/factors`,
        jsonOptions("POST", {
          fromUnit: values.fromUnit,
          toUnit: values.toUnit,
          factor: values.factor,
          factorType: values.factorType,
          reason: values.reason,
        }));
      return mapFactor(payload);
    },

    async listUnresolved({ page = 1, pageSize = 50 } = {}) {
      const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
      const payload = await client.request(`${base}/material-prices/unresolved?${query}`);
      return {
        items: (payload.items ?? []).map((item) => ({
          providerItemId: item.id,
          externalId: item.externalId,
          name: item.externalName,
          category: item.category,
          sourceUnit: item.sourceUnit ?? null,
          worksheet: item.sourceWorksheet ?? null,
          active: item.active,
        })),
        page: payload.page,
        pageSize: payload.pageSize,
        totalItems: payload.totalItems,
        totalPages: payload.totalPages,
      };
    },
  });
}
