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
  const issueText = (issue) => `${issue.field}: ${issue.reason}`;
  const rows = (value.rows ?? []).map((row) => kind === "prices"
    ? {
      rowNumber: row.rowNumber,
      resourceTitle: row.resourceTitle ?? "—",
      resourceCode: row.resourceCode ?? "—",
      importedAmount: row.unitPrice,
      unitPriceIRR: row.normalizedUnitPriceIrr ?? "نامعتبر",
      currency: row.currency ?? "",
      effectiveFrom: row.effectiveFrom,
      scope: row.scope ?? "",
      status: row.status,
      errors: (row.errors ?? []).map(issueText),
    }
    : {
      rowNumber: row.rowNumber,
      activityTitle: row.activityTitle ?? row.activityExternalId ?? "—",
      activityExternalId: row.activityExternalId,
      resourceTitle: row.resourceTitle ?? "—",
      resourceCode: row.resourceCode,
      value: row.originalQuantity ?? "—",
      unit: row.baseUnit,
      status: row.status,
      errors: (row.errors ?? []).map(issueText),
    });
  const rowNumbers = new Set((value.rows ?? []).map((row) => row.rowNumber));
  return {
    previewId: value.previewId,
    totalRows: value.rowCount,
    validRows: value.validCount,
    invalidRows: value.invalidCount,
    rows,
    fileErrors: (value.errors ?? []).filter((issue) => !rowNumbers.has(issue.row)).map(issueText),
    canCommit: value.canCommit,
  };
}
