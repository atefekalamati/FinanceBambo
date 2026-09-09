import { getConversionDimension, getUnitDefinition, setUnitRegistry } from "../../features/prices/unit-conversions-validation.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { selectActiveResources } from "../../shared/finance/active-resources.js";
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

function buildWorkspace(context, allResources, prices, conversions, currentTrends) {
  const asOfDate = getTehranTodayIso();
  // The operational list is the items somebody can price today. Rows the local
  // test seed made out of schedule tasks are withheld -- unless a person has
  // since priced or invoiced one, in which case it is theirs and it stays.
  // Nothing is deleted: the API still returns them and the price versions are
  // untouched; `withheldResourceCount` exists so the page can say so.
  const { rows: resources, withheldCount: withheldResourceCount } = selectActiveResources(allResources);
  const visible = new Set(resources.map((resource) => resource.resourceId));
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
  // The history belongs to the same list. Left whole it would name withheld
  // items in a column the page resolves from `currentPrices`, printing them as
  // «قلم حذف‌شده» -- which they are not.
  const activeHistory = prices.filter((price) => visible.has(price.resourceId));
  return { currentPrices, withheldResourceCount,
           withheldPriceCount: prices.length - activeHistory.length,
           history: activeHistory.sort(compareVersion), currentConversions, conversionHistory: [...conversions].sort((left, right) => right.effectiveDate.localeCompare(left.effectiveDate) || right.version - left.version), asOfDate, scope: { organizationId: context.organizationId, projectId: context.projectId } };
}

export function createApiPricesAdapter(context, client) {
  const base = financeBase(context);
  async function getPrices() {
    const asOfDate = getTehranTodayIso();
    const [resourcePayload, pricePayload, conversionPayload, currentPayload] = await Promise.all([client.request(`${base}/resources`), client.request(`${base}/price-history`), client.request(`${base}/unit-conversions`), client.request(`${base}/prices/current?asOf=${encodeURIComponent(asOfDate)}`)]);
    return buildWorkspace(context, resourcePayload.map(mapResource), pricePayload.map(mapPrice), conversionPayload.map((item) => mapConversion(item, context)), currentPayload.map(mapCurrentTrend));
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
  return Object.freeze({ getPrices, createPriceVersion, previewPriceImport, previewPriceImportFromLink, commitPriceImport, createUnitConversion });
}
