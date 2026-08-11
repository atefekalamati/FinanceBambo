import { financeBase } from "./api-utils.js";

export function createApiAuditAdapter(context, client) {
  const base = financeBase(context);

  async function getEvents() {
    return client.request(`${base}/audit-events`);
  }

  return Object.freeze({ getEvents });
}
