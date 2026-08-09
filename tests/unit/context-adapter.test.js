import test from "node:test";
import assert from "node:assert/strict";
import { normalizeContext } from "../../src/adapters/host/context-adapter.js";

test("accepts the v1.1 camelCase public host context", () => {
  const context = normalizeContext({
    userId: "user-id",
    organizationId: "11111111-1111-4111-8111-111111111111",
    projectId: "project_01",
    permissionCodes: ["finance.view"],
  });
  assert.equal(context.organizationId, "11111111-1111-4111-8111-111111111111");
  assert.equal(context.projectId, "project_01");
});

test("normalizes snake_case host context", () => {
  const context = normalizeContext({
    user_id: "user-id",
    organization_id: "11111111-1111-4111-8111-111111111111",
    project_id: "project_01",
    permission_codes: ["finance.view"],
  });
  assert.equal(context.projectId, "project_01");
  assert.deepEqual(context.permissionCodes, ["finance.view"]);
});

test("rejects an invalid project identifier", () => {
  assert.throws(() => normalizeContext({ organizationId: "org-id", projectId: "../project", permissionCodes: [] }));
});
