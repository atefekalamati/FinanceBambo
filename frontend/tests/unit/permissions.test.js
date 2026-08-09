import test from "node:test";
import assert from "node:assert/strict";
import { canAccessRoute, hasPermission } from "../../src/core/auth/permissions.js";

const context = { permissionCodes: ["finance.view"] };

test("checks existing coarse permission codes", () => {
  assert.equal(hasPermission(context, "finance.view"), true);
  assert.equal(hasPermission(context, "finance.edit"), false);
});

test("allows routes without a permission and rejects unavailable permissions", () => {
  assert.equal(canAccessRoute(context, { permission: null }), true);
  assert.equal(canAccessRoute(context, { permission: "finance.edit" }), false);
});
