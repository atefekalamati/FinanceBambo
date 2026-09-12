import { getConversionDimension, getUnitDefinition, setUnitRegistry } from "../../features/prices/unit-conversions-validation.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { financeBase, formDataWithFile, jsonOptions, mapImportPreview, mapResource } from "./api-utils.js";

function mapPrice(value) {
  return {
    priceId: value.id,
    sequence: value.version,
    resourceId: value.resourceId,
    scope: value.scopeKind,
    unitPriceIRR: value.unitPriceIrr,
    currency: "IRR",
    effectiveFrom: value.effectiveFrom,
    reason: value.reason,
    actorId: value.createdBy,
    actorName: value.createdByName ?? null,
    createdAt: value.createdAt,
  };
}

function mapConversion(value, context) {
  return {
    conversionId: value.id,
    organizationId: context.organizationId,
    projectId: value.scopeKind === "project" ? context.projectId : null,
    scope: value.scopeKind,
    sourceUnit: value.sourceUnit,
    targetUnit: value.targetUnit,
    dimension: value.dimension,
    factor: value.factor,
    effectiveDate: value.effectiveFrom,
    reason: value.reason,
    version: value.version,
    createdBy: value.createdBy,
    createdAt: value.createdAt,
  };
}

function compareVersion(left, right) {
  return right.effectiveFrom.localeCompare(left.effectiveFrom)
    || right.sequence - left.sequence
    || right.createdAt.localeCompare(left.createdAt)
    || right.priceId.localeCompare(left.priceId);
}

function mapCurrentTrend(value) {
  return {
    resourceId: value.resourceId,
    organizationPriceIrr: value.organizationPriceIrr,
    organizationEffectiveFrom: value.organizationEffectiveFrom,
    projectPriceIrr: value.projectPriceIrr,
    projectEffectiveFrom: value.projectEffectiveFrom,
    currentPriceIrr: value.currentPriceIrr,
    currentEffectiveFrom: value.currentEffectiveFrom,
    previousPriceIrr: value.previousPriceIrr,
    latestChangePercent: value.latestChangePercent,
    trendDirection: value.trendDirection,
    scopeKind: value.scopeKind,
    trendPoints: value.trendPoints ?? [],
  };
}

function buildWorkspace(context, resources, conversions, currentTrends) {
  const asOfDate = getTehranTodayIso();
  const currentPrices = resources.map((resource) => {
    const trend = currentTrends.find((item) => item.resourceId === resource.resourceId) ?? { resourceId: resource.resourceId, currentPriceIrr: null, previousPriceIrr: null, latestChangePercent: null, trendDirection: "none", scopeKind: null, trendPoints: [] };
    const organizationPrice = trend.organizationPriceIrr === null || trend.organizationPriceIrr === undefined ? null : { scope: "organization", unitPriceIRR: trend.organizationPriceIrr, effectiveFrom: trend.organizationEffectiveFrom };
    const projectPrice = trend.projectPriceIrr === null || trend.projectPriceIrr === undefined ? null : { scope: "project", unitPriceIRR: trend.projectPriceIrr, effectiveFrom: trend.projectEffectiveFrom };
    const currentPrice = trend.currentPriceIrr === null || trend.currentPriceIrr === undefined ? null : { scope: trend.scopeKind, unitPriceIRR: trend.currentPriceIrr, effectiveFrom: trend.currentEffectiveFrom };
    return { resource, currentPrice, organizationPrice, projectPrice, trend };
  });
  const groups = new Map();
  conversions.filter((item) => item.effectiveDate <= asOfDate).forEach((item) => {
    const key = `${item.sourceUnit}:${item.targetUnit}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  });
  const currentConversions = [...groups.values()].map((versions) => {
    const sorted = versions.sort((left, right) => right.effectiveDate.localeCompare(left.effectiveDate) || right.version - left.version);
    const projectConversion = sorted.find((item) => item.scope === "project") ?? null;
    const organizationConversion = sorted.find((item) => item.scope === "organization") ?? null;
    return { sourceUnit: sorted[0].sourceUnit, targetUnit: sorted[0].targetUnit, dimension: sorted[0].dimension ?? getUnitDefinition(sorted[0].sourceUnit)?.dimension ?? null, currentConversion: projectConversion ?? organizationConversion, projectConversion, organizationConversion };
  });
  return { currentPrices, history: null, currentConversions, conversionHistory: [...conversions].sort((left, right) => right.effectiveDate.localeCompare(left.effectiveDate) || right.version - left.version), asOfDate, scope: { organizationId: context.organizationId, projectId: context.projectId } };
}

export function createApiPricesAdapter(context, client) {
  const base = financeBase(context);
  /* Opening this page no longer asks for the price history.
     It is append-only by contract -- a new price never rewrites an old row -- so
     it only grows: 835 items changing price once a week is 43,000 rows in the
     first year and never fewer. Every reader who opened the page to see today's
     price for one item was waiting for all of them.

     Nothing on the page needs it. The current price of every item comes from
     `/prices/current`, and the sparkline beside each one is drawn from that
     endpoint's own `trendPoints`. Filtering the full history was only ever the
     fallback for a server that did not send those, and it draws six points
     either way.

     So it is fetched when a reader asks to see it, by `getPriceHistory` below.
     `history: null` is what "not asked for yet" looks like -- distinct from an
     empty array, which means a project with no price changes at all. */
  async function getPrices() {
    const asOfDate = getTehranTodayIso();
    const [resourcePayload, conversionPayload, currentPayload] = await Promise.all([client.request(`${base}/resources`), client.request(`${base}/unit-conversions`), client.request(`${base}/prices/current?asOf=${encodeURIComponent(asOfDate)}`)]);
    return buildWorkspace(context, resourcePayload.map(mapResource), conversionPayload.map((item) => mapConversion(item, context)), currentPayload.map(mapCurrentTrend));
  }

  /* The whole history, because the endpoint takes no arguments: no page, no
     range, no resource. Deferring it means a reader who never opens the section
     never pays for it, which is the win available today -- but the request it
     finally sends is still the whole table, so this stays a stopgap until
     `/price-history` accepts a range and a page. */
  async function getPriceHistory() {
    return (await client.request(`${base}/price-history`)).map(mapPrice).sort(compareVersion);
  }
  async function createPriceVersion(values) {
    await client.request(`${base}/resources/${encodeURIComponent(values.resourceId)}/prices`, jsonOptions("POST", { scopeKind: values.scope, unitPriceIrr: values.unitPriceIRR, effectiveFrom: values.effectiveFrom, reason: values.reason || "ثبت نسخه قیمت از رابط مالی" }));
    return getPrices();
  }
  async function previewPriceImport(file) {
    return mapImportPreview(await client.request(`${base}/imports/prices/preview`, { method: "POST", body: formDataWithFile(file) }), "prices");
  }
  /* The same preview, for a workbook the service fetches rather than the browser
     uploading. Same shape back, same previewId, committed by the same call. */
  async function previewPriceImportFromLink(sourceUrl) {
    return mapImportPreview(await client.request(`${base}/imports/prices/preview-link`, jsonOptions("POST", { sourceUrl })), "prices");
  }
  async function commitPriceImport({ previewId }) {
    await client.request(`${base}/imports/prices/commit`, jsonOptions("POST", { previewId }));
    return { workspace: await getPrices() };
  }
  async function createUnitConversion(values) {
    await client.request(`${base}/unit-conversions`, jsonOptions("POST", { scopeKind: values.scope, sourceUnit: values.sourceUnit, targetUnit: values.targetUnit, dimension: getConversionDimension(values.sourceUnit, values.targetUnit) ?? "unknown", factor: values.factor, effectiveFrom: values.effectiveDate, reason: values.reason || "ثبت تبدیل واحد از رابط مالی" }));
    return getPrices();
  }
  return Object.freeze({ getPrices, getPriceHistory, createPriceVersion, previewPriceImport, previewPriceImportFromLink, commitPriceImport, createUnitConversion });
}
