import test from "node:test";
import assert from "node:assert/strict";
import { canAccessRoute, hasPermission } from "../../src/core/auth/permissions.js";
import { DEFAULT_ROUTE, ROUTES, SURFACES, homeRouteFor, routesForSurface, surfaceOfPath } from "../../src/core/config/routes.js";

const context = { permissionCodes: ["finance.view"] };

test("checks existing coarse permission codes", () => {
  assert.equal(hasPermission(context, "finance.view"), true);
  assert.equal(hasPermission(context, "finance.edit"), false);
});

test("allows routes without a permission and rejects unavailable permissions", () => {
  assert.equal(canAccessRoute(context, { permission: null }), true);
  assert.equal(canAccessRoute(context, { permission: "finance.edit" }), false);
});

/**
 * Every route opens a page whose first request is a GET, and the Backend gates
 * those on reading, not writing: finance.view everywhere except the reporting
 * routes, which ask for finance_report.view. A route demanding finance.edit
 * would hide a page the API would have served — settings did exactly that,
 * because PATCH /settings needs the edit permission and the route copied it.
 * Write permissions belong on the buttons inside a page, never on its door.
 */
const ROUTE_PERMISSIONS = Object.freeze({
  "finance-home": "finance.view",
  "financial-items": "finance.view",
  prices: "finance.view",
  progress: "finance.view",
  invoices: "finance.view",
  "invoice-files": "finance.view",
  "ai-review": "finance.view",
  reports: "finance_report.view",
  "period-report": "finance_report.view",
  audit: "finance.view",
  settings: "finance.view",
  "report-home": "finance.view",
  // The reader-only settings view shows a currency choice held in this browser
  // and a read-back of the permissions the host granted. Its one request is
  // GET /settings, so it asks for reading like every other door.
  "report-settings": "finance.view",
});

test("every route asks for the permission its Backend GET asks for", () => {
  assert.deepEqual(
    Object.fromEntries(ROUTES.map((route) => [route.key, route.permission])),
    ROUTE_PERMISSIONS,
  );
});

test("no route is gated on a write permission", () => {
  const writeGated = ROUTES.filter((route) => /\.(edit|issue|export)$/.test(route.permission ?? ""));
  assert.deepEqual(writeGated.map((route) => route.key), [], "a write permission gates a control, not a page");
});

test("each route belongs to exactly one surface, and each surface has one home", () => {
  const surfaces = new Set([SURFACES.OPERATIONS, SURFACES.REPORT]);
  ROUTES.forEach((route) => {
    assert.ok(surfaces.has(route.surface), `${route.key} belongs to no surface`);
  });
  [...surfaces].forEach((surface) => {
    const homes = routesForSurface(surface).filter((route) => route.home);
    assert.equal(homes.length, 1, `${surface} must have exactly one home`);
    assert.equal(homeRouteFor(surface), homes[0]);
  });
  // Two routes sharing a path would make surfaceOfPath answer at random.
  const paths = ROUTES.map((route) => route.path);
  assert.equal(new Set(paths).size, paths.length, "two routes share a path");
});

test("the split moved pages between surfaces without dropping any", () => {
  // Whatever the surfaces are, together they must still be the whole module:
  // a page that belongs to neither is a page nobody can reach.
  const covered = [...routesForSurface(SURFACES.OPERATIONS), ...routesForSurface(SURFACES.REPORT)];
  assert.deepEqual(
    covered.map((route) => route.key).sort(),
    ROUTES.filter((route) => route.enabled).map((route) => route.key).sort(),
  );
  // What the customer reads, and what the operator authors.
  assert.deepEqual(routesForSurface(SURFACES.REPORT).map((route) => route.key), [
    "report-home",
    "reports",
    "period-report",
    "invoices",
    "report-settings",
  ]);
  assert.deepEqual(routesForSurface(SURFACES.OPERATIONS).map((route) => route.key), [
    "finance-home",
    "financial-items",
    "prices",
    "progress",
    "invoice-files",
    "ai-review",
    "audit",
    "settings",
  ]);
});

test("the default route opens the surface whose home it is", () => {
  assert.equal(surfaceOfPath(DEFAULT_ROUTE), SURFACES.OPERATIONS);
  assert.equal(homeRouteFor(SURFACES.OPERATIONS).path, DEFAULT_ROUTE);
  assert.equal(surfaceOfPath("/nowhere"), null);
});
