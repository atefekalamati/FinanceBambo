import test from "node:test";
import assert from "node:assert/strict";
import { createApiPricesAdapter } from "../../src/adapters/api/prices-api-adapter.js";

const context = { organizationId: "org-1", projectId: "project-1" };

function clientWith(payloads) {
  return {
    calls: [],
    async request(path, options) {
      this.calls.push({ path, options });
      if (path.endsWith("/resources")) return payloads.resources;
      if (path.endsWith("/price-history")) return payloads.prices;
      if (path.endsWith("/unit-conversions")) return payloads.conversions ?? [];
      if (path.includes("/prices/current?asOf=")) return payloads.current ?? [];
      throw new Error(`unexpected path: ${path}`);
    },
  };
}

test("builds a dynamic trend from real backend price history in effective order", async () => {
  const client = clientWith({
    resources: [{ id: "resource-1", type: "material", code: "MAT-1", title: "میلگرد", baseUnit: "kg", dimension: "mass", externalResourceId: null }],
    prices: [
      { id: "price-3", resourceId: "resource-1", scopeKind: "project", version: 3, unitPriceIrr: "330000", effectiveFrom: "2026-08-03", reason: "سوم", createdBy: "user-1", createdAt: "2026-08-03T08:00:00Z" },
      { id: "price-1", resourceId: "resource-1", scopeKind: "project", version: 1, unitPriceIrr: "300000", effectiveFrom: "2026-08-01", reason: "اول", createdBy: "user-1", createdAt: "2026-08-01T08:00:00Z" },
      { id: "price-2", resourceId: "resource-1", scopeKind: "project", version: 2, unitPriceIrr: "280000", effectiveFrom: "2026-08-02", reason: "دوم", createdBy: "user-1", createdAt: "2026-08-02T08:00:00Z" },
      { id: "base-1", resourceId: "resource-1", scopeKind: "organization", version: 1, unitPriceIrr: "250000", effectiveFrom: "2026-07-01", reason: "پایه", createdBy: "user-1", createdAt: "2026-07-01T08:00:00Z" },
    ],
    current: [{ resourceId: "resource-1", organizationPriceIrr: "250000", organizationEffectiveFrom: "2026-07-01", projectPriceIrr: "330000", projectEffectiveFrom: "2026-08-03", currentPriceIrr: "330000", currentEffectiveFrom: "2026-08-03", previousPriceIrr: "280000", latestChangePercent: "17.857143", trendDirection: "up", scopeKind: "project", trendPoints: [{ effectiveFrom: "2026-08-01", unitPriceIrr: "300000" }, { effectiveFrom: "2026-08-02", unitPriceIrr: "280000" }, { effectiveFrom: "2026-08-03", unitPriceIrr: "330000" }] }],
  });
  const workspace = await createApiPricesAdapter(context, client).getPrices();
  const item = workspace.currentPrices[0];
  assert.equal(item.currentPrice.unitPriceIRR, "330000");
  assert.equal(item.currentPrice.effectiveFrom, "2026-08-03");
  assert.equal(item.organizationPrice.unitPriceIRR, "250000");
  assert.equal(item.projectPrice.unitPriceIRR, "330000");
  assert.equal(item.trend.scopeKind, "project");
  assert.equal(item.trend.latestChangePercent, "17.857143");
  assert.equal(item.trend.trendDirection, "up");
  assert.deepEqual(item.trend.trendPoints.map((point) => point.unitPriceIrr), ["300000", "280000", "330000"]);
  assert.ok(client.calls.some((call) => call.path === "/api/projects/project-1/finance/price-history"));
  const currentCall = client.calls.find((call) => call.path.includes("/api/projects/project-1/finance/prices/current?asOf="));
  assert.match(new URL(currentCall.path, "https://example.test").searchParams.get("asOf"), /^\d{4}-\d{2}-\d{2}$/);
});

test("uses organization history when no project override exists", async () => {
  const client = clientWith({
    resources: [{ id: "resource-1", type: "labor", code: "LAB-1", title: "نیروی کار", baseUnit: "hour", dimension: "time", externalResourceId: null }],
    prices: [
      { id: "price-1", resourceId: "resource-1", scopeKind: "organization", version: 1, unitPriceIrr: "100", effectiveFrom: "2026-07-01", reason: "اول", createdBy: "user-1", createdAt: "2026-07-01T08:00:00Z" },
      { id: "price-2", resourceId: "resource-1", scopeKind: "organization", version: 2, unitPriceIrr: "90", effectiveFrom: "2026-08-01", reason: "دوم", createdBy: "user-1", createdAt: "2026-08-01T08:00:00Z" },
    ],
    current: [{ resourceId: "resource-1", organizationPriceIrr: "90", organizationEffectiveFrom: "2026-08-01", projectPriceIrr: null, projectEffectiveFrom: null, currentPriceIrr: "90", currentEffectiveFrom: "2026-08-01", previousPriceIrr: "100", latestChangePercent: "-10", trendDirection: "down", scopeKind: "organization", trendPoints: [{ effectiveFrom: "2026-07-01", unitPriceIrr: "100" }, { effectiveFrom: "2026-08-01", unitPriceIrr: "90" }] }],
  });
  const item = (await createApiPricesAdapter(context, client).getPrices()).currentPrices[0];
  assert.equal(item.currentPrice.scope, "organization");
  assert.equal(item.trend.trendDirection, "down");
});
