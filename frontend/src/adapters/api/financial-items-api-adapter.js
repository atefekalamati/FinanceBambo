import { financeBase, formDataWithFile, jsonOptions, mapImportPreview, mapResource } from "./api-utils.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";
import { setUnitRegistry } from "../../features/prices/unit-conversions-validation.js";

/**
 * `estimate_lines` has no activity_title or wbs_code column and the read models
 * return null for both, because the activity catalogue belongs to the host
 * project module. The title is therefore joined here from /activities.
 */
function mapLine(value, resources, activities = []) {
  const resource = resources.find((item) => item.resourceId === value.resourceId);
  const general = resource?.type === "general_cost";
  const activity = activities.find((item) => item.activityExternalId === value.activityExternalId);
  return {
    lineId: value.id,
    activityExternalId: value.activityExternalId,
    taskExternalId: activity?.taskExternalId ?? value.activityExternalId,
    assignmentExternalId: value.assignmentExternalId,
    activityTitle: value.activityTitle || activity?.title || value.activityExternalId || "فعالیت بدون عنوان",
    wbsCode: value.wbsCode || activity?.wbsCode || "—",
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
      isOverrun: compareDecimalStrings(revision.newQuantity, general ? value.originalUnitPriceIrr : value.originalQuantity) > 0,
    })),
  };
}

export function createApiFinancialItemsAdapter(context, client) {
  const base = financeBase(context);
  let resourceCache = [];
  async function getWorkspace() {
    const [resourcePayload, linePayload, activityPayload, unitPayload] = await Promise.all([
      client.request(`${base}/resources`),
      client.request(`${base}/estimate-lines`),
      client.request(`${base}/activities?status=active&page=1&pageSize=200`),
      client.request(`${base}/unit-registry`),
    ]);
    const resources = resourcePayload.map(mapResource);
    resourceCache = resources;
    const activities = (activityPayload.items ?? []).map((item) => ({
      activityExternalId: item.activityExternalId,
      taskExternalId: item.taskExternalId,
      title: item.title,
      wbsCode: item.wbsCode,
      status: item.status,
    }));
    const estimateLines = linePayload.map((line) => mapLine(line, resources, activities));
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
  async function commitEstimateImport({ previewId }) {
    const result = await client.request(`${base}/imports/estimate/commit`, jsonOptions("POST", { previewId }));
    return { workspace: await getWorkspace(), importedCount: result.committedCount };
  }
  return Object.freeze({ getWorkspace, createResource, createActivity, createEstimateLine, reviseEstimateLine, previewEstimateImport, commitEstimateImport });
}
