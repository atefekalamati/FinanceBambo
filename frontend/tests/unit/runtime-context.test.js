import test from "node:test";
import assert from "node:assert/strict";
import { resolveRuntimeContext } from "../../src/adapters/host/runtime-context.js";

const hostContext = { organizationId: "org-1", projectId: "terrace", permissionCodes: ["finance.view"] };
const noMock = () => assert.fail("Host startup must not initialize mock data");

test("missing host context fails closed by default and in host mode", () => {
  for (const mode of [undefined, "host"]) {
    assert.throws(() => resolveRuntimeContext({ mode, createStandaloneContext: noMock }), /اطلاعات پروژه/);
  }
});

test("only explicit standalone mode initializes the development context", () => {
  const demo = { projectId: "demo" };
  assert.deepEqual(resolveRuntimeContext({ mode: "standalone", createStandaloneContext: () => demo }), {
    runtime: "standalone", context: demo,
  });
});

test("valid host context overrides the standalone preview marker", () => {
  for (const mode of [undefined, "host", "standalone"]) {
    const result = resolveRuntimeContext({ mode, hostContext, createStandaloneContext: noMock });
    assert.equal(result.runtime, "host");
    assert.equal(result.context.projectId, "terrace");
  }
});

test("invalid host context cannot fall back to mock even in standalone", () => {
  for (const invalid of [{}, false, { ...hostContext, projectId: "../other" }]) {
    assert.throws(() => resolveRuntimeContext({ mode: "standalone", hostContext: invalid, createStandaloneContext: noMock }));
  }
});

test("unknown runtime configuration fails closed", () => {
  assert.throws(() => resolveRuntimeContext({ mode: "demo", hostContext, createStandaloneContext: noMock }), /حالت اجرای/);
});
