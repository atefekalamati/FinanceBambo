import { financeBase } from "./api-utils.js";

/**
 * GET /audit-events takes page (>=1) and pageSize (1..200, default 50) and
 * answers with a paged envelope: { items, page, pageSize, totalItems,
 * totalPages }. The envelope exists so a client filtering by date cannot
 * mistake an unfetched page for an empty history, so the total is reported
 * rather than inferred from a full page.
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

  /**
   * The route also accepts occurredFrom/occurredTo, action, entityType and
   * query, and applies them in SQL. Passing them through means a date-bounded
   * read fetches only the period rather than paging the whole history and
   * filtering what arrives — which would report a page as if it were the total.
   */
  async function getEvents({ occurredFrom, occurredTo, action, entityType, query, ...paging } = {}) {
    const { page, pageSize } = normalizeAuditPaging(paging);
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    if (occurredFrom) params.set("occurredFrom", occurredFrom);
    if (occurredTo) params.set("occurredTo", occurredTo);
    if (action) params.set("action", action);
    if (entityType) params.set("entityType", entityType);
    if (query?.trim()) params.set("query", query.trim());
    const payload = await client.request(`${base}/audit-events?${params.toString()}`);
    return {
      items: payload.items ?? [],
      page: payload.page,
      pageSize: payload.pageSize,
      totalItems: payload.totalItems,
      totalPages: payload.totalPages,
    };
  }

  return Object.freeze({ getEvents });
}
