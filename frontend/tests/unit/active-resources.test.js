import test from "node:test";
import assert from "node:assert/strict";
import {
  isActiveFinanceResource, isSeedTaskResource, selectActiveResources,
} from "../../src/shared/finance/active-resources.js";
import { createApiPricesAdapter } from "../../src/adapters/api/prices-api-adapter.js";
import { isLegacyTaskResource } from "../../src/features/financial-items/financial-items-presentation.js";

/**
 * What an operational list shows, and what it refuses to decide from a name.
 *
 * Every rule here is written to fail towards showing: hiding a real item costs
 * a person their data, and showing a stale one costs them a glance.
 */

const context = { organizationId: "org-1", projectId: "terrace" };

const scheduleResource = {
  id: "r-mpp", type: "material", code: "MPP-R98", title: "بتن 400", baseUnit: "m3",
  dimension: "volume", externalResourceId: null, sourceResourceUid: 98,
  hasOperationalRecords: false, createdBy: "u", createdAt: "2026-01-01",
};
const seedResource = {
  id: "r-seed", type: "material", code: "MSP-T7847", title: "اجرای رابیتس بندی نما",
  baseUnit: "unit", dimension: "count", externalResourceId: "7847", sourceResourceUid: null,
  hasOperationalRecords: false, createdBy: "u", createdAt: "2026-01-01",
};
const seedButUsed = { ...seedResource, id: "r-used", code: "MSP-T915", title: "نصب داربست",
  externalResourceId: "915", hasOperationalRecords: true };
const manualResource = {
  id: "r-manual", type: "equipment", code: "123", title: "جرثقیل", baseUnit: "day",
  dimension: "equipment_time", externalResourceId: null, sourceResourceUid: null,
  hasOperationalRecords: false, createdBy: "u", createdAt: "2026-01-01",
};
// A person who types a code that looks like the seed's, and nothing else matches.
const manualLookalike = { ...manualResource, id: "r-lookalike", code: "MSP-T5", title: "جرثقیل دوم" };

test("all three marks must coincide before a row is called seed-made", () => {
  assert.equal(isSeedTaskResource(seedResource), true);
  assert.equal(isSeedTaskResource(scheduleResource), false, "a schedule identity settles it");
  assert.equal(isSeedTaskResource(manualResource), false);
  assert.equal(isSeedTaskResource(manualLookalike), false, "a typed code is not evidence");
  assert.equal(isSeedTaskResource({ code: "MSP-T5", externalResourceId: "5", sourceResourceUid: 5 }), false);
  assert.equal(isSeedTaskResource({ code: "MSP-T5", externalResourceId: "9", sourceResourceUid: null }), false,
    "the code and the external id must name the same task");
});

test("a seed row a person has priced or invoiced stays in the list", () => {
  assert.equal(isSeedTaskResource(seedButUsed), true, "its origin is unchanged");
  assert.equal(isActiveFinanceResource(seedButUsed), true, "and it is still shown");
  assert.equal(isActiveFinanceResource(seedResource), false);
});

test("silence about operational records is read as untouched, never as used", () => {
  const { hasOperationalRecords, ...withoutTheField } = seedResource;
  assert.equal(isActiveFinanceResource(withoutTheField), false);
  assert.equal(isActiveFinanceResource({ ...seedResource, hasOperationalRecords: "yes" }), false,
    "only a real true counts");
});

test("a schedule item and a hand-made item are both active", () => {
  assert.equal(isActiveFinanceResource(scheduleResource), true);
  assert.equal(isActiveFinanceResource(manualResource), true);
  assert.equal(isActiveFinanceResource(manualLookalike), true);
});

test("the selection reports what it withheld instead of quietly showing less", () => {
  const selected = selectActiveResources([scheduleResource, seedResource, seedButUsed, manualResource]);
  assert.deepEqual(selected.rows.map((r) => r.id), ["r-mpp", "r-used", "r-manual"]);
  assert.equal(selected.withheldCount, 1);
});

test("withholding is not removing: the caller's array is untouched", () => {
  const given = [scheduleResource, seedResource, manualResource];
  selectActiveResources(given);
  assert.equal(given.length, 3);
  assert.ok(given.includes(seedResource));
});

test("the items page and the prices page answer the same question the same way", () => {
  for (const resource of [scheduleResource, seedResource, seedButUsed, manualResource, manualLookalike]) {
    assert.equal(isLegacyTaskResource(resource), !isActiveFinanceResource(resource),
      `${resource.code} must be classified identically by both pages`);
  }
});

// --------------------------------------------------------------- the prices workspace

function pricesStub({ resources, history = [], current = [] }) {
  const seen = [];
  return {
    seen,
    request(path) {
      seen.push(path);
      if (path.endsWith("/resources")) return Promise.resolve(resources);
      if (path.endsWith("/price-history")) return Promise.resolve(history);
      if (path.endsWith("/unit-conversions")) return Promise.resolve([]);
      if (path.includes("/prices/current?")) return Promise.resolve(current);
      throw new Error(`unexpected request ${path}`);
    },
  };
}

const price = (id, resourceId, extra = {}) => ({
  id, resourceId, scopeKind: "project", unitPriceIrr: "1000000", currency: "IRR",
  effectiveFrom: "2026-01-01", version: 1, reason: "TEST ONLY -- local demo rate",
  createdBy: "u", createdAt: "2026-01-01T00:00:00Z", ...extra,
});
const trend = (resourceId, extra = {}) => ({
  resourceId, organizationPriceIrr: null, organizationEffectiveFrom: null,
  projectPriceIrr: null, projectEffectiveFrom: null, currentPriceIrr: null,
  currentEffectiveFrom: null, previousPriceIrr: null, latestChangePercent: null,
  trendDirection: "none", scopeKind: null, trendPoints: [], ...extra,
});

async function pricesWorkspace(options) {
  return createApiPricesAdapter(context, pricesStub(options)).getPrices();
}

test("the prices list holds the schedule items, the manual item and the used seed row", async () => {
  const workspace = await pricesWorkspace({
    resources: [scheduleResource, seedResource, seedButUsed, manualResource],
  });
  assert.deepEqual(workspace.currentPrices.map((item) => item.resource.code),
    ["MPP-R98", "MSP-T915", "123"]);
  assert.equal(workspace.withheldResourceCount, 1);
});

test("a withheld row's price versions stay in the database and leave the active history", async () => {
  const workspace = await pricesWorkspace({
    resources: [scheduleResource, seedResource],
    history: [price("p-1", "r-seed"), price("p-2", "r-mpp", { reason: "قیمت پیمانکار" })],
  });
  assert.deepEqual(workspace.history.map((item) => item.priceId), ["p-2"]);
  assert.equal(workspace.withheldPriceCount, 1, "and the page is told how many it did not show");
});

test("a valid resource's project price still resolves and still wins", async () => {
  const workspace = await pricesWorkspace({
    resources: [scheduleResource],
    current: [trend("r-mpp", { organizationPriceIrr: "80000", organizationEffectiveFrom: "2025-01-01",
      projectPriceIrr: "92000", projectEffectiveFrom: "2026-01-01",
      currentPriceIrr: "92000", currentEffectiveFrom: "2026-01-01", scopeKind: "project" })],
  });
  const [row] = workspace.currentPrices;
  assert.equal(row.currentPrice.unitPriceIRR, "92000");
  assert.equal(row.currentPrice.scope, "project", "project over organization, unchanged");
  assert.equal(row.organizationPrice.unitPriceIRR, "80000", "and the organization price is still shown");
});

test("a valid resource with only an organization price resolves to it", async () => {
  const workspace = await pricesWorkspace({
    resources: [scheduleResource],
    current: [trend("r-mpp", { organizationPriceIrr: "80000", organizationEffectiveFrom: "2025-01-01",
      currentPriceIrr: "80000", currentEffectiveFrom: "2025-01-01", scopeKind: "organization" })],
  });
  assert.equal(workspace.currentPrices[0].currentPrice.scope, "organization");
  assert.equal(workspace.currentPrices[0].projectPrice, null);
});

test("a valid resource with no price is listed with no price, not with zero", async () => {
  const workspace = await pricesWorkspace({ resources: [scheduleResource], current: [trend("r-mpp")] });
  const [row] = workspace.currentPrices;
  assert.equal(row.currentPrice, null);
  assert.equal(row.organizationPrice, null);
  assert.equal(row.projectPrice, null);
  assert.notEqual(row.currentPrice, 0);
});

test("the list the page counts, searches and exports is one list", async () => {
  const workspace = await pricesWorkspace({
    resources: [scheduleResource, seedResource, manualResource],
    history: [price("p-1", "r-seed")],
  });
  // Every consumer in prices-page.js reads workspace.currentPrices: the badge, the
  // search filter, the CSV export and the "new price version" picker.
  const codes = workspace.currentPrices.map((item) => item.resource.code);
  assert.deepEqual(codes, ["MPP-R98", "123"]);
  assert.equal(codes.includes("MSP-T7847"), false, "a search cannot rediscover it here");
  assert.equal(workspace.history.length, 0);
});
