import test from "node:test";
import assert from "node:assert/strict";
import { createHashRouter } from "../../src/core/routing/router.js";

test("keeps deep-link query parameters on an enabled hash route", () => {
  const previousWindow = globalThis.window;
  let navigation;
  globalThis.window = {
    location: { hash: "#finance/prices?resourceId=resource-1" },
    history: { replaceState() { throw new Error("valid deep link must not be replaced"); } },
    addEventListener() {},
    removeEventListener() {},
  };
  try {
    createHashRouter({
      routes: [{ key: "prices", path: "finance/prices", enabled: true }],
      defaultPath: "finance/prices",
      onNavigate: (route, query) => { navigation = { route, query }; },
    }).start();
    assert.equal(navigation.route.key, "prices");
    assert.equal(navigation.query.get("resourceId"), "resource-1");
  } finally {
    globalThis.window = previousWindow;
  }
});
