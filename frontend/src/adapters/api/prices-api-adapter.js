import { getUnitDefinition } from "../../features/prices/unit-conversions-validation.js";
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

function trendFor(resourceId, selectedScope, prices) {
  const points = prices
    .filter((price) => price.resourceId === resourceId && price.scope === selectedScope)
    .sort((left, right) => left.effectiveFrom.localeCompare(right.effectiveFrom) || left.sequence - right.sequence)
    .map((price) => ({ effectiveFrom: price.effectiveFrom, unitPriceIrr: price.unitPriceIRR }));
  const current = points.at(-1)?.unitPriceIrr ?? null;
  const previous = points.at(-2)?.unitPriceIrr ?? null;
  const direction = previous === null ? "none" : BigInt(current) > BigInt(previous) ? "up" : BigInt(current) < BigInt(previous) ? "down" : "flat";
  return { resourceId, currentPriceIrr: current, previousPriceIrr: previous, latestChangePercent: null, trendDirection: direction, scopeKind: selectedScope, trendPoints: points };
}

function buildWorkspace(context, resources, prices, conversions) {
  const asOfDate = new Date().toISOString().slice(0, 10);
  const effectivePrices = prices.filter((price) => price.effectiveFrom <= asOfDate);
  const currentPrices = resources.map((resource) => {
    const versions = effectivePrices.filter((price) => price.resourceId === resource.resourceId).sort(compareVersion);
    const projectPrice = versions.find((price) => price.scope === "project") ?? null;
    const organizationPrice = versions.find((price) => price.scope === "organization") ?? null;
    const currentPrice = projectPrice ?? organizationPrice;
    return { resource, currentPrice, organizationPrice, projectPrice, trend: trendFor(resource.resourceId, currentPrice?.scope ?? null, effectivePrices) };
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
  return { currentPrices, history: [...prices].sort(compareVersion), currentConversions, conversionHistory: [...conversions].sort((left, right) => right.effectiveDate.localeCompare(left.effectiveDate) || right.version - left.version), asOfDate, scope: { organizationId: context.organizationId, projectId: context.projectId } };
}

export function createApiPricesAdapter(context, client) {
  const base = financeBase(context);
  async function getPrices() {
    const [resourcePayload, pricePayload, conversionPayload] = await Promise.all([client.request(`${base}/resources`), client.request(`${base}/price-history`), client.request(`${base}/unit-conversions`)]);
    return buildWorkspace(context, resourcePayload.map(mapResource), pricePayload.map(mapPrice), conversionPayload.map((item) => mapConversion(item, context)));
  }
  async function createPriceVersion(values) {
    await client.request(`${base}/resources/${encodeURIComponent(values.resourceId)}/prices`, jsonOptions("POST", { scopeKind: values.scope, unitPriceIrr: values.unitPriceIRR, effectiveFrom: values.effectiveFrom, reason: values.reason || "ثبت نسخه قیمت از رابط مالی" }));
    return getPrices();
  }
  async function previewPriceImport(file) {
    return mapImportPreview(await client.request(`${base}/imports/prices/preview`, { method: "POST", body: formDataWithFile(file, { currencyUnit: "IRR" }) }), "prices");
  }
  async function commitPriceImport({ previewId }) {
    await client.request(`${base}/imports/prices/commit`, jsonOptions("POST", { previewId }));
    return { workspace: await getPrices() };
  }
  async function createUnitConversion(values) {
    await client.request(`${base}/unit-conversions`, jsonOptions("POST", { scopeKind: values.scope, sourceUnit: values.sourceUnit, targetUnit: values.targetUnit, dimension: getUnitDefinition(values.sourceUnit)?.dimension ?? "unknown", factor: values.factor, effectiveFrom: values.effectiveDate, reason: values.reason || "ثبت تبدیل واحد از رابط مالی" }));
    return getPrices();
  }
  return Object.freeze({ getPrices, createPriceVersion, previewPriceImport, commitPriceImport, createUnitConversion });
}
