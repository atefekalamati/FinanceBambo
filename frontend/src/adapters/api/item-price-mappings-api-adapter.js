import { financeBase, jsonOptions } from "./api-utils.js";

/* The materials a schedule item consumes, read from the Finance backend and from nowhere
 * else.
 *
 * An activity is not a material. «کانال‌کنی» is 500 cubic metres of trenching, and it
 * consumes rebar and pipe and brick that the schedule never names -- a schedule describes
 * work, not a bill of materials. So a line is priced by a LIST of components, each naming
 * a real listing, an official unit, and how much of it this activity uses.
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

/* One estimate line's pricing state: the sum of its materials, and how much of it is
   settled. The counts are not decoration -- a reader looking at a total needs to know it
   came from two of three materials before they treat it as the line's cost. */
function mapRowStatus(value) {
  return {
    estimateLineId: value.estimateLineId,
    status: value.status,
    statusLabel: value.statusLabel,
    reason: value.reason ?? null,

    /* The sum of the components that resolved. Null when none did -- an item whose
       materials cannot be priced has no cost, and zero would say the work is free. */
    dailyItemCostIRR: value.dailyItemCostIrr ?? null,

    componentCount: value.componentCount ?? 0,
    readyComponentCount: value.readyComponentCount ?? 0,
    unresolvedComponentCount: value.unresolvedComponentCount ?? 0,

    /* The «منبع» column. One material names its product; several say how many there are,
       because listing three product names in a table cell is unreadable and naming only
       the first would be a lie about what priced the row. */
    providerName: value.providerName ?? null,
    productName: value.productName ?? null,
    sourceSummary: value.sourceSummary ?? null,
  };
}

/* One material of one line, priced at today's price.
 *
 * `reason` is why there is no number; `reasonText` is the person's own justification for
 * adding this material. Two different sentences -- conflating them would lose the author
 * behind an automatic status message. */
function mapComponent(value) {
  return {
    componentId: value.componentId ?? null,
    id: value.id ?? null,
    estimateLineId: value.estimateLineId ?? null,
    providerItemId: value.providerItemId ?? null,

    status: value.status,
    statusLabel: value.statusLabel,
    reason: value.reason ?? null,
    reasonText: value.reasonText ?? null,

    convertedDailyUnitPriceIRR: value.convertedDailyUnitPriceIrr ?? null,
    componentQuantity: value.componentQuantity ?? null,
    componentDailyCostIRR: value.componentDailyCostIrr ?? null,
    /* What the listing costs in ITS OWN unit, before any conversion. Kept separate so the
       panel never shows one number under two labels, which reads as "no conversion took
       place". */
    sourcePriceIRR: value.sourcePriceIrr ?? null,

    selectedUnit: value.selectedUnit ?? null,
    sourceUnit: value.sourceUnit ?? null,
    conversionFactor: value.conversionFactor ?? null,
    conversionStatus: value.conversionStatus ?? null,
    conversionFactorId: value.conversionFactorId ?? null,

    usageMode: value.usageMode ?? null,
    usageQuantity: value.usageQuantity ?? null,
    usageUnit: value.usageUnit ?? null,
    mspQuantity: value.mspQuantity ?? null,

    providerName: value.providerName ?? null,
    productName: value.productName ?? null,
    productExternalId: value.productExternalId ?? null,
    productType: value.productType ?? null,
    category: value.category ?? null,
    categoryLabel: value.categoryLabel ?? null,
    worksheet: value.worksheet ?? null,
    workflowDateJalali: value.workflowDateJalali ?? null,

    specs: value.specs ?? {},
    specColumns: value.specColumns ?? [],

    active: value.active !== false,
    version: value.version ?? null,
    createdBy: value.createdBy ?? null,
    createdByName: value.createdByName ?? null,
    createdAt: value.createdAt ?? null,
  };
}

/* What the schedule says about the activity being priced. The panel's header, so a person
   can see WHICH 500 cubic metres they are entering materials for. */
function mapLineHeader(value) {
  if (!value) return null;
  return {
    estimateLineId: value.estimateLineId,
    activityExternalId: value.activityExternalId ?? null,
    title: value.title ?? null,
    mspUnit: value.mspUnit ?? null,
    mspQuantity: value.mspQuantity ?? null,
    mspCostIRR: value.mspCostIrr ?? null,
    originalUnitPriceIRR: value.originalUnitPriceIrr ?? null,
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

/* A stored component version, as written. Evidence of what was approved and when -- not
   what the material costs today, which the read endpoints recompute. */
function mapComponentRow(value) {
  if (!value) return null;
  return {
    id: value.id,
    componentId: value.componentId,
    estimateLineId: value.estimateLineId ?? null,
    providerItemId: value.providerItemId,
    selectedUnit: value.selectedUnit,
    usageMode: value.usageMode ?? null,
    usageQuantity: value.usageQuantityDecimal ?? null,
    usageUnit: value.usageUnit ?? null,
    conversionStatus: value.conversionStatus,
    conversionFactorId: value.conversionFactorId ?? null,
    componentDailyCostIRR: value.componentDailyCostIrr ?? null,
    status: value.status ?? null,
    active: value.active !== false,
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
  const line = (id) => `${base}/estimate-lines/${encodeURIComponent(id)}`;
  return {
    /* One call for the whole table. A line nobody has priced is PRESENT in the answer
       with `needs_components` -- the table has to show what is waiting, and an absent row
       would be indistinguishable from one the page forgot to ask about. */
    async statuses() {
      const body = await client.request(`${base}/item-price-mappings/status`);
      return (body.items ?? []).map(mapRowStatus);
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

    /* The cascade narrows as choices are made: providers by category, product types by
       category AND provider. Both are sent, so a supplier who sells no brick never appears
       under «آجر» -- a choice that yields an empty product list reads as a broken page
       rather than as an empty category. */
    async filters({ category, providerId } = {}) {
      const body = await client.request(
        `${base}/item-price-mappings/filters${query({ category, providerId })}`);
      return {
        providers: body.providers ?? [],
        productTypes: body.productTypes ?? [],
        categories: body.categories ?? [],
        units: body.units ?? [],
        usageModes: body.usageModes ?? [],
      };
    },

    /* Every material of one line, priced, with the row total beside them. Inactive ones
       travel too: somebody who retired a material needs to see that they did. */
    async componentsFor(estimateLineId) {
      const body = await client.request(`${line(estimateLineId)}/price-mapping/components`);
      return {
        line: mapLineHeader(body.line),
        components: (body.components ?? []).map(mapComponent),
        total: body.total ? mapRowStatus(body.total) : null,
      };
    },

    async componentHistory(estimateLineId) {
      const body = await client.request(
        `${line(estimateLineId)}/price-mapping/components/history`);
      return (body ?? []).map(mapComponentRow);
    },

    /* What one material would cost, asked BEFORE anything is saved -- so «نیازمند ضریب
       تبدیل» is something a person sees while choosing rather than discovers after
       committing. */
    async previewComponent(estimateLineId, draft) {
      const body = await client.request(
        `${line(estimateLineId)}/price-component-preview`
        + query({
          providerItemId: draft?.providerItemId,
          selectedUnit: draft?.selectedUnit,
          usageMode: draft?.usageMode,
          usageQuantity: draft?.usageQuantity,
        }));
      return mapComponent(body);
    },

    /* What the ROW will come to, including one unsaved material. The draft is what makes
       this different from reading the total back: a person sees the effect before they
       commit it, not after. */
    async previewTotal(estimateLineId, draft = null) {
      const body = await client.request(
        `${line(estimateLineId)}/price-total-preview`
        + query({
          providerItemId: draft?.providerItemId,
          selectedUnit: draft?.selectedUnit,
          usageMode: draft?.usageMode,
          usageQuantity: draft?.usageQuantity,
        }));
      return mapRowStatus(body);
    },

    async addComponent(estimateLineId, payload) {
      return mapComponentRow(await client.request(
        `${line(estimateLineId)}/price-mapping/components`,
        jsonOptions("POST", payload)));
    },

    async updateComponent(estimateLineId, componentId, payload) {
      return mapComponentRow(await client.request(
        `${line(estimateLineId)}/price-mapping/components/${encodeURIComponent(componentId)}`,
        jsonOptions("PATCH", payload)));
    },

    /* Retiring a material appends an inactive version; it never deletes one. A report
       issued while it was active was calculated with it. */
    async deactivateComponent(estimateLineId, componentId, reason) {
      return mapComponentRow(await client.request(
        `${line(estimateLineId)}/price-mapping/components/${encodeURIComponent(componentId)}/deactivate`,
        jsonOptions("POST", { reason })));
    },
  };
}
