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
  const grouped = new Map();
  (value.errors ?? []).forEach((issue) => {
    const row = grouped.get(issue.row) ?? [];
    row.push(`${issue.field}: ${issue.reason}`);
    grouped.set(issue.row, row);
  });
  const rows = [...grouped.entries()].map(([rowNumber, errors]) => kind === "prices"
    ? { rowNumber, resourceTitle: "ردیف نامعتبر", resourceCode: "—", importedAmount: null, unitPriceIRR: "نامعتبر", currency: "", effectiveFrom: null, scope: "", status: "invalid", errors }
    : { rowNumber, activityTitle: "ردیف نامعتبر", activityExternalId: null, resourceTitle: "—", resourceCode: null, value: "—", unit: null, status: "invalid", errors });
  const invalidRows = grouped.size;
  return { previewId: value.previewId, totalRows: value.rowCount, validRows: Math.max(0, value.rowCount - invalidRows), invalidRows, rows, canCommit: value.canCommit };
}
