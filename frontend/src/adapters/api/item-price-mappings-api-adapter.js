import { financeBase, jsonOptions } from "./api-utils.js";

/* The bridge between a schedule item and a market listing, read from the Finance backend
 * and from nowhere else.
 *
 * There is deliberately no Google Sheets call in this file and there must never be one.
 * The sheet is read by a server-side import; a page that fetched a spreadsheet would leak
 * its address to every viewer and let whoever can edit it decide what a Finance page
 * shows. What the browser sees is what the database holds.
 *
 * Every money value arrives as an exact decimal STRING and is passed through untouched.
 * Nothing here parses one into a Number: a rial amount that went through JavaScript's
 * float would come back subtly wrong, and the place it would show is a total.
 *
 * `null` means "nobody knows", never zero. Every caller branches on it. */

function mapStatus(value) {
  return {
    estimateLineId: value.estimateLineId,
    status: value.status,
    statusLabel: value.statusLabel,
    reason: value.reason ?? null,

    /* The daily price converted into the official calculation unit, and the quantity
       times it. Both null unless the row is ready -- an item whose units cannot be
       crossed has no price, and showing zero would say the material is free. */
    convertedDailyUnitPriceIRR: value.convertedDailyUnitPriceIrr ?? null,
    dailyItemCostIRR: value.dailyItemCostIrr ?? null,

    selectedUnit: value.selectedUnit ?? null,
    sourceUnit: value.sourceUnit ?? null,
    conversionFactor: value.conversionFactor ?? null,
    quantity: value.quantity ?? null,

    providerItemId: value.providerItemId ?? null,
    providerName: value.providerName ?? null,
    productName: value.productName ?? null,
    productExternalId: value.productExternalId ?? null,
    category: value.category ?? null,
    worksheet: value.worksheet ?? null,
    workflowDateJalali: value.workflowDateJalali ?? null,
    mappingVersion: value.mappingVersion ?? null,
    conversionFactorId: value.conversionFactorId ?? null,
  };
}

function mapCandidate(value) {
  return {
    providerItemId: value.providerItemId,
    externalId: value.externalId ?? null,
    name: value.externalName ?? null,
    displayName: value.displayName ?? null,
    category: value.category ?? null,
    categoryLabel: value.categoryLabel ?? null,
    providerId: value.providerId ?? null,
    providerName: value.providerName ?? null,
    productType: value.productType ?? null,

    sourceUnit: value.sourceUnit ?? null,
    sourceUnitCode: value.sourceUnitCode ?? null,
    sourceBasis: value.sourceBasis ?? null,

    currentPriceIRR: value.currentPriceIrr ?? null,
    rawPrice: value.rawPrice ?? null,
    sourceCurrency: value.sourceCurrency ?? null,
    workflowDateJalali: value.workflowDateJalali ?? null,

    active: value.active !== false,
    inactiveReason: value.inactiveReason ?? null,
    worksheet: value.worksheet ?? null,

    /* The worksheet's own category columns, verbatim. An angle's thickness and branch
       count; a brick's code and dimensions. Never invented: a category whose sheet states
       no thickness has no thickness key, and a blank cell is null rather than a dash. */
    specs: value.specs ?? {},
    specColumns: value.specColumns ?? [],
  };
}

function mapMapping(value) {
  if (!value) return null;
  return {
    id: value.id,
    estimateLineId: value.estimateLineId ?? null,
    providerItemId: value.providerItemId,
    selectedUnit: value.selectedUnit,
    sourcePriceUnit: value.sourcePriceUnit ?? null,
    sourcePriceBasis: value.sourcePriceBasis ?? null,
    conversionStatus: value.conversionStatus,
    conversionFactorId: value.conversionFactorId ?? null,
    version: value.version,
    effectiveFrom: value.effectiveFrom,
    supersededAt: value.supersededAt ?? null,
    createdBy: value.createdBy,
    createdByName: value.createdByName ?? null,
    createdAt: value.createdAt,
    reason: value.reason,
  };
}

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function createItemPriceMappingsApiAdapter(context, { client }) {
  const base = financeBase(context);
  return {
    /* One call for the whole table. A line nobody has mapped is PRESENT in the answer
       with `needs_product` -- the table has to show what is waiting, and an absent row
       would be indistinguishable from one the page forgot to ask about. */
    async statuses() {
      const body = await client.request(`${base}/item-price-mappings/status`);
      return (body.items ?? []).map(mapStatus);
    },

    async candidates(filters = {}) {
      const body = await client.request(
        `${base}/item-price-mappings/candidates${query(filters)}`);
      return {
        items: (body.items ?? []).map(mapCandidate),
        page: body.page,
        pageSize: body.pageSize,
        totalItems: body.totalItems,
      };
    },

    async filters(category) {
      const body = await client.request(
        `${base}/item-price-mappings/filters${query({ category })}`);
      return {
        providers: body.providers ?? [],
        productTypes: body.productTypes ?? [],
        categories: body.categories ?? [],
        units: body.units ?? [],
      };
    },

    async mappingFor(estimateLineId) {
      return mapMapping(await client.request(
        `${base}/estimate-lines/${encodeURIComponent(estimateLineId)}/price-mapping`));
    },

    async historyFor(estimateLineId) {
      const body = await client.request(
        `${base}/estimate-lines/${encodeURIComponent(estimateLineId)}/price-mapping/history`);
      return (body ?? []).map(mapMapping);
    },

    /* What this listing would cost in this unit, asked BEFORE anything is saved -- so
       «ضریب تبدیل لازم است» is something a person sees while choosing rather than
       discovers after committing. */
    async preview(estimateLineId, { providerItemId, selectedUnit }) {
      const body = await client.request(
        `${base}/estimate-lines/${encodeURIComponent(estimateLineId)}/price-preview`
        + query({ providerItemId, selectedUnit }));
      return mapStatus({ ...body, estimateLineId });
    },

    async saveMapping(estimateLineId, payload) {
      return mapMapping(await client.request(
        `${base}/estimate-lines/${encodeURIComponent(estimateLineId)}/price-mapping`,
        jsonOptions("POST", payload)));
    },
  };
}
