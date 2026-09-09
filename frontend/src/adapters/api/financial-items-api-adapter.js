import { financeBase, formDataWithFile, jsonOptions, mapImportPreview, mapResource } from "./api-utils.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";
import { setUnitRegistry } from "../../features/prices/unit-conversions-validation.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";

/**
 * `estimate_lines` has no activity_title or wbs_code column and the read models
 * return null for both, because the activity catalogue belongs to the host
 * project module. The title is therefore joined here from /activities.
 */
function mapLine(value, resources, activities = [], currentPrices = new Map()) {
  const resource = resources.find((item) => item.resourceId === value.resourceId);
  const general = resource?.type === "general_cost";
  const activity = activities.find((item) => item.activityExternalId === value.activityExternalId);
  const baseline = general ? value.originalUnitPriceIrr : value.originalQuantity;
  return {
    lineId: value.id,
    activityExternalId: value.activityExternalId,
    // The schedule identity, read from the fields that carry it. Null on a line
    // nobody read from a schedule, which is how the page tells the two apart.
    sourceAssignmentUid: value.sourceAssignmentUid ?? null,
    sourceTaskUid: value.sourceTaskUid ?? null,
    // The activity's cost in the schedule -- the activity's, not this item's.
    mppTaskCostIrr: activity?.mppTaskCostIrr ?? null,
    // The price a person entered for this item today, if anyone has. Separate
    // from the schedule's cost above and from the frozen original below; the
    // three are different numbers and are never derived from one another.
    currentUnitPriceIRR: currentPrices.get(value.resourceId) ?? null,
    // Null when the catalogue does not name a task. The previous fallback put the
    // activity's WBS code in a field named for a task uid, which is a different
    // identity: anything ordering or joining by it was reading the wrong key.
    taskExternalId: activity?.taskExternalId ?? null,
    assignmentExternalId: value.assignmentExternalId,
    // Null, not the id and not a placeholder: an activity whose title the
    // catalogue does not carry has no title, and saying so is the presentation
    // layer's job. Substituting the external id here is what printed a WBS code
    // where a title belongs.
    activityTitle: value.activityTitle || activity?.title || null,
    wbsCode: value.wbsCode || activity?.wbsCode || null,
    resourceId: value.resourceId,
    originalQuantity: general ? null : value.originalQuantity,
    revisedQuantity: general ? null : value.revisedQuantity,
    originalAmount: general ? value.originalUnitPriceIrr : null,
    revisedAmount: general ? value.revisedQuantity : null,
    originalUnitPriceIRR: value.originalUnitPriceIrr,
    source: value.source,
    revision: value.revision,
    revisions: (value.revisions ?? []).map((revision) => ({
      revisionId: revision.id,
      revisionNumber: revision.revision,
      previousValue: revision.previousQuantity,
      newValue: revision.newQuantity,
      reason: revision.reason,
      actorId: revision.createdBy,
      actorName: null,
      occurredAt: revision.createdAt,
      // No baseline, no overrun. Comparing against a null original read it as
      // zero, which made every revision on a schedule line an overrun.
      isOverrun: baseline == null
        ? false
        : compareDecimalStrings(revision.newQuantity, baseline) > 0,
    })),
  };
}

/** The service caps a page at 200 and this project has more activities than
 *  that. Reading one page dropped every activity past the cap, and each line
 *  belonging to a dropped activity lost its title and its WBS code — so the
 *  whole catalogue is read, page by page, as the service paginates it. */
const ACTIVITY_PAGE_SIZE = 200;
const ACTIVITY_PAGE_LIMIT = 50;

async function fetchAllActivities(client, base) {
  const items = [];
  let page = 1;
  let totalPages = 1;
  while (page <= totalPages && page <= ACTIVITY_PAGE_LIMIT) {
    const payload = await client.request(`${base}/activities?status=active&page=${page}&pageSize=${ACTIVITY_PAGE_SIZE}`);
    items.push(...(payload.items ?? []));
    totalPages = Number(payload.totalPages) || 1;
    page += 1;
  }
  return { items };
}

export function createApiFinancialItemsAdapter(context, client) {
  const base = financeBase(context);
  let resourceCache = [];
  async function getWorkspace() {
    const asOfDate = getTehranTodayIso();
    const [resourcePayload, linePayload, activityPayload, unitPayload, currentPayload] = await Promise.all([
      client.request(`${base}/resources`),
      client.request(`${base}/estimate-lines`),
      fetchAllActivities(client, base),
      client.request(`${base}/unit-registry`),
      // The same endpoint and the same as-of date the قیمت روز page reads, so the
      // two pages cannot disagree about what today's price is. The selection rule
      // stays where it already lives; nothing here re-implements it.
      client.request(`${base}/prices/current?asOf=${encodeURIComponent(asOfDate)}`),
    ]);
    const resources = resourcePayload.map(mapResource);
    resourceCache = resources;
    const activities = (activityPayload.items ?? []).map((item) => ({
      activityExternalId: item.activityExternalId,
      taskExternalId: item.taskExternalId,
      title: item.title,
      wbsCode: item.wbsCode,
      mppTaskCostIrr: item.mppTaskCostIrr ?? null,
      status: item.status,
    }));
    const currentPrices = new Map((currentPayload ?? [])
      .filter((item) => item.currentPriceIrr !== null && item.currentPriceIrr !== undefined)
      .map((item) => [item.resourceId, item.currentPriceIrr]));
    const estimateLines = linePayload.map((line) => mapLine(line, resources, activities, currentPrices));
    const unitRegistry = (unitPayload.items ?? []).filter((item) => item.active).map((item) => ({
      code: item.code,
      label: item.labelFa,
      dimension: item.dimension,
      dimensionLabel: item.dimensionLabelFa,
      decimalPrecision: item.decimalPrecision,
    }));
    // Unit validation elsewhere reads from the registry the service serves.
    setUnitRegistry(unitRegistry);
    return { resources, estimateLines, activities, unitRegistry, scope: { organizationId: context.organizationId, projectId: context.projectId } };
  }
  async function createResource(values) {
    await client.request(`${base}/resources`, jsonOptions("POST", { type: values.type, code: values.code, title: values.title, baseUnit: values.baseUnit || null, externalResourceId: values.externalResourceId || null }));
    return getWorkspace();
  }
  async function createActivity(values) {
    const created = await client.request(`${base}/activities`, jsonOptions("POST", {
      title: values.title,
      wbsCode: values.wbsCode || null,
      parentTaskExternalId: values.parentTaskExternalId || null,
    }));
    return { created, workspace: await getWorkspace() };
  }
  async function createEstimateLine(values) {
    if (!resourceCache.length) await getWorkspace();
    const general = resourceCache.find((resource) => resource.resourceId === values.resourceId)?.type === "general_cost";
    await client.request(`${base}/estimate-lines`, jsonOptions("POST", {
      resourceId: values.resourceId,
      activityExternalId: values.activityExternalId || null,
      assignmentExternalId: values.assignmentExternalId || null,
      originalQuantity: general ? null : values.originalQuantity,
      originalUnitPriceIrr: general ? values.originalQuantity : values.originalUnitPriceIRR || null,
      source: "manual_entry",
    }));
    return getWorkspace();
  }
  async function reviseEstimateLine({ lineId, revisedValue, reason }) {
    await client.request(`${base}/estimate-lines/${encodeURIComponent(lineId)}/revisions`, jsonOptions("POST", { newQuantity: revisedValue, reason }));
    return getWorkspace();
  }
  async function previewEstimateImport(file) {
    return mapImportPreview(await client.request(`${base}/imports/estimate/preview`, { method: "POST", body: formDataWithFile(file) }), "estimate");
  }
  /* The same preview, for a workbook the service fetches rather than the browser
     uploading. Same shape back, same previewId, committed by the same call. */
  async function previewEstimateImportFromLink(sourceUrl) {
    return mapImportPreview(await client.request(`${base}/imports/estimate/preview-link`, jsonOptions("POST", { sourceUrl })), "estimate");
  }
  async function commitEstimateImport({ previewId }) {
    const result = await client.request(`${base}/imports/estimate/commit`, jsonOptions("POST", { previewId }));
    return { workspace: await getWorkspace(), importedCount: result.committedCount };
  }
  return Object.freeze({ getWorkspace, createResource, createActivity, createEstimateLine, reviseEstimateLine, previewEstimateImport, previewEstimateImportFromLink, commitEstimateImport });
}
