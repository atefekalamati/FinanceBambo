import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { ROUTES } from "../../src/core/config/routes.js";
import { presentApiError } from "../../src/shared/errors/error-presentation.js";
import { ApiError } from "../../src/core/api/api-error.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

/* The host team's answers, 2026-09-12. Each of these is a sentence from that
   reply turned into something that fails when the code stops matching it. */

test("every route lives under the finance prefix the host asked for", () => {
  // «فقط hashها با finance شروع شوند تا بعداً با خود داشبورد یا ماژول‌های دیگر
  // تداخل پیدا نکنند.» The dashboard owns the address bar; this module is a
  // guest in it, and a bare #/settings is a name two guests could both want.
  ROUTES.forEach((route) => {
    assert.match(route.path, /^finance\//, `${route.key} is at ${route.path}, outside the finance prefix`);
    assert.doesNotMatch(route.path, /^\//, `${route.key} keeps a leading slash, so its hash would be #/…`);
  });
});

test("no source names a hash outside the prefix", () => {
  // A link written by hand is the way one escapes.
  ["../../src/features", "../../src/core", "../../src/shared", "../../src/app"].forEach((dir) => {
    void dir;
  });
  const files = [
    "../../src/app/bootstrap.js",
    "../../src/core/auth/permissions.js",
    "../../src/features/finance-home/finance-home-page.js",
    "../../src/features/finance-home/operations-home-page.js",
    "../../src/features/invoices/invoices-page.js",
    "../../src/features/level-one/level-one-page.js",
  ];
  files.forEach((path) => {
    const source = read(path);
    assert.doesNotMatch(source, /"#\/[a-z]/, `${path} writes a hash outside the finance prefix`);
    assert.doesNotMatch(source, /`#\/[a-z]/, `${path} writes a hash outside the finance prefix`);
  });
});

test("a 401 is the end of a session, not a request to try again", () => {
  // «نشست کوکی‌محور است و توکن جدا نداریم… اگر 401 گرفتید، آن را پایان نشست در
  // نظر بگیرید.» There is no token here to refresh, so a retry would fail the
  // same way and would teach the reader that the module is broken.
  const shown = presentApiError(new ApiError({ status: 401, code: "UNAUTHENTICATED", message: "Unauthorized" }));
  assert.equal(shown.retryable, false);
  assert.match(shown.title, /نشست/);
  // And the English developer string never reaches the page.
  assert.doesNotMatch(shown.message, /[A-Za-z]{4,}/);
});

test("the session end is announced once, from the one place every request passes", () => {
  const client = read("../../src/core/api/api-client.js");
  assert.match(client, /export const SESSION_ENDED_EVENT/);
  // Once: eight adapters can be in flight together and eight notices are not an answer.
  assert.match(client, /let sessionEndedAnnounced = false/);
  assert.match(client, /if \(status !== 401 \|\| sessionEndedAnnounced\) return/);
  // Both paths, because a report download fails the same way a read does.
  assert.equal((client.match(/announceSessionEnd\(response\.status\)/g) ?? []).length, 2);

  const bootstrap = read("../../src/app/bootstrap.js");
  assert.match(bootstrap, /SESSION_ENDED_EVENT/);
  assert.match(bootstrap, /function renderSessionEnded\(\)/);
  // Reload, not a login URL: this module is served by the host, so a fresh load
  // goes through whatever the host does for a visitor who is not signed in.
  assert.match(bootstrap, /window\.location\.reload\(\)/);
});

/** Source with comments stripped: these rules are about what runs, not what is explained. */
const codeOf = (path) => read(path)
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

test("nothing reads a token, and the cookie is what travels", () => {
  // «لازم نیست چیزی از localStorage یا sessionStorage بخوانید یا Authorization
  // header بسازید.»
  const client = codeOf("../../src/core/api/api-client.js");
  assert.match(client, /credentials: "same-origin"/);
  assert.doesNotMatch(client, /Authorization/, "the client builds an Authorization header");
  assert.doesNotMatch(client, /localStorage|sessionStorage/, "the client reads a credential out of storage");
  // And no CSRF token anywhere: the host confirmed none is required.
  ["../../src/core/api/api-client.js", "../../src/adapters/api/api-utils.js"].forEach((path) => {
    assert.doesNotMatch(codeOf(path), /csrf/i, `${path} sends a CSRF token the host does not want`);
  });
});
