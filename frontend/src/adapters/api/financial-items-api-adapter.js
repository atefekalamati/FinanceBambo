import { financeBase, formDataWithFile, jsonOptions, mapImportPreview, mapResource } from "./api-utils.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";

function mapLine(value, resources) {
  const resource = resources.find((item) => item.resourceId === value.resourceId);
  const general = resource?.type === "general_cost";
  return {
    lineId: value.id,
    activityExternalId: value.activityExternalId,
    taskExternalId: value.activityExternalId,
    assignmentExternalId: value.assignmentExternalId,
    activityTitle: value.activityExternalId || "فعالیت بدون عنوان",
    wbsCode: "—",
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
  async function getWorkspace() {
    const [resourcePayload, linePayload] = await Promise.all([client.request(`${base}/resources`), client.request(`${base}/estimate-lines`)]);
    const resources = resourcePayload.map(mapResource);
    const estimateLines = linePayload.map((line) => mapLine(line, resources));
    const activities = [...new Map(estimateLines.filter((line) => line.activityExternalId).map((line) => [line.activityExternalId, { activityExternalId: line.activityExternalId, taskExternalId: line.taskExternalId, title: line.activityTitle, wbsCode: line.wbsCode }])).values()];
    return { resources, estimateLines, activities, scope: { organizationId: context.organizationId, projectId: context.projectId } };
  }
  async function createResource(values) {
    await client.request(`${base}/resources`, jsonOptions("POST", { type: values.type, code: values.code, title: values.title, baseUnit: values.baseUnit || null, dimension: values.dimension || null, externalResourceId: values.externalResourceId || null }));
    return getWorkspace();
  }
  async function createEstimateLine(values) {
    await client.request(`${base}/estimate-lines`, jsonOptions("POST", { resourceId: values.resourceId, activityExternalId: values.activityExternalId || null, assignmentExternalId: values.assignmentExternalId || null, originalQuantity: values.originalQuantity, originalUnitPriceIrr: values.originalUnitPriceIRR || null, source: "manual_entry" }));
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
  return Object.freeze({ getWorkspace, createResource, createEstimateLine, reviseEstimateLine, previewEstimateImport, commitEstimateImport });
}
