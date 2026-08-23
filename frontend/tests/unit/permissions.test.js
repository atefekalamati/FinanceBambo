import test from "node:test";
import assert from "node:assert/strict";
import { canAccessRoute, hasPermission } from "../../src/core/auth/permissions.js";
import { ROUTES } from "../../src/core/config/routes.js";

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
  audit: "finance.view",
  settings: "finance.view",
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
