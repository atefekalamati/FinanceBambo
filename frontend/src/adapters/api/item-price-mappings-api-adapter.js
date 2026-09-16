import { financeBase, jsonOptions } from "./api-utils.js";

/* Which market listing prices one schedule item, read from the Finance backend and from
 * nowhere else.
 *
 * ONE LINE IS ONE MATERIAL, NOT AN ACTIVITY
 * An estimate line here is one resource on one activity -- it arrives that way from the
 * MPP assignment rows, already naming «آرماتور» with its own quantity in kilograms. So it
 * is priced by ONE listing, not by a list of materials entered underneath it: a material
 * inside a material is a level this data does not have.
 *
 * The server still stores that link in the component table, and it is written as a single
 * component with `usage_mode: per_msp_unit` and `usage_quantity: 1` -- "one unit of this
 * product per unit of this line", which IS the line's own quantity. Written as a ratio
 * rather than a copy, so a later revision of the line's quantity carries through instead
 * of leaving a stale number behind.
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

    /* The unit the sheet quotes this listing in, and the unit this line is priced in.
       Read here so «واحد شیت قیمت» is a column of the table rather than something a
       person has to open a panel to see. The service does not send them yet: they are
       null until it does, and the cell says the status instead of inventing a unit. */
    sourcePriceUnit: value.sourcePriceUnit ?? null,
    selectedUnit: value.selectedUnit ?? null,
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

/* One conversion rule, as stored.
 *
 * `1 fromUnit = factor toUnit`, and that direction is the whole meaning: read the other
 * way round, «۱ شاخه = ۲۲ کیلوگرم» becomes a claim that a kilogram weighs twenty-two
 * branches. The server states it once, in one direction, and nothing here reverses it. */
function mapConversionRule(value) {
  if (!value) return null;
  return {
    id: value.id,
    scopeType: value.scopeType,
    projectId: value.projectId ?? null,
    providerId: value.providerId ?? null,
    providerItemId: value.providerItemId ?? null,
    category: value.category ?? null,

    fromUnit: value.fromUnit,
    toUnit: value.toUnit,
    conversionMethod: value.conversionMethod ?? "factor",
    /* A decimal STRING, like every other exact number here. A factor parsed into a float
       and multiplied by a price is how a rial becomes almost-a-rial. */
    factorValue: value.factorValue ?? null,
    formulaDefinition: value.formulaDefinition ?? null,
    directionDefinition: value.directionDefinition ?? null,

    status: value.status,
    version: value.version ?? null,
    effectiveFrom: value.effectiveFrom ?? null,
    effectiveTo: value.effectiveTo ?? null,
    supersedesRuleId: value.supersedesRuleId ?? null,

    /* Present only once the backend ships it. Until then it is null everywhere and the
       panel simply has nothing to mark -- which is the truth, because until then a rule
       this broad cannot be saved at all. */
    productDependentAcknowledged: value.productDependentAcknowledged ?? null,

    evidenceSource: value.evidenceSource ?? null,
    reason: value.reason ?? null,
    createdBy: value.createdBy ?? null,
    createdByName: value.createdByName ?? null,
    createdAt: value.createdAt ?? null,
    approvedBy: value.approvedBy ?? null,
    approvedByName: value.approvedByName ?? null,
    approvedAt: value.approvedAt ?? null,
  };
}

/* One place a conversion was needed and was not there. Recorded by the server as it
   calculates, so the worklist is what actually blocked a figure rather than a guess at
   what might. */
function mapConversionIssue(value) {
  return {
    id: value.id ?? null,
    estimateLineId: value.estimateLineId ?? null,
    providerItemId: value.providerItemId ?? null,
    fromUnit: value.fromUnit ?? null,
    toUnit: value.toUnit ?? null,
    status: value.status ?? null,
    statusLabel: value.statusLabel ?? null,
    reason: value.reason ?? null,
    productName: value.productName ?? null,
    providerName: value.providerName ?? null,
    category: value.category ?? null,
    occurrences: value.occurrences ?? null,
    lastSeenAt: value.lastSeenAt ?? null,
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

/* How the single link is written into the component row.
 *
 * `per_msp_unit` with a usage of 1 says "one unit of this product for each unit of this
 * line", which is the line's own quantity and nothing else. A `total_quantity` of the
 * line's quantity would compute the same number TODAY and then stop being true the moment
 * somebody revised the line. */
const WHOLE_LINE = Object.freeze({ usageMode: "per_msp_unit", usageQuantity: "1" });

export function createItemPriceMappingsApiAdapter(context, { client }) {
  const base = financeBase(context);
  const line = (id) => `${base}/estimate-lines/${encodeURIComponent(id)}`;

  return {
    /* One call for the whole table. A line nobody has priced is PRESENT in the answer with
       its waiting status -- an absent row would be indistinguishable from one the page
       forgot to ask about. */
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
      };
    },

    /* What this line is linked to, or null when nothing yet. The server answers with a
       list because that is the shape of its table; exactly one of those rows is this
       line's link, and a second would be a state this page cannot produce. */
    async connectionFor(estimateLineId) {
      const body = await client.request(`${line(estimateLineId)}/price-mapping/components`);
      const active = (body.components ?? []).map(mapComponent).filter((row) => row.active);
      return {
        line: mapLineHeader(body.line),
        connection: active[0] ?? null,
        total: body.total ? mapRowStatus(body.total) : null,
      };
    },

    async history(estimateLineId) {
      const body = await client.request(
        `${line(estimateLineId)}/price-mapping/components/history`);
      return (body ?? []).map(mapComponentRow);
    },

    /* What this listing would cost this line, asked BEFORE anything is saved -- so
       «نیازمند ضریب تبدیل» is something a person sees while choosing rather than
       discovers after committing. */
    async preview(estimateLineId, draft) {
      const body = await client.request(
        `${line(estimateLineId)}/price-component-preview`
        + query({ providerItemId: draft?.providerItemId, selectedUnit: draft?.selectedUnit,
                  usageMode: WHOLE_LINE.usageMode, usageQuantity: WHOLE_LINE.usageQuantity }));
      return mapComponent(body);
    },

    async connect(estimateLineId, { providerItemId, selectedUnit, reason }) {
      return mapComponentRow(await client.request(
        `${line(estimateLineId)}/price-mapping/components`,
        jsonOptions("POST", { providerItemId, selectedUnit, reason, ...WHOLE_LINE })));
    },

    async reconnect(estimateLineId, componentId, { providerItemId, selectedUnit, reason }) {
      return mapComponentRow(await client.request(
        `${line(estimateLineId)}/price-mapping/components/${encodeURIComponent(componentId)}`,
        jsonOptions("PATCH", { providerItemId, selectedUnit, reason, ...WHOLE_LINE })));
    },

    /* Removing a link appends an inactive version; it never deletes one. A report issued
       while it was in force was calculated with it. */
    async disconnect(estimateLineId, componentId, reason) {
      return mapComponentRow(await client.request(
        `${line(estimateLineId)}/price-mapping/components/${encodeURIComponent(componentId)}/deactivate`,
        jsonOptions("POST", { reason })));
    },

    // ------------------------------------------------------ unit conversion rules
    /* Read and written from the panel as well as from the settings page. A person who
       hits «نیازمند ضریب تبدیل» while pricing an item should be able to answer it there,
       rather than be sent to another page to find their way back. */
    async conversionRules(filters = {}) {
      const body = await client.request(`${base}/finance-settings/unit-conversions${query(filters)}`);
      return {
        items: (body.items ?? []).map(mapConversionRule),
        units: body.units ?? [],
      };
    },

    /* A project-scoped rule needs to name its project, and the panel that raises one is
       already inside that project. Filled here rather than asked for: a form that made
       somebody retype the project they are looking at would be asking them to get it
       wrong. Every other scope's identifier IS a choice and stays with the caller. */
    async createConversionRule(payload) {
      const body = payload?.scopeType === "project" && !payload.projectId
        ? { ...payload, projectId: context.projectId }
        : payload;
      return mapConversionRule(await client.request(
        `${base}/finance-settings/unit-conversions`, jsonOptions("POST", body)));
    },

    async conversionRuleHistory(ruleId) {
      const body = await client.request(`${base}/finance-settings/unit-conversions/${encodeURIComponent(ruleId)}/history`);
      return (body.items ?? body ?? []).map(mapConversionRule);
    },

    async previewConversionRule(ruleId, priceIrr = null) {
      return client.request(
        `${base}/finance-settings/unit-conversions/${encodeURIComponent(ruleId)}/preview`
        + query({ priceIrr }));
    },

    async approveConversionRule(ruleId, payload = {}) {
      return mapConversionRule(await client.request(
        `${base}/finance-settings/unit-conversions/${encodeURIComponent(ruleId)}/approve`,
        jsonOptions("POST", payload)));
    },

    async supersedeConversionRule(ruleId, payload = {}) {
      return mapConversionRule(await client.request(
        `${base}/finance-settings/unit-conversions/${encodeURIComponent(ruleId)}/supersede`,
        jsonOptions("POST", payload)));
    },

    /* Everywhere a conversion was needed and missing. The admin's worklist: better than
       reading 835 rows looking for the ones that are stuck. */
    async conversionIssues(filters = {}) {
      const body = await client.request(
        `${base}/finance-settings/unit-conversion-issues${query(filters)}`);
      return (body.items ?? []).map(mapConversionIssue);
    },
  };
}
