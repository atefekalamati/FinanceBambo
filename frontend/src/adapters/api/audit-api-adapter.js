import { financeBase } from "./api-utils.js";

/**
 * GET /audit-events accepts page (>=1) and pageSize (1..200, default 50) and
 * responds with a bare list[AuditEventResponse] — no items/totalCount envelope,
 * unlike /invoices, /files and /extractions. A caller therefore cannot know the
 * total; a full page is the only signal that older events may still exist.
 */
export const AUDIT_DEFAULT_PAGE_SIZE = 50;
export const AUDIT_MAX_PAGE_SIZE = 200;

export function normalizeAuditPaging({ page = 1, pageSize = AUDIT_DEFAULT_PAGE_SIZE } = {}) {
  return {
    page: Math.max(Number(page) || 1, 1),
    pageSize: Math.min(Math.max(Number(pageSize) || AUDIT_DEFAULT_PAGE_SIZE, 1), AUDIT_MAX_PAGE_SIZE),
  };
}

export function createApiAuditAdapter(context, client) {
  const base = financeBase(context);

  async function getEvents(paging = {}) {
    const { page, pageSize } = normalizeAuditPaging(paging);
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    return client.request(`${base}/audit-events?${params.toString()}`);
  }

  return Object.freeze({ getEvents });
}
