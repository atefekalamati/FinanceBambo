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
      if (path.includes("/price-history")) return payloads.prices;
      if (path.includes("/unit-conversions")) return payloads.conversions ?? [];
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
  /* Opening the page must NOT ask for the history. It is append-only and only
     grows -- 835 items changing price weekly is 43,000 rows in a year -- and
     nothing on the page reads it: the sparkline above is drawn from this
     endpoint's own trendPoints, which is what the assertion before this one
     checks. The reader asks for the history when they want to see it. */
  assert.ok(!client.calls.some((call) => call.path.includes("/price-history")),
    "opening the page fetched the whole price history");
  assert.ok(client.calls.some((call) => call.path.includes("/prices/current?asOf=")),
    "the current prices, which the page does read, were not fetched");
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

test("the history is fetched only when the reader asks for it", async () => {
  const client = clientWith({
    resources: [{ id: "resource-1", type: "material", code: "MAT-1", title: "میلگرد", baseUnit: "kg", dimension: "mass", externalResourceId: null }],
    prices: [
      { id: "price-2", resourceId: "resource-1", scopeKind: "project", version: 2, unitPriceIrr: "280000", effectiveFrom: "2026-08-02", reason: "دوم", createdBy: "user-1", createdAt: "2026-08-02T08:00:00Z" },
      { id: "price-1", resourceId: "resource-1", scopeKind: "project", version: 1, unitPriceIrr: "300000", effectiveFrom: "2026-08-01", reason: "اول", createdBy: "user-1", createdAt: "2026-08-01T08:00:00Z" },
    ],
    current: [],
  });
  const adapter = createApiPricesAdapter(context, client);

  const workspace = await adapter.getPrices();
  // null, not [] -- "not asked for yet" is a different answer from "this
  // project has never changed a price", and the page draws them differently.
  assert.equal(workspace.history, null);

  const history = await adapter.getPriceHistory();
  assert.ok(client.calls.some((call) => call.path.includes("/price-history")));
  // Newest first, the order the table has always shown.
  assert.deepEqual(history.map((price) => price.priceId), ["price-2", "price-1"]);
});
