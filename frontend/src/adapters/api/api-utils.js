import { DUPLICATE_IMPORT_REASON } from "../../shared/imports/import-preview-notice.js";

export function financeBase(context) {
  return `/api/projects/${encodeURIComponent(context.projectId)}/finance`;
}

export function jsonOptions(method, payload) {
  return { method, body: payload === undefined ? undefined : JSON.stringify(payload) };
}

export function mapResource(value) {
  return {
    resourceId: value.id,
    type: value.type,
    code: value.code,
    title: value.title,
    baseUnit: value.baseUnit ?? null,
    dimension: value.dimension ?? null,
    externalResourceId: value.externalResourceId ?? null,
    createdBy: value.createdBy,
    createdAt: value.createdAt,
    source: value.externalResourceId ? "progress_feed" : "manual_entry",
  };
}

export function formDataWithFile(file, fields = {}) {
  const body = new FormData();
  Object.entries(fields).forEach(([key, value]) => body.append(key, value));
  body.append("file", file);
  return body;
}

export function mapImportPreview(value, kind) {
  // ImportPreviewResponse says a repeated file twice: on these three fields,
  // and as an issue whose reason is the machine string `duplicate_import_file`.
  // The structured form is the one a UI can phrase; the raw issue is dropped
  // below so it cannot reach a reader as-is.
  const issueText = (issue) => `${issue.field}: ${issue.reason}`;
  const rows = (value.rows ?? []).map((row) => {
    const errors = (row.errors ?? []).map(issueText);
    if (kind === "prices") {
      return {
        rowNumber: row.rowNumber,
        resourceId: row.resourceId ?? null,
        resourceTitle: row.resourceTitle ?? "قلم ناشناخته",
        resourceCode: row.resourceCode ?? "—",
        importedAmount: row.unitPrice ?? null,
        unitPriceIRR: row.normalizedUnitPriceIrr ?? "نامعتبر",
        currency: row.currency ?? "",
        effectiveFrom: row.effectiveFrom ?? null,
        scope: row.scope ?? "",
        status: row.status,
        errors,
      };
    }
    return {
      rowNumber: row.rowNumber,
      activityTitle: row.activityTitle ?? row.activityExternalId ?? "فعالیت نامشخص",
      activityExternalId: row.activityExternalId ?? null,
      assignmentExternalId: row.assignmentExternalId ?? null,
      resourceId: row.resourceId ?? null,
      resourceTitle: row.resourceTitle ?? "قلم ناشناخته",
      resourceCode: row.resourceCode ?? null,
      value: row.originalQuantity ?? "—",
      unit: row.baseUnit ?? null,
      source: row.source ?? null,
      status: row.status,
      errors,
    };
  });
  const rowNumbers = new Set((value.rows ?? []).map((row) => row.rowNumber));
  return {
    previewId: value.previewId,
    totalRows: value.rowCount,
    validRows: value.validCount,
    invalidRows: value.invalidCount,
    rows,
    fileErrors: (value.errors ?? [])
      .filter((issue) => !rowNumbers.has(issue.row) && issue.reason !== DUPLICATE_IMPORT_REASON)
      .map(issueText),
    canCommit: value.canCommit,
    duplicateFile: value.duplicateFile ?? false,
    // Carried, not displayed: no screen lists past imports yet, and the id is
    // what a future one would need to link to. The date is what the wording uses.
    duplicateOfImportId: value.duplicateOfImportId ?? null,
    duplicateCommittedAt: value.duplicateCommittedAt ?? null,
  };
}
