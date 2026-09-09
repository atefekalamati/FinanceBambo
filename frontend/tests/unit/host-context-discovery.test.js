import test from "node:test";
import assert from "node:assert/strict";

import {
  HostContextError,
  discoverHostContext,
  readHostProjectId,
} from "../../src/adapters/host/host-context-discovery.js";
import { normalizeContext } from "../../src/adapters/host/context-adapter.js";

/* The shapes the BAMBO dashboard actually answers with, read off its own
   scripts on 2026-09-09: /api/me, /api/projects/{id} (wrapped in `project`),
   and /api/rbac/my-permissions. */
const ME = { user: { id: "user-9" }, orgs: [{ id: "org-1", name: "بامبو", role: "org_chief" }] };
const PROJECT = {
  project: {
    id: "terrace", name: "پروژه احداث پل", code: "PRJ-11",
    organizationId: "org-1", builtAreaSqm: 4250.5,
  },
};
const RBAC = { isBamboAdmin: false, permissions: ["finance.view", "finance_report.view", "msp.view"] };

function hostFetch(routes) {
  return async (path) => {
    for (const [match, answer] of Object.entries(routes)) {
      if (!path.includes(match)) continue;
      if (typeof answer === "number") return { ok: false, status: answer, json: async () => null };
      return { ok: true, status: 200, json: async () => answer };
    }
    return { ok: false, status: 404, json: async () => null };
  };
}

const ALL_ROUTES = { "/me": ME, "/projects/": PROJECT, "/rbac/my-permissions": RBAC };

test("the address names the project, and beats what was stored", () => {
  const storage = { getItem: () => "stored-one" };
  assert.equal(readHostProjectId({ search: "?project=from-url", storage }), "from-url");
  assert.equal(readHostProjectId({ search: "", storage }), "stored-one");
  // The dashboard still answers to its older name for the same thing.
  assert.equal(readHostProjectId({ search: "?building=legacy", storage }), "legacy");
});

test("a browser that refuses storage leaves no project rather than throwing", () => {
  const storage = { getItem: () => { throw new Error("blocked"); } };
  assert.equal(readHostProjectId({ search: "", storage }), "");
});

test("the host's three answers become a context this module accepts", async () => {
  const context = await discoverHostContext({ fetchImpl: hostFetch(ALL_ROUTES), projectId: "terrace" });
  // The real proof: it survives the same normalizer the handed-over path uses.
  const normalized = normalizeContext(context);
  assert.equal(normalized.projectId, "terrace");
  assert.equal(normalized.organizationId, "org-1");
  assert.equal(normalized.projectName, "پروژه احداث پل");
  assert.equal(normalized.grossBuiltArea, 4250.5);
  assert.equal(normalized.timezone, "Asia/Tehran");
  assert.deepEqual(context.permissionCodes, ["finance.view", "finance_report.view", "msp.view"]);
});

test("an unwrapped project payload is accepted too", async () => {
  const context = await discoverHostContext({
    fetchImpl: hostFetch({ ...ALL_ROUTES, "/projects/": PROJECT.project }),
    projectId: "terrace",
  });
  assert.equal(context.projectId, "terrace");
});

test("an administrator flag grants nothing the finance service would honour", async () => {
  // The dashboard's own gates read `isBamboAdmin || permissions.includes(code)`,
  // but the finance service has no such bypass -- CoreRbacPermissionAuthorizer
  // re-reads user_roles/role_permissions and refuses. Copying the flag here
  // would draw buttons whose only answer is 403.
  const context = await discoverHostContext({
    fetchImpl: hostFetch({ ...ALL_ROUTES, "/rbac/my-permissions": { isBamboAdmin: true, permissions: [] } }),
    projectId: "terrace",
  });
  assert.deepEqual(context.permissionCodes, []);
});

test("no project chosen says so, rather than failing as a broken context", async () => {
  await assert.rejects(
    () => discoverHostContext({ fetchImpl: hostFetch(ALL_ROUTES), projectId: "" }),
    (error) => error instanceof HostContextError && error.message.includes("پروژه‌ای انتخاب نشده"));
});

test("a signed-out session is named as one", async () => {
  await assert.rejects(
    () => discoverHostContext({ fetchImpl: hostFetch({ "/me": 401 }), projectId: "terrace" }),
    (error) => error instanceof HostContextError && error.message.includes("وارد شوید"));
});

test("a project the host does not know is named as that", async () => {
  await assert.rejects(
    () => discoverHostContext({ fetchImpl: hostFetch({ "/me": ME, "/projects/": 404, "/rbac/my-permissions": RBAC }), projectId: "gone" }),
    (error) => error instanceof HostContextError && error.message.includes("پیدا نشد"));
});

test("a host that is unreachable does not surface a raw network error", async () => {
  await assert.rejects(
    () => discoverHostContext({ fetchImpl: async () => { throw new TypeError("Failed to fetch"); }, projectId: "terrace" }),
    (error) => error instanceof HostContextError && error.message.includes("ارتباط با سایت اصلی"));
});

test("permissions are optional; the rest of the context still forms", async () => {
  // rbac answering 500 must not take the module down: it renders with nothing
  // granted, which the backend would enforce anyway.
  const context = await discoverHostContext({
    fetchImpl: hostFetch({ "/me": ME, "/projects/": PROJECT, "/rbac/my-permissions": 500 }),
    projectId: "terrace",
  });
  assert.deepEqual(context.permissionCodes, []);
  assert.equal(normalizeContext(context).projectId, "terrace");
});

test("without fetch there is nothing to discover, and that is not an error", async () => {
  assert.equal(await discoverHostContext({ fetchImpl: null, projectId: "terrace" }), null);
});
